import argparse
import sys
import os
import json
import signal
import threading
import time

from src.agent import Agent
from src.commands.registry import CommandRegistry
from src.utils import discover_skills
from ui.theme import COLORS
from src.utils import process_file_references
from dotenv import set_key
from src.cli.terminal import copy_to_clipboard, sanitize_terminal_input
from src.mission import MissionController, MissionStore


def create_display(stop_event):
    """Create the Rich terminal UI."""
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
        self.sigint_grace_window = 2.0  # seconds to treat double Ctrl+C as exit
        self._last_response: str | None = None
        self._prev_sigint = signal.getsignal(signal.SIGINT)
        self._shutting_down = False
        signal.signal(signal.SIGINT, self._handle_sigint)

    def _mark_interrupt(self) -> bool:
        """Track whether this interrupt should exit the app."""
        now = time.monotonic()
        self.sigint_pending_exit = (
            now - self.last_sigint_time
        ) <= self.sigint_grace_window
        self.last_sigint_time = now
        return self.sigint_pending_exit

    def _handle_sigint(self, signum, frame):
        if self._shutting_down:
            return
        # First Ctrl+C cancels current turn; a second within the grace window exits
        self.stop_event.set()
        self._mark_interrupt()
        raise KeyboardInterrupt()

    def begin_shutdown(self):
        """Prevent late SIGINTs from interrupting interpreter teardown."""
        self._shutting_down = True
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            self.agent.tool_registry.shutdown()
        except Exception:
            pass
        if self._active_mission is not None:
            self._active_mission.cancel()
            self._active_mission = None
        try:
            self.mission_store.close()
        except Exception:
            pass

    def _exit_app(self):
        self.begin_shutdown()
        self.display.clear_pending_exit()
        self.display.print_centered(
            "Shutting down TERMINUS...", style=f"bold {COLORS['text']}"
        )
        if hasattr(self.display, "shutdown"):
            self.display.shutdown()
        sys.exit(0)

    def _emit_worker_event(self, event_type: str, data: dict):
        """Forward subagent lifecycle events to the display."""
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
        if hasattr(self.display, "handle_mission_event"):
            self.display.handle_mission_event(event)

    def process_query(self, user_input: str):
        """Process user query and coordinate with agent and display"""
        try:
            self.stop_event.clear()
            # Process @ file references
            enriched_message, loaded_files, errors = process_file_references(user_input)

            # Display loaded files
            if loaded_files:
                files_list = ", ".join([f"[red]{f}[/red]" for f in loaded_files])
                self.display.print_message(f"[dim red]Loaded files: {files_list}")

            # Display errors if any
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
                )

            # Render final response after live display stops to keep content visible
            handler.render_final_response(response)
            self._last_response = response
            self.sigint_pending_exit = False
            self.display.clear_pending_exit()

            # Display footer with context info
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
        """Execute a slash command. Returns True if should continue loop, False if should exit"""

        # Exit commands
        if command.lower() in ["exit", "quit", "/exit", "/quit", "q"]:
            self.display.print_centered(
                "Shutting down TERMINUS...", style=f"bold {COLORS['text']}"
            )
            return False

        # Reset session
        if command.lower() == "/reset":
            self.agent.clear_session()
            self.display.render_success_message("Session reset successfully")
            return True

        # Clear screen
        if command.lower() in ["/clear", "clear"]:
            self.display.clear_screen()
            self.display.render_banner()
            return True

        # Display context size
        if command.lower() == "/context_size":
            self.display.print_message(f"Context Size: {self.agent.context_size}")
            return True

        # Compact conversation context
        if command.lower() == "/compact":
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

        # Display history
        if command.lower() == "/history":
            self._display_history()
            return True

            # Display help
        if command.lower() == "/help":
            self.display.render_help()
            return True

        # Durable Mission Control runtime and audit commands.
        if command.lower().startswith("/mission"):
            task = command[len("/mission") :].strip()
            if not task:
                self.display.render_error(
                    "Usage: /mission <goal> | /mission list | /mission replay <id>"
                )
                return True
            if task.lower() == "list":
                self._list_missions()
                return True
            if task.lower() == "replay":
                self.display.render_error("Usage: /mission replay <id>")
                return True
            if task.lower().startswith("replay "):
                if self._active_mission is not None:
                    self.display.render_error(
                        "Finish or cancel the active mission before opening a replay."
                    )
                    return True
                self._replay_mission(task.split(maxsplit=1)[1])
                return True
            if self._active_mission is not None:
                self.display.render_error(
                    "A mission is awaiting input. Answer it or cancel it before starting another."
                )
                return True
            self._start_mission(task)
            self.display.print_newline()
            return True

        # Copy last response to clipboard
        if command.lower() == "/copy":
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

        if command.lower() == "/init":
            handler = self.display.create_response_handler()
            with handler:
                result = self.agent.init(
                    status_callback=handler.update_status,
                    todo_display_callback=lambda todos: self.display.render_todo_panel(
                        todos, handler=handler
                    ),
                    tool_call_callback=handler.display_tool_call,
                    stop_event=self.stop_event,
                )
            handler.render_final_response(result)
            return True

            # Display context
        if command.lower() == "/context":
            self.display.print_message(str(self.agent.context))
            return True

        if command.lower() == "/models":
            selected = self.display.select_model_ui(current_model=self.agent.model)
            if selected:
                self.agent.switch_model(selected)
                self.display.print_message(
                    f"[green]Switched model to[/green] [bold]{selected.name}[/bold]"
                )
            else:
                self.display.print_message("[dim]Model selection cancelled.[/dim]")
            return True

        # Connect provider and configure API key
        if command.lower() == "/connect":
            try:
                result = self.display.connect_provider_ui()
                if result is None:
                    self.display.print_message(
                        "[dim]Provider connection cancelled.[/dim]"
                    )
                    return True

                provider_name, api_key = result

                # Determine the env var name for this provider
                env_var_map = {
                    "openrouter": "OPEN_ROUTER_API_KEY",
                }
                env_var = env_var_map.get(provider_name)
                if not env_var:
                    self.display.render_error(f"Unknown provider: {provider_name}")
                    return True

                # Save to user-level .env
                env_dir = os.path.expanduser("~/.terminus")
                os.makedirs(env_dir, exist_ok=True)
                env_path = os.path.join(env_dir, ".env")
                set_key(env_path, env_var, api_key)
                os.environ[env_var] = api_key
                if env_var == "OPEN_ROUTER_API_KEY":
                    os.environ["OPENROUTER_API_KEY"] = api_key

                # Update the provider's API key in-memory
                self.agent.llm_service.set_provider_api_key(provider_name, api_key)
                self.display.render_success_message(
                    f"API key configured for {provider_name}. "
                    f"Use /models to switch to a {provider_name} model."
                )
            except KeyboardInterrupt:
                self.display.print_message("[dim]Provider connection cancelled.[/dim]")
            except Exception as e:
                self.display.render_error(str(e))
            return True

        # List available skills
        if command.lower() == "/skills":
            skills = discover_skills(os.getcwd())
            skills = self.agent.annotate_skills(skills)
            self.display.render_skills(skills)
            return True

        # Load a skill by name
        if command.lower() == "/skill" or command.lower().startswith("/skill "):
            parts = command.strip().split(maxsplit=1)
            skills = discover_skills(os.getcwd())
            skills = self.agent.annotate_skills(skills)

            if not skills:
                self.display.render_error("No skills found in .skills/ directory.")
                return True

            if len(parts) < 2:
                selected = self.display.select_skill_ui(skills)
                if selected:
                    self._load_skill(selected)
                else:
                    self.display.print_message("[dim]Skill selection cancelled.[/dim]")
            else:
                skill_name = parts[1]
                match = next((s for s in skills if s["name"] == skill_name), None)
                if match:
                    self._load_skill(match)
                else:
                    self.display.render_error(
                        f"Skill '{skill_name}' not found. Use /skills to list available skills."
                    )
            return True

        # Fallback: React owns command suggestions; unknown commands are explicit errors.
        if command.startswith("/"):
            self.display.render_error(f"Unknown command: {command}")
            return True

        return True

    def _display_history(self):
        """Display session history"""
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
            self.display.mission_end(summary=outcome.summary, status=outcome.status.value)
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

    def _replay_mission(self, mission_id: str):
        mission = self.mission_store.get_mission(mission_id)
        if mission is None:
            matches = [
                item
                for item in self.mission_store.list_missions(limit=100)
                if item["id"].startswith(mission_id)
            ]
            if len(matches) == 1:
                mission = matches[0]
                mission_id = mission["id"]
        if mission is None:
            self.display.render_error(f"Mission not found: {mission_id}")
            return
        self.display.mission_start(
            title="replay",
            goal=mission["goal"],
            phase="brief",
            mission_id=mission_id,
        )
        for event in self.mission_store.get_events(mission_id):
            self._emit_mission_event(event)
        self.display.mission_end(
            summary=mission.get("summary") or "",
            status=mission["status"],
        )

    def _load_skill(self, skill: dict):
        """Load a skill's content into the current conversation context."""
        skill_name = skill.get("name", "unknown")
        loaded = self.agent.load_skill(skill)
        if not loaded:
            self.display.render_success_message(
                f"Skill '{skill_name}' is already loaded"
            )
            return
        self.display.render_success_message(f"Skill '{skill_name}' loaded into context")

    def run_interactive(self):
        """Run interactive mode with conversation loop"""
        if hasattr(self.display, "start_interactive"):
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

                # Handle empty input
                if not user_input.strip():
                    continue

                # ask_question already paints the selection into the transcript;
                # don't re-render the auto-queued answer as another "You" block.
                silent = False
                if hasattr(self.display, "consume_last_input_was_silent"):
                    silent = self.display.consume_last_input_was_silent()
                if not silent and hasattr(self.display, "render_user_message"):
                    self.display.render_user_message(user_input)

                # Check if it's a registered slash command or exit alias
                is_known_command = CommandRegistry.is_registered(
                    user_input.lower().split()[0]
                ) or user_input.lower().split()[0] in ["exit", "quit", "q", "clear"]
                if is_known_command:
                    should_continue = self.execute_command(user_input)
                    if not should_continue:
                        break
                    continue

                if self._active_mission is not None:
                    if hasattr(self.display, "generation_start"):
                        self.display.generation_start()
                    try:
                        self.stop_event.clear()
                        self._run_mission_turn(user_input)
                    finally:
                        if hasattr(self.display, "generation_end"):
                            self.display.generation_end()
                    self.display.print_newline()
                    continue

                # Process as query
                if hasattr(self.display, "generation_start"):
                    self.display.generation_start()
                try:
                    self.process_query(user_input)
                finally:
                    if hasattr(self.display, "generation_end"):
                        self.display.generation_end()
                self.display.print_newline()

            except KeyboardInterrupt:
                if self.sigint_pending_exit or self.display.check_pending_exit():
                    self._exit_app()
                # Single interrupt: cancel turn, keep session
                self.stop_event.clear()
                self.display.clear_pending_exit()
                self.sigint_pending_exit = False
                continue
            except EOFError:
                break

    def run_single_query(self, query: str):
        """Run a single query (useful for non-interactive mode)"""
        self.display.render_banner()
        first = query.lower().split()[0] if query.strip() else ""
        if CommandRegistry.is_registered(first):
            self.execute_command(query)
        else:
            self.process_query(query)


def main():
    """Main entry point for 'terminus' command"""
    parser = argparse.ArgumentParser(
        prog="terminus",
        description="AI-powered development companion for the command line",
    )
    parser.add_argument(
        "query", nargs="*", help="Single query to run (non-interactive)"
    )
    args = parser.parse_args()

    # Always use the current working directory where the command is invoked
    invoked_dir = os.getcwd()
    cli = TerminusCLI(cwd=invoked_dir)

    try:
        if args.query:
            cli.run_single_query(" ".join(args.query))
        else:
            cli.run_interactive()
    finally:
        cli.begin_shutdown()
        # Graceful shutdown for React UI
        if hasattr(cli.display, "shutdown"):
            cli.display.shutdown()
