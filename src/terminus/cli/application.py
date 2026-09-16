import argparse
import os
import json
import signal
import threading
import time

from terminus.agent import Agent
from terminus.commands.registry import CommandRegistry
from terminus.utils import discover_skills
from ui.theme import COLORS
from terminus.utils import process_file_references
from dotenv import set_key
from terminus.cli.terminal import copy_to_clipboard, sanitize_terminal_input
from terminus.mission import MissionController, MissionStore


def create_display(stop_event):
    from rich_ui import RichDisplay

    return RichDisplay(stop_event=stop_event)


class TerminusCLI:
    def __init__(self, cwd=None):
        if cwd:
            os.chdir(cwd)

        self.stop_event = threading.Event()
        self.agent = Agent(cwd=cwd, use_streaming=True)
        self.display = create_display(stop_event=self.stop_event)
        self.mission_store = MissionStore()
        self.mission_store.mark_active_interrupted()
        self._active_mission: MissionController | None = None
        self.sigint_pending_exit = False
        self.last_sigint_time = 0.0
        self.sigint_grace_window = 2.0
        self._last_response: str | None = None
        self._shutting_down = False
        signal.signal(signal.SIGINT, self._handle_sigint)

    def _mark_interrupt(self) -> bool:
        now = time.monotonic()
        self.sigint_pending_exit = (
            now - self.last_sigint_time
        ) <= self.sigint_grace_window
        self.last_sigint_time = now
        return self.sigint_pending_exit

    def _handle_sigint(self, signum, frame):
        if self._shutting_down:
            return

        self.stop_event.set()
        self._mark_interrupt()
        raise KeyboardInterrupt()

    def begin_shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if self._active_mission is not None:
            self._active_mission.cancel()
            self._active_mission = None
        self.mission_store.close()

    def _exit_app(self):
        self.display.clear_pending_exit()
        self.display.print_centered(
            "Shutting down TERMINUS...", style=f"bold {COLORS['text']}"
        )
        raise SystemExit(0)

    def _emit_worker_event(self, event_type: str, data: dict):
        method_name = f"send_{event_type}"
        method = getattr(self.display, method_name, None)
        if method is None:
            return
        allowed = {
            "worker_spawned": {"worker_id", "name", "description", "role"},
            "worker_notification": {
                "worker_id",
                "status",
                "summary",
                "final_response",
                "timestamp",
            },
            "worker_status": {
                "worker_id",
                "status",
                "result",
                "result_envelope",
                "timestamp",
            },
            "worker_detail": {
                "worker_id",
                "detail_type",
                "content",
                "tool_name",
                "args",
                "timestamp",
            },
        }.get(event_type, set(data))
        method(**{key: value for key, value in data.items() if key in allowed})

    def _emit_mission_event(self, event):
        self.display.handle_mission_event(event)

    def process_query(self, user_input: str):
        try:
            self.stop_event.clear()

            enriched_message, loaded_files, errors = process_file_references(user_input)

            if loaded_files:
                files_list = ", ".join([f"[red]{f}[/red]" for f in loaded_files])
                self.display.print_message(f"[dim red]Loaded files: {files_list}")

            if errors:
                for error in errors:
                    self.display.print_message(
                        f"[dim {COLORS['warning']}]Warning: {error}"
                    )

            handler = self.display.create_response_handler()

            with handler:
                response = self.agent.run(
                    enriched_message,
                    status_callback=handler.update_status,
                    todo_display_callback=lambda todos: self.display.render_todo_panel(
                        todos, handler=handler
                    ),
                    tool_call_callback=handler.display_tool_call,
                    tool_output_callback=handler.display_tool_output,
                    stop_event=self.stop_event,
                    worker_event_callback=self._emit_worker_event,
                    stream_callback=handler.handle_streaming,
                    permission_callback=self.display.request_command_permission,
                )

            handler.render_final_response(response)
            self._last_response = response
            self.sigint_pending_exit = False
            self.display.clear_pending_exit()

            self.display.render_footer(
                cwd=os.getcwd(),
                model=self.agent.model,
                context_size=self.agent.context_size,
                model_context_size=self.agent.model_context_size,
            )

        except KeyboardInterrupt:
            if self.sigint_pending_exit or self.display.check_pending_exit():
                self.display.clear_pending_exit()
                raise
            self.display.clear_pending_exit()
            self.sigint_pending_exit = False
            return
        except Exception as e:
            self.display.render_error(str(e))

    def execute_command(self, command: str) -> bool:
        command = command.strip()
        parts = command.split(maxsplit=1)
        token = parts[0].lower() if parts else ""
        command_spec = CommandRegistry.resolve(token)
        command_name = command_spec.name if command_spec else None
        argument = parts[1] if len(parts) > 1 else ""

        if command_name == "/exit" and not argument:
            self.display.print_centered(
                "Shutting down TERMINUS...", style=f"bold {COLORS['text']}"
            )
            return False

        if command_name == "/reset" and not argument:
            self.agent.clear_session()
            self.display.render_success_message("Session reset successfully")
            return True

        if command_name == "/clear" and not argument:
            self.display.clear_screen()
            self.display.render_banner()
            return True

        if command_name == "/context_size" and not argument:
            self.display.print_message(f"Context Size: {self.agent.context_size}")
            return True

        if command_name == "/compact" and not argument:
            result = self.agent.context_manager.compact()
            if result is None:
                self.display.print_message(
                    "[dim]Nothing to compact (conversation too short).[/dim]"
                )
            else:
                self.display.render_success_message(
                    f"Context compacted: {result['before_count']} -> {result['after_count']} messages"
                )
                if result["summary"]:
                    self.display.print_message(
                        f"[dim]Summary: {result['summary'][:200]}...[/dim]"
                    )
            return True

        if command_name == "/history" and not argument:
            self._display_history()
            return True

        if command_name == "/help" and not argument:
            self.display.render_help()
            return True

        if command_name == "/mission":
            task = argument.strip()
            if not task:
                self.display.render_error("Usage: /mission <goal> | /mission list")
                return True
            if task.lower() == "list":
                self._list_missions()
                return True
            if self._active_mission is not None:
                self.display.render_error(
                    "A mission is awaiting input. Answer it or cancel it before starting another."
                )
                return True
            self._start_mission(task)
            self.display.print_newline()
            return True

        if command_name == "/copy" and not argument:
            if self._last_response:
                if copy_to_clipboard(self._last_response):
                    self.display.render_success_message(
                        "Copied last response to clipboard"
                    )
                else:
                    self.display.render_error(
                        "Failed to copy to clipboard (clipboard tool not found)"
                    )
            else:
                self.display.render_error("No response to copy yet")
            return True

        if command_name == "/init" and not argument:
            handler = self.display.create_response_handler()
            with handler:
                result = self.agent.init(
                    status_callback=handler.update_status,
                    todo_display_callback=lambda todos: self.display.render_todo_panel(
                        todos, handler=handler
                    ),
                    tool_call_callback=handler.display_tool_call,
                    stop_event=self.stop_event,
                    permission_callback=self.display.request_command_permission,
                )
            handler.render_final_response(result)
            return True

        if command_name == "/context" and not argument:
            self.display.print_message(str(self.agent.context))
            return True

        if command_name == "/models" and not argument:
            selected = self.display.select_model_ui(current_model=self.agent.model)
            if selected:
                self.agent.switch_model(selected)
                self.display.print_message(
                    f"[green]Switched model to[/green] [bold]{selected.name}[/bold]"
                )
            else:
                self.display.print_message("[dim]Model selection cancelled.[/dim]")
            return True

        if command_name == "/connect" and not argument:
            try:
                result = self.display.connect_provider_ui()
                if result is None:
                    self.display.print_message(
                        "[dim]Provider connection cancelled.[/dim]"
                    )
                    return True

                provider_name, api_key = result

                env_var_map = {
                    "openrouter": "OPEN_ROUTER_API_KEY",
                }
                env_var = env_var_map.get(provider_name)
                if not env_var:
                    self.display.render_error(f"Unknown provider: {provider_name}")
                    return True

                env_dir = os.path.expanduser("~/.terminus")
                os.makedirs(env_dir, exist_ok=True)
                env_path = os.path.join(env_dir, ".env")
                set_key(env_path, env_var, api_key)
                os.environ[env_var] = api_key

                self.agent.llm_service.set_api_key(api_key)
                self.display.render_success_message(
                    f"API key configured for {provider_name}. "
                    f"Use /models to switch to a {provider_name} model."
                )
            except KeyboardInterrupt:
                self.display.print_message("[dim]Provider connection cancelled.[/dim]")
            except Exception as e:
                self.display.render_error(str(e))
            return True

        if command_name == "/skills" and not argument:
            skills = discover_skills(os.getcwd())
            skills = self.agent.annotate_skills(skills)
            self.display.render_skills(skills)
            return True

        if command_name == "/skill":
            skills = discover_skills(os.getcwd())
            skills = self.agent.annotate_skills(skills)

            if not skills:
                self.display.render_error("No skills found in .skills/ directory.")
                return True

            if not argument:
                selected = self.display.select_skill_ui(skills)
                if selected:
                    self._load_skill(selected)
                else:
                    self.display.print_message("[dim]Skill selection cancelled.[/dim]")
            else:
                skill_name = argument
                match = next((s for s in skills if s["name"] == skill_name), None)
                if match:
                    self._load_skill(match)
                else:
                    self.display.render_error(
                        f"Skill '{skill_name}' not found. Use /skills to list available skills."
                    )
            return True

        if token.startswith("/"):
            self.display.render_error(f"Unknown command: {command}")
            return True

        return True

    def _display_history(self):
        history = self.agent.get_session_history(limit=5)

        if not history:
            self.display.print_message("[yellow]No session history available.[/yellow]")
            return

        history_lines = []
        for idx, msg in enumerate(history, 1):
            try:
                msg_data = json.loads(msg["content"])
                role = msg_data.get("role", "unknown")
                content = msg_data.get("content", "")

                if len(content) > 150:
                    display_content = content[:150] + "..."
                else:
                    display_content = content

                color = self.display.get_role_color(role)
                line = f"{idx}. [bold {color}]{role.upper()}:[/] {display_content}"
                history_lines.append(line)

            except json.JSONDecodeError:
                role = msg["role"]
                content = msg["content"][:150]
                color = self.display.get_role_color(role)
                line = f"{idx}. [bold {color}]{role.upper()}:[/] {content}"
                history_lines.append(line)

        self.display.render_history(history_lines)

    def _start_mission(self, goal: str):
        self.stop_event.clear()
        self._last_response = None
        controller = MissionController(
            goal=goal,
            cwd=os.getcwd(),
            store=self.mission_store,
            event_callback=self._emit_mission_event,
            stop_event=self.stop_event,
        )
        self._active_mission = controller
        self.display.mission_start(
            title="mission",
            goal=goal,
            phase="brief",
            mission_id=controller.mission_id,
        )
        self._run_mission_turn()

    def _run_mission_turn(self, answer: str | None = None):
        controller = self._active_mission
        if controller is None:
            return
        handler = self.display.create_response_handler()
        try:
            with handler:
                outcome = controller.run(
                    answer,
                    status_callback=handler.update_status,
                    tool_call_callback=handler.display_tool_call,
                    tool_output_callback=handler.display_tool_output,
                )
        except KeyboardInterrupt:
            controller.cancel()
            outcome = controller.outcome()
        self._last_response = outcome.summary
        if outcome.awaiting_input:
            handler.render_final_response(outcome.summary)
            return
        if outcome.terminal:
            self.display.mission_end(
                summary=outcome.summary, status=outcome.status.value
            )
            self._active_mission = None
            self.sigint_pending_exit = False
            self.display.clear_pending_exit()

    def _list_missions(self):
        missions = self.mission_store.list_missions()
        if not missions:
            self.display.print_message("No persisted missions.")
            return
        self.display.print_message("[bold]Recent missions[/bold]")
        for mission in missions:
            mission_id = mission["id"]
            self.display.print_message(
                f"[dim]{mission_id[:8]}[/dim]  {mission['status']:<11}  "
                f"{mission['phase']:<14}  {mission['goal']}"
            )

    def _load_skill(self, skill: dict):
        skill_name = skill.get("name", "unknown")
        loaded = self.agent.load_skill(skill)
        if not loaded:
            self.display.render_success_message(
                f"Skill '{skill_name}' is already loaded"
            )
            return
        self.display.render_success_message(f"Skill '{skill_name}' loaded into context")

    def run_interactive(self):
        self.display.start_interactive()
        self.display.render_banner()
        while True:
            try:
                self.stop_event.clear()

                user_input = self.display.get_user_input(
                    model=self.agent.model,
                    context_size=self.agent.context_size,
                    model_context_size=self.agent.model_context_size,
                )

                user_input = sanitize_terminal_input(user_input)

                if not user_input.strip():
                    continue

                silent = self.display.consume_last_input_was_silent()
                if not silent:
                    self.display.render_user_message(user_input)

                if CommandRegistry.is_command(user_input):
                    should_continue = self.execute_command(user_input)
                    if not should_continue:
                        break
                    continue

                if self._active_mission is not None:
                    self.display.generation_start()
                    try:
                        self.stop_event.clear()
                        self._run_mission_turn(user_input)
                    finally:
                        self.display.generation_end()
                    self.display.print_newline()
                    continue

                self.display.generation_start()
                try:
                    self.process_query(user_input)
                finally:
                    self.display.generation_end()
                self.display.print_newline()

            except KeyboardInterrupt:
                if self.sigint_pending_exit or self.display.check_pending_exit():
                    self._exit_app()

                self.stop_event.clear()
                self.display.clear_pending_exit()
                self.sigint_pending_exit = False
                continue
            except EOFError:
                break

    def run_single_query(self, query: str):
        self.display.render_banner()
        if CommandRegistry.is_command(query):
            self.execute_command(query)
        else:
            self.process_query(query)


def main():
    parser = argparse.ArgumentParser(
        prog="terminus",
        description="AI-powered development companion for the command line",
    )
    parser.add_argument(
        "query", nargs="*", help="Single query to run (non-interactive)"
    )
    args = parser.parse_args()

    invoked_dir = os.getcwd()
    cli = TerminusCLI(cwd=invoked_dir)

    try:
        if args.query:
            cli.run_single_query(" ".join(args.query))
        else:
            cli.run_interactive()
    finally:
        cli.begin_shutdown()
        cli.display.shutdown()
