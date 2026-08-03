"""Typed state and event contracts for Mission Control."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class MissionRole(StrEnum):
    SCOUT = "scout"
    WORKER = "worker"
    VERIFIER = "verifier"


class MissionPhase(StrEnum):
    BRIEF = "brief"
    SCOUTING = "scouting"
    PLANNING = "planning"
    AWAITING_INPUT = "awaiting_input"
    EXECUTING = "executing"
    INTEGRATING = "integrating"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    TERMINAL = "terminal"


class MissionStatus(StrEnum):
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TERMINAL_MISSION_STATUSES = {
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.BLOCKED,
    MissionStatus.CANCELLED,
    MissionStatus.INTERRUPTED,
}


@dataclass(slots=True)
class MissionTask:
    task_id: str
    role: MissionRole
    title: str
    instructions: str
    file_scope: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    attempt: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any], attempt: int = 0) -> "MissionTask":
        task_id = str(value.get("task_id") or value.get("id") or "").strip()
        if not task_id:
            raise ValueError("mission task requires task_id")
        try:
            role = MissionRole(str(value.get("role", "")).strip().lower())
        except ValueError as exc:
            raise ValueError("role must be scout, worker, or verifier") from exc
        title = str(value.get("title") or "").strip()
        instructions = str(value.get("instructions") or "").strip()
        if not title or not instructions:
            raise ValueError(f"task {task_id} requires title and instructions")
        return cls(
            task_id=task_id,
            role=role,
            title=title,
            instructions=instructions,
            file_scope=_string_list(value.get("file_scope")),
            dependencies=_string_list(value.get("dependencies")),
            acceptance_criteria=_string_list(value.get("acceptance_criteria")),
            attempt=attempt,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["role"] = self.role.value
        return value


@dataclass(slots=True)
class TaskResult:
    task_id: str
    role: MissionRole
    status: TaskStatus
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    criteria_evidence: dict[str, list[str]] = field(default_factory=dict)
    remaining_risks: list[str] = field(default_factory=list)
    error: str | None = None
    verdict: str | None = None

    @classmethod
    def from_agent_output(
        cls,
        task: MissionTask,
        output: str,
        files_changed: list[str] | None = None,
        checks_run: list[str] | None = None,
    ) -> "TaskResult":
        raw = (output or "").strip()
        parsed = _extract_json_object(raw)
        if parsed is None:
            return cls(
                task_id=task.task_id,
                role=task.role,
                status=TaskStatus.FAILED,
                summary=raw,
                error="task response was not valid structured JSON",
            )

        required = {
            "status",
            "summary",
            "files_changed",
            "checks_run",
            "evidence",
            "criteria_evidence",
            "remaining_risks",
            "error",
        }
        if task.role is MissionRole.VERIFIER:
            required.add("verdict")
        missing = sorted(required - parsed.keys())
        if missing:
            return cls(
                task_id=task.task_id,
                role=task.role,
                status=TaskStatus.FAILED,
                summary=str(parsed.get("summary") or raw).strip(),
                error=f"task response missing required fields: {', '.join(missing)}",
            )

        status = TaskStatus.FAILED
        error = None
        if _looks_like_error(raw):
            status = TaskStatus.FAILED
            error = raw
        requested_status = str(parsed.get("status") or "").lower()
        try:
            status = TaskStatus(requested_status)
        except ValueError:
            status = TaskStatus.FAILED
            error = f"invalid task status: {requested_status}"
        error = str(parsed.get("error") or "").strip() or error
        if error:
            status = TaskStatus.FAILED
        summary = str(parsed.get("summary") or raw).strip()
        verdict = str(parsed.get("verdict") or "").strip().lower() or None
        if task.role is MissionRole.VERIFIER:
            if verdict not in {"pass", "fail"}:
                status = TaskStatus.FAILED
                error = error or "verifier did not return verdict=pass or verdict=fail"
            elif verdict == "fail":
                status = TaskStatus.FAILED
        else:
            verdict = None
        return cls(
            task_id=task.task_id,
            role=task.role,
            status=status,
            summary=summary,
            files_changed=_merge_lists(
                files_changed or [], _string_list(parsed.get("files_changed"))
            ),
            checks_run=_merge_lists(
                checks_run or [], _string_list(parsed.get("checks_run"))
            ),
            evidence=_string_list(parsed.get("evidence")),
            criteria_evidence=_string_list_mapping(parsed.get("criteria_evidence")),
            remaining_risks=_string_list(parsed.get("remaining_risks")),
            error=error,
            verdict=verdict,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["role"] = self.role.value
        value["status"] = self.status.value
        return value


@dataclass(slots=True)
class MissionEvent:
    mission_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _merge_lists(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def _string_list_mapping(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): _string_list(items)
        for key, items in value.items()
        if str(key).strip()
    }


def _looks_like_error(value: str) -> bool:
    lower = value.lower()
    return lower.startswith(("error", "subagent execution failed", "command failed"))


def _extract_json_object(value: str) -> dict[str, Any] | None:
    candidates = [value]
    if "```" in value:
        for block in value.split("```"):
            cleaned = block.strip()
            if cleaned.startswith("json"):
                candidates.append(cleaned[4:].strip())
            elif cleaned.startswith("{"):
                candidates.append(cleaned)
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        candidates.append(value[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
