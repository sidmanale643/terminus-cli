"""Rich-based terminal UI for Terminus CLI.

The display owns the terminal directly and prints synchronously (no socket/IPC).
Keyboard input is line-based (Rich `Prompt`); double-Ctrl+C exit semantics are
handled by `TerminusCLI`'s SIGINT handler in `src/cli/application.py`.
"""

import json
import os
import re
import time
from collections import deque

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.markup import MarkupError, escape
from rich.padding import Padding
from rich.panel import Panel
from rich.prompt import Prompt
from rich.segment import Segment, Segments
from rich.table import Table
from rich.text import Text

from rich_ui.worker_board import MissionBoard
from src.cli.terminal import MOUSE_REPORTING_OFF, MOUSE_REPORTING_ON, read_terminal_line
from src.commands.registry import CommandRegistry
from src.models.llm import available_models
from ui.theme import COLORS, create_progress_bar, get_role_color

MAX_BODY_CHARS = 12000
MAX_PREVIEW_CHARS = 240
QUESTION_FALLBACK_OPTIONS = [
    "Use the recommended default",
    "Let me decide manually",
    "Skip this for now",
]

WIDE_BANNER_MIN_WIDTH = 78
WIDE_BANNER_ROWS = 9
COMPOSER_ROWS = 5
WELCOME_IDENTITY_WIDTH = 48
SYNC_UPDATE_BEGIN = "\x1b[?2026h"
SYNC_UPDATE_END = "\x1b[?2026l"
TRANSCRIPT_BLOCK_PADDING = (0, 0, 1, 0)

TERMINUS_WORDMARK = [
    "╺━┳━╸ ┏━━╸ ┏━━┓ ┏┓ ┏┓ ┏━┓ ┏┓ ╻ ╻ ╻ ┏━━┓",
    "  ┃   ┃    ┃  ┃ ┃┗┳┛┃  ┃  ┃┗┓┃ ┃ ┃ ┃   ",
    "  ┃   ┣━╸  ┣━┳┛ ┃ ┃ ┃  ┃  ┃ ┗┫ ┃ ┃ ┗━━┓",
    "  ┃   ┃    ┃ ┗╸ ┃   ┃  ┃  ┃  ┃ ┃ ┃    ┃",
    "  ╹   ┗━━╸ ╹  ╹ ╹   ╹ ┗━┛ ╹  ╹ ┗━┛ ┗━━┛",
]


class ThinkingMessage:
    """Mutable renderable used while provider reasoning streams in."""

    def __init__(self, content: str):
        self.content = content

    def __rich_console__(self, console, options):
        yield Padding(
            Group(
                Text("Thinking", style=f"bold {COLORS['dim']}"),
                Padding(Text(self.content, style=f"italic {COLORS['muted']}"), (0, 2)),
            ),
            TRANSCRIPT_BLOCK_PADDING,
        )


class RichDisplay:
    """Pure-Python terminal UI backed by Rich."""

    def __init__(self, stop_event=None):
        self._stop_event = stop_event
        self.console = Console(highlight=False)
        self.pending_exit = False
        self._queued_input: deque[str] = deque()
        # True when the next queued input was already shown in the transcript
        # (e.g. ask_question selection) and should not re-render as "You".
        self._queued_input_silent: deque[bool] = deque()
        self._board: MissionBoard | None = None
        self._footer = {"cwd": "", "model": "", "context_percent": 0.0}
        self._welcome_pending = False
        self._interactive = False
        self._screen_active = False
        self._generation_active = False
        self._transcript: list = []
        self._stream_buffer = ""
        self._last_stream_refresh = 0.0
        self._input_buffer = ""
        self._scroll_offset = 0
        # When ask_question already rendered the prompt in-chat, skip re-dumping
        # the same formatted text as the turn's final assistant response.
        self._suppress_next_response = False
        self._last_input_was_silent = False

    # ------------------------------------------------------------------ #
    # Text helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean_text(value: str) -> str:
        text = str(value)
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
        text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
        return text

    def _bounded_text(self, value: str, max_chars: int = MAX_BODY_CHARS) -> str:
        clean = self._clean_text(value)
        if len(clean) <= max_chars:
            return clean
        omitted = len(clean) - max_chars
        return (
            f"{clean[:max_chars]}\n... truncated {omitted} character(s) for UI display"
        )

    def _preview_text(self, value: str, max_chars: int = MAX_PREVIEW_CHARS) -> str:
        clean = self._clean_text(value)
        first_line = clean.splitlines()[0] if clean else ""
        return first_line[:max_chars]

    def _args_preview(self, args: dict) -> str:
        try:
            encoded = json.dumps(args or {})
        except (TypeError, ValueError):
            encoded = str(args)
        return encoded[:200]

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #

    def _to_plain(self, renderable) -> str:
        if isinstance(renderable, Text):
            return renderable.plain
        if isinstance(renderable, ThinkingMessage):
            return renderable.content
        try:
            lines = self.console.render_lines(renderable, pad=False)
        except Exception:
            return str(renderable)
        return "\n".join(
            "".join(segment.text for segment in line).rstrip() for line in lines
        ).rstrip()

    def _emit(self, renderable, markup: bool = False, style: str | None = None):
        """Print, routing through the mission board when the theater is live."""
        if self._board is not None and self._board.is_live():
            self._board.log(self._to_plain(renderable), style=COLORS["text"])
            return
        if self._interactive and self.console.is_terminal:
            if isinstance(renderable, str):
                if markup:
                    try:
                        renderable = Text.from_markup(renderable, style=style or "")
                    except MarkupError:
                        renderable = Text(renderable, style=style or "")
                else:
                    renderable = Text(renderable, style=style or "")
            self._transcript.append(renderable)
            self._transcript = self._transcript[-200:]
            self._redraw()
            return
        try:
            self.console.print(renderable, markup=markup, style=style)
        except MarkupError:
            self.console.print(self._to_plain(renderable), markup=False)

    def start_interactive(self):
        self._interactive = True

    def _ensure_screen(self):
        if not self._interactive or not self.console.is_terminal or self._screen_active:
            return
        # Alternate screen + SGR mouse (same modes as the React UI) so trackpad
        # scroll arrives as parseable CSI instead of leaking into the composer.
        self.console.file.write("\x1b[?1049h\x1b[?25l" + MOUSE_REPORTING_ON)
        self.console.file.flush()
        self._screen_active = True

    def _suspend_screen(self):
        if self.console.is_terminal:
            self.console.file.write(MOUSE_REPORTING_OFF)
            self.console.file.flush()
        if not self._screen_active:
            return
        self.console.file.write("\x1b[?25h\x1b[?1049l")
        self.console.file.flush()
        self._screen_active = False

    def _transcript_lines(self, width: int) -> list[list[Segment]]:
        renderables = list(self._transcript)
        if self._stream_buffer.strip():
            renderables.append(
                Group(
                    Text("Assistant", style=f"bold {COLORS['dim']}"),
                    Markdown(self._stream_buffer),
                )
            )
        if not renderables:
            return []
        transcript = Padding(Group(*renderables), (0, 2))
        options = self.console.options.update(width=max(1, width), height=None)
        return self.console.render_lines(transcript, options, pad=False)

    def _print_screen_rows(self, lines: list[list[Segment]], row_count: int):
        max_offset = max(0, len(lines) - row_count)
        self._scroll_offset = min(max(0, self._scroll_offset), max_offset)
        end = max(0, len(lines) - self._scroll_offset)
        start = max(0, end - row_count)
        visible = lines[start:end] if row_count > 0 else []
        for line in visible:
            self.console.file.write("\x1b[2K")
            self.console.print(
                Segments([*line, Segment.line()]),
                end="",
                soft_wrap=True,
            )
        remaining = max(0, row_count - len(visible))
        if remaining:
            self.console.file.write("\x1b[2K\n" * remaining)

    def _redraw(self, input_active: bool = False):
        if not self._interactive or not self.console.is_terminal:
            return
        self._ensure_screen()
        self.console.file.write(SYNC_UPDATE_BEGIN + "\x1b[?25l\x1b[H")
        try:
            cwd = self._footer["cwd"] or os.getcwd()
            model = self._footer["model"]
            if self.console.size.width >= WIDE_BANNER_MIN_WIDTH:
                self.console.print(Padding(self._welcome_panel(cwd, model), (0, 1)))
                banner_rows = WIDE_BANNER_ROWS
            else:
                self.console.print(self._compact_banner(cwd))
                banner_rows = 4

            transcript_rows = max(
                0, self.console.size.height - banner_rows - COMPOSER_ROWS
            )
            self._print_screen_rows(
                self._transcript_lines(self.console.size.width), transcript_rows
            )
            self.console.print(self._composer_panel(input_active=input_active))
            self.console.print(self._status_line(), end="")
        finally:
            self.console.file.write(SYNC_UPDATE_END)
            self.console.file.flush()

    @staticmethod
    def _home_compressed(path: str) -> str:
        home = os.path.expanduser("~")
        if home and path.startswith(home):
            return f"~{path[len(home) :]}"
        return path or "."

    @staticmethod
    def _truncate_middle(value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        if max_length <= 5:
            return value[:max_length]
        head = (max_length - 1) // 2
        tail = max_length - head - 1
        return f"{value[:head]}~{value[-tail:]}"

    @staticmethod
    def _fit_text(value: Text, width: int, overflow: str = "ellipsis") -> Text:
        fitted = value.copy()
        fitted.truncate(max(0, width), overflow=overflow, pad=True)
        return fitted

    @classmethod
    def _split_line(cls, left: Text, right: Text, width: int) -> Text:
        available = max(1, width)
        if left.cell_len + right.cell_len > available:
            right = cls._fit_text(right, max(0, available - left.cell_len))
        gap = max(0, available - left.cell_len - right.cell_len)
        line = left.copy()
        line.append(" " * gap)
        line.append_text(right)
        return cls._fit_text(line, available, overflow="crop")

    @staticmethod
    def _quick_commands() -> list[str]:
        available = set(CommandRegistry.command_names())
        return [
            command
            for command in ("/mission", "/models", "/connect", "/skills")
            if command in available
        ]

    def _welcome_panel(self, cwd: str, model: str) -> Panel:
        terminal_width = max(20, self.console.size.width)
        panel_width = max(18, terminal_width - 2)
        content_width = max(1, panel_width - 4)
        identity_width = min(
            WELCOME_IDENTITY_WIDTH,
            max(38, int(terminal_width * 0.42)),
        )
        identity_width = min(identity_width, max(1, content_width - 25))
        detail_width = max(1, content_width - identity_width - 1)
        workspace = self._truncate_middle(
            self._home_compressed(cwd), max(18, identity_width - 4)
        )
        model_label = self._truncate_middle(
            model or "model not selected", max(18, identity_width - 4)
        )

        left_rows = [
            Text(line, style=f"bold {COLORS['accent']}") for line in TERMINUS_WORDMARK
        ]
        left_rows.append(Text())
        ready = Text("Ready to build.  ", style=f"bold {COLORS['text']}")
        ready.append(workspace, style=COLORS["muted"])
        left_rows.append(ready)

        right_rows = [
            Text(
                "WHAT ARE WE BUILDING?",
                style=f"bold {COLORS['accent_soft']}",
            ),
            Text(
                "Describe the outcome. Terminus will inspect the codebase and work through it with you.",
                style=COLORS["dim"],
            ),
        ]
        try_line = Text("Try  ", style=COLORS["muted"])
        try_line.append("Fix the failing tests", style=COLORS["text"])
        try_line.append("  ·  ", style=COLORS["border_hover"])
        try_line.append("Explain @src/agent.py", style=COLORS["text"])
        right_rows.extend((try_line, Text()))

        commands = Text("Commands  ", style=COLORS["muted"])
        for index, command in enumerate(self._quick_commands()):
            if index:
                commands.append("   ")
            commands.append(command, style=f"bold {COLORS['text']}")
        right_rows.append(commands)

        detail = Text(model_label, style=COLORS["muted"])
        detail.append("   ·   Inspect. Build. Verify.", style=COLORS["muted"])
        right_rows.extend((detail, Text()))

        body = Text()
        for row_index in range(7):
            body.append_text(
                self._fit_text(left_rows[row_index], identity_width, overflow="crop")
            )
            body.append("│", style=COLORS["border"])
            detail_row = Text("  ")
            detail_row.append_text(right_rows[row_index])
            body.append_text(
                self._fit_text(detail_row, detail_width, overflow="ellipsis")
            )
            if row_index < 6:
                body.append("\n")

        return Panel(
            body,
            box=box.SQUARE,
            border_style=COLORS["border_hover"],
            padding=(0, 1),
            width=panel_width,
            height=WIDE_BANNER_ROWS,
        )

    def _compact_banner(self, cwd: str) -> Panel:
        title = Text("TERMINUS", style=f"bold {COLORS['accent']}")
        subtitle = Text("Ready to build.  ", style=f"bold {COLORS['text']}")
        subtitle.append(self._home_compressed(cwd), style=COLORS["muted"])
        return Panel(
            Group(title, subtitle),
            box=box.SQUARE,
            border_style=COLORS["border_hover"],
            padding=(0, 1),
            width=max(18, self.console.size.width),
        )

    def _composer_panel(self, input_active: bool = False) -> Panel:
        width = max(18, self.console.size.width)
        content_width = max(1, width - 4)
        pct = float(self._footer["context_percent"])
        model = self._truncate_middle(self._footer["model"] or "no model selected", 34)
        blocks = max(0, min(8, round(pct * 8 / 100)))

        brand = Text("◈ TERMINUS", style=f"bold {COLORS['accent_soft']}")
        meta = Text(model, style=COLORS["dim"])
        meta.append("  │  ", style=COLORS["border_hover"])
        meta.append("■" * blocks + "·" * (8 - blocks), style=COLORS["accent"])
        meta.append(f" {pct:.0f}%", style=COLORS["muted"])
        header = self._split_line(brand, meta, content_width)

        prompt = Text("//  ", style=f"bold {COLORS['accent_soft']}")
        if input_active:
            prompt.append(self._input_buffer, style=COLORS["text"])
        prompt.append("▌" if input_active else "▏", style=COLORS["accent"])
        prompt = self._fit_text(prompt, content_width, overflow="crop")
        return Panel(
            Group(header, prompt),
            box=box.SQUARE,
            border_style=COLORS["accent"],
            padding=(0, 1),
            width=width,
            height=4,
        )

    def _status_line(self) -> Text:
        width = max(1, self.console.size.width - 2)
        if self._generation_active:
            status = Text("◆", style=COLORS["accent_soft"])
            status.append(" processing", style=COLORS["muted"])
        else:
            status = Text("◆", style=COLORS["success"])
            status.append(" ready", style=COLORS["muted"])
        line = Text(" " * max(0, width - status.cell_len))
        line.append_text(status)
        return line

    def render_banner(self):
        self._welcome_pending = True
        if self._interactive and self.console.is_terminal:
            return
        cwd = self._footer["cwd"] or os.getcwd()
        if self.console.size.width >= WIDE_BANNER_MIN_WIDTH:
            self.console.print(
                Padding(
                    self._welcome_panel(cwd, self._footer["model"]),
                    (0, 1),
                )
            )
        else:
            self.console.print(self._compact_banner(cwd))

    def get_user_input(self, model=None, context_size=None, model_context_size=None):
        self._last_input_was_silent = False
        if self._queued_input:
            self._last_input_was_silent = (
                self._queued_input_silent.popleft()
                if self._queued_input_silent
                else False
            )
            return self._queued_input.popleft()
        if model is not None:
            self.render_footer(
                cwd=os.getcwd(),
                model=model,
                context_size=context_size or 0,
                model_context_size=model_context_size or 0,
            )
        self._interactive = True
        self._welcome_pending = False
        if not self.console.is_terminal:
            return input("//  ")

        self._input_buffer = ""

        def update_input(value: str) -> None:
            self._input_buffer = value
            self._redraw(input_active=True)

        def update_scroll(delta: int) -> None:
            self._scroll_offset = max(0, self._scroll_offset + delta)
            self._redraw(input_active=True)

        try:
            value = read_terminal_line(
                on_change=update_input,
                on_scroll=update_scroll,
            )
        finally:
            self._input_buffer = ""
            self._scroll_offset = 0
            self._redraw(input_active=False)
        return value

    def consume_last_input_was_silent(self) -> bool:
        """Whether the last get_user_input value was already shown in the transcript."""
        silent = self._last_input_was_silent
        self._last_input_was_silent = False
        return silent

    def _ask_line(self, prompt_text: str, password: bool = False) -> str:
        """Line prompt for menus/selectors; empty input returns ''."""
        if password:
            return Prompt.ask(prompt_text, password=True)
        self.console.print(Text(f"{prompt_text} ", style=COLORS["muted"]), end="")
        return read_terminal_line()

    def _print_footer(self):
        cwd = self._footer["cwd"]
        model = self._footer["model"]
        pct = self._footer["context_percent"]
        if not cwd and not model:
            return
        footer = Text()
        first = True
        if cwd:
            footer.append(cwd, style=f"bold {COLORS['subtle']}")
            first = False
        if model:
            if not first:
                footer.append("  ·  ", style=COLORS["muted"])
            footer.append(model, style=COLORS["muted"])
            first = False
        if pct > 0:
            if not first:
                footer.append("  ·  ", style=COLORS["muted"])
            bar, color = create_progress_bar(pct)
            footer.append(f"{bar} {pct:.0f}%", style=color)
        self.console.print(footer)

    def render_footer(
        self, cwd: str, model: str, context_size: int, model_context_size: int
    ):
        pct = (context_size / model_context_size) * 100 if model_context_size else 0.0
        self._footer = {"cwd": cwd, "model": model, "context_percent": pct}

    def print_message(self, message: str, style: str = ""):
        clean = self._clean_text(message)
        if not clean.strip():
            return
        self._emit(clean, markup=True, style=style or None)

    def print_centered(self, message: str, style: str = ""):
        self.print_message(message, style)

    def print_newline(self):
        self._emit("")

    def render_response(self, content: str):
        content = self._clean_text(content)
        if not content.strip():
            return
        self._emit(
            Padding(
                Group(
                    Text("Assistant", style=f"bold {COLORS['dim']}"),
                    Markdown(content),
                ),
                TRANSCRIPT_BLOCK_PADDING,
            )
        )

    def render_user_message(self, content: str):
        content = self._clean_text(content)
        if not content.strip():
            return
        tag = "command" if content.lstrip().startswith("/") else "user"
        label = "Command" if tag == "command" else "You"
        color = COLORS["accent_alt"] if tag == "command" else COLORS["accent_soft"]
        self._emit(
            Padding(
                Group(
                    Text(label, style=f"bold {color}"),
                    Text(content, style=COLORS["text"]),
                ),
                TRANSCRIPT_BLOCK_PADDING,
            )
        )

    def render_thinking(
        self, content: str, message: ThinkingMessage | None = None
    ) -> ThinkingMessage:
        """Add or update one visible reasoning entry in the transcript."""
        bounded = self._bounded_text(content)
        if self._board is not None and self._board.is_live():
            if message is None:
                message = ThinkingMessage(bounded)
            else:
                message.content = bounded
            self._board.thinking_update(bounded)
            return message
        if message is None:
            message = ThinkingMessage(bounded)
            self._emit(message)
        else:
            message.content = bounded
            if self._interactive and self.console.is_terminal:
                self._redraw()
        return message

    def clear_thinking(self):
        if self._board is not None:
            self._board.thinking_clear()

    def render_error(self, error_message: str):
        self._emit(
            Panel(
                escape(self._bounded_text(error_message)),
                title="ERROR",
                border_style=COLORS["danger"],
            ),
            markup=False,
        )

    def render_success_message(self, message: str):
        self._emit(Text(f"✓ {message}", style=COLORS["success"]))

    def clear_screen(self):
        self._transcript.clear()
        self._stream_buffer = ""
        if self._interactive and self.console.is_terminal:
            self._redraw()
        else:
            self.console.clear()

    def get_role_color(self, role: str) -> str:
        return get_role_color(role)

    # ------------------------------------------------------------------ #
    # Streaming
    # ------------------------------------------------------------------ #

    def send_stream_chunk(self, chunk: str):
        chunk = self._clean_text(chunk)
        if not chunk:
            return
        if self._board is not None:
            self._board.stream_append(chunk)
            return
        if self._interactive and self.console.is_terminal:
            self._stream_buffer += chunk
            now = time.monotonic()
            if now - self._last_stream_refresh >= 0.08:
                self._last_stream_refresh = now
                self._redraw()
            return
        self.console.print(chunk, end="", markup=False, soft_wrap=True)

    def send_stream_end(self, content: str):
        content = self._clean_text(content)
        if self._suppress_next_response:
            self._suppress_next_response = False
            self._stream_buffer = ""
            if self._board is not None:
                self._board.stream = ""
            elif self._interactive and self.console.is_terminal:
                self._redraw()
            return
        if self._board is not None:
            self._board.stream_finish(content)
            return
        if self._interactive and self.console.is_terminal:
            self._stream_buffer = ""
            if content.strip():
                self.render_response(content)
            else:
                self._redraw()
            return
        if not content.strip():
            return
        self.console.print("")
        self.render_response(content)

    # ------------------------------------------------------------------ #
    # Tool events
    # ------------------------------------------------------------------ #

    def send_tool_call(self, tool_name: str, label: str, args: dict):
        is_question_tool = tool_name == "ask_question"
        if self._board is not None:
            self._board.tool_call(tool_name, label)
        else:
            self._emit(
                Text(f"▸ {tool_name} · {label}", style=f"bold {COLORS['warning']}")
            )
            # Question content is rendered as an in-chat block; skip raw args dump.
            if not is_question_tool:
                preview = self._args_preview(args)
                if preview:
                    self._emit(
                        Text(f"  args: {preview}", style=COLORS["subtle"]),
                        markup=False,
                    )
        if is_question_tool:
            self._ask_questions(args)

    def send_tool_output(self, tool_name: str, output: str):
        if self._board is not None:
            self._board.tool_output(tool_name, output)
            return
        # ask_question already presents the full prompt + answer in-chat.
        if tool_name == "ask_question":
            return
        preview = self._preview_text(str(output))
        if preview:
            self._emit(Text(f"  ↳ {preview}", style=COLORS["subtle"]), markup=False)

    # ------------------------------------------------------------------ #
    # Question prompt (ask_question tool)
    # ------------------------------------------------------------------ #

    def send_question_request(self, args: dict):
        self._ask_questions(args)

    def _ask_questions(self, args: dict):
        """Present clarifying questions in the chat transcript and collect answers.

        Stays inside the interactive UI (no alternate-screen suspend / modal).
        Answers are queued so the next agent turn receives them as user input.
        """
        questions = self._normalize_question_request(args.get("questions") or [])
        if not questions:
            return

        answers: list[str] = []
        board_live = self._board is not None and self._board.is_live()
        if board_live:
            self._board.pause()

        prev_generation = self._generation_active
        self._generation_active = False
        try:
            total = len(questions)
            for index, question in enumerate(questions, start=1):
                self._render_question_block(index, question, total)
                options = question["options"]
                if question["allowMultiple"]:
                    raw = self._ask_in_chat(
                        "Select options (comma-separated numbers, Enter = all)"
                    )
                    picked = self._parse_option_numbers(raw, options)
                    answer = "; ".join(picked) if picked else "; ".join(options)
                else:
                    raw = self._ask_in_chat("Select (number, Enter = 1)")
                    picked = self._parse_option_numbers(raw, options)
                    answer = picked[0] if picked else options[0]
                answers.append(answer)
                self._render_question_selection(answer)
        finally:
            self._generation_active = prev_generation
            if board_live and self._board is not None:
                self._board.resume()

        self._suppress_next_response = True
        self._queued_input.append(
            "\n".join(
                f"{index}. {answer}" for index, answer in enumerate(answers, start=1)
            )
        )
        self._queued_input_silent.append(True)

    def _render_question_block(
        self, index: int, question: dict, total: int
    ) -> None:
        title = f"Question {index}" if total == 1 else f"Question {index}/{total}"
        body = Text()
        body.append(self._clean_text(question["text"]), style=COLORS["text"])
        mode = (
            "select one or more"
            if question.get("allowMultiple")
            else "select one"
        )
        body.append(f"  ·  {mode}", style=f"italic {COLORS['muted']}")
        body.append("\n")
        for option_index, option in enumerate(question["options"], start=1):
            body.append(f"\n  {option_index}. ", style=COLORS["muted"])
            body.append(self._clean_text(option), style=COLORS["text"])

        renderable = Padding(
            Group(
                Text(title, style=f"bold {COLORS['warning']}"),
                body,
            ),
            TRANSCRIPT_BLOCK_PADDING,
        )
        # Mission board owns the terminal; print on the plain console while paused.
        if self._board is not None:
            self.console.print(renderable)
        else:
            self._emit(renderable)

    def _render_question_selection(self, answer: str) -> None:
        renderable = Padding(
            Group(
                Text("You", style=f"bold {COLORS['accent_soft']}"),
                Text(self._clean_text(answer), style=COLORS["text"]),
            ),
            TRANSCRIPT_BLOCK_PADDING,
        )
        if self._board is not None:
            self.console.print(renderable)
        else:
            self._emit(renderable)

    def _ask_in_chat(self, prompt_text: str) -> str:
        """Collect a selection via the normal composer, keeping the chat UI up."""
        hint = self._clean_text(prompt_text)
        if self._board is not None:
            # Mission board owns the screen; fall back to a simple line prompt.
            self.console.print(Text(f"{hint} ", style=COLORS["muted"]), end="")
            return read_terminal_line()

        if self._interactive and self.console.is_terminal:
            self._emit(Text(hint, style=COLORS["muted"]))
            self._input_buffer = ""

            def update_input(value: str) -> None:
                self._input_buffer = value
                self._redraw(input_active=True)

            def update_scroll(delta: int) -> None:
                self._scroll_offset = max(0, self._scroll_offset + delta)
                self._redraw(input_active=True)

            try:
                self._redraw(input_active=True)
                return read_terminal_line(
                    on_change=update_input,
                    on_scroll=update_scroll,
                )
            finally:
                self._input_buffer = ""
                self._scroll_offset = 0
                self._redraw(input_active=False)

        self.console.print(Text(f"{hint} ", style=COLORS["muted"]), end="")
        return read_terminal_line()

    @staticmethod
    def _parse_option_numbers(raw: str, options: list[str]) -> list[str]:
        picked = []
        for token in re.split(r"[,\s]+", raw.strip()):
            if not token.isdigit():
                continue
            index = int(token)
            if 1 <= index <= len(options):
                picked.append(options[index - 1])
        return picked

    def _normalize_question_request(self, questions: list) -> list[dict]:
        return [self._normalize_question(question) for question in questions]

    def _normalize_question(self, question) -> dict:
        if isinstance(question, dict):
            return {
                "text": str(
                    question.get("text")
                    or question.get("question")
                    or "Please clarify your preference."
                ).strip(),
                "options": self._normalize_question_options(question.get("options")),
                "allowMultiple": bool(
                    question.get("allow_multiple", question.get("allowMultiple", False))
                ),
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

    # ------------------------------------------------------------------ #
    # Mission Control
    # ------------------------------------------------------------------ #

    def mission_start(
        self,
        title: str = "mission",
        goal: str = "",
        phase: str = "brief",
        mission_id: str | None = None,
    ):
        self._suspend_screen()
        # Prefer a short title derived from the goal when the generic default is used.
        resolved_title = (title or "mission").strip() or "mission"
        resolved_goal = (goal or "").strip()
        if resolved_title.lower() == "mission" and resolved_goal:
            resolved_title = (
                self._preview_text(resolved_goal, max_chars=48) or "mission"
            )
        self._board = MissionBoard(
            self.console,
            resolved_title,
            resolved_goal or resolved_title,
            phase,
            mission_id=mission_id,
        )
        self._board.start()

    def mission_phase(self, phase: str):
        if self._board is not None:
            self._board.set_phase(phase)

    def mission_end(
        self,
        summary: str = "",
        stats: dict | None = None,
        status: str = "completed",
    ):
        if self._board is None:
            return
        board_stats = self._board.stats_snapshot()
        if stats:
            board_stats.update({k: v for k, v in stats.items() if v is not None})
        debrief = self._bounded_text(summary or "")
        self._board.finish(summary=debrief, stats=board_stats, status=status)
        self._board = None

    def handle_mission_event(self, event):
        """Reduce one persisted typed mission event into the active board."""
        if self._board is None or self._board.mission_id != event.mission_id:
            return False
        payload = event.payload
        if event.event_type == "mission_transition":
            self._board.set_phase(payload.get("phase", self._board.phase))
        elif event.event_type == "task_spawned":
            self._board.spawn(
                event.task_id,
                payload.get("title", event.task_id),
                payload.get("instructions", ""),
                payload.get("role", "worker"),
            )
        elif event.event_type == "task_status":
            self._board.status(event.task_id, payload.get("status", "running"))
        elif event.event_type == "task_result":
            status = payload.get("status", "failed")
            summary = payload.get("summary") or payload.get("error") or ""
            self._board.notify(event.task_id, status, summary)
            self._board.status(event.task_id, status, result=summary)
        return True

    def send_worker_spawned(
        self, worker_id: str, name: str, description: str, role: str | None = None
    ):
        if self._board is not None:
            self._board.spawn(worker_id, name, description, role or "worker")
        else:
            self.print_message(
                f"worker {name} ({role or 'worker'}) spawned: {self._preview_text(description)}"
            )

    def send_worker_notification(
        self,
        worker_id: str,
        status: str,
        summary: str,
        final_response: str | None = None,
        timestamp: float | None = None,
    ):
        if self._board is not None:
            self._board.notify(worker_id, status, summary)
        else:
            self.print_message(f"[{status}] {summary}")

    def send_worker_status(
        self,
        worker_id: str,
        status: str,
        result: str | None = None,
        result_envelope: dict | None = None,
        timestamp: float | None = None,
    ):
        if self._board is not None:
            self._board.status(worker_id, status, result=result)
        else:
            self.print_message(f"worker {worker_id}: {status}")

    def send_worker_detail(
        self,
        worker_id: str,
        detail_type: str,
        content: str,
        tool_name: str | None = None,
        args: dict | None = None,
        timestamp: float | None = None,
    ):
        if self._board is not None:
            self._board.detail(worker_id, detail_type, content, tool_name=tool_name)
        else:
            self.print_message(self._preview_text(content))

    # ------------------------------------------------------------------ #
    # Panels / menus
    # ------------------------------------------------------------------ #

    def render_help(self):
        table = Table(
            title="Available Commands", border_style=COLORS["border"], expand=True
        )
        table.add_column("Command", style="bold", no_wrap=True)
        table.add_column("Usage", style=COLORS["muted"], no_wrap=True)
        table.add_column("Description", style=COLORS["text"], overflow="ellipsis")
        for command in CommandRegistry.all():
            table.add_row(command.name, command.usage or "", command.description or "")
        self._emit(table)

    def render_skills(self, skills: list):
        if not skills:
            self.print_message("No skills found in .skills/ directory.")
            return
        table = Table(
            title="Available Skills", border_style=COLORS["border"], expand=True
        )
        table.add_column("Skill", style="bold", no_wrap=True)
        table.add_column("Description", style=COLORS["text"], overflow="ellipsis")
        table.add_column("Trigger", style=COLORS["muted"], overflow="ellipsis")
        for skill in skills:
            name = skill.get("name", "unknown")
            if skill.get("loaded"):
                name += " [loaded]"
            table.add_row(
                name, skill.get("description", "") or "", skill.get("trigger", "") or ""
            )
        self._emit(table)
        self.print_message("[dim]Use /skill <name> to load a skill.[/dim]")

    def render_history(self, history_lines: list):
        for line in history_lines:
            self.print_message(line)

    def render_todo_panel(self, todos: list, handler=None):
        if handler is not None:
            handler.update_todo_display(todos)
        if not todos:
            return
        todos_text = Text()
        todos_text.append("  todos:", style=f"bold {COLORS['subtle']}")
        for item in todos:
            status = item.get("status", "pending")
            task = item.get("task", "")
            if status == "completed":
                marker = "✓"
                marker_style = COLORS["success"]
            elif status == "in_progress":
                marker = "◐"
                marker_style = COLORS["warning"]
            else:
                marker = "○"
                marker_style = COLORS["subtle"]
            todos_text.append("\n    ")
            todos_text.append(marker, style=marker_style)
            todos_text.append(f" {task}", style=COLORS["text"])
        self._emit(todos_text)

    # ------------------------------------------------------------------ #
    # Interactive selectors (blocking, like the React selectors)
    # ------------------------------------------------------------------ #

    def select_model_ui(self, current_model: str = None):
        self._suspend_screen()
        table = Table(title="Available Models", border_style=COLORS["border"])
        table.add_column("#", style="dim", no_wrap=True)
        table.add_column("Model", style="bold", no_wrap=True)
        table.add_column("Provider", style=COLORS["muted"], no_wrap=True)
        table.add_column("Context", style=COLORS["muted"], no_wrap=True)
        table.add_column(
            "$/1M in", style=COLORS["muted"], justify="right", no_wrap=True
        )
        table.add_column(
            "$/1M out", style=COLORS["muted"], justify="right", no_wrap=True
        )
        models = []
        for model in available_models:
            inst = model() if isinstance(model, type) else model
            models.append(inst)
            marker = " ◀" if inst.name == current_model else ""
            table.add_row(
                str(len(models)),
                inst.name + marker,
                inst.provider,
                f"{inst.context_size // 1024}K",
                f"{inst.input_tokens_pricing:.2f}",
                f"{inst.output_tokens_pricing:.2f}",
            )
        self.console.print(table)
        raw = self._ask_line("Select model (number, Enter = keep current, q = cancel)")
        if (
            not raw.strip()
            or raw.strip().lower() in ("q", "cancel", "quit")
            or not raw.strip().isdigit()
        ):
            return None
        index = int(raw.strip())
        if 1 <= index <= len(models):
            return models[index - 1]
        return None

    def select_skill_ui(self, skills: list):
        self._suspend_screen()
        table = Table(title="Available Skills", border_style=COLORS["border"])
        table.add_column("#", style="dim", no_wrap=True)
        table.add_column("Skill", style="bold", no_wrap=True)
        table.add_column("Description", style=COLORS["text"], overflow="ellipsis")
        for index, skill in enumerate(skills, start=1):
            name = skill.get("name", "unknown")
            if skill.get("loaded"):
                name += " [loaded]"
            table.add_row(str(index), name, skill.get("description", "") or "")
        self.console.print(table)
        raw = self._ask_line("Select skill (number, Enter = cancel)")
        if not raw.strip() or not raw.strip().isdigit():
            return None
        index = int(raw.strip())
        if 1 <= index <= len(skills):
            return skills[index - 1]
        return None

    def connect_provider_ui(self) -> tuple[str, str] | None:
        self._suspend_screen()
        providers = ["openrouter"]
        self.console.print(
            Panel(
                Text(
                    "Connect an LLM provider to configure its API key.",
                    style=COLORS["text"],
                ),
                title="Provider Setup",
                border_style=COLORS["accent"],
            ),
            markup=False,
        )
        for index, name in enumerate(providers, start=1):
            self.console.print(
                Text(f"  {index}. {name}", style=COLORS["text"]), markup=False
            )
        raw = self._ask_line("Select provider (number, Enter = cancel)")
        if not raw.strip().isdigit():
            return None
        index = int(raw.strip())
        if not 1 <= index <= len(providers):
            return None
        provider_name = providers[index - 1]
        api_key = Prompt.ask("Enter API key", password=True)
        if not api_key.strip():
            return None
        return provider_name, api_key.strip()

    # ------------------------------------------------------------------ #
    # Turn lifecycle
    # ------------------------------------------------------------------ #

    def generation_start(self):
        self._generation_active = True
        self._stream_buffer = ""
        # Avoid clobbering the Mission Control Live alternate screen.
        if self._board is None:
            self._redraw()

    def generation_end(self):
        self._generation_active = False
        self._stream_buffer = ""
        if self._board is None:
            self._redraw()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def create_response_handler(self):
        return RichResponseHandler(self)

    def check_pending_exit(self) -> bool:
        return self.pending_exit

    def clear_pending_exit(self):
        self.pending_exit = False

    def shutdown(self):
        if self._board is not None:
            self._board.stop()
            self._board = None
        self._suspend_screen()


class RichResponseHandler:
    """Status and event handler mirroring `ReactResponseHandler`."""

    def __init__(self, display: RichDisplay):
        self.display = display
        self._content: list[str] = []
        self._active = False
        self._thinking_buffer: list[str] = []
        self._thinking_active = False
        self._thinking_message: ThinkingMessage | None = None

    def _flush_thinking(self):
        if self._thinking_active:
            self.display.clear_thinking()
        self._thinking_active = False
        self._thinking_buffer = []
        self._thinking_message = None

    def _pending_stream_text(self) -> str:
        if self._content:
            return "".join(self._content)
        return getattr(self.display, "_stream_buffer", "") or ""

    def _flush_stream_content(self):
        """Commit streamed assistant text into the transcript at the current point.

        Without this, tool calls / thinking land in `_transcript` immediately while
        assistant text stays in `_stream_buffer` and is always painted at the end —
        so intermediate narration dumps below later tools instead of before them.
        """
        text = self._pending_stream_text()
        if not text.strip():
            self._content = []
            if getattr(self.display, "_stream_buffer", ""):
                self.display._stream_buffer = ""
            return
        self._content = []
        self.display.send_stream_end(text)

    def __enter__(self):
        self._active = True
        self._content = []
        self._thinking_active = False
        self._thinking_buffer = []
        self._thinking_message = None
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
        self._thinking_message = None

    def stop(self):
        self._flush_thinking()
        self._active = False

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
            self._flush_stream_content()
            self.display.render_error(message)
        elif is_thinking:
            # Starting a new reasoning block — pin any prior assistant text first so
            # order is assistant → thinking → tools, not tools then a late dump.
            if not self._thinking_active:
                self._flush_stream_content()
            self._thinking_active = True
            self._thinking_buffer.append(message)
            self._thinking_message = self.display.render_thinking(
                "".join(self._thinking_buffer), self._thinking_message
            )
        else:
            self._flush_thinking()
            self._flush_stream_content()
            self.display.print_message(message)

    def display_tool_call(self, tool_name: str, label: str, args: dict):
        self._flush_thinking()
        self._flush_stream_content()
        self.display.send_tool_call(tool_name, label, args)

    def display_tool_output(self, tool_name: str, output: str):
        self.display.send_tool_output(tool_name, output)

    def handle_streaming(self, chunk: str):
        if self._active:
            self._flush_thinking()
            self._content.append(chunk)
            self.display.send_stream_chunk(chunk)

    def update_todo_display(self, todos: list):
        self.display.render_todo_panel(todos)

    def render_final_response(self, response: str):
        self._flush_thinking()
        pending = self._pending_stream_text()
        self._content = []
        if pending.strip():
            self.display.send_stream_end(pending)
        elif response and str(response).strip():
            # Non-streaming / already-flushed path: still show the final answer.
            self.display.send_stream_end(str(response))
        else:
            # Clear any empty live stream buffer so it doesn't linger on redraw.
            if getattr(self.display, "_stream_buffer", ""):
                self.display._stream_buffer = ""
                if self.display._interactive and self.display.console.is_terminal:
                    self.display._redraw()
