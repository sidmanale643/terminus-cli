"""Compact Mission Control board rendered with rich.live.Live."""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from rich import box
from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.cli.terminal import (
    MOUSE_REPORTING_OFF,
    MOUSE_REPORTING_ON,
    legacy_mouse_scroll_delta,
    terminal_scroll_delta,
)
from ui.display_text import (
    ACTIVITY_LINE_MAX,
    DETAIL_LINE_MAX,
    TOOL_OUTPUT_LINES,
    humanize_output_lines,
    humanize_text,
    one_line,
    tool_call_label,
    wrap_lines,
)
from ui.theme import COLORS

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ACTIVITY_MAX_LINES = 80
WORKER_DETAIL_LINES = 400
STREAM_MAX_CHARS = 8000
THINKING_MAX_CHARS = 400
REFRESH_INTERVAL_SECONDS = 0.1
GOAL_MAX_CHARS = 160
# Overview cards stay compact; inspector stores/shows much more.
DETAIL_PREVIEW = 220
INSPECTOR_DETAIL_MAX = DETAIL_LINE_MAX

MISSION_PHASES = (
    "brief",
    "scouting",
    "planning",
    "executing",
    "integrating",
    "verifying",
    "repairing",
    "terminal",
)

PIPELINE_PHASES = (
    ("scout", "scouting"),
    ("plan", "planning"),
    ("execute", "executing"),
    ("integrate", "integrating"),
    ("verify", "verifying"),
    ("repair", "repairing"),
)

STATUS_LABELS = {
    "spawned": "queued",
    "running": "running",
    "completed": "done",
    "succeeded": "done",
    "failed": "failed",
    "stopped": "stopped",
    "blocked": "blocked",
    "cancelled": "cancelled",
}

STATUS_STYLES = {
    "spawned": COLORS["muted"],
    "running": COLORS["warning"],
    "completed": COLORS["success"],
    "succeeded": COLORS["success"],
    "failed": COLORS["danger"],
    "stopped": COLORS["accent"],
    "blocked": COLORS["warning"],
    "cancelled": COLORS["muted"],
}

STATUS_MARKS = {
    "spawned": "○",
    "running": "◆",
    "completed": "✔",
    "succeeded": "✔",
    "failed": "✘",
    "stopped": "■",
    "blocked": "!",
    "cancelled": "■",
}

ROLE_STYLES = {
    "scout": COLORS["warning"],
    "explorer": COLORS["warning"],
    "worker": COLORS["accent"],
    "implementer": COLORS["accent"],
    "verifier": COLORS["success"],
    "summarizer": COLORS["dim"],
    "agent": COLORS["text"],
}

ROLE_GLYPHS = {
    "scout": "⌕",
    "worker": "✎",
    "verifier": "◎",
    "summarizer": "≡",
    "agent": "·",
}

ROLE_LABELS = {
    "explorer": "SCOUT",
    "implementer": "WORKER",
    "verifier": "VERIFY",
    "summarizer": "SUMMARY",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _compact(value: str, max_length: int) -> str:
    """Single-line ellipsize for overview chrome (cards, feed previews)."""
    return one_line(
        humanize_text(value or "", max_chars=max(max_length * 4, 400)), max_length
    )


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _role_style(role: str) -> str:
    return ROLE_STYLES.get((role or "worker").lower(), COLORS["text"])


def _role_glyph(role: str) -> str:
    return ROLE_GLYPHS.get((role or "worker").lower(), "·")


def _status_mark(status: str) -> str:
    return STATUS_MARKS.get(status, "○")


def _status_style(status: str) -> str:
    return STATUS_STYLES.get(status, COLORS["muted"])


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status or "unknown")


def _is_terminal_status(status: str) -> bool:
    return status in (
        "completed",
        "succeeded",
        "failed",
        "stopped",
        "blocked",
        "cancelled",
    )


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


@dataclass
class WorkerState:
    worker_id: str
    name: str
    role: str = "worker"
    status: str = "spawned"
    description: str = ""
    summary: str = ""
    result: str = ""
    result_data: dict = field(default_factory=dict)
    details: deque = field(default_factory=lambda: deque(maxlen=WORKER_DETAIL_LINES))
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def mark_status(self, status: str) -> None:
        self.status = status or self.status
        if _is_terminal_status(self.status) and self.finished_at is None:
            self.finished_at = time.time()
        elif not _is_terminal_status(self.status):
            self.finished_at = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)


# --------------------------------------------------------------------------- #
# Board
# --------------------------------------------------------------------------- #


class MissionBoard:
    """Live full-screen theater for Mission Control."""

    def __init__(
        self, console, title: str, goal: str, phase: str, mission_id: str | None = None
    ):
        self.console = console
        self.title = (title or "mission").strip() or "mission"
        self.goal = (goal or title or "mission").strip() or "mission"
        self.phase = (phase or "brief").strip().lower() or "brief"
        self.mission_id = mission_id
        self.started_at = time.time()
        self.tool_calls = 0
        self.workers: dict[str, WorkerState] = {}
        self.selected_worker_id: str | None = None
        self.inspector_open = False
        self.activity: deque[tuple[str, str, str]] = deque(maxlen=ACTIVITY_MAX_LINES)
        self.stream = ""
        self.thinking = ""
        self.activity_expanded = False
        # Rows of older feed/inspector content held above the live edge.
        # Without capturing wheel events the terminal scrolls the primary
        # buffer underneath Live's alternate screen ("back to homepage").
        self._scroll_offset = 0
        self._last_refresh = 0.0
        self._finished = False
        self._paused = False
        self._input_stop = threading.Event()
        self._input_thread: threading.Thread | None = None
        self._live = Live(
            self._render(),
            console=console,
            screen=console.is_terminal,
            auto_refresh=False,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def is_live(self) -> bool:
        return self._live.is_started

    def start(self):
        self._live.start()
        self._start_input_listener()

    def _stop_live(self):
        if self._live.is_started:
            self._live.stop()

    def stop(self):
        self._stop_input_listener()
        self._stop_live()

    def stats_snapshot(self) -> dict:
        workers = list(self.workers.values())
        done = sum(1 for w in workers if w.status in ("completed", "succeeded"))
        failed = sum(1 for w in workers if w.status == "failed")
        running = sum(1 for w in workers if w.status == "running")
        return {
            "workers": len(workers),
            "done": done,
            "failed": failed,
            "running": running,
            "tool_calls": self.tool_calls,
            "durationMs": int((time.time() - self.started_at) * 1000),
            "phase": self.phase,
        }

    def finish(
        self,
        summary: str = "",
        stats: dict | None = None,
        status: str = "completed",
    ):
        self._finished = True
        self._paused = False
        self._stop_input_listener()
        self._stop_live()
        if not self.console.is_terminal:
            return

        snapshot = self.stats_snapshot()
        if stats:
            snapshot.update({k: v for k, v in stats.items() if v is not None})

        titles = {
            "completed": ("MISSION COMPLETE", COLORS["success"]),
            "failed": ("MISSION FAILED", COLORS["danger"]),
            "blocked": ("MISSION BLOCKED", COLORS["warning"]),
            "cancelled": ("MISSION CANCELLED", COLORS["muted"]),
            "interrupted": ("MISSION INTERRUPTED", COLORS["warning"]),
        }
        label, terminal_style = titles.get(status, ("MISSION ENDED", COLORS["muted"]))
        header = Text()
        header.append(label, style=f"bold {terminal_style}")
        goal_preview = _compact(self.goal, 48)
        if goal_preview:
            header.append("  ·  ", style=COLORS["muted"])
            header.append(goal_preview, style=COLORS["text"])

        meta = Text()
        meta.append(f"{snapshot.get('workers', 0)} workers", style=COLORS["dim"])
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(
            f"{snapshot.get('done', 0)} done",
            style=COLORS["success"],
        )
        if snapshot.get("failed"):
            meta.append("  ·  ", style=COLORS["muted"])
            meta.append(f"{snapshot['failed']} failed", style=COLORS["danger"])
        duration_ms = snapshot.get("durationMs")
        if duration_ms is not None:
            meta.append("  ·  ", style=COLORS["muted"])
            meta.append(_format_elapsed(duration_ms / 1000), style=COLORS["muted"])
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(
            f"{snapshot.get('tool_calls', self.tool_calls)} tools",
            style=COLORS["muted"],
        )

        body_parts: list[RenderableType] = [meta]
        debrief = (summary or "").strip()
        if debrief and debrief != self.goal.strip():
            body_parts.append(Text(""))
            body_parts.append(Text(debrief, style=COLORS["text"]))
        elif self.goal:
            body_parts.append(Text(""))
            body_parts.append(Text(self.goal, style=COLORS["dim"]))

        # Compact worker recap
        if self.workers:
            body_parts.append(Text(""))
            for worker in self.workers.values():
                line = Text()
                line.append(
                    f"  {_status_mark(worker.status)} ",
                    style=_status_style(worker.status),
                )
                line.append(
                    f"{worker.role.upper():<12}",
                    style=f"bold {_role_style(worker.role)}",
                )
                line.append(
                    _compact(worker.summary or worker.description or worker.name, 64),
                    style=COLORS["dim"],
                )
                body_parts.append(line)

        self.console.print(
            Panel(
                Group(*body_parts),
                title=header,
                title_align="left",
                border_style=terminal_style,
                box=box.SQUARE,
                padding=(1, 2),
            )
        )

    def set_phase(self, phase: str):
        self.phase = (phase or self.phase).strip().lower() or self.phase
        self._refresh(force=True)

    def pause(self):
        """Suspend the live display so a prompt can take over the terminal."""
        if not self._finished:
            self._paused = True
            self._stop_input_listener()
            self._stop_live()

    def resume(self):
        if self._paused and not self._finished:
            self._paused = False
            self._live = Live(
                self._render(),
                console=self.console,
                screen=self.console.is_terminal,
                auto_refresh=False,
            )
            self._live.start()
            self._start_input_listener()

    def handle_key(self, key: str) -> bool:
        """Open and navigate worker inspectors using single-key controls."""
        workers = list(self.workers.values())
        if not workers:
            return False
        if key.isdigit() and key != "0":
            index = int(key) - 1
            if index >= len(workers):
                return False
            self.selected_worker_id = workers[index].worker_id
            self.inspector_open = True
            self._scroll_offset = 0
        elif key == "l" and not self.inspector_open:
            self.activity_expanded = not self.activity_expanded
        elif key in ("\t", "j", "l"):
            self._move_selection(1)
            self.inspector_open = True
            self._scroll_offset = 0
        elif key in ("k", "h"):
            self._move_selection(-1)
            self.inspector_open = True
            self._scroll_offset = 0
        elif key in ("o", "\r", "\n"):
            if self.selected_worker_id not in self.workers:
                self.selected_worker_id = workers[0].worker_id
            self.inspector_open = True
            self._scroll_offset = 0
        elif key in ("\x1b", "q") and self.inspector_open:
            self.inspector_open = False
            self._scroll_offset = 0
        else:
            return False
        self._refresh(force=True)
        return True

    def handle_scroll(self, delta: int) -> bool:
        """Scroll the activity feed or open inspector; swallow terminal wheel events.

        Positive delta scrolls into older content; negative returns toward the
        live edge. Capturing the wheel is required so the terminal does not
        scroll Live's alternate screen away and reveal the homepage.
        """
        if not delta:
            return False
        self._scroll_offset = max(0, self._scroll_offset + delta)
        self._refresh(force=True)
        return True

    def _move_selection(self, delta: int) -> None:
        ids = list(self.workers)
        if not ids:
            return
        try:
            current = ids.index(self.selected_worker_id)
        except ValueError:
            current = -1 if delta > 0 else 0
        self.selected_worker_id = ids[(current + delta) % len(ids)]

    def _start_input_listener(self) -> None:
        if (
            self._finished
            or self._paused
            or not self.console.is_terminal
            or not sys.stdin.isatty()
            or sys.platform == "win32"
            or (self._input_thread and self._input_thread.is_alive())
        ):
            return
        self._input_stop.clear()
        self._input_thread = threading.Thread(
            target=self._input_loop,
            name="mission-worker-navigation",
            daemon=True,
        )
        self._input_thread.start()

    def _stop_input_listener(self) -> None:
        self._input_stop.set()
        thread = self._input_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.3)
        self._input_thread = None

    def _input_loop(self) -> None:
        """Keyboard + mouse listener for Mission Control navigation.

        Enables SGR mouse reporting so trackpad/wheel events arrive as CSI
        sequences we can consume. Without this, the terminal scrolls the
        primary buffer under Live's alternate screen and the UI appears to
        jump back to the Terminus homepage.
        """
        import os
        import select
        import termios
        import time

        input_fd = sys.stdin.fileno()
        output = sys.stdout
        try:
            original = termios.tcgetattr(input_fd)
        except termios.error:
            return

        attributes = termios.tcgetattr(input_fd)
        attributes[3] &= ~(termios.ICANON | termios.ECHO)
        attributes[6][termios.VMIN] = 1
        attributes[6][termios.VTIME] = 0

        def read_bytes(count: int, timeout: float = 0.05) -> bytes:
            collected = bytearray()
            deadline = time.monotonic() + timeout
            while len(collected) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if not select.select([input_fd], [], [], remaining)[0]:
                    break
                chunk = os.read(input_fd, count - len(collected))
                if not chunk:
                    break
                collected.extend(chunk)
            return bytes(collected)

        def consume_escape_sequence() -> bytes:
            """Read a full CSI/SS3/OSC sequence (same contract as read_terminal_line)."""
            sequence = bytearray()
            deadline = time.monotonic() + 0.05
            while len(sequence) < 128:
                remaining = deadline - time.monotonic()
                if (
                    remaining <= 0
                    or not select.select([input_fd], [], [], remaining)[0]
                ):
                    return bytes(sequence)
                byte = os.read(input_fd, 1)
                if not byte:
                    return bytes(sequence)
                sequence.extend(byte)
                first = sequence[0]
                last = sequence[-1]
                if first == ord("["):
                    if len(sequence) == 1:
                        # Longer window for SGR mouse frames (``[<btn;x;yM``).
                        deadline = time.monotonic() + 0.12
                    if len(sequence) > 1 and 0x40 <= last <= 0x7E:
                        return bytes(sequence)
                    continue
                if first == ord("O") and len(sequence) >= 2:
                    return bytes(sequence)
                if first == ord("]") and (last == 0x07 or sequence.endswith(b"\x1b\\")):
                    return bytes(sequence)
                if first not in (ord("["), ord("O"), ord("]")):
                    return bytes(sequence)
            return bytes(sequence)

        try:
            termios.tcsetattr(input_fd, termios.TCSADRAIN, attributes)
            output.write(MOUSE_REPORTING_ON)
            output.flush()
            while not self._input_stop.is_set():
                if not select.select([input_fd], [], [], 0.1)[0]:
                    continue
                raw = os.read(input_fd, 1)
                if not raw:
                    return
                if raw == b"\x1b":
                    sequence = consume_escape_sequence()
                    # Legacy X10 mouse: ESC [ M Cb Cx Cy
                    if sequence == b"[M":
                        payload = read_bytes(3, timeout=0.12)
                        self.handle_scroll(legacy_mouse_scroll_delta(payload))
                        continue
                    # Arrow keys navigate workers; page up/down + wheel scroll.
                    arrows = {
                        b"[A": "k",
                        b"OA": "k",
                        b"[B": "j",
                        b"OB": "j",
                        b"[C": "l",
                        b"OC": "l",
                        b"[D": "h",
                        b"OD": "h",
                    }
                    if sequence in arrows:
                        self.handle_key(arrows[sequence])
                        continue
                    delta = terminal_scroll_delta(sequence)
                    if delta:
                        self.handle_scroll(delta)
                        continue
                    # Bare Esc closes the inspector; other CSI (clicks) is swallowed.
                    if not sequence:
                        self.handle_key("\x1b")
                    continue
                try:
                    key = raw.decode(sys.stdin.encoding or "utf-8")
                except UnicodeDecodeError:
                    continue
                # Drop leftover printable fragments from partial mouse frames.
                if key in "Mm<>;":
                    continue
                self.handle_key(key)
        finally:
            try:
                output.write(MOUSE_REPORTING_OFF)
                output.flush()
            except OSError:
                pass
            try:
                termios.tcsetattr(input_fd, termios.TCSADRAIN, original)
            except termios.error:
                pass

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def _refresh(self, force: bool = False):
        if not self._live.is_started:
            return
        now = time.monotonic()
        should_paint = force or now - self._last_refresh >= REFRESH_INTERVAL_SECONDS
        self._live.update(self._render(), refresh=should_paint)
        if should_paint:
            self._last_refresh = now

    def _render(self) -> RenderableType:
        width = max(40, self.console.size.width)
        height = max(12, self.console.size.height)

        header = self._render_header(width)
        if self.inspector_open and self.selected_worker_id in self.workers:
            navigator = self._render_worker_navigator(width)
            inspector = self._render_worker_inspector(width, height)
            return Group(header, navigator, inspector)
        workers_panel = self._render_workers(width, height)
        feed = self._render_feed(width, height, header, workers_panel)
        footer = self._render_footer()
        return Group(header, workers_panel, feed, footer)

    def _render_header(self, width: int) -> Panel:
        elapsed = _format_elapsed(time.time() - self.started_at)
        workers = list(self.workers.values())
        total = len(workers)
        done = sum(1 for w in workers if w.status in ("completed", "succeeded"))
        failed = sum(1 for w in workers if w.status == "failed")
        meta = Text("  ")
        meta.append("terminal", style=COLORS["dim"])
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(elapsed, style=COLORS["dim"])
        if total:
            meta.append("  ·  ", style=COLORS["muted"])
            meta.append(
                f"{done}/{total}", style=COLORS["success"] if done else COLORS["dim"]
            )
            meta.append(" done", style=COLORS["muted"])
            if failed:
                meta.append("  ·  ", style=COLORS["muted"])
                meta.append(f"{failed} failed", style=COLORS["danger"])
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(f"{self.tool_calls} tools", style=COLORS["muted"])

        goal_line = Text(self.goal[:GOAL_MAX_CHARS], style=COLORS["text"])
        pipeline = self._phase_pipeline(max(20, width - 4))
        body = Group(goal_line, Text(""), pipeline, Text(""), meta)
        return Panel(
            body,
            title=Text("MISSION", style=f"bold {COLORS['accent_soft']}"),
            title_align="left",
            box=box.SQUARE,
            border_style=COLORS["border"],
            padding=(0, 1),
        )

    def _phase_pipeline(self, width: int) -> Text:
        phase_aliases = {"brief": "scouting", "execute": "executing"}
        current = phase_aliases.get(self.phase, self.phase)
        phase_values = [value for _, value in PIPELINE_PHASES]
        current_idx = phase_values.index(current) if current in phase_values else 2
        terminal = self.phase == "terminal"

        line = Text("  ")
        for index, (label, phase) in enumerate(PIPELINE_PHASES):
            if index:
                line.append("  ·  ", style=COLORS["muted"])
            if terminal or index < current_idx:
                line.append(f"{label} ✔", style=COLORS["success"])
            elif index == current_idx:
                line.append(f"{label} ▸", style=f"bold {_phase_style(phase)}")
            else:
                line.append(label, style=COLORS["muted"])

        line.truncate(max(10, width), overflow="ellipsis")
        return line

    def _render_workers(self, width: int, height: int) -> Panel:
        workers = list(self.workers.values())
        title = Text()
        title.append("WORKERS", style=f"bold {COLORS['accent_soft']}")
        if workers:
            title.append(f"  {len(workers)}", style=COLORS["dim"])
        else:
            title.append("  waiting for agents…", style=COLORS["muted"])

        border = COLORS["border"]

        if not workers:
            empty = Text()
            empty.append("  No subagents yet.  ", style=COLORS["muted"])
            empty.append(
                "The orchestrator will spawn role-focused workers as the mission unfolds.",
                style=COLORS["dim"],
            )
            return Panel(
                empty,
                title=title,
                title_align="left",
                box=box.SQUARE,
                border_style=border,
                padding=(0, 1),
                height=4,
            )

        body = self._workers_table(workers, width)
        panel_height = min(max(5, len(workers) + 4), max(5, height - 11))

        return Panel(
            body,
            title=title,
            title_align="left",
            box=box.SQUARE,
            border_style=border,
            padding=(0, 1),
            height=panel_height,
        )

    def _workers_table(self, workers: list[WorkerState], width: int) -> Table:
        table = Table(
            expand=True,
            box=box.SIMPLE_HEAD,
            show_header=True,
            show_edge=False,
            header_style=COLORS["muted"],
            pad_edge=False,
            padding=(0, 1),
        )
        table.add_column("#", width=2, no_wrap=True)
        table.add_column("ROLE", width=8, no_wrap=True)
        table.add_column("TASK", ratio=1, overflow="ellipsis", no_wrap=True)
        table.add_column("STATUS", width=8, no_wrap=True)
        table.add_column("TIME", width=5, no_wrap=True)

        for index, worker in enumerate(workers, start=1):
            status = worker.status or "spawned"
            role = (worker.role or "worker").lower()
            role_label = ROLE_LABELS.get(role, role.upper())
            role_text = Text()
            role_text.append(f"{_status_mark(status)} ", style=_status_style(status))
            role_text.append(role_label, style=f"bold {_role_style(role)}")
            table.add_row(
                str(index),
                role_text,
                _compact(worker.description or worker.name, max(16, width - 43)),
                Text(_status_label(status), style=_status_style(status)),
                Text(
                    "–"
                    if status == "spawned"
                    else _format_elapsed(worker.elapsed_seconds),
                    style=COLORS["muted"],
                ),
            )
        return table

    def _workers_stack(self, workers: list[WorkerState], width: int) -> RenderableType:
        rows: list[RenderableType] = []
        inner = max(24, width - 6)
        for index, worker in enumerate(workers, start=1):
            if index > 1:
                rows.append(Rule(style=COLORS["border"], characters="─"))
            rows.append(self._worker_card(worker, inner, index))
        return Group(*rows)

    def _workers_columns(
        self, workers: list[WorkerState], columns: int, width: int
    ) -> RenderableType:
        table = Table(
            expand=True,
            box=None,
            show_header=False,
            pad_edge=False,
            padding=(0, 1),
        )
        for _ in range(columns):
            table.add_column(ratio=1, overflow="fold")

        col_width = max(24, (width - 6) // columns - 2)
        cells = [
            self._worker_card(worker, col_width, index + 1)
            for index, worker in enumerate(workers)
        ]
        # Pad to full rows
        while len(cells) % columns:
            cells.append(Text(""))
        for start in range(0, len(cells), columns):
            table.add_row(*cells[start : start + columns])
        return table

    def _worker_card(
        self, worker: WorkerState, width: int, index: int | None = None
    ) -> RenderableType:
        role = (worker.role or "worker").lower()
        status = worker.status or "spawned"
        role_style = _role_style(role)
        status_style = _status_style(status)

        # Header: mark ROLE description ........ status elapsed
        header = Text()
        if index is not None:
            header.append(f"[{index}] ", style=f"bold {COLORS['accent_soft']}")
        header.append(f"{_status_mark(status)} ", style=status_style)
        header.append(f"{_role_glyph(role)} ", style=role_style)
        role_label = role.upper()
        header.append(f"{role_label:<11}", style=f"bold {role_style}")

        status_text = _status_label(status)
        elapsed = _format_elapsed(worker.elapsed_seconds)
        right = Text()
        right.append(status_text, style=status_style)
        right.append(f"  {elapsed}", style=COLORS["muted"])

        detail_budget = max(
            8,
            width - header.cell_len - right.cell_len - 2,
        )
        detail_source = worker.description or worker.summary or worker.name
        if detail_source:
            header.append(" ")
            header.append(_compact(detail_source, detail_budget), style=COLORS["dim"])

        header = _split_line(header, right, width)

        lines: list[RenderableType] = [header]

        # Activity / result body
        if worker.details:
            for detail in list(worker.details)[-3:]:
                lines.append(self._format_detail_line(detail, width))
        elif status == "running":
            wait = Text()
            wait.append("  ", style="")
            wait.append("⋯ working…", style=f"italic {COLORS['muted']}")
            lines.append(wait)
        elif status == "spawned":
            wait = Text()
            wait.append("  ", style="")
            wait.append("queued", style=COLORS["muted"])
            lines.append(wait)

        # Result summary when finished
        if _is_terminal_status(status) and (worker.summary or worker.result):
            result_text = worker.summary or worker.result
            result_line = Text()
            marker = "✓" if status in ("completed", "succeeded") else "!"
            marker_style = (
                COLORS["success"]
                if status in ("completed", "succeeded")
                else COLORS["danger"]
            )
            result_line.append(f"  {marker} ", style=marker_style)
            result_line.append(
                _compact(result_text, max(12, width - 4)),
                style=COLORS["text"] if status != "failed" else COLORS["danger"],
            )
            lines.append(result_line)

        return Group(*lines)

    def _render_worker_navigator(self, width: int) -> Panel:
        line = Text("  ")
        for index, worker in enumerate(self.workers.values(), start=1):
            if index > 1:
                line.append("   ", style=COLORS["border"])
            selected = worker.worker_id == self.selected_worker_id
            style = _role_style(worker.role) if selected else COLORS["muted"]
            prefix = "●" if selected else "○"
            line.append(
                f"{prefix} [{index}] ", style=f"bold {style}" if selected else style
            )
            line.append(
                _compact(
                    worker.name,
                    max(10, min(28, width // max(1, len(self.workers)) - 10)),
                ),
                style=f"bold {style}" if selected else style,
            )
            line.append(
                f"  {_status_label(worker.status)}", style=_status_style(worker.status)
            )
        title = Text()
        title.append("WORKER NAVIGATOR", style=f"bold {COLORS['accent_soft']}")
        title.append(
            "  ·  1–9 open  ·  Tab/←/→ switch  ·  Esc close",
            style=COLORS["muted"],
        )
        return Panel(
            line,
            title=title,
            title_align="left",
            box=box.SQUARE,
            border_style=COLORS["accent"],
            padding=(0, 1),
            height=3,
        )

    def _render_worker_inspector(self, width: int, height: int) -> Panel:
        worker = self.workers[self.selected_worker_id]
        role_style = _role_style(worker.role)
        status_style = _status_style(worker.status)
        title = Text()
        title.append(
            f"{_role_glyph(worker.role)} {worker.role.upper()}",
            style=f"bold {role_style}",
        )
        title.append(f"  {worker.name}", style=COLORS["text"])
        title.append("  ·  ", style=COLORS["muted"])
        title.append(_status_label(worker.status), style=f"bold {status_style}")
        title.append(
            f"  {_format_elapsed(worker.elapsed_seconds)}", style=COLORS["muted"]
        )

        body: list[RenderableType] = []
        task_label = Text()
        task_label.append("TASK", style=f"bold {COLORS['muted']}")
        body.append(task_label)
        body.append(Text(worker.description or worker.name, style=COLORS["text"]))
        body.append(Text(""))

        activity_label = Text()
        activity_label.append("LIVE ACTIVITY", style=f"bold {COLORS['accent_soft']}")
        activity_label.append(
            f"  ·  {len(worker.details)} events",
            style=COLORS["muted"],
        )
        body.append(activity_label)

        result_data = worker.result_data or {}
        evidence_lines = []
        for check in result_data.get("checks_run") or []:
            evidence_lines.append(("✓", f"check  {check}", COLORS["success"]))
        for path in result_data.get("files_changed") or []:
            evidence_lines.append(("∆", f"file   {path}", COLORS["accent_soft"]))
        for risk in result_data.get("remaining_risks") or []:
            evidence_lines.append(("!", f"risk   {risk}", COLORS["warning"]))

        inspector_height = max(6, height - 8)
        reserved = 8 + len(evidence_lines)
        # Budget rows for activity; wrap each event so long tool output is readable.
        row_budget = max(6, inspector_height - reserved)
        wrap_width = max(24, width - 8)
        rendered_rows: list[RenderableType] = []
        for detail in worker.details:
            rendered_rows.extend(
                self._format_inspector_detail_block(detail, wrap_width)
            )
        # Cap extreme histories while keeping the most recent activity.
        max_inspector_rows = max(row_budget * 20, 400)
        if len(rendered_rows) > max_inspector_rows:
            rendered_rows = rendered_rows[-max_inspector_rows:]

        max_offset = max(0, len(rendered_rows) - row_budget)
        self._scroll_offset = min(max(0, self._scroll_offset), max_offset)
        end = len(rendered_rows) - self._scroll_offset
        start = max(0, end - row_budget)
        visible_rows = rendered_rows[start:end]

        if visible_rows:
            body.extend(visible_rows)
        elif worker.status == "spawned":
            body.append(
                Text(
                    "  Waiting for an execution slot…",
                    style=f"italic {COLORS['muted']}",
                )
            )
        else:
            body.append(
                Text(
                    "  Waiting for the first activity event…",
                    style=f"italic {COLORS['muted']}",
                )
            )

        if evidence_lines:
            body.append(Text(""))
            evidence_label = Text("RESULT EVIDENCE", style=f"bold {COLORS['muted']}")
            body.append(evidence_label)
            for marker, value, style in evidence_lines:
                line = Text(f"  {marker} ", style=style)
                line.append(humanize_text(value, max_chars=240), style=COLORS["text"])
                body.append(line)

        footer = Text()
        footer.append("Esc", style=f"bold {COLORS['text']}")
        footer.append(" back to mission overview", style=COLORS["muted"])
        if max_offset:
            footer.append("  ·  ", style=COLORS["muted"])
            footer.append("scroll for more", style=COLORS["dim"])
        return Panel(
            Group(*body),
            title=title,
            title_align="left",
            subtitle=footer,
            subtitle_align="right",
            box=box.SQUARE,
            border_style=role_style,
            padding=(1, 2),
            height=inspector_height,
        )

    def _format_inspector_detail_block(
        self, detail: str, width: int
    ) -> list[RenderableType]:
        """Multi-line wrap for one stored event (no mid-line hard truncate)."""
        raw = humanize_text((detail or "").strip(), max_chars=INSPECTOR_DETAIL_MAX)
        if not raw:
            return []
        if raw.startswith("▸"):
            style = COLORS["warning"]
        elif raw.startswith("↳"):
            style = COLORS["subtle"]
        elif raw.startswith("⋯"):
            style = f"italic {COLORS['muted']}"
        elif raw.startswith("·"):
            style = COLORS["text"]
        else:
            style = COLORS["text"]

        rows: list[RenderableType] = []
        for index, piece in enumerate(wrap_lines(raw, width)):
            line = Text("  " if index == 0 else "    ")
            line.append(piece, style=style)
            rows.append(line)
        return rows

    def _format_detail_line(self, detail: str, width: int) -> Text:
        text = Text("  ")
        raw = detail or ""
        if raw.startswith("▸"):
            text.append(_compact(raw, max(12, width - 2)), style=COLORS["warning"])
        elif raw.startswith("  ↳") or raw.startswith("↳"):
            text.append(
                _compact(raw.lstrip(), max(12, width - 2)),
                style=COLORS["subtle"],
            )
        elif raw.startswith("⋯"):
            text.append(
                _compact(raw, max(12, width - 2)),
                style=f"italic {COLORS['muted']}",
            )
        elif raw.startswith("·"):
            text.append(_compact(raw, max(12, width - 2)), style=COLORS["text"])
        else:
            text.append(_compact(raw, max(12, width - 2)), style=COLORS["dim"])
        return text

    def _render_feed(
        self,
        width: int,
        height: int,
        header: RenderableType,
        workers_panel: RenderableType,
    ) -> Panel:
        activity_lines: list[Text] = []
        for timestamp, style, text in self.activity:
            line = Text()
            line.append(f"{timestamp}  ", style=COLORS["muted"])
            line.append(text, style=style)
            activity_lines.append(line)

        if self.thinking:
            thinking_text = Text()
            thinking_text.append(
                f"{time.strftime('%H:%M:%S')}  ", style=COLORS["muted"]
            )
            thinking_text.append("⋯ ", style=COLORS["muted"])
            thinking_text.append(
                _compact(self.thinking, max(20, width - 8)),
                style=f"italic {COLORS['muted']}",
            )
            activity_lines.append(thinking_text)

        if self.stream:
            # Show trailing lines of stream so latest content is visible
            stream_clean = self.stream.strip()
            if stream_clean:
                for stream_line in stream_clean.splitlines()[-6:]:
                    line = Text()
                    line.append(f"{time.strftime('%H:%M:%S')}  ", style=COLORS["muted"])
                    line.append(
                        _compact(stream_line, max(20, width - 6)),
                        style=COLORS["text"],
                    )
                    activity_lines.append(line)

        if not activity_lines:
            placeholder = Text()
            placeholder.append(
                "  Orchestrator feed — tool calls, reasoning, and streaming output appear here.",
                style=COLORS["muted"],
            )
            activity_lines.append(placeholder)

        chrome = Group(header, workers_panel)
        chrome_options = self.console.options.update(height=None)
        try:
            chrome_rows = len(
                self.console.render_lines(chrome, chrome_options, pad=False)
            )
        except Exception:
            chrome_rows = 12

        feed_height = max(4, height - chrome_rows - 1)
        if not self.activity_expanded:
            feed_height = min(feed_height, max(3, len(activity_lines) + 2))
        # Visible window ending `scroll_offset` rows above the live edge.
        visible_count = max(1, feed_height - 2) if feed_height > 2 else 1
        max_offset = max(0, len(activity_lines) - visible_count)
        self._scroll_offset = min(max(0, self._scroll_offset), max_offset)
        end = len(activity_lines) - self._scroll_offset
        start = max(0, end - visible_count)
        visible = activity_lines[start:end]

        title = Text()
        title.append("ACTIVITY", style=f"bold {COLORS['accent_soft']}")

        return Panel(
            Group(*visible),
            title=title,
            title_align="left",
            box=box.SQUARE,
            border_style=COLORS["border"],
            padding=(0, 1),
            height=feed_height,
        )

    def _render_footer(self) -> Text:
        worker_count = min(9, len(self.workers))
        worker_keys = f"1–{worker_count}" if worker_count > 1 else "1"
        footer = Text(justify="center")
        footer.append(worker_keys, style=f"bold {COLORS['text']}")
        footer.append(" inspect worker   ·   ", style=COLORS["muted"])
        footer.append("l", style=f"bold {COLORS['text']}")
        footer.append(
            " collapse log" if self.activity_expanded else " expand log",
            style=COLORS["muted"],
        )
        footer.append("   ·   ", style=COLORS["muted"])
        footer.append("r", style=f"bold {COLORS['text']}")
        footer.append(" replay mission   ·   ", style=COLORS["muted"])
        footer.append("q", style=f"bold {COLORS['text']}")
        footer.append(" quit", style=COLORS["muted"])
        return footer

    # ------------------------------------------------------------------ #
    # Display events
    # ------------------------------------------------------------------ #

    def log(self, text: str, style: str = COLORS["muted"]):
        cleaned = one_line(humanize_text(text or ""), ACTIVITY_LINE_MAX)
        if not cleaned:
            return
        self.activity.append((time.strftime("%H:%M:%S"), style, cleaned))
        self._refresh(force=True)

    def stream_append(self, chunk: str):
        self.thinking = ""
        self.stream = (self.stream + chunk)[-STREAM_MAX_CHARS:]
        self._refresh()

    def stream_finish(self, content: str):
        """Finalize the current stream without appending its full text twice."""
        self.thinking = ""
        self.stream = (content or "")[-STREAM_MAX_CHARS:]
        # Promote final stream into activity as a single entry for history
        preview = _compact(
            self.stream.strip().splitlines()[-1] if self.stream.strip() else "", 160
        )
        if preview:
            self.activity.append((time.strftime("%H:%M:%S"), COLORS["text"], preview))
        self.stream = ""
        self._refresh(force=True)

    def thinking_update(self, content: str):
        """Replace the in-progress reasoning line instead of logging each delta."""
        single_line = " ".join((content or "").split())
        if len(single_line) > THINKING_MAX_CHARS:
            single_line = f"…{single_line[-(THINKING_MAX_CHARS - 1) :]}"
        self.thinking = single_line
        self._refresh()

    def thinking_clear(self):
        if not self.thinking:
            return
        self.thinking = ""
        self._refresh(force=True)

    def tool_call(self, tool_name: str, label: str, args: dict | None = None):
        self.tool_calls += 1
        name = tool_name or "tool"
        detail = tool_call_label(name, args, fallback=label or "")
        self.log(
            f"▸ {name} · {detail}" if detail else f"▸ {name}", style=COLORS["warning"]
        )

    def tool_output(self, tool_name: str, output: str):
        lines = humanize_output_lines(
            output or "", max_lines=6, max_chars=DETAIL_LINE_MAX
        )
        if not lines:
            return
        # Activity feed: first line plus a short continuation hint.
        self.log(f"  ↳ {one_line(lines[0], ACTIVITY_LINE_MAX)}", style=COLORS["subtle"])
        if len(lines) > 1:
            self.log(
                f"    … {len(lines) - 1} more line(s)",
                style=COLORS["dim"],
            )

    def spawn(
        self, worker_id: str, name: str, description: str, role: str | None = None
    ):
        resolved_role = (role or "worker").strip() or "worker"
        self.workers[worker_id] = WorkerState(
            worker_id=worker_id,
            name=name or worker_id,
            role=resolved_role,
            status="spawned",
            description=(description or "").strip(),
        )
        self.log(
            f"dispatch → {name}",
            style=_role_style(resolved_role),
        )

    def notify(self, worker_id: str, status: str, summary: str):
        worker = self._get_or_create(worker_id)
        if status:
            worker.mark_status(status)
        if summary:
            cleaned = humanize_text(summary, max_chars=INSPECTOR_DETAIL_MAX)
            worker.summary = one_line(cleaned, 240)
            worker.details.append(f"· {cleaned}")
            self.log(
                f"[{worker.name}] {one_line(cleaned, ACTIVITY_LINE_MAX)}",
                style=COLORS["text"],
            )
        self._refresh()

    def status(
        self,
        worker_id: str,
        status: str,
        result: str | None = None,
        result_data: dict | None = None,
    ):
        worker = self._get_or_create(worker_id)
        if status:
            worker.mark_status(status)
        if result_data:
            worker.result_data = result_data
        if result:
            cleaned = humanize_text(result, max_chars=INSPECTOR_DETAIL_MAX)
            worker.result = cleaned
            if not worker.summary:
                worker.summary = one_line(cleaned, 240)
            worker.details.append(f"↳ {cleaned}")
            self.log(
                f"[{worker.name}] {_status_label(status)}: {one_line(cleaned, ACTIVITY_LINE_MAX)}",
                style=_status_style(status),
            )
        else:
            self._refresh()

    def detail(
        self,
        worker_id: str,
        detail_type: str,
        content: str,
        tool_name: str | None = None,
        args: dict | None = None,
    ):
        worker = self._get_or_create(worker_id)
        text = (content or "").strip()
        if not text:
            return

        if detail_type == "tool_call":
            self.tool_calls += 1
            if worker.status == "spawned":
                worker.mark_status("running")
            label = tool_call_label(tool_name or "", args, fallback=text)
            line = f"▸ {label}"
            style = COLORS["warning"]
            worker.details.append(line)
            self.log(f"[{worker.name}] {line}", style=style)
            return

        if detail_type == "tool_output":
            output_lines = humanize_output_lines(
                text,
                max_lines=TOOL_OUTPUT_LINES,
                max_chars=INSPECTOR_DETAIL_MAX,
            )
            if tool_name == "check_runner" and len(output_lines) > TOOL_OUTPUT_LINES:
                output_lines = output_lines[-TOOL_OUTPUT_LINES:]
            for output_line in output_lines or ["No output"]:
                worker.details.append(f"↳ {output_line}")
            preview = one_line(
                output_lines[0] if output_lines else "No output", ACTIVITY_LINE_MAX
            )
            self.log(f"[{worker.name}] ↳ {preview}", style=COLORS["subtle"])
            if len(output_lines) > 1:
                self.log(
                    f"[{worker.name}]    … {len(output_lines) - 1} more line(s)",
                    style=COLORS["dim"],
                )
            return

        if detail_type == "thinking":
            cleaned = humanize_text(text, max_chars=INSPECTOR_DETAIL_MAX)
            line = f"⋯ {cleaned}"
            style = f"italic {COLORS['muted']}"
        else:
            cleaned = humanize_text(text, max_chars=INSPECTOR_DETAIL_MAX)
            line = f"· {cleaned}"
            style = COLORS["text"]

        worker.details.append(line)
        self.log(
            f"[{worker.name}] {one_line(line, ACTIVITY_LINE_MAX)}",
            style=style,
        )

    def _get_or_create(self, worker_id: str) -> WorkerState:
        worker = self.workers.get(worker_id)
        if worker is None:
            worker = WorkerState(
                worker_id=worker_id,
                name=worker_id,
                status="running",
            )
            self.workers[worker_id] = worker
        return worker


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #


def _phase_style(phase: str) -> str:
    styles = {
        "brief": COLORS["dim"],
        "scouting": COLORS["warning"],
        "planning": COLORS["warning"],
        "awaiting_input": COLORS["warning"],
        "executing": COLORS["accent_soft"],
        "integrating": COLORS["accent"],
        "verifying": COLORS["success"],
        "repairing": COLORS["danger"],
        "terminal": COLORS["dim"],
    }
    return styles.get((phase or "").lower(), COLORS["accent_soft"])


def _split_line(left: Text, right: Text, width: int) -> Text:
    available = max(1, width)
    left_copy = left.copy()
    right_copy = right.copy()
    if left_copy.cell_len + right_copy.cell_len > available:
        # Prefer shrinking left
        room_for_left = max(0, available - right_copy.cell_len)
        left_copy.truncate(room_for_left, overflow="ellipsis")
    gap = max(0, available - left_copy.cell_len - right_copy.cell_len)
    line = left_copy
    line.append(" " * gap)
    line.append_text(right_copy)
    line.truncate(available, overflow="crop")
    return line
