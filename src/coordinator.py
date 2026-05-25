import asyncio
import json
import os
import sys
import time
from typing import Any, Callable, Literal, Optional

from src.llm_service.service import LLMService
from src.constants import DEFAULT_MODEL
from src.models.llm import available_models
from src.tools.tool_registry import ToolRegistry
from src.prompts import PromptManager
from src.agent import Agent

MAX_ITERATIONS = 50
COORDINATOR_MODEL = DEFAULT_MODEL
WORKER_ROLES = ("explorer", "implementer", "verifier", "summarizer")
COORDINATOR_WORKER_MAX_ITERATIONS = 12
COORDINATOR_WORKER_EXCLUDED_TOOLS = ("subagent", "todo_write", "todo_update", "todo_read", "ask_question")


def _debug(message: str) -> None:
    if os.environ.get("TERMINUS_DEBUG"):
        print(message, file=sys.stderr)


class WorkerHandle:
    """Handle to a running background worker."""
    def __init__(
        self,
        worker_id: str,
        name: str,
        description: str,
        role: str,
        task: asyncio.Task,
        stop_event: asyncio.Event,
        worker_event_callback=None,
    ):
        self.worker_id = worker_id
        self.name = name
        self.description = description
        self.role = role
        self.task = task
        self.stop_event = stop_event
        self.notifications: list[dict] = []
        self.final_response: str | None = None
        self.result_envelope: dict[str, Any] | None = None
        self.last_notification: dict[str, Any] | None = None
        self.result_consumed = False
        self.status = "running"  # running | completed | failed | stopped
        self._worker_event_callback = worker_event_callback

    def to_dict(self):
        return {
            "id": self.worker_id,
            "name": self.name,
            "description": self.description,
            "role": self.role,
            "status": self.status,
            "notification_count": len(self.notifications),
            "last_notification": self.last_notification,
            "result_consumed": self.result_consumed,
        }

    def _on_notification(self, notification: dict):
        self.notifications.append(notification)
        self.last_notification = notification
        if self._worker_event_callback:
            self._worker_event_callback(
                "worker_notification",
                {
                    "worker_id": self.worker_id,
                    "status": notification.get("status", ""),
                    "summary": notification.get("summary", ""),
                    "final_response": notification.get("final_response"),
                    "timestamp": notification.get("timestamp", time.time()),
                },
            )

    def _on_done(self, outcome: dict):
        self.status = outcome.get("status", "completed")
        self.final_response = outcome.get("result", "")
        self.result_envelope = outcome.get("result_envelope")
        if self._worker_event_callback:
            self._worker_event_callback(
                "worker_status",
                {
                    "worker_id": self.worker_id,
                    "status": self.status,
                    "result": self.final_response,
                    "result_envelope": self.result_envelope,
                    "timestamp": outcome.get("timestamp", time.time()),
                },
            )

    def _on_status(self, message: str, is_thinking: bool = False, **kwargs):
        if not self._worker_event_callback:
            return
        if is_thinking:
            self._worker_event_callback(
                "worker_detail",
                {
                    "worker_id": self.worker_id,
                    "detail_type": "thinking",
                    "content": message,
                    "timestamp": kwargs.get("timestamp", time.time()),
                },
            )
        else:
            self._worker_event_callback(
                "worker_notification",
                {
                    "worker_id": self.worker_id,
                    "status": "running",
                    "summary": message,
                    "timestamp": kwargs.get("timestamp", time.time()),
                },
            )

    def _on_tool_call(self, tool_name: str, label: str, args: dict):
        if self._worker_event_callback:
            self._worker_event_callback(
                "worker_detail",
                {
                    "worker_id": self.worker_id,
                    "detail_type": "tool_call",
                    "content": label,
                    "tool_name": tool_name,
                    "args": args,
                    "timestamp": time.time(),
                },
            )

    def _on_tool_output(self, tool_name: str, output: str):
        if self._worker_event_callback:
            self._worker_event_callback(
                "worker_detail",
                {
                    "worker_id": self.worker_id,
                    "detail_type": "tool_output",
                    "content": str(output),
                    "tool_name": tool_name,
                    "timestamp": time.time(),
                },
            )


class Coordinator:
    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_iterations: int = MAX_ITERATIONS,
        worker_event_callback: Optional[Callable] = None,
    ):
        _debug("[Coordinator] Initializing...")
        self.llm_service = LLMService()
        self.tools = ToolRegistry()
        self.max_iterations = max_iterations
        self.context: list[dict[str, Any]] = []
        self.iteration: int = 0
        self._workers: dict[str, WorkerHandle] = {}
        self._worker_counter: int = 0
        self._worker_event_callback = worker_event_callback
        self._active_model: str = DEFAULT_MODEL
        self._available_models = available_models
        self._digest_marker = "Worker state digest:"
        self._require_worker_await_guard = False
        self._require_worker_result_guard = False

        self._worker_shared_prompt: str | None = None

        if system_prompt is None:
            prompt_manager = PromptManager()
            system_prompt = prompt_manager.get_coordinator_prompt()
            self._worker_shared_prompt = prompt_manager.get_system_prompt()

        self.system_prompt = system_prompt
        self._add_system_message()
        _debug("[Coordinator] Ready.")

    def _add_system_message(self) -> None:
        self.context.append({"role": "system", "content": self.system_prompt})

    def _add_user_message(self, content: str) -> None:
        self.context.append({"role": "user", "content": content})

    def _add_assistant_message(self, content: str, tool_calls: Optional[list] = None) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        self.context.append(msg)

    def _add_tool_message(self, tool_call, output: str) -> None:
        self.context.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": output,
            }
        )

    def reset(self) -> None:
        self.context.clear()
        self.iteration = 0
        self._workers.clear()
        self._worker_counter = 0
        self._require_worker_await_guard = False
        self._require_worker_result_guard = False
        self._add_system_message()

    async def areset(self) -> None:
        """Async-aware reset (cancels running workers before clearing state)."""
        await self._cancel_all_workers()
        self.reset()

    def _next_worker_id(self) -> str:
        self._worker_counter += 1
        return f"worker_{self._worker_counter}"

    def _build_worker_system_prompt(self, role: str) -> str:
        role_instructions = {
            "explorer": "Focus on investigation, code reading, and identifying the most relevant facts quickly.",
            "implementer": "Focus on making or describing concrete code changes and implementation steps.",
            "verifier": "Focus on validation, regression risk, missing tests, and whether the output actually works.",
            "summarizer": "Focus on condensing evidence from prior work into concise, decision-ready output.",
        }
        role_instruction = role_instructions.get(role, role_instructions["explorer"])
        worker_prompt = (
            "You are a specialized background worker for the coordinator.\n"
            f"Your role is `{role}`. {role_instruction}\n\n"
            "Operate within the task boundaries the coordinator gives you.\n"
            "Execute the assigned task directly. Do not re-plan the overall problem.\n"
            "Do not delegate to other agents or tools that ask for delegation.\n"
            "Do not create or manage todo lists.\n"
            "Do not ask the user clarifying questions. If the task is ambiguous, make the smallest reasonable assumption and continue; if that is unsafe, return blocked.\n"
            "If your role is `implementer`, edit only the files or directories assigned by the coordinator, avoid unrelated changes, and report every changed path in evidence.\n"
            "If you make edits, verify them when practical and include the command or check result in evidence.\n"
            "Stop as soon as you have enough evidence for a useful handoff. Prefer finishing quickly over exhaustive exploration.\n"
            "When blocked, send a notification that clearly says you are blocked and what decision or input is needed.\n"
            "Keep your working context isolated. Do not assume the coordinator saw your intermediate reasoning.\n"
        )
        output_contract = (
            "Your final response MUST be valid JSON only. Do not include markdown fences, prose before the JSON, or prose after the JSON.\n"
            "Your final response MUST be a compact handoff with exactly these top-level keys:\n"
            "- what_was_done: string describing the completed work\n"
            "- evidence: array of strings or objects with concrete proof, file paths, commands, outputs, or findings\n"
            "- unresolved_risks: array of strings describing remaining risks, unknowns, or blockers; use [] if none\n"
            "- exact_next_step: string describing the single next action the coordinator should take\n"
            "- status: one of completed, blocked, failed, partial\n"
            "If you have enough information, stop using tools and emit the JSON immediately."
        )
        if not self._worker_shared_prompt:
            return worker_prompt + output_contract

        return (
            worker_prompt
            + "\n\nShared coding-agent and project instructions follow. The worker-specific instructions and output contract below override them when they conflict.\n\n"
            + self._worker_shared_prompt
            + "\n\nWorker-specific final output contract follows and takes precedence over all shared instructions.\n\n"
            + output_contract
        )

    def _build_worker_task_prompt(self, prompt: str, role: str) -> str:
        return (
            f"Task role: {role}\n\n"
            "Complete the task below and return only the required JSON handoff.\n"
            "Use tools only when they materially improve the answer. Once you have enough evidence, stop and emit JSON.\n\n"
            "Task:\n"
            f"{prompt.strip()}\n\n"
            "Return JSON with exactly this shape:\n"
            "{\n"
            '  "what_was_done": "string",\n'
            '  "evidence": ["..."],\n'
            '  "unresolved_risks": [],\n'
            '  "exact_next_step": "string",\n'
            '  "status": "completed"\n'
            "}"
        )

    def _normalize_worker_result(
        self,
        worker_id: str,
        role: str,
        raw_result: Any,
        terminal_status: str,
    ) -> dict[str, Any]:
        parsed: dict[str, Any] | None = None
        raw_text = raw_result.strip() if isinstance(raw_result, str) else ""
        if isinstance(raw_result, str):
            try:
                candidate = json.loads(raw_result)
                if isinstance(candidate, dict):
                    parsed = candidate
            except json.JSONDecodeError:
                parsed = None
        elif isinstance(raw_result, dict):
            parsed = raw_result

        envelope: dict[str, Any] = {}
        if parsed:
            envelope.update(parsed)

        status = envelope.get("status")
        max_iterations_hit = raw_text == "Max iterations reached. Process terminated."
        malformed_handoff = terminal_status == "completed" and parsed is None
        if status not in {"completed", "blocked", "failed", "partial"}:
            if terminal_status == "failed":
                status = "failed"
            elif terminal_status == "completed" and (max_iterations_hit or malformed_handoff):
                status = "partial"
            else:
                status = "completed" if terminal_status == "completed" else "partial"

        what_was_done = envelope.get("what_was_done")
        if not isinstance(what_was_done, str) or not what_was_done.strip():
            legacy_summary = envelope.get("summary")
            if isinstance(legacy_summary, str) and legacy_summary.strip():
                what_was_done = legacy_summary
            elif max_iterations_hit:
                what_was_done = (
                    f"Worker {worker_id} hit the coordinator worker iteration cap before producing a valid handoff."
                )
            elif malformed_handoff:
                what_was_done = (
                    f"Worker {worker_id} finished without returning the required JSON handoff."
                )
            elif raw_text:
                what_was_done = raw_text
            else:
                what_was_done = f"Worker {worker_id} finished with status {terminal_status}."

        evidence = envelope.get("evidence")
        if not isinstance(evidence, list):
            legacy_artifacts = envelope.get("artifacts")
            legacy_findings = envelope.get("findings")
            evidence = []
            if isinstance(legacy_artifacts, list):
                evidence.extend(legacy_artifacts)
            elif legacy_artifacts:
                evidence.append(legacy_artifacts)
            if isinstance(legacy_findings, list):
                evidence.extend(legacy_findings)
            elif legacy_findings:
                evidence.append(legacy_findings)

        unresolved_risks = envelope.get("unresolved_risks")
        if not isinstance(unresolved_risks, list):
            unresolved_risks = []
        if max_iterations_hit and not unresolved_risks:
            unresolved_risks = [
                "Worker exhausted its coordinator iteration budget before finishing cleanly."
            ]
        elif malformed_handoff and not unresolved_risks:
            unresolved_risks = [
                "Worker returned plain text instead of the required JSON handoff."
            ]
        if status in {"blocked", "failed", "partial"} and not unresolved_risks:
            unresolved_risks = [what_was_done]

        exact_next_step = envelope.get("exact_next_step")
        if not isinstance(exact_next_step, str) or not exact_next_step.strip():
            legacy_next_action = envelope.get("recommended_next_action")
            if isinstance(legacy_next_action, str) and legacy_next_action.strip():
                exact_next_step = legacy_next_action
            elif max_iterations_hit:
                exact_next_step = "Retry with a narrower task or handle the work locally."
            elif malformed_handoff:
                exact_next_step = "Retry with a narrower task and require the compact JSON handoff."
            elif status == "blocked":
                exact_next_step = "Decide how to unblock this worker."
            elif status == "failed":
                exact_next_step = "Retry with a narrower task or handle the work locally."
            elif status == "partial":
                exact_next_step = "Review partial output and decide whether more work is needed."
            else:
                exact_next_step = "Synthesize this handoff into the coordinator response."

        # Keep legacy fields populated so existing coordinator synthesis and UI
        # consumers continue to work while new callers use the explicit handoff.
        summary = what_was_done
        artifacts = envelope.get("artifacts")
        if not isinstance(artifacts, list):
            artifacts = []
        findings = envelope.get("findings")
        if not isinstance(findings, list):
            findings = evidence
        next_action = exact_next_step

        if not next_action:
            if status == "blocked":
                next_action = "Decide how to unblock this worker."
            elif status == "failed":
                next_action = "Retry with a narrower task or handle the work locally."
            elif status == "partial":
                next_action = "Review partial output and decide whether more work is needed."
            else:
                next_action = "Synthesize this result into the coordinator response."

        normalized = {
            "handoff": {
                "what_was_done": what_was_done,
                "evidence": evidence,
                "unresolved_risks": unresolved_risks,
                "exact_next_step": exact_next_step,
            },
            "what_was_done": what_was_done,
            "evidence": evidence,
            "unresolved_risks": unresolved_risks,
            "exact_next_step": exact_next_step,
            "summary": summary,
            "artifacts": artifacts,
            "findings": findings,
            "status": status,
            "recommended_next_action": next_action,
            "provenance": {
                "worker_id": worker_id,
                "role": role,
            },
        }
        return normalized

    def _coerce_worker_result_json(
        self,
        worker_id: str,
        role: str,
        raw_result: Any,
        terminal_status: str,
    ) -> tuple[str, dict[str, Any]]:
        """Return a JSON handoff string plus the normalized coordinator envelope."""
        envelope = self._normalize_worker_result(worker_id, role, raw_result, terminal_status)
        handoff = envelope.get("handoff") if isinstance(envelope.get("handoff"), dict) else {}
        json_handoff = {
            "what_was_done": handoff.get("what_was_done", envelope.get("what_was_done", "")),
            "evidence": handoff.get("evidence", envelope.get("evidence", [])),
            "unresolved_risks": handoff.get("unresolved_risks", envelope.get("unresolved_risks", [])),
            "exact_next_step": handoff.get("exact_next_step", envelope.get("exact_next_step", "")),
            "status": envelope.get("status", terminal_status),
        }
        result_json = json.dumps(json_handoff, ensure_ascii=True)
        return result_json, envelope

    def _worker_result_payload(self, handle: WorkerHandle, *, include_done: bool | None = None) -> dict[str, Any]:
        result = {
            "id": handle.worker_id,
            "name": handle.name,
            "role": handle.role,
            "status": handle.status,
            "result": handle.result_envelope,
            "raw_result": handle.final_response,
            "provenance": {
                "worker_id": handle.worker_id,
                "worker_name": handle.name,
                "role": handle.role,
            },
        }
        if include_done is not None:
            result["done"] = include_done
        return result

    def _consume_worker_result(self, handle: WorkerHandle) -> dict[str, Any]:
        handle.result_consumed = True
        return self._worker_result_payload(handle)

    def _build_worker_digest(self) -> str | None:
        if not self._workers:
            return None

        handles = list(self._workers.values())
        running = [h for h in handles if h.status == "running"]
        blocked = [
            h for h in handles
            if (h.result_envelope and h.result_envelope.get("status") == "blocked")
            or ((h.last_notification or {}).get("status", "").lower() == "blocked")
        ]
        failures = [h for h in handles if h.status == "failed"]
        completed_pending = [
            h for h in handles
            if h.status == "completed"
            and h.result_envelope is not None
            and not h.result_consumed
        ]
        failed_pending = [
            h for h in handles
            if h.status in ("failed", "stopped")
            and h.result_envelope is not None
            and not h.result_consumed
        ]

        unresolved_actions = []
        if failures:
            unresolved_actions.append(f"{len(failures)} failed needs retry decision")
        if blocked:
            unresolved_actions.append(f"{len(blocked)} blocked needs unblock decision")
        if completed_pending:
            unresolved_actions.append(f"{len(completed_pending)} completed awaiting synthesis")
        if failed_pending:
            unresolved_actions.append(f"{len(failed_pending)} terminal failures awaiting synthesis")
        if running:
            unresolved_actions.append(f"{len(running)} still running")

        summary_line = (
            f"{len(running)} running, {len(blocked)} blocked, "
            f"{len(completed_pending)} completed awaiting synthesis, "
            f"{len(failures)} failed needing triage, "
            f"{len(failed_pending)} failed or stopped awaiting synthesis."
        )
        if unresolved_actions:
            summary_line += " Unresolved actions: " + "; ".join(unresolved_actions) + "."

        lines = [self._digest_marker, summary_line]
        for handle in handles:
            line = (
                f"- {handle.worker_id} [{handle.role}] {handle.name}: status={handle.status}, "
                f"notifications={len(handle.notifications)}, consumed={handle.result_consumed}"
            )
            if handle.last_notification:
                note_status = handle.last_notification.get("status", "")
                note_summary = handle.last_notification.get("summary", "")
                if note_status or note_summary:
                    line += f", latest_note={note_status or 'n/a'}:{note_summary[:120]}"
            lines.append(line)

            if handle.result_envelope and not handle.result_consumed:
                result = handle.result_envelope
                handoff = result.get("handoff") if isinstance(result.get("handoff"), dict) else {}
                evidence = handoff.get("evidence", result.get("evidence", result.get("findings", [])))
                evidence_preview = evidence[:2] if isinstance(evidence, list) else [evidence]
                risks = handoff.get("unresolved_risks", result.get("unresolved_risks", []))
                lines.append(
                    f"  pending_handoff from {handle.worker_id}: status={result.get('status')} what_was_done={str(handoff.get('what_was_done', result.get('what_was_done', result.get('summary', ''))))[:180]}"
                )
                if evidence_preview:
                    lines.append(f"  evidence_preview: {json.dumps(evidence_preview, ensure_ascii=True)[:220]}")
                if risks:
                    lines.append(f"  unresolved_risks: {json.dumps(risks, ensure_ascii=True)[:220]}")
                lines.append(
                    f"  exact_next_step: {str(handoff.get('exact_next_step', result.get('exact_next_step', result.get('recommended_next_action', ''))))[:180]}"
                )
        return "\n".join(lines)

    def _build_iteration_messages(self) -> list[dict[str, Any]]:
        """Build the prompt for one coordinator turn without bloating history."""
        messages = list(self.context)
        digest = self._build_worker_digest()
        if digest:
            messages.append({"role": "system", "content": digest})
        running = self._get_running_workers()
        if self._require_worker_await_guard and running:
            worker_names = ", ".join(f"{w['id']} ({w['name']})" for w in running)
            messages.append({
                "role": "system",
                "content": (
                    f"You have {len(running)} worker(s) still running: {worker_names}. "
                    "You must use await_workers to collect their results before returning your final answer. "
                    "Do not end the conversation while workers are active."
                ),
            })
        elif not running:
            self._require_worker_await_guard = False
        pending_terminal = self._get_unconsumed_terminal_workers()
        if self._require_worker_result_guard and pending_terminal:
            worker_names = ", ".join(f"{w.worker_id} ({w.name})" for w in pending_terminal)
            messages.append({
                "role": "system",
                "content": (
                    f"You have {len(pending_terminal)} completed worker handoff(s) awaiting synthesis: {worker_names}. "
                    "You must call await_workers or get_worker_result to collect their structured results before returning your final answer. "
                    "Do not return an empty or generic final answer while worker results are unconsumed."
                ),
            })
        elif not pending_terminal:
            self._require_worker_result_guard = False
        return messages

    async def spawn_worker(self, name: str, description: str, prompt: str, role: Literal["explorer", "implementer", "verifier", "summarizer"] = "explorer") -> str:
        """Spawn a background worker agent and return its ID immediately.

        The worker runs independently in a background asyncio.Task so this
        coroutine returns as soon as the task is scheduled.
        """
        worker_id = self._next_worker_id()

        worker_tool_registry = ToolRegistry(
            exclude_tool_names=COORDINATOR_WORKER_EXCLUDED_TOOLS
        )
        agent = Agent(
            id=worker_id,
            name=name,
            description=description,
            system_prompt=self._build_worker_system_prompt(role),
            notification_callback=lambda n: handle._on_notification(n),
            tool_registry=worker_tool_registry,
            max_iterations=COORDINATOR_WORKER_MAX_ITERATIONS,
            execution_mode="coordinator_worker",
        )
        if self._active_model:
            target_model = next(
                (m for m in agent.available_models if m.name == self._active_model),
                None,
            )
            if target_model:
                agent.switch_model(target_model)
        agent.add_system_message()

        stop_event = asyncio.Event()

        async def _worker_task():
            try:
                result = await agent.arun(
                    user_message=self._build_worker_task_prompt(prompt, role),
                    stop_event=stop_event,
                    status_callback=lambda msg, is_thinking=False, **kwargs: handle._on_status(msg, is_thinking, **kwargs),
                    tool_call_callback=lambda tool_name, label, args: handle._on_tool_call(tool_name, label, args),
                    tool_output_callback=lambda tool_name, output: handle._on_tool_output(tool_name, output),
                )
                result_json, result_envelope = self._coerce_worker_result_json(
                    worker_id,
                    role,
                    result,
                    "completed",
                )
                return {
                    "status": "completed",
                    "result": result_json,
                    "result_envelope": result_envelope,
                    "timestamp": time.time(),
                }
            except asyncio.CancelledError:
                stopped_result = "Worker was stopped."
                result_json, result_envelope = self._coerce_worker_result_json(
                    worker_id,
                    role,
                    stopped_result,
                    "stopped",
                )
                return {
                    "status": "stopped",
                    "result": result_json,
                    "result_envelope": result_envelope,
                    "timestamp": time.time(),
                }
            except Exception as e:
                failure_result = f"Worker failed: {e}"
                result_json, result_envelope = self._coerce_worker_result_json(
                    worker_id,
                    role,
                    failure_result,
                    "failed",
                )
                return {
                    "status": "failed",
                    "result": result_json,
                    "result_envelope": result_envelope,
                    "timestamp": time.time(),
                }

        task = asyncio.create_task(_worker_task())
        handle = WorkerHandle(
            worker_id,
            name,
            description,
            role,
            task,
            stop_event,
            self._worker_event_callback,
        )
        self._workers[worker_id] = handle

        # Attach a done callback to capture the result
        def _task_done(t: asyncio.Task):
            if handle.status in {"completed", "failed", "stopped"}:
                return
        try:
            outcome = t.result()
        except asyncio.CancelledError:
            result_json, result_envelope = self._coerce_worker_result_json(
                handle.worker_id,
                handle.role,
                "Worker was stopped.",
                "stopped",
            )
            outcome = {
                "status": "stopped",
                "result": result_json,
                "result_envelope": result_envelope,
            }
        except Exception as e:
            failure_result = f"Worker failed: {e}"
            result_json, result_envelope = self._coerce_worker_result_json(
                handle.worker_id,
                handle.role,
                failure_result,
                "failed",
            )
            outcome = {
                "status": "failed",
                "result": result_json,
                "result_envelope": result_envelope,
            }
        handle._on_done(outcome)

        task.add_done_callback(_task_done)

        if self._worker_event_callback:
            self._worker_event_callback(
                "worker_spawned",
                {
                    "worker_id": worker_id,
                    "name": name,
                    "description": description,
                    "role": role,
                },
            )

        _debug(f"[Coordinator] Spawned worker {worker_id}: {name}")
        return worker_id

    def _materialize_done_worker(self, handle: WorkerHandle) -> None:
        """Populate handle result fields when a task completed before its callback ran."""
        if not handle.task.done() or handle.status in {"completed", "failed", "stopped"}:
            return
        try:
            outcome = handle.task.result()
        except asyncio.CancelledError:
            outcome = {
                "status": "stopped",
                "result": "Worker was stopped.",
                "result_envelope": self._normalize_worker_result(
                    handle.worker_id,
                    handle.role,
                    "Worker was stopped.",
                    "stopped",
                ),
                "timestamp": time.time(),
            }
        except Exception as exc:
            failure_result = f"Worker failed: {exc}"
            outcome = {
                "status": "failed",
                "result": failure_result,
                "result_envelope": self._normalize_worker_result(
                    handle.worker_id,
                    handle.role,
                    failure_result,
                    "failed",
                ),
                "timestamp": time.time(),
            }
        handle._on_done(outcome)

    async def spawn_workers(
        self,
        configs: list[dict],
    ) -> list[str]:
        """Spawn multiple workers concurrently and return their IDs.

        Example:
            ids = await coordinator.spawn_workers([
                {"name": "explorer", "description": "Explore src/", "prompt": "List all files in src/"},
                {"name": "linter",  "description": "Lint code",    "prompt": "Run ruff check"},
            ])
        """
        coros = [
            self.spawn_worker(
                name=c.get("name", "unnamed"),
                description=c.get("description", ""),
                prompt=c.get("prompt", ""),
                role=c.get("role", "explorer"),
            )
            for c in configs
        ]
        return await asyncio.gather(*coros)

    async def stop_worker(self, worker_id: str) -> str:
        """Stop a running worker."""
        handle = self._workers.get(worker_id)
        if not handle:
            return f"Worker {worker_id} not found."
        if handle.task.done():
            return f"Worker {worker_id} is already {handle.status}."
        if self._task_loop_closed(handle):
            self._mark_worker_abandoned(handle)
            return f"Worker {worker_id} could not be stopped because its event loop is closed."
        handle.status = "stopping"
        handle.stop_event.set()
        handle.task.cancel()
        return f"Worker {worker_id} stopped."

    async def _cancel_all_workers(self) -> None:
        """Cancel every running worker and wait for them to finish."""
        running = [h for h in self._workers.values() if not h.task.done()]
        if not running:
            return
        awaitable = []
        for h in running:
            h.status = "stopping"
            h.stop_event.set()
            if self._task_loop_closed(h):
                self._mark_worker_abandoned(h)
                continue
            h.task.cancel()
            if self._task_belongs_to_current_loop(h):
                awaitable.append(h.task)
        if awaitable:
            await asyncio.gather(*awaitable, return_exceptions=True)

    def _task_loop_closed(self, handle: WorkerHandle) -> bool:
        """Return True when a worker task belongs to an event loop that is gone."""
        try:
            return handle.task.get_loop().is_closed()
        except RuntimeError:
            return True

    def _task_belongs_to_current_loop(self, handle: WorkerHandle) -> bool:
        """Return True when the worker task can be awaited by this coroutine."""
        try:
            return handle.task.get_loop() is asyncio.get_running_loop()
        except RuntimeError:
            return False

    def _mark_worker_abandoned(self, handle: WorkerHandle) -> None:
        """Record a terminal result for a worker that cannot progress anymore."""
        if handle.status in {"completed", "failed", "stopped"}:
            return
        failure_result = "Worker stopped because its event loop is closed."
        handle._on_done(
            {
                "status": "failed",
                "result": failure_result,
                "result_envelope": self._normalize_worker_result(
                    handle.worker_id,
                    handle.role,
                    failure_result,
                    "failed",
                ),
                "timestamp": time.time(),
            }
        )

    def list_workers(self) -> list[dict]:
        """Return a list of all workers and their statuses."""
        return [w.to_dict() for w in self._workers.values()]

    def _get_running_workers(self) -> list[dict]:
        """Return a list of workers that are still running."""
        return [w.to_dict() for w in self._workers.values() if w.status == "running"]

    def _get_unconsumed_terminal_workers(self) -> list[WorkerHandle]:
        """Return completed/terminal workers whose final handoff has not been read."""
        return [
            w
            for w in self._workers.values()
            if w.status in {"completed", "failed", "stopped"}
            and w.result_envelope is not None
            and not w.result_consumed
        ]

    def _format_worker_results_fallback(self, handles: list[WorkerHandle]) -> str:
        """Build a useful final response if the coordinator model refuses to fetch results."""
        lines = ["Worker results:"]
        for handle in handles:
            result = handle.result_envelope or {}
            handoff = result.get("handoff") if isinstance(result.get("handoff"), dict) else {}
            what_was_done = handoff.get(
                "what_was_done",
                result.get("what_was_done", result.get("summary", handle.final_response or "")),
            )
            exact_next_step = handoff.get(
                "exact_next_step",
                result.get("exact_next_step", result.get("recommended_next_action", "")),
            )
            evidence = handoff.get("evidence", result.get("evidence", result.get("findings", [])))
            unresolved_risks = handoff.get("unresolved_risks", result.get("unresolved_risks", []))

            lines.append(f"- {handle.worker_id} ({handle.name}) [{result.get('status', handle.status)}]: {what_was_done}")
            if evidence:
                evidence_items = evidence if isinstance(evidence, list) else [evidence]
                for item in evidence_items[:3]:
                    lines.append(f"  evidence: {item}")
            if unresolved_risks:
                risk_items = unresolved_risks if isinstance(unresolved_risks, list) else [unresolved_risks]
                for item in risk_items[:3]:
                    lines.append(f"  risk: {item}")
            if exact_next_step:
                lines.append(f"  next: {exact_next_step}")
            handle.result_consumed = True
        return "\n".join(lines)

    def get_worker_result(self, worker_id: str) -> dict | None:
        """Get the final result of a worker if it has completed."""
        handle = self._workers.get(worker_id)
        if not handle:
            return None
        if handle.result_envelope is None and handle.final_response is None:
            return self._worker_result_payload(handle)
        return self._consume_worker_result(handle)

    async def await_workers(
        self,
        worker_ids: list[str],
        timeout: Optional[float] = None,
    ) -> list[dict]:
        """Wait for a specific set of workers to finish.

        Returns a list of result dicts (same shape as `get_worker_result`).
        Missing IDs are silently ignored.
        """
        wait_handles: list[WorkerHandle] = []
        immediate_handles: list[WorkerHandle] = []
        unavailable_handles: list[WorkerHandle] = []
        for wid in worker_ids:
            h = self._workers.get(wid)
            if not h:
                continue
            if h.task.done() or h.status in {"completed", "failed", "stopped"}:
                self._materialize_done_worker(h)
                immediate_handles.append(h)
            elif self._task_loop_closed(h):
                self._mark_worker_abandoned(h)
                immediate_handles.append(h)
            elif self._task_belongs_to_current_loop(h):
                wait_handles.append(h)
            else:
                unavailable_handles.append(h)
        if not wait_handles and not immediate_handles and not unavailable_handles:
            return []

        done: set[asyncio.Task] = set()
        pending: set[asyncio.Task] = set()
        if wait_handles:
            done, pending = await asyncio.wait(
                [h.task for h in wait_handles],
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
        pending_tasks = set(pending)
        results = []
        for handle in immediate_handles:
            payload = self._consume_worker_result(handle)
            payload["done"] = True
            results.append(payload)
        for handle in wait_handles:
            if handle.task in pending_tasks:
                results.append(
                    {
                        **self._worker_result_payload(handle, include_done=False),
                        "status": "timeout" if timeout is not None else handle.status,
                    }
                )
                continue
            payload = self._consume_worker_result(handle)
            payload["done"] = handle.task in done
            results.append(payload)
        for handle in unavailable_handles:
            results.append(
                {
                    **self._worker_result_payload(handle, include_done=False),
                    "status": "running_unavailable",
                    "error": "Worker is running on a different event loop and cannot be awaited from this turn.",
                }
            )
        return results

    async def await_all_workers(
        self,
        timeout: Optional[float] = None,
    ) -> list[dict]:
        """Wait for every tracked worker to finish."""
        return await self.await_workers(
            list(self._workers.keys()), timeout=timeout
        )

    @classmethod
    async def create(
        cls,
        system_prompt: Optional[str] = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> "Coordinator":
        """Async factory so callers can `await Coordinator.create()`."""
        # __init__ is intentionally kept sync-friendly; this factory
        # gives us a hook if we ever need async setup (e.g. lazy tool
        # registry initialisation, remote config fetching, etc.).
        return cls(system_prompt=system_prompt, max_iterations=max_iterations)

    def _apply_active_model(self, model_name: str) -> None:
        match = next(
            (m for m in self._available_models if m.name == model_name),
            None,
        )
        if not match:
            return
        provider = "groq" if match.provider == "groq" else "openrouter"
        self.llm_service.set_active_provider(provider)

    async def run(
        self,
        user_message: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
        status_callback: Optional[Callable[[str, bool], None]] = None,
        tool_call_callback: Optional[Callable[[str, str, dict], None]] = None,
        tool_output_callback: Optional[Callable[[str, str], None]] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> str:
        active_model = model or COORDINATOR_MODEL
        self._active_model = active_model
        self._apply_active_model(active_model)
        _debug(f"[Coordinator] Starting run: {user_message!r} (model={active_model})")
        stop_event = stop_event or asyncio.Event()
        if stop_event.is_set():
            _debug("[Coordinator] Stop event set at entry.")
            raise KeyboardInterrupt()

        self._add_user_message(user_message)
        self.iteration = 0

        while self.iteration < self.max_iterations:
            if stop_event.is_set():
                _debug("[Coordinator] Stop event set during loop.")
                raise KeyboardInterrupt()

            _debug(f"[Coordinator] Iteration {self.iteration + 1}/{self.max_iterations}")
            try:
                response = await self.llm_service.agenerate(
                    messages=self._build_iteration_messages(),
                    tools=self.tools.coordinator_tool_schemas,
                    tool_choice="auto",
                    model_name=active_model,
                    temperature=temperature,
                )
            except Exception as exc:
                _debug(f"[Coordinator] LLM call failed: {exc}")
                return f"Error occurred while calling LLM: {exc}"

            if stop_event.is_set():
                _debug("[Coordinator] Stop event set after LLM call.")
                raise KeyboardInterrupt()

            if response.reasoning:
                _debug(f"[Coordinator] Thinking: {response.reasoning}")
                if status_callback:
                    status_callback(response.reasoning, is_thinking=True)

            content = response.content or ""
            tool_calls = response.tool_calls or []
            _debug(f"[Coordinator] LLM response: content_len={len(content)}, tool_calls={len(tool_calls)}")
            if tool_calls:
                for tc in tool_calls:
                    _debug(f"[Coordinator] Raw tool call: {tc.function.name}({tc.function.arguments})")

            if not tool_calls:
                running = self._get_running_workers()
                if running:
                    _debug(f"[Coordinator] {len(running)} worker(s) still running - cannot return final response yet.")
                    self._add_assistant_message(content)
                    self._require_worker_await_guard = True
                    self.iteration += 1
                    continue
                pending_terminal = self._get_unconsumed_terminal_workers()
                if pending_terminal:
                    _debug(f"[Coordinator] {len(pending_terminal)} completed worker result(s) pending - cannot return final response yet.")
                    if content.strip():
                        self._add_assistant_message(content)
                    if self._require_worker_result_guard:
                        _debug("[Coordinator] Worker result guard already triggered - returning fallback synthesis.")
                        return self._format_worker_results_fallback(pending_terminal)
                    self._require_worker_result_guard = True
                    self.iteration += 1
                    continue
                self._require_worker_await_guard = False
                self._require_worker_result_guard = False
                _debug("[Coordinator] No tool calls - returning final response.")
                self._add_assistant_message(content)
                return content

            parsed_calls = []
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    _debug("[Coordinator] Invalid tool arguments format.")
                    return "Error: Invalid tool arguments format."
                parsed_calls.append((tc, args))

            for tc, args in parsed_calls:
                label = f"calling {tc.function.name}"
                _debug(f"[Coordinator] {label} with args {args}")
                if tool_call_callback:
                    tool_call_callback(tc.function.name, label, args)
                elif status_callback:
                    status_callback(label, is_thinking=False)

            # Execute coordinator tools concurrently
            async def _exec_one(tc, args):
                if stop_event.is_set():
                    raise KeyboardInterrupt()
                try:
                    if tc.function.name == "spawn_worker":
                        worker_id = await self.spawn_worker(
                            name=args.get("name", "unnamed"),
                            description=args.get("description", ""),
                            prompt=args.get("prompt", ""),
                            role=args.get("role", "explorer"),
                        )
                        output = json.dumps({"worker_id": worker_id, "status": "spawned"})
                    elif tc.function.name == "spawn_workers_batch":
                        worker_ids = await self.spawn_workers(
                            configs=args.get("workers", [])
                        )
                        output = json.dumps({"worker_ids": worker_ids, "status": "spawned"})
                    elif tc.function.name == "stop_worker":
                        output = await self.stop_worker(args.get("id", ""))
                    elif tc.function.name == "list_workers":
                        workers = self.list_workers()
                        output = json.dumps({"workers": workers, "allowed_roles": list(WORKER_ROLES)})
                    elif tc.function.name == "await_workers":
                        worker_ids = args.get("worker_ids", [])
                        timeout = args.get("timeout")
                        if worker_ids:
                            results = await self.await_workers(worker_ids, timeout=timeout)
                        else:
                            results = await self.await_all_workers(timeout=timeout)
                        output = json.dumps({"results": results})
                    elif tc.function.name == "get_worker_result":
                        result = self.get_worker_result(args.get("worker_id", ""))
                        output = json.dumps({"result": result})
                    else:
                        output = await self.tools.run_coordinator_tool_async(
                            tc.function.name, **args
                        )
                    if tool_output_callback:
                        tool_output_callback(tc.function.name, output)
                    _debug(f"[Coordinator] Tool {tc.function.name} succeeded.")
                    return tc, output, False
                except Exception as exc:
                    _debug(f"[Coordinator] Tool {tc.function.name} failed: {exc}")
                    return tc, f"Error executing tool: {exc}", True

            results = await asyncio.gather(
                *[_exec_one(tc, args) for tc, args in parsed_calls],
                return_exceptions=True,
            )

            self._add_assistant_message(content, tool_calls=tool_calls)
            for res in results:
                if isinstance(res, Exception):
                    # Create a synthetic tool message for the exception
                    # We don't have a tool_call here, so skip (shouldn't happen often)
                    continue
                tc, output, _ = res
                self._add_tool_message(tc, output)

            self.iteration += 1

        _debug("[Coordinator] Max iterations reached.")
        return "Max iterations reached. Process terminated."
