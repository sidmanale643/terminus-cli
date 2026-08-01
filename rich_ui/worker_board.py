"""Mission Control theater rendered with rich.live.Live.

Full-screen board while a /mission turn runs:
  • Mission bar — objective, phase pipeline, elapsed, progress
  • Worker cards — role-colored agents with live activity + results
  • Orchestrator feed — stream, thinking, tool calls

Mirrors the React MissionBar + WorkerPanes aesthetic for the pure-Python Rich UI.
"""

from __future__ import annotations

import re
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

from ui.theme import COLORS

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ACTIVITY_MAX_LINES = 48
WORKER_DETAIL_LINES = 5
STREAM_MAX_CHARS = 8000
THINKING_MAX_CHARS = 280
REFRESH_INTERVAL_SECONDS = 0.1
SIDE_BY_SIDE_MIN_WIDTH = 110
SIDE_BY_SIDE_MIN_HEIGHT = 22
MAX_WORKERS_SIDE_COLUMNS = 3
GOAL_MAX_CHARS = 160
DETAIL_PREVIEW = 140

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

STATUS_LABELS = {
    "spawned": "spawned",
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
    "completed": "✓",
    "succeeded": "✓",
    "failed": "✕",
    "stopped": "■",
    "blocked": "!",
    "cancelled": "■",
}

ROLE_STYLES = {
    "scout": COLORS["warning"],
    "worker": COLORS["accent"],
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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _compact(value: str, max_length: int) -> str:
    single = re.sub(r"\s+", " ", (value or "")).strip()
    if len(single) <= max_length:
        return single
    if max_length <= 1:
        return single[:max_length]
    return f"{single[: max_length - 1]}…"


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
        self.activity: deque[tuple[str, str]] = deque(maxlen=ACTIVITY_MAX_LINES)
        self.stream = ""
        self.thinking = ""
        self._last_refresh = 0.0
        self._finished = False
        self._paused = False
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

    def _stop_live(self):
        if self._live.is_started:
            self._live.stop()

    def stop(self):
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
        meta.append(f"{snapshot.get('tool_calls', self.tool_calls)} tools", style=COLORS["muted"])

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
        workers_panel = self._render_workers(width, height)
        feed = self._render_feed(width, height, header, workers_panel)
        return Group(header, workers_panel, feed)

    def _render_header(self, width: int) -> Panel:
        elapsed = _format_elapsed(time.time() - self.started_at)
        workers = list(self.workers.values())
        total = len(workers)
        done = sum(1 for w in workers if w.status in ("completed", "succeeded"))
        failed = sum(1 for w in workers if w.status == "failed")
        running = sum(1 for w in workers if w.status == "running")

        # Top row: brand + meta
        brand = Text()
        brand.append("◈  MISSION", style=f"bold {COLORS['accent_soft']}")

        meta = Text()
        meta.append(self.phase, style=f"bold {_phase_style(self.phase)}")
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(elapsed, style=COLORS["dim"])
        if total:
            meta.append("  ·  ", style=COLORS["muted"])
            meta.append(f"{done}/{total}", style=COLORS["success"] if done else COLORS["dim"])
            meta.append(" done", style=COLORS["muted"])
            if running:
                meta.append("  ·  ", style=COLORS["muted"])
                meta.append(f"{running} running", style=COLORS["warning"])
            if failed:
                meta.append("  ·  ", style=COLORS["muted"])
                meta.append(f"{failed} failed", style=COLORS["danger"])
        meta.append("  ·  ", style=COLORS["muted"])
        meta.append(f"{self.tool_calls} tools", style=COLORS["muted"])

        top = _split_line(brand, meta, max(20, width - 4))

        # Goal line
        goal_line = Text()
        goal_line.append("  ", style="")
        goal_line.append("objective  ", style=COLORS["muted"])
        goal_line.append(_compact(self.goal, max(20, width - 18)), style=COLORS["text"])

        # Phase pipeline
        pipeline = self._phase_pipeline(max(20, width - 4))

        body = Group(top, goal_line, pipeline)
        return Panel(
            body,
            box=box.SQUARE,
            border_style=COLORS["accent"],
            padding=(0, 1),
            height=5,
        )

    def _phase_pipeline(self, width: int) -> Text:
        current = self.phase if self.phase in MISSION_PHASES else "executing"
        try:
            current_idx = MISSION_PHASES.index(current)
        except ValueError:
            current_idx = 3

        line = Text("  ")
        for index, name in enumerate(MISSION_PHASES):
            if index:
                connector = " ─ "
                if index <= current_idx:
                    line.append(connector, style=COLORS["accent"])
                else:
                    line.append(connector, style=COLORS["border"])

            if index < current_idx:
                line.append(name, style=COLORS["muted"])
            elif index == current_idx:
                line.append(f"● {name}", style=f"bold {_phase_style(name)}")
            else:
                line.append(name, style=COLORS["border"])

        line.truncate(max(10, width), overflow="ellipsis")
        return line

    def _render_workers(self, width: int, height: int) -> Panel:
        workers = list(self.workers.values())
        running = sum(1 for w in workers if w.status == "running")

        title = Text()
        title.append("WORKERS", style=f"bold {COLORS['accent_soft']}")
        if workers:
            title.append(f"  {len(workers)}", style=COLORS["dim"])
            if running:
                title.append(f"  ·  {running} active", style=COLORS["warning"])
        else:
            title.append("  waiting for agents…", style=COLORS["muted"])

        border = COLORS["warning"] if running else COLORS["border"]

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

        use_columns = (
            width >= SIDE_BY_SIDE_MIN_WIDTH
            and height >= SIDE_BY_SIDE_MIN_HEIGHT
            and len(workers) >= 2
        )

        if use_columns:
            columns = min(MAX_WORKERS_SIDE_COLUMNS, len(workers))
            body = self._workers_columns(workers, columns, width)
            # Rough height: header row per worker block ~ 3-5 lines
            panel_height = min(14, max(6, 3 + (len(workers) + columns - 1) // columns * 5))
        else:
            body = self._workers_stack(workers, width)
            # Cap stacked workers panel so feed still has room
            per = 4
            panel_height = min(16, max(5, 2 + len(workers) * per))

        return Panel(
            body,
            title=title,
            title_align="left",
            box=box.SQUARE,
            border_style=border,
            padding=(0, 1),
            height=panel_height,
        )

    def _workers_stack(self, workers: list[WorkerState], width: int) -> RenderableType:
        rows: list[RenderableType] = []
        inner = max(24, width - 6)
        for index, worker in enumerate(workers):
            if index:
                rows.append(Rule(style=COLORS["border"], characters="─"))
            rows.append(self._worker_card(worker, inner))
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
        cells = [self._worker_card(worker, col_width) for worker in workers]
        # Pad to full rows
        while len(cells) % columns:
            cells.append(Text(""))
        for start in range(0, len(cells), columns):
            table.add_row(*cells[start : start + columns])
        return table

    def _worker_card(self, worker: WorkerState, width: int) -> RenderableType:
        role = (worker.role or "worker").lower()
        status = worker.status or "spawned"
        role_style = _role_style(role)
        status_style = _status_style(status)

        # Header: mark ROLE description ........ status elapsed
        header = Text()
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
        for style, text in self.activity:
            line = Text()
            line.append(text, style=style)
            activity_lines.append(line)

        if self.thinking:
            thinking_text = Text()
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

        feed_height = max(4, height - chrome_rows)
        # Keep only the tail that fits
        visible = activity_lines[-(feed_height - 2) :] if feed_height > 2 else activity_lines[-1:]

        title = Text()
        title.append("ORCHESTRATOR", style=f"bold {COLORS['accent_soft']}")
        if self.thinking:
            title.append("  ·  thinking", style=f"italic {COLORS['muted']}")
        elif self.stream:
            title.append("  ·  streaming", style=COLORS["warning"])

        return Panel(
            Group(*visible),
            title=title,
            title_align="left",
            box=box.SQUARE,
            border_style=COLORS["border"],
            padding=(0, 1),
            height=feed_height,
        )

    # ------------------------------------------------------------------ #
    # Display events
    # ------------------------------------------------------------------ #

    def log(self, text: str, style: str = COLORS["muted"]):
        cleaned = re.sub(r"\s+", " ", (text or "")).strip()
        if not cleaned:
            return
        self.activity.append((style, _compact(cleaned, 200)))
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
        preview = _compact(self.stream.strip().splitlines()[-1] if self.stream.strip() else "", 160)
        if preview:
            self.activity.append((COLORS["text"], preview))
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

    def tool_call(self, tool_name: str, label: str):
        self.tool_calls += 1
        name = tool_name or "tool"
        detail = _compact(label or "", 100)
        self.log(f"▸ {name} · {detail}" if detail else f"▸ {name}", style=COLORS["warning"])

    def tool_output(self, tool_name: str, output: str):
        preview = (output or "").strip().splitlines()[0][:DETAIL_PREVIEW] if (output or "").strip() else ""
        if preview:
            self.log(f"  ↳ {preview}", style=COLORS["subtle"])

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
        glyph = _role_glyph(resolved_role)
        self.log(
            f"+ {glyph} {name} ({resolved_role}): {_compact(description or '', 100)}",
            style=_role_style(resolved_role),
        )

    def notify(self, worker_id: str, status: str, summary: str):
        worker = self._get_or_create(worker_id)
        if status:
            worker.mark_status(status)
        if summary:
            worker.summary = summary.strip()
            worker.details.append(f"· {_compact(summary, DETAIL_PREVIEW)}")
            self.log(
                f"[{worker.name}] {_compact(summary, 140)}",
                style=COLORS["text"],
            )
        self._refresh()

    def status(self, worker_id: str, status: str, result: str | None = None):
        worker = self._get_or_create(worker_id)
        if status:
            worker.mark_status(status)
        if result:
            cleaned = result.strip()
            worker.result = cleaned
            if not worker.summary:
                worker.summary = _compact(cleaned, 200)
            worker.details.append(f"↳ {_compact(cleaned, DETAIL_PREVIEW)}")
            self.log(
                f"[{worker.name}] {_status_label(status)}: {_compact(cleaned, 120)}",
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
    ):
        worker = self._get_or_create(worker_id)
        text = (content or "").strip()
        if not text:
            return

        if detail_type == "tool_call":
            self.tool_calls += 1
            if worker.status == "spawned":
                worker.mark_status("running")
            line = f"▸ {tool_name or 'tool'} · {_compact(text, 100)}"
            style = COLORS["warning"]
        elif detail_type == "tool_output":
            line = f"  ↳ {_compact(text, DETAIL_PREVIEW)}"
            style = COLORS["subtle"]
        elif detail_type == "thinking":
            line = f"⋯ {_compact(text, DETAIL_PREVIEW)}"
            style = f"italic {COLORS['muted']}"
        else:
            line = f"· {_compact(text, DETAIL_PREVIEW)}"
            style = COLORS["text"]

        worker.details.append(line)
        self.log(f"[{worker.name}] {line}", style=style)

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
