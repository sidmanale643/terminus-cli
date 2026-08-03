"""Durable, role-enforced Mission Control runtime."""

from __future__ import annotations

import difflib
import json
import os
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agent import Agent
from src.mission.models import (
    TERMINAL_MISSION_STATUSES,
    MissionEvent,
    MissionPhase,
    MissionRole,
    MissionStatus,
    MissionTask,
    TaskResult,
    TaskStatus,
)
from src.mission.store import MissionStore
from src.mission.tools import (
    MissionAskQuestion,
    normalize_scope,
    read_only_tools,
    scopes_overlap,
    worker_tools,
)
from src.prompts.system_prompt import get_agents_prompt
from src.tools import MissionDispatch
from src.tools.tool_registry import ToolRegistry


EventCallback = Callable[[MissionEvent], None]
TaskRunner = Callable[[MissionTask, str], TaskResult]


@dataclass(slots=True)
class MissionOutcome:
    mission_id: str
    phase: MissionPhase
    status: MissionStatus
    summary: str
    awaiting_input: bool = False

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_MISSION_STATUSES


class MissionController:
    MAX_CONCURRENCY = 3

    def __init__(
        self,
        goal: str,
        cwd: str,
        store: MissionStore,
        event_callback: EventCallback | None = None,
        stop_event: threading.Event | None = None,
        mission_id: str | None = None,
        task_runner: TaskRunner | None = None,
        agent_factory: Callable[..., Agent] = Agent,
    ):
        self.mission_id = mission_id or str(uuid.uuid4())
        self.goal = goal.strip()
        self.cwd = os.path.realpath(os.path.abspath(cwd))
        self.store = store
        self.event_callback = event_callback
        self.stop_event = stop_event or threading.Event()
        self.phase = MissionPhase.BRIEF
        self.status = MissionStatus.RUNNING
        self.repair_count = 0
        self.results: dict[str, TaskResult] = {}
        self.tasks: dict[str, MissionTask] = {}
        self._task_runner = task_runner
        self._agent_factory = agent_factory
        self._lock = threading.RLock()
        self._event_lock = threading.RLock()
        self._file_baselines: dict[str, bytes | None] = {}
        self._project_instructions = get_agents_prompt(Path(self.cwd))
        dispatch = MissionDispatch(self)
        registry = ToolRegistry(tools=[dispatch, MissionAskQuestion()])
        self.orchestrator = agent_factory(
            cwd=self.cwd,
            name="mission-orchestrator",
            system_prompt=self._mission_system_prompt(self._orchestrator_prompt()),
            tool_registry=registry,
        )
        provider, model = self._agent_identity(self.orchestrator)
        self.store.create_mission(
            self.mission_id,
            self.goal,
            self.cwd,
            provider=provider,
            model=model,
        )

    def run(self, user_message: str | None = None, **callbacks) -> MissionOutcome:
        if self.status in TERMINAL_MISSION_STATUSES:
            return self.outcome()
        message = user_message or self._initial_brief()
        if self.phase is MissionPhase.AWAITING_INPUT:
            self._transition(self._phase_before_input, MissionStatus.RUNNING)
        try:
            response = self.orchestrator.run(
                message,
                stop_event=self.stop_event,
                tool_call_callback=self._wrap_tool_callback(
                    callbacks.get("tool_call_callback")
                ),
                status_callback=callbacks.get("status_callback"),
                tool_output_callback=callbacks.get("tool_output_callback"),
                usage_callback=self._usage_callback(),
            )
        except KeyboardInterrupt:
            self.cancel()
            return self.outcome()
        self._emit(
            "orchestrator_response",
            {"content": str(response)[-100000:]},
        )
        if self.phase is MissionPhase.AWAITING_INPUT:
            return MissionOutcome(
                self.mission_id,
                self.phase,
                self.status,
                str(response),
                awaiting_input=True,
            )
        if self.status in TERMINAL_MISSION_STATUSES:
            return self.outcome()
        if str(response).lower().startswith("error occurred"):
            self._terminal(MissionStatus.FAILED, str(response))
        else:
            self._terminal(
                MissionStatus.BLOCKED,
                "The orchestrator stopped before a verifier produced a passing verdict.",
            )
        return self.outcome()

    def dispatch(self, phase: str, task_values: list[dict[str, Any]]) -> dict[str, Any]:
        if self.stop_event.is_set():
            raise KeyboardInterrupt()
        requested = MissionPhase(phase)
        tasks = [
            MissionTask.from_dict(value, self.repair_count) for value in task_values
        ]
        self._validate_dispatch(requested, tasks)
        self._transition(requested, MissionStatus.RUNNING)
        for task in tasks:
            self.tasks[task.task_id] = task
            self._deliver(self.store.add_task(self.mission_id, task))

        try:
            results = self._schedule(tasks)
        except RuntimeError as exc:
            self._terminal(MissionStatus.FAILED, str(exc))
            raise
        failed = [
            result for result in results if result.status is not TaskStatus.COMPLETED
        ]
        if (
            requested
            in {MissionPhase.SCOUTING, MissionPhase.EXECUTING, MissionPhase.REPAIRING}
            and failed
        ):
            detail = "; ".join(result.error or result.summary for result in failed)
            self._terminal(MissionStatus.FAILED, f"Mission task failed: {detail}")
        elif requested is MissionPhase.SCOUTING:
            self._transition(MissionPhase.PLANNING, MissionStatus.RUNNING)
        elif requested in {MissionPhase.EXECUTING, MissionPhase.REPAIRING}:
            self._transition(MissionPhase.INTEGRATING, MissionStatus.RUNNING)
        elif requested is MissionPhase.VERIFYING:
            verifier = results[0]
            if verifier.verdict == "pass" and verifier.status is TaskStatus.COMPLETED:
                self._terminal(
                    MissionStatus.COMPLETED, verifier.summary or "Verification passed."
                )
            elif verifier.verdict == "fail" and self.repair_count == 0:
                self.repair_count = 1
                self._transition(
                    MissionPhase.REPAIRING, MissionStatus.RUNNING, repair_count=1
                )
            else:
                self._terminal(
                    MissionStatus.FAILED,
                    verifier.error
                    or verifier.summary
                    or "Verification failed after repair.",
                )
        return {
            "mission_id": self.mission_id,
            "phase": self.phase.value,
            "status": self.status.value,
            "repair_count": self.repair_count,
            "results": [result.to_dict() for result in results],
        }

    def cancel(self) -> None:
        self.stop_event.set()
        if self.status not in TERMINAL_MISSION_STATUSES:
            for task_id in self.tasks:
                if task_id not in self.results:
                    event = self.store.set_task_status(
                        self.mission_id, task_id, TaskStatus.CANCELLED.value
                    )
                    self._deliver(event)
            self._terminal(MissionStatus.CANCELLED, "Mission cancelled by the user.")

    def outcome(self) -> MissionOutcome:
        record = self.store.get_mission(self.mission_id) or {}
        return MissionOutcome(
            self.mission_id,
            self.phase,
            self.status,
            str(record.get("summary") or ""),
            self.phase is MissionPhase.AWAITING_INPUT,
        )

    def _validate_dispatch(self, phase: MissionPhase, tasks: list[MissionTask]) -> None:
        allowed_from = {
            MissionPhase.SCOUTING: {MissionPhase.BRIEF},
            MissionPhase.EXECUTING: {MissionPhase.PLANNING},
            MissionPhase.REPAIRING: {MissionPhase.REPAIRING},
            MissionPhase.VERIFYING: {MissionPhase.INTEGRATING, MissionPhase.PLANNING},
        }
        expected_role = {
            MissionPhase.SCOUTING: MissionRole.SCOUT,
            MissionPhase.EXECUTING: MissionRole.WORKER,
            MissionPhase.REPAIRING: MissionRole.WORKER,
            MissionPhase.VERIFYING: MissionRole.VERIFIER,
        }
        if phase not in allowed_from or self.phase not in allowed_from[phase]:
            raise RuntimeError(
                f"invalid transition: {self.phase.value} -> {phase.value}"
            )
        if phase is MissionPhase.VERIFYING and len(tasks) != 1:
            raise ValueError("verification requires exactly one verifier task")
        if phase is MissionPhase.SCOUTING and not tasks:
            raise ValueError("scouting requires at least one scout task")
        if phase in {MissionPhase.EXECUTING, MissionPhase.REPAIRING} and not tasks:
            raise ValueError(
                "worker dispatch requires at least one task; skip to verification instead"
            )
        if any(task.role is not expected_role[phase] for task in tasks):
            raise ValueError(
                f"all {phase.value} tasks must use role={expected_role[phase].value}"
            )
        ids = [task.task_id for task in tasks]
        if len(ids) != len(set(ids)) or any(task_id in self.tasks for task_id in ids):
            raise ValueError("task IDs must be unique within a mission")
        known = set(self.tasks) | set(ids)
        if any(
            dependency not in known
            for task in tasks
            for dependency in task.dependencies
        ):
            raise ValueError("task dependency references an unknown task ID")
        for task in tasks:
            if not task.acceptance_criteria:
                raise ValueError(
                    f"task {task.task_id} requires at least one acceptance criterion"
                )
            if len(task.acceptance_criteria) != len(set(task.acceptance_criteria)):
                raise ValueError(
                    f"task {task.task_id} acceptance criteria must be unique"
                )
            if len(task.dependencies) != len(set(task.dependencies)):
                raise ValueError(f"task {task.task_id} dependencies must be unique")
            if task.role is MissionRole.WORKER and not task.file_scope:
                raise ValueError(
                    f"worker task {task.task_id} requires a non-empty file_scope"
                )
            if task.role is not MissionRole.WORKER and task.file_scope:
                raise ValueError(
                    f"{task.role.value} task {task.task_id} must use file_scope=[]"
                )
            normalize_scope(self.cwd, task.file_scope)
        if phase is MissionPhase.VERIFYING:
            worker_criteria = {
                criterion
                for existing in self.tasks.values()
                if existing.role is MissionRole.WORKER
                for criterion in existing.acceptance_criteria
            }
            missing = sorted(worker_criteria - set(tasks[0].acceptance_criteria))
            if missing:
                raise ValueError(
                    "verifier acceptance criteria must include every Worker criterion: "
                    + ", ".join(missing)
                )

    def _schedule(self, tasks: list[MissionTask]) -> list[TaskResult]:
        pending = {task.task_id: task for task in tasks}
        completed = {
            task_id
            for task_id, result in self.results.items()
            if result.status is TaskStatus.COMPLETED
        }
        running: dict[Any, MissionTask] = {}
        results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENCY) as executor:
            while pending or running:
                if self.stop_event.is_set():
                    raise KeyboardInterrupt()
                for task_id, task in list(pending.items()):
                    if len(running) >= self.MAX_CONCURRENCY:
                        break
                    if not self._dependencies_ready(task, completed):
                        continue
                    if task.role is MissionRole.WORKER and any(
                        scopes_overlap(self.cwd, task.file_scope, active.file_scope)
                        for active in running.values()
                    ):
                        continue
                    future = executor.submit(self._execute_task, task)
                    running[future] = task
                    del pending[task_id]
                if not running:
                    details = []
                    for task in pending.values():
                        dependency_detail = self._dependency_failure_detail(
                            task, completed
                        )
                        error = f"task blocked by dependencies: {dependency_detail}"
                        result = TaskResult(
                            task.task_id,
                            task.role,
                            TaskStatus.BLOCKED,
                            summary=error,
                            error=error,
                        )
                        self.results[task.task_id] = result
                        results.append(result)
                        self._deliver(self.store.update_task(self.mission_id, result))
                        details.append(f"{task.task_id} ({dependency_detail})")
                    pending.clear()
                    raise RuntimeError(
                        "mission tasks could not start: " + "; ".join(details)
                    )
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    task = running.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = TaskResult(
                            task.task_id, task.role, TaskStatus.FAILED, error=str(exc)
                        )
                    self.results[task.task_id] = result
                    results.append(result)
                    if result.status is TaskStatus.COMPLETED:
                        completed.add(task.task_id)
                    self._deliver(self.store.update_task(self.mission_id, result))
        return results

    def _dependencies_ready(self, task: MissionTask, completed: set[str]) -> bool:
        for dependency in task.dependencies:
            if dependency in completed:
                continue
            result = self.results.get(dependency)
            if (
                self.phase is MissionPhase.REPAIRING
                and result is not None
                and result.role is MissionRole.VERIFIER
                and result.verdict == "fail"
            ):
                continue
            return False
        return True

    def _dependency_failure_detail(self, task: MissionTask, completed: set[str]) -> str:
        details = []
        for dependency in task.dependencies:
            if dependency in completed:
                continue
            result = self.results.get(dependency)
            if result is None:
                details.append(f"{dependency}=unresolved")
                continue
            reason = result.error or result.summary or "no failure detail"
            details.append(f"{dependency}={result.status.value}: {reason}")
        return ", ".join(details) or "dependency cycle"

    def _execute_task(self, task: MissionTask) -> TaskResult:
        event = self.store.set_task_status(
            self.mission_id, task.task_id, TaskStatus.RUNNING.value
        )
        self._deliver(event)
        context = self._task_context(task)
        if self._task_runner:
            return self._task_runner(task, context)
        files_changed: list[str] = []
        checks_run: list[str] = []
        tool_calls: list[str] = []
        tool_outputs: list[tuple[str, str]] = []
        check_outputs: list[str] = []

        def track_file(path: str) -> None:
            files_changed.append(os.path.relpath(path, self.cwd))

        track_check = checks_run.append
        tools = (
            worker_tools(
                self.cwd,
                task.file_scope,
                track_file,
                track_check,
                self._capture_file_baseline,
            )
            if task.role is MissionRole.WORKER
            else read_only_tools(self.cwd, track_check)
        )
        agent = self._agent_factory(
            cwd=self.cwd,
            id=task.task_id,
            name=task.title,
            system_prompt=self._mission_system_prompt(self._role_prompt(task.role)),
            tool_registry=ToolRegistry(tools=tools),
        )

        def task_status(message: str, is_thinking: bool = False, **kwargs) -> None:
            self._emit(
                "task_detail",
                {
                    "detail_type": "thinking" if is_thinking else "status",
                    "content": str(message)[-4000:],
                },
                task.task_id,
            )

        def task_tool_call(tool_name: str, label: str, args: dict) -> None:
            tool_calls.append(tool_name)
            self._emit(
                "task_detail",
                {
                    "detail_type": "tool_call",
                    "content": label,
                    "tool_name": tool_name,
                    "args": args,
                },
                task.task_id,
            )

        def task_tool_output(tool_name: str, output: str) -> None:
            tool_outputs.append((tool_name, str(output)))
            if tool_name == "check_runner" and str(output).startswith("exit_code="):
                check_outputs.append(str(output))
            self._emit(
                "task_detail",
                {
                    "detail_type": "tool_output",
                    "content": str(output)[-8000:],
                    "tool_name": tool_name,
                },
                task.task_id,
            )

        output = agent.run(
            context,
            stop_event=self.stop_event,
            status_callback=task_status,
            tool_call_callback=task_tool_call,
            tool_output_callback=task_tool_output,
            usage_callback=self._usage_callback(task.task_id),
            response_format=self._task_response_format(task),
        )
        provider, model = self._agent_identity(agent)
        self._emit(
            "task_response",
            {
                "content": str(output)[-100000:],
                "provider": provider,
                "model": model,
            },
            task.task_id,
        )
        result = TaskResult.from_agent_output(task, output)
        if self._needs_structured_retry(task, result):
            output = agent.run(
                "Your previous response did not satisfy the required JSON contract. "
                "Do not repeat repository work. Return only one corrected JSON object "
                "using the exact required fields and criterion IDs from your assignment.",
                stop_event=self.stop_event,
                status_callback=task_status,
                tool_call_callback=task_tool_call,
                tool_output_callback=task_tool_output,
                usage_callback=self._usage_callback(task.task_id),
                response_format=self._task_response_format(task),
            )
            self._emit(
                "task_response_retry",
                {"content": str(output)[-100000:]},
                task.task_id,
            )
            result = TaskResult.from_agent_output(task, output)
        result.files_changed = list(dict.fromkeys(files_changed))
        recorded_checks = list(checks_run)
        result.checks_run = list(dict.fromkeys(recorded_checks))
        result.evidence = self._tool_backed_evidence(
            tool_outputs,
            files_changed=result.files_changed,
            checks_run=recorded_checks,
        )
        return self._validate_task_result(
            task,
            result,
            tool_calls=tool_calls,
            tool_outputs=tool_outputs,
            checks_run=recorded_checks,
            check_outputs=check_outputs,
        )

    @staticmethod
    def _tool_backed_evidence(
        tool_outputs: list[tuple[str, str]],
        *,
        files_changed: list[str],
        checks_run: list[str],
    ) -> list[str]:
        evidence = [f"recorded file change: {path}" for path in files_changed]
        check_index = 0
        for tool_name, output in tool_outputs:
            if not output or output.startswith(("Error:", "Error executing tool:")):
                continue
            first_line = output.splitlines()[0][:300]
            if tool_name == "check_runner" and check_index < len(checks_run):
                evidence.append(f"check `{checks_run[check_index]}`: {first_line}")
                check_index += 1
            else:
                evidence.append(f"{tool_name} returned: {first_line}")
        return list(dict.fromkeys(evidence))

    @staticmethod
    def _validate_task_result(
        task: MissionTask,
        result: TaskResult,
        *,
        tool_calls: list[str],
        tool_outputs: list[tuple[str, str]],
        checks_run: list[str],
        check_outputs: list[str],
    ) -> TaskResult:
        criteria_problems = MissionController._criterion_evidence_problems(
            task, result, tool_outputs
        )
        if result.status is not TaskStatus.COMPLETED:
            problems = list(criteria_problems)
            if task.role is MissionRole.VERIFIER and result.verdict == "fail":
                if "check_runner" not in tool_calls or not checks_run:
                    problems.append("verifier failed without running a check")
                if not result.evidence:
                    problems.append("verifier failure has no tool-backed evidence")
                if len(check_outputs) < len(checks_run):
                    problems.append("one or more checks have no recorded output")
                if any(not output.startswith("exit_code=") for output in check_outputs):
                    problems.append("one or more checks did not execute")
            if problems:
                if task.role is MissionRole.VERIFIER:
                    result.verdict = None
                existing = f"{result.error}; " if result.error else ""
                result.error = existing + "; ".join(problems)
            return result

        problems = list(criteria_problems)
        if not tool_calls:
            problems.append("no repository tools were used")
        elif not any(
            output and not output.startswith(("Error:", "Error executing tool:"))
            for _, output in tool_outputs
        ):
            problems.append("no repository tool completed successfully")
        if not result.evidence:
            problems.append("task has no tool-backed evidence")
        if task.role is MissionRole.WORKER:
            if not result.files_changed:
                problems.append("worker completed without a recorded file change")
            if not checks_run:
                problems.append("worker completed without running a check")
        if task.role is MissionRole.VERIFIER:
            if "check_runner" not in tool_calls or not checks_run:
                problems.append("verifier completed without running a check")
            if result.verdict != "pass":
                problems.append("completed verifier did not return verdict=pass")

        latest_outcomes: dict[str, str] = {}
        for command, output in zip(checks_run, check_outputs):
            latest_outcomes[command] = output
        if checks_run and len(check_outputs) < len(checks_run):
            problems.append("one or more checks have no recorded output")
        failed_checks = [
            command
            for command, output in latest_outcomes.items()
            if not output.startswith("exit_code=0\n")
        ]
        if failed_checks and task.role is not MissionRole.SCOUT:
            problems.append("latest check failed: " + ", ".join(failed_checks))

        if problems:
            result.status = TaskStatus.FAILED
            result.error = "; ".join(problems)
            if task.role is MissionRole.VERIFIER:
                result.verdict = "fail"
        return result

    @staticmethod
    def _criterion_evidence_problems(
        task: MissionTask,
        result: TaskResult,
        tool_outputs: list[tuple[str, str]],
    ) -> list[str]:
        expected = {
            item["criterion_id"] for item in MissionController._criterion_contract(task)
        }
        provided = set(result.criteria_evidence)
        problems = []
        missing = sorted(expected - provided)
        unknown = sorted(provided - expected)
        if missing:
            problems.append("missing criterion evidence keys: " + ", ".join(missing))
        if unknown:
            problems.append("unknown criterion evidence keys: " + ", ".join(unknown))

        valid_evidence = {
            item.strip()
            for item in result.evidence
            if MissionController._is_specific_evidence(item)
        }
        for _, output in tool_outputs:
            if not output or output.startswith(("Error:", "Error executing tool:")):
                continue
            valid_evidence.update(
                line.strip()
                for line in output.splitlines()
                if MissionController._is_specific_evidence(line)
            )

        for criterion_id in sorted(expected & provided):
            items = result.criteria_evidence[criterion_id]
            requires_evidence = (
                result.status is TaskStatus.COMPLETED
                or task.role is MissionRole.VERIFIER
            )
            if requires_evidence and not items:
                problems.append(f"{criterion_id} has no evidence")
            invalid = [item for item in items if item.strip() not in valid_evidence]
            if invalid:
                problems.append(
                    f"{criterion_id} contains evidence not found in successful tool output"
                )
        return problems

    @staticmethod
    def _is_specific_evidence(value: str) -> bool:
        cleaned = str(value).strip()
        return len(cleaned) >= 8 and cleaned not in {
            "File Content:",
            "No matches found.",
            "exit_code=0",
        }

    @staticmethod
    def _criterion_contract(task: MissionTask) -> list[dict[str, str]]:
        return [
            {
                "criterion_id": f"{task.task_id}:criterion:{index}",
                "description": description,
            }
            for index, description in enumerate(task.acceptance_criteria, start=1)
        ]

    @staticmethod
    def _needs_structured_retry(task: MissionTask, result: TaskResult) -> bool:
        error = result.error or ""
        structural_error = error.startswith(
            (
                "task response was not valid structured JSON",
                "task response missing required fields",
                "invalid task status",
                "verifier did not return verdict=pass or verdict=fail",
            )
        )
        expected = {
            item["criterion_id"] for item in MissionController._criterion_contract(task)
        }
        return structural_error or set(result.criteria_evidence) != expected

    @staticmethod
    def _task_response_format(task: MissionTask) -> dict[str, Any]:
        criterion_ids = [
            item["criterion_id"] for item in MissionController._criterion_contract(task)
        ]
        properties: dict[str, Any] = {
            "status": {
                "type": "string",
                "enum": ["completed", "failed", "blocked", "cancelled"],
            },
            "summary": {"type": "string"},
            "files_changed": {"type": "array", "items": {"type": "string"}},
            "checks_run": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "criteria_evidence": {
                "type": "object",
                "properties": {
                    criterion_id: {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                    for criterion_id in criterion_ids
                },
                "required": criterion_ids,
                "additionalProperties": False,
            },
            "remaining_risks": {"type": "array", "items": {"type": "string"}},
            "error": {"type": ["string", "null"]},
        }
        required = list(properties)
        if task.role is MissionRole.VERIFIER:
            properties["verdict"] = {
                "type": "string",
                "enum": ["pass", "fail"],
            }
            required.append("verdict")
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "mission_task_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    def _task_context(self, task: MissionTask) -> str:
        prior = [result.to_dict() for result in self.results.values()]
        extra = ""
        if task.role is MissionRole.VERIFIER:
            extra = (
                "\nMission-only diff captured from immediately before each mission "
                f"edit:\n{self._mission_diff()}"
            )
        criteria = self._criterion_contract(task)
        return (
            "Your assigned task below is authoritative. You are a role agent, not "
            "the mission orchestrator. Do not dispatch agents, repeat the mission "
            "lifecycle, or merely describe what you intend to do. Use your provided "
            "repository tools now and finish only this assignment.\n"
            f"Assigned task: {json.dumps(task.to_dict())}\n"
            f"Acceptance criteria contract: {json.dumps(criteria)}\n"
            f"Overall mission context: {self.goal}\n"
            f"Prior structured results: {json.dumps(prior)}{extra}\n"
            "Return one JSON object with status, summary, files_changed, checks_run, "
            "evidence, criteria_evidence, remaining_risks, and error. The controller "
            "independently replaces files_changed, checks_run, and evidence with its "
            "recorded telemetry, so never invent values. criteria_evidence must contain "
            "every criterion_id above. For completed work, each value must contain at "
            "least one exact, specific line copied from a successful repository tool "
            "output. Failed or blocked work may use an empty list where proof is "
            "unavailable. Status must be exactly completed, failed, blocked, or "
            "cancelled. A verifier must also return verdict=pass or verdict=fail. Never "
            "report completed or pass without criterion-level tool evidence."
        )

    def _capture_file_baseline(self, path: str) -> None:
        resolved = Path(path).resolve()
        relative = os.path.relpath(resolved, self.cwd)
        with self._lock:
            if relative in self._file_baselines:
                return
            try:
                self._file_baselines[relative] = (
                    resolved.read_bytes() if resolved.exists() else None
                )
            except OSError:
                self._file_baselines[relative] = None

    def _mission_diff(self) -> str:
        chunks = []
        for relative, before in sorted(self._file_baselines.items()):
            path = Path(self.cwd, relative)
            try:
                after = path.read_bytes() if path.exists() else None
            except OSError as exc:
                chunks.append(f"Unable to read {relative}: {exc}")
                continue
            if before == after:
                continue
            if b"\0" in (before or b"") or b"\0" in (after or b""):
                chunks.append(f"Binary file changed: {relative}")
                continue
            before_lines = (
                (before or b"")
                .decode("utf-8", errors="replace")
                .splitlines(keepends=True)
            )
            after_lines = (
                (after or b"")
                .decode("utf-8", errors="replace")
                .splitlines(keepends=True)
            )
            chunks.extend(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"a/{relative}" if before is not None else "/dev/null",
                    tofile=f"b/{relative}" if after is not None else "/dev/null",
                    lineterm="",
                )
            )
        return ("\n".join(chunks) or "No recorded mission file changes.")[-100000:]

    def _transition(
        self,
        phase: MissionPhase,
        status: MissionStatus,
        summary: str | None = None,
        repair_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.status = status
        event = self.store.transition(
            self.mission_id, phase, status, summary, repair_count
        )
        self._deliver(event)

    def _terminal(self, status: MissionStatus, summary: str) -> None:
        self._transition(MissionPhase.TERMINAL, status, summary, self.repair_count)

    def _emit(
        self, event_type: str, payload: dict[str, Any], task_id: str | None = None
    ):
        event = self.store.append_event(
            MissionEvent(self.mission_id, event_type, payload, task_id)
        )
        self._deliver(event)

    def _deliver(self, event: MissionEvent) -> None:
        if not self.event_callback:
            return
        with self._event_lock:
            self.event_callback(event)

    def _usage_callback(self, task_id: str | None = None):
        def record(payload: dict[str, Any]) -> None:
            event = self.store.record_usage(self.mission_id, payload, task_id)
            self._deliver(event)

        return record

    @staticmethod
    def _agent_identity(agent) -> tuple[str | None, str | None]:
        service = getattr(agent, "llm_service", None)
        provider = getattr(service, "active_provider_name", None)
        model = getattr(agent, "model", None)
        return provider, model

    def _wrap_tool_callback(self, callback):
        def wrapped(tool_name, label, args):
            if callback:
                callback(tool_name=tool_name, label=label, args=args)
            if (
                tool_name == "ask_question"
                and self.phase is not MissionPhase.AWAITING_INPUT
            ):
                self._phase_before_input = self.phase
                self._transition(
                    MissionPhase.AWAITING_INPUT, MissionStatus.AWAITING_INPUT
                )

        return wrapped

    def _mission_system_prompt(self, role_prompt: str) -> str:
        project_context = self._project_instructions.strip()
        mission_rules = (
            "<mission_role>\n"
            f"{role_prompt}\n"
            "Project instructions above remain authoritative. Do not edit AGENTS.md, "
            "coding-agent configuration, skill files, settings, or other instruction "
            "files unless the assigned task and user explicitly require it.\n"
            "</mission_role>"
        )
        return (
            f"{project_context}\n\n{mission_rules}"
            if project_context
            else mission_rules
        )

    def _initial_brief(self) -> str:
        return f"Start this mission and enforce the complete lifecycle. Objective: {self.goal}"

    def _orchestrator_prompt(self) -> str:
        return """You coordinate a mission but never inspect or edit files yourself.
Use mission_dispatch for every batch. First dispatch one or more Scouts. Scouts and
Verifiers must use file_scope=[]. After Scout results, plan and dispatch Workers with
non-empty repository-relative file scopes and one or more concrete, observable
acceptance criteria per task. Prefer non-overlapping Worker scopes; when overlap is
unavoidable, express ordering with dependencies and let the controller serialize them.
If no changes are needed, dispatch verification directly. Then dispatch exactly one
Verifier whose acceptance criteria cover the mission objective and every implemented
change. Copy every Worker acceptance criterion verbatim into the Verifier task and add
an objective-level criterion. If verification fails, dispatch one focused repair Worker batch and a fresh
Verifier. A repair Worker may depend on the failed Verifier because its failure is the
repair input. Never claim completion yourself. Ask a clarifying question only when a
missing user choice materially blocks safe progress and repository evidence cannot
resolve it. Continue until the controller returns a terminal state."""

    @staticmethod
    def _role_prompt(role: MissionRole) -> str:
        capability = {
            MissionRole.SCOUT: (
                "Investigate only. You cannot edit source files. Use file_reader or "
                "repo_search before answering and copy specific tool-output lines into "
                "the required criterion evidence."
            ),
            MissionRole.WORKER: (
                "Implement only within the declared file scope. Use file_editor or "
                "file_creator, then run an allowlisted check before reporting completed. "
                "Copy specific successful tool-output lines into criterion evidence."
            ),
            MissionRole.VERIFIER: (
                "Validate independently. You cannot edit source files. Inspect the "
                "repository and run the acceptance checks with check_runner before "
                "returning pass or fail. Copy exact output lines that prove each "
                "criterion; do not rely on the Verifier summary as evidence."
            ),
        }[role]
        return (
            f"You are the mission {role.value}, not the orchestrator. {capability} "
            "Use only provided tools. Do not dispatch other agents or return a plan."
        )
