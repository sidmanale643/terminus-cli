"""Human-readable display formatting for Terminus UI surfaces.

Raw JSON is never suitable for the transcript or Mission Control. These helpers
turn tool args/outputs (and any accidental JSON payloads) into plain text.
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any

# Soft caps so a single event cannot flood the UI, while still showing useful body.
ONE_LINE_DEFAULT = 160
ACTIVITY_LINE_MAX = 280
DETAIL_LINE_MAX = 4000
TOOL_OUTPUT_LINES = 48
MAX_STRUCTURED_LINES = 80


def collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def one_line(value: str, max_length: int = ONE_LINE_DEFAULT) -> str:
    """Collapse to a single line and optionally ellipsize."""
    single = collapse_ws(value)
    if max_length <= 0 or len(single) <= max_length:
        return single
    if max_length <= 1:
        return single[:max_length]
    return f"{single[: max_length - 1]}…"


def wrap_lines(value: str, width: int) -> list[str]:
    """Wrap text for inspector panes without truncating mid-content."""
    width = max(12, width)
    lines: list[str] = []
    for paragraph in (value or "").splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])
    return lines


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return collapse_ws(str(value))


def format_data(
    value: Any, *, indent: int = 0, max_lines: int = MAX_STRUCTURED_LINES
) -> list[str]:
    """Render structured data as plain key/value lines (no braces/brackets)."""
    prefix = "  " * indent
    lines: list[str] = []

    def remaining() -> int:
        return max(0, max_lines - len(lines))

    if isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}(empty)")
            return lines
        for key, item in value.items():
            if remaining() <= 0:
                lines.append(f"{prefix}…")
                break
            label = str(key)
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{prefix}{label}:")
                lines.extend(
                    format_data(item, indent=indent + 1, max_lines=remaining())
                )
            else:
                lines.append(f"{prefix}{label}: {_format_scalar(item)}")
        return lines

    if isinstance(value, (list, tuple)):
        if not value:
            lines.append(f"{prefix}(empty)")
            return lines
        for index, item in enumerate(value):
            if remaining() <= 0:
                lines.append(f"{prefix}…")
                break
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{prefix}-")
                lines.extend(
                    format_data(item, indent=indent + 1, max_lines=remaining())
                )
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines

    text = _format_scalar(value)
    if text:
        lines.append(f"{prefix}{text}")
    return lines


def try_parse_json(text: str) -> Any | None:
    cleaned = (text or "").strip()
    if not cleaned or cleaned[0] not in "{[":
        return None
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def humanize_text(value: str, *, max_chars: int = DETAIL_LINE_MAX) -> str:
    """Return display-safe text; convert whole-string JSON to plain lines."""
    text = (value or "").strip()
    if not text:
        return ""
    parsed = try_parse_json(text)
    if parsed is not None:
        rendered = "\n".join(format_data(parsed))
        text = rendered if rendered else text
    if max_chars > 0 and len(text) > max_chars:
        omitted = len(text) - max_chars
        return f"{text[:max_chars]}\n… truncated {omitted} character(s)"
    return text


def humanize_output_lines(
    value: str,
    *,
    max_lines: int = TOOL_OUTPUT_LINES,
    max_chars: int = DETAIL_LINE_MAX,
) -> list[str]:
    """Split tool output into human-readable lines for feed/inspector storage."""
    text = humanize_text(value, max_chars=max_chars)
    if not text:
        return []
    lines = [line.rstrip() for line in text.splitlines()]
    lines = [line for line in lines if line.strip()]
    if len(lines) > max_lines:
        head = max_lines // 2
        tail = max_lines - head - 1
        omitted = len(lines) - head - tail
        lines = [
            *lines[:head],
            f"… {omitted} more line(s) …",
            *lines[-tail:],
        ]
    return lines


def _path_list(args: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = args.get(key)
        if isinstance(value, list) and value:
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def tool_call_label(
    tool_name: str, args: dict[str, Any] | None, fallback: str = ""
) -> str:
    """Short human label for a tool invocation (never JSON)."""
    args = args or {}
    name = (tool_name or "tool").strip() or "tool"

    if name == "bash":
        command = str(args.get("command") or "").strip()
        if command:
            return f"$ {one_line(command, 140)}"
        return "run shell command"

    if name == "file_reader":
        paths = _path_list(args, "files", "file_paths", "paths", "file_path", "path")
        if len(paths) == 1:
            return f"read {paths[0]}"
        if paths:
            return f"read {len(paths)} files"
        return "read file"

    if name == "file_creator":
        path = args.get("file_path") or args.get("path")
        return f"create {path}" if path else "create file"

    if name == "file_editor":
        path = args.get("file_path") or args.get("path")
        if path and "old_strings" in args:
            return f"multi-edit {path}"
        return f"edit {path}" if path else "edit file"

    if name in {"repo_search", "web_search"}:
        query = str(args.get("query") or "").strip()
        path = args.get("path") or args.get("path_glob") or ""
        if name == "repo_search" and args.get("files_only"):
            return f"list files in {path or '.'}"
        if query and path:
            return f"search {query!r} in {path}"
        if query:
            return f"search {query!r}"
        return "search"

    if name == "check_runner":
        command = str(args.get("command") or "").strip()
        return f"check $ {one_line(command, 120)}" if command else "run check"

    if name == "sandbox":
        language = args.get("language") or "python"
        return f"sandbox ({language})"

    if name == "subagent":
        task = str(args.get("task") or "").strip()
        return f"delegate: {one_line(task, 100)}" if task else "delegate to sub-agent"

    if name == "mission_dispatch":
        goal = str(args.get("goal") or args.get("objective") or "").strip()
        return (
            f"dispatch mission: {one_line(goal, 100)}" if goal else "dispatch mission"
        )

    if name in {"todo_write", "todo_update"}:
        task = str(args.get("task") or "").strip()
        status = str(args.get("status") or "").strip()
        if name == "todo_write" and task:
            return f"todo add: {one_line(task, 80)}"
        if task and status:
            return f"todo {status}: {one_line(task, 80)}"
        if task:
            return f"todo: {one_line(task, 80)}"
        return "update todos"

    if name == "todo_read":
        return "read todos"

    if name == "ask_question":
        questions = args.get("questions") or []
        count = len(questions) if isinstance(questions, list) else 0
        if count == 1:
            return "ask a clarifying question"
        if count:
            return f"ask {count} clarifying questions"
        return "ask clarifying question"

    if name == "load_skill":
        skill = args.get("name") or args.get("skill") or ""
        return f"load skill {skill}" if skill else "load skill"

    fallback_line = one_line(fallback, 120)
    if fallback_line:
        return fallback_line
    return name.replace("_", " ")


def tool_arg_detail_lines(tool_name: str, args: dict[str, Any] | None) -> list[str]:
    """Secondary human details for a tool call — never a raw JSON blob.

    Used when the short label alone is not enough (e.g. multi-file reads).
    """
    args = args or {}
    name = (tool_name or "").strip()
    lines: list[str] = []

    if name == "file_reader":
        paths = _path_list(args, "files", "file_paths", "paths")
        if len(paths) > 1:
            for path in paths[:12]:
                lines.append(f"path  {path}")
            if len(paths) > 12:
                lines.append(f"… {len(paths) - 12} more path(s)")
        return lines

    if name == "bash":
        # Command already lives in the label; only surface timeout when non-default.
        timeout = args.get("timeout")
        if timeout not in (None, "", 30):
            lines.append(f"timeout  {timeout}s")
        return lines

    if name == "file_editor":
        old_strings = args.get("old_strings")
        if isinstance(old_strings, list) and len(old_strings) > 1:
            lines.append(f"edits  {len(old_strings)}")
        return lines

    if name == "web_search":
        max_results = args.get("max_results") or args.get("num_results")
        if max_results:
            lines.append(f"results  {max_results}")
        return lines

    # Generic fallback: skip bulky/nested fields; never dump whole args as JSON.
    skip = {
        "content",
        "old_string",
        "new_string",
        "old_strings",
        "new_strings",
        "code",
        "questions",
        "command",
        "task",
        "query",
    }
    for key, value in args.items():
        if key in skip or value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            continue
        lines.append(f"{key}  {_format_scalar(value)}")
        if len(lines) >= 6:
            break
    return lines
