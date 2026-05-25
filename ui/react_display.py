import json
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from itertools import count

from ui.theme import get_role_color
from src.models.llm import available_models
from src.commands.registry import CommandRegistry


MAX_UI_BODY_CHARS = 12000
MAX_UI_PREVIEW_CHARS = 240
MAX_UI_ARG_CHARS = 4000
BATCH_INTERVAL_SECONDS = 0.04
MAX_BATCH_EVENTS = 50
QUESTION_FALLBACK_OPTIONS = [
    "Use the recommended default",
    "Let me decide manually",
    "Skip this for now",
]


class ReactDisplay:
    """Bridge to the Ink/React terminal UI.

    React inherits the real terminal stdin/stdout so Ink can use raw mode
    for keyboard input and render to the screen.  Python ↔ React commands
    travel over a Unix domain socket so the two streams don't interfere.
    """

    def __init__(self, stop_event=None):
        self._stop_event = stop_event
        self.last_interrupt_time = 0.0
        self.interrupt_grace_window = 1.5
        self.pending_exit = False
        self._event_counter = count(1)
        self._seq_counter = count(1)
        self._turn_counter = count(1)
        self._turn_id = "turn-0"
        self._active_stream_item_id: str | None = None
        self._pending_events: list[dict] = []
        self._flush_timer: threading.Timer | None = None
        self._last_flush = time.monotonic()
        self._react_debug = os.environ.get("TERMINUS_REACT_DEBUG") == "1"
        self._recent_stderr: deque[str] = deque(maxlen=200)
        react_dir = os.path.join(os.path.dirname(__file__), "react")
        entry = os.path.join(react_dir, "src", "main.tsx")

        tsx_bin = os.path.join(react_dir, "node_modules", ".bin", "tsx")
        if not os.path.exists(tsx_bin):
            tsx_bin = "npx"
            args = ["tsx", entry]
        else:
            args = [entry]

        # Unix socket for JSON IPC
        self._sock_path = os.path.join(
            tempfile.gettempdir(), f"terminus_{os.getpid()}.sock"
        )
        if os.path.exists(self._sock_path):
            os.remove(self._sock_path)

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self._sock_path)
        self._server.listen(1)

        # Spawn React with the real terminal for stdin/stdout
        self._proc = subprocess.Popen(
            [tsx_bin, *args],
            stdin=None,          # inherit real TTY → Ink keyboard works
            stdout=None,         # inherit real TTY → Ink renders to screen
            stderr=subprocess.PIPE,
            env={**os.environ, "TERMINUS_SOCK": self._sock_path},
            cwd=react_dir,
        )

        # Accept the connection React will make back to us
        self._server.settimeout(15)
        try:
            self._conn, _ = self._server.accept()
        except socket.timeout:
            err = self._proc.stderr.read()
            self._cleanup()
            raise RuntimeError(
                f"React UI did not connect within 15s.\nstderr: {err}"
            )

        self._conn.setblocking(True)
        self._lock = threading.RLock()
        self._read_queue: queue.Queue[dict] = queue.Queue()

        # Background thread drains the socket into a queue
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

        # Drain stderr so the pipe doesn't back-pressure
        self._stderr_reader = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_reader.start()

        self._wait_for_ready(timeout=10)
        self._send_command_list()

    # ------------------------------------------------------------------ #
    # Low-level IPC
    # ------------------------------------------------------------------ #

    def _reader_loop(self):
        """Background thread: read JSON lines from the socket."""
        buffer = ""
        while True:
            try:
                data = self._conn.recv(4096)
            except OSError:
                break
            if not data:
                break
            buffer += data.decode()
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "interrupt" and self._stop_event is not None:
                        now = time.monotonic()
                        self.pending_exit = (
                            now - self.last_interrupt_time
                        ) <= self.interrupt_grace_window
                        self.last_interrupt_time = now
                        self._stop_event.set()
                    self._read_queue.put(msg)
                except json.JSONDecodeError:
                    pass

    def _stderr_loop(self):
        """Background thread: drain React stderr."""
        for line in iter(self._proc.stderr.readline, b""):
            if line.strip():
                decoded = line.decode(errors="replace").strip()
                self._recent_stderr.append(decoded)
                if self._react_debug:
                    print(f"[REACT] {decoded}", file=sys.__stderr__)

    def _send(self, msg: dict):
        self.send_immediate(msg)

    def _write_unlocked(self, msg: dict):
        try:
            self._conn.sendall((json.dumps(msg) + "\n").encode())
        except (BrokenPipeError, OSError):
            pass

    def _event_with_metadata(self, msg: dict) -> dict:
        return {
            **msg,
            "seq": msg.get("seq", next(self._seq_counter)),
            "turnId": msg.get("turnId", self._turn_id),
            "timestamp": msg.get("timestamp", time.time()),
        }

    def _flush_unlocked(self):
        if not self._pending_events:
            self._flush_timer = None
            return
        timer = self._flush_timer
        self._flush_timer = None
        if timer is not None and timer.is_alive():
            timer.cancel()
        events = self._pending_events
        self._pending_events = []
        self._last_flush = time.monotonic()
        if len(events) == 1:
            self._write_unlocked(events[0])
            return
        self._write_unlocked({"type": "event_batch", "events": events})

    def _schedule_flush_unlocked(self):
        if self._flush_timer is not None:
            return
        self._flush_timer = threading.Timer(BATCH_INTERVAL_SECONDS, self.flush_events)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def send_event(self, msg: dict):
        event = self._event_with_metadata(msg)
        with self._lock:
            self._pending_events.append(event)
            elapsed = time.monotonic() - self._last_flush
            if elapsed >= BATCH_INTERVAL_SECONDS or len(self._pending_events) >= MAX_BATCH_EVENTS:
                self._flush_unlocked()
            else:
                self._schedule_flush_unlocked()

    def flush_events(self):
        with self._lock:
            self._flush_unlocked()

    def send_immediate(self, msg: dict):
        event = self._event_with_metadata(msg)
        with self._lock:
            self._flush_unlocked()
            self._write_unlocked(event)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._event_counter)}"

    def _clean_text(self, value: str) -> str:
        text = str(value)
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
        text = "".join(
            ch for ch in text
            if ch in "\n\t" or ord(ch) >= 32
        )
        return text

    def _preview_text(self, value: str, max_chars: int = MAX_UI_PREVIEW_CHARS) -> str:
        clean = self._clean_text(value)
        first_line = clean.splitlines()[0] if clean else ""
        return first_line[:max_chars]

    def _bounded_text(self, value: str, max_chars: int = MAX_UI_BODY_CHARS) -> str:
        clean = self._clean_text(value)
        if len(clean) <= max_chars:
            return clean
        omitted = len(clean) - max_chars
        return f"{clean[:max_chars]}\n... truncated {omitted} character(s) for UI display"

    def _bounded_args(self, args: dict) -> dict:
        try:
            encoded = json.dumps(args)
        except (TypeError, ValueError):
            return {"preview": self._bounded_text(str(args), MAX_UI_ARG_CHARS)}
        if len(encoded) <= MAX_UI_ARG_CHARS:
            return args
        return {"preview": self._bounded_text(encoded, MAX_UI_ARG_CHARS)}

    def _read(self, block: bool = True, timeout: float = 0.1) -> dict:
        try:
            return self._read_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return {}

    def _wait_for_ready(self, timeout: float = 10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"React UI exited early (code {self._proc.returncode})"
                )
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "ready":
                return
        raise TimeoutError("React UI did not send ready handshake.")

    def _send_command_list(self):
        self._send(
            {
                "type": "command_list",
                "commands": [
                    {"name": command.name, "description": command.description}
                    for command in CommandRegistry.all()
                ],
            }
        )

    # ------------------------------------------------------------------ #
    # TerminalDisplay-compatible API
    # ------------------------------------------------------------------ #

    def render_banner(self):
        logo = [
            "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗██╗   ██╗███████╗",
            "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██║   ██║██╔════╝",
            "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║██║   ██║███████╗",
            "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║   ██║╚════██║",
            "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║╚██████╔╝███████║",
            "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝",
        ]
        self.send_immediate({
            "type": "banner",
            "logo": logo,
            "subtitle": "Your coding sidekick",
        })

    def get_user_input(self, model=None, context_size=None, model_context_size=None):
        if model is not None:
            self.render_footer(
                cwd=os.getcwd(),
                model=model,
                context_size=context_size or 0,
                model_context_size=model_context_size or 0,
            )
        self._drain_stale_interrupts()
        self.send_immediate({"type": "input_request"})
        while True:
            if self._proc.poll() is not None:
                raise RuntimeError("React UI process exited unexpectedly")
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "input":
                content = msg.get("content", "")
                return content
            if msg.get("type") == "question_answer":
                content = msg.get("content", "")
                return content
            if msg.get("type") == "copy_last_response":
                return "/copy"
            if msg.get("type") == "interrupt":
                raise KeyboardInterrupt()

    def _drain_stale_interrupts(self):
        retained = []
        while True:
            msg = self._read(block=False)
            if not msg:
                break
            if msg.get("type") != "interrupt":
                retained.append(msg)
        for msg in retained:
            self._read_queue.put(msg)

    def generation_start(self):
        self._turn_id = f"turn-{next(self._turn_counter)}"
        self.send_immediate({"type": "generation_start"})

    def generation_end(self):
        self.send_immediate({"type": "generation_end"})

    def render_footer(self, cwd: str, model: str, context_size: int, model_context_size: int):
        pct = (context_size / model_context_size) * 100 if model_context_size else 0.0
        self.send_event({
            "type": "status",
            "cwd": cwd,
            "model": model,
            "contextPercent": pct,
        })

    def print_message(self, message: str, style: str = ""):
        clean = re.sub(r"\[/(/?\w+)\]", "", re.sub(r"\[(/?\w+)\]", "", message))
        clean = self._clean_text(clean)
        if not clean.strip():
            return
        self.send_event(
            {
                "type": "response",
                "id": self._next_id("timeline"),
                "content": clean,
                "tag": "system",
            }
        )

    def send_tool_call(self, tool_name: str, label: str, args: dict):
        is_question_tool = tool_name == "ask_question"
        self.send_event(
            {
                "type": "tool_call",
                "id": self._next_id("timeline"),
                "toolName": tool_name,
                "label": label,
                "args": self._bounded_args(args),
                "collapsible": not is_question_tool,
                "groupKey": tool_name,
            }
        )
        if is_question_tool:
            self.send_question_request(args)

    def send_question_request(self, args: dict):
        questions = self._normalize_question_request(args.get("questions") or [])
        if not questions:
            return
        self.send_immediate(
            {
                "type": "question_request",
                "questions": questions,
            }
        )

    def _normalize_question_request(self, questions: list) -> list[dict]:
        return [self._normalize_question(question) for question in questions]

    def _normalize_question(self, question) -> dict:
        if isinstance(question, dict):
            return {
                "text": str(question.get("text") or question.get("question") or "Please clarify your preference.").strip(),
                "options": self._normalize_question_options(question.get("options")),
                "allowMultiple": bool(question.get("allow_multiple", question.get("allowMultiple", False))),
            }
        return {
            "text": str(question).strip() or "Please clarify your preference.",
            "options": QUESTION_FALLBACK_OPTIONS.copy(),
            "allowMultiple": False,
        }

    def _normalize_question_options(self, options) -> list[str]:
        if not isinstance(options, list):
            return QUESTION_FALLBACK_OPTIONS.copy()
        normalized = [str(option).strip() for option in options if str(option).strip()]
        return (normalized + QUESTION_FALLBACK_OPTIONS)[:3]

    def send_tool_output(self, tool_name: str, output: str):
        bounded_output = self._bounded_text(str(output))
        self.send_event(
            {
                "type": "tool_output",
                "id": self._next_id("timeline"),
                "toolName": tool_name,
                "content": bounded_output,
                "collapsible": True,
                "preview": self._preview_text(str(output)) if output else "",
                "groupKey": f"{tool_name}:output",
            }
        )

    def render_error(self, error_message: str):
        self.send_immediate(
            {
                "type": "error",
                "id": self._next_id("timeline"),
                "message": self._bounded_text(error_message),
                "severity": "error",
            }
        )

    def render_success_message(self, message: str):
        self.send_immediate(
            {
                "type": "response",
                "id": self._next_id("timeline"),
                "content": message,
                "tag": "success",
            }
        )

    def render_response(self, content: str):
        content = self._clean_text(content)
        if not content.strip():
            return
        self.send_immediate(
            {
                "type": "response",
                "id": self._next_id("timeline"),
                "content": self._bounded_text(content),
                "tag": "assistant",
            }
        )

    def render_user_message(self, content: str):
        content = self._clean_text(content)
        if not content.strip():
            return
        self.send_immediate(
            {
                "type": "response",
                "id": self._next_id("timeline"),
                "content": content,
                "tag": "user",
            }
        )

    def send_stream_chunk(self, chunk: str):
        chunk = self._clean_text(chunk)
        if not chunk:
            return
        if self._active_stream_item_id is None:
            self._active_stream_item_id = self._next_id("stream")
        self.send_event(
            {
                "type": "stream_chunk",
                "itemId": self._active_stream_item_id,
                "content": chunk,
            }
        )

    def send_stream_end(self, content: str):
        content = self._clean_text(content)
        if not content.strip():
            self._active_stream_item_id = None
            return
        item_id = self._active_stream_item_id or self._next_id("stream")
        self._active_stream_item_id = None
        self.send_immediate({"type": "stream_end", "itemId": item_id, "content": self._bounded_text(content)})

    def send_mode_switch(self, mode: str, note: str | None = None):
        payload = {"type": "mode_switch", "mode": mode}
        if note:
            payload["note"] = note
        self.send_immediate(payload)

    def send_worker_spawned(self, worker_id: str, name: str, description: str, role: str | None = None):
        self.send_event({
            "type": "worker_spawned",
            "workerId": worker_id,
            "name": name,
            "description": self._bounded_text(description),
            "role": role or "worker",
        })

    def send_worker_notification(
        self,
        worker_id: str,
        status: str,
        summary: str,
        final_response: str | None = None,
        timestamp: float | None = None,
    ):
        payload: dict = {
            "type": "worker_notification",
            "workerId": worker_id,
            "status": status,
            "summary": self._bounded_text(summary),
            "timestamp": timestamp or time.time(),
            "id": self._next_id(f"worker-note-{worker_id}"),
        }
        if final_response is not None:
            payload["finalResponse"] = self._bounded_text(final_response)
        self.send_event(payload)

    def send_worker_status(
        self,
        worker_id: str,
        status: str,
        result: str | None = None,
        result_envelope: dict | None = None,
        timestamp: float | None = None,
    ):
        payload: dict = {
            "type": "worker_status",
            "workerId": worker_id,
            "status": status,
            "timestamp": timestamp or time.time(),
            "id": f"worker-status-{worker_id}",
        }
        if result is not None:
            payload["result"] = self._bounded_text(result)
        if result_envelope is not None:
            payload["resultEnvelope"] = result_envelope
        self.send_event(payload)

    def send_worker_detail(
        self,
        worker_id: str,
        detail_type: str,
        content: str,
        tool_name: str | None = None,
        args: dict | None = None,
        timestamp: float | None = None,
    ):
        payload: dict = {
            "type": "worker_detail",
            "workerId": worker_id,
            "detailType": detail_type,
            "content": self._bounded_text(content),
            "timestamp": timestamp or time.time(),
            "id": self._next_id(f"worker-detail-{worker_id}-{detail_type}"),
        }
        if tool_name is not None:
            payload["toolName"] = tool_name
        if args is not None:
            payload["args"] = self._bounded_args(args)
        self.send_event(payload)

    def clear_screen(self):
        self.send_immediate({"type": "clear"})

    def print_centered(self, message: str, style: str = ""):
        self.print_message(message, style)

    def print_newline(self):
        pass

    def get_role_color(self, role: str) -> str:
        return get_role_color(role)

    def render_history(self, history_lines: list):
        for line in history_lines:
            self.print_message(line)

    def render_help(self):
        self.print_message(
            "Commands: /help, /plan <task>, /context, /history, /reset, "
            "/context_size, /copy, /clear, /models, /skills, /skill <name>, exit/quit"
        )

    def render_skills(self, skills: list):
        if not skills:
            self.print_message("No skills found in .skills/ directory.")
            return
        lines = ["Available Skills:"]
        for skill in skills:
            name = skill.get("name", "unknown")
            desc = skill.get("description", "")
            trigger = skill.get("trigger", "")
            line = f"  {name}"
            if skill.get("loaded"):
                line += " [loaded]"
            if desc:
                line += f" - {desc}"
            if trigger:
                line += f" (trigger: {trigger})"
            lines.append(line)
        lines.append("\nUse /skill <name> to load a skill.")
        self.print_message("\n".join(lines))

    def connect_provider_ui(self) -> tuple[str, str] | None:
        providers = [
            {"name": "groq", "description": "Fast inference via Groq"},
            {"name": "openrouter", "description": "Broad model selection via OpenRouter"},
        ]

        self.send_immediate(
            {
                "type": "provider_select",
                "providers": providers,
            }
        )

        provider_name = None
        while True:
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "provider_selected":
                provider_name = msg.get("name")
                if not provider_name:
                    return None
                break
            if msg.get("type") == "interrupt":
                raise KeyboardInterrupt()

        self.send_immediate(
            {
                "type": "api_key_request",
                "provider": provider_name,
            }
        )

        while True:
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "api_key_submitted":
                api_key = msg.get("key", "")
                if not api_key:
                    return None
                return provider_name, api_key
            if msg.get("type") == "interrupt":
                raise KeyboardInterrupt()

    def select_model_ui(self, current_model: str = None):
        models = []
        for model in available_models:
            inst = model() if isinstance(model, type) else model
            service_provider = "groq" if inst.provider == "groq" else "openrouter"
            models.append(
                {
                    "name": inst.name,
                    "provider": inst.provider,
                    "creator": inst.name.split("/")[0],
                    "serviceProvider": service_provider,
                    "contextSize": inst.context_size,
                    "inputPricing": inst.input_tokens_pricing,
                    "outputPricing": inst.output_tokens_pricing,
                }
            )

        self.send_immediate(
            {
                "type": "model_select",
                "models": models,
                "currentModel": current_model,
            }
        )

        while True:
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "model_selected":
                selected_name = msg.get("name")
                if not selected_name:
                    return None
                for model in available_models:
                    inst = model() if isinstance(model, type) else model
                    if inst.name == selected_name:
                        return inst
                return None
            if msg.get("type") == "interrupt":
                raise KeyboardInterrupt()

    def select_skill_ui(self, skills: list):
        self.send_immediate(
            {
                "type": "skill_select",
                "skills": [
                    {
                        "name": s.get("name", "unknown"),
                        "description": s.get("description", ""),
                        "trigger": s.get("trigger", ""),
                        "loaded": s.get("loaded", False),
                    }
                    for s in skills
                ],
            }
        )

        while True:
            msg = self._read(block=True, timeout=0.5)
            if msg.get("type") == "skill_selected":
                selected_name = msg.get("name")
                if not selected_name:
                    return None
                for s in skills:
                    if s["name"] == selected_name:
                        return s
                return None
            if msg.get("type") == "interrupt":
                raise KeyboardInterrupt()

    def create_response_handler(self):
        return ReactResponseHandler(self)

    def render_todo_panel(self, todos: list, handler=None):
        if handler is not None:
            handler.update_todo_display(todos)

    def check_pending_exit(self) -> bool:
        return self.pending_exit

    def clear_pending_exit(self):
        self.pending_exit = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def _cleanup(self):
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        try:
            if hasattr(self, "_conn"):
                self._conn.close()
        except Exception:
            pass
        try:
            self._server.close()
        except Exception:
            pass
        if os.path.exists(self._sock_path):
            os.remove(self._sock_path)

    def shutdown(self):
        try:
            self.send_immediate({"type": "exit"})
        except (BrokenPipeError, OSError):
            pass
        try:
            self._proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._cleanup()



class ReactResponseHandler:
    """Status and event handler for the React UI."""

    def __init__(self, display: ReactDisplay):
        self.display = display
        self._content = []
        self._todos = []
        self._active = False
        self._thinking_active = False
        self._thinking_buffer = []
        self._active_thinking_item_id = None

    def _flush_thinking(self):
        self._thinking_active = False
        self._thinking_buffer = []

    def __enter__(self):
        self._active = True
        self._content = []
        self._thinking_active = False
        self._thinking_buffer = []
        self._active_thinking_item_id = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._flush_thinking()
        self._active = False
        return False

    def start(self):
        self._active = True
        self._content = []
        self._thinking_active = False
        self._thinking_buffer = []
        self._active_thinking_item_id = None

    def stop(self):
        self._active = False
        self._active_thinking_item_id = None

    def update_status(
        self,
        message: str,
        is_thinking: bool = False,
        is_tool_output: bool = False,
        keep_stopped: bool = False,
        is_alert: bool = False,
    ):
        if is_alert:
            self._flush_thinking()
            self._active_thinking_item_id = None
            self.display.send_immediate(
                {
                    "type": "alert",
                    "id": self.display._next_id("timeline"),
                    "content": self.display._bounded_text(message),
                    "severity": "warning",
                }
            )
        elif is_thinking:
            self._thinking_active = True
            if self._active_thinking_item_id is None:
                self._active_thinking_item_id = self.display._next_id("thinking")
            self.display.send_event(
                {
                    "type": "thinking",
                    "id": self._active_thinking_item_id,
                    "content": self.display._bounded_text(message),
                    "collapsible": True,
                    "preview": self.display._preview_text(message),
                }
            )
        else:
            self._flush_thinking()
            self._active_thinking_item_id = None
            self.display.print_message(message)

    def display_tool_call(self, tool_name: str, label: str, args: dict):
        self.display.send_tool_call(tool_name, label, args)

    def display_tool_output(self, tool_name: str, output: str):
        self.display.send_tool_output(tool_name, output)

    def handle_streaming(self, chunk: str):
        if self._active:
            self._flush_thinking()
            self._active_thinking_item_id = None
            self._content.append(chunk)
            self.display.send_stream_chunk(chunk)

    def update_todo_display(self, todos: list):
        self._todos = todos
        self.display.send_event({
            "type": "todo_list",
            "items": [
                {"task": item.get("task", ""), "status": item.get("status", "pending")}
                for item in todos
            ],
        })

    def render_final_response(self, response: str):
        self._flush_thinking()
        self._active_thinking_item_id = None
        final = "".join(self._content) if self._content else response
        self._content = []
        if self.display._active_stream_item_id is not None:
            self.display.send_stream_end(final)
            return
        self.display.render_response(final)
