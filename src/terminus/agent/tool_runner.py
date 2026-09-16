from __future__ import annotations

import json
import time
from threading import Event
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from terminus.agent import Agent


ASK_QUESTION_TOOL_NAME = "ask_question"
_ASK_QUESTION_SKIPPED = (
    "Skipped because ask_question ended the turn and is waiting for the user's answer."
)


class AgentToolRunner:
    def __init__(self, owner: "Agent") -> None:
        self.owner = owner

    @staticmethod
    def _tool_call_field(tool_call: Any, field: str, default: Any = None) -> Any:
        if isinstance(tool_call, dict):
            return tool_call.get(field, default)
        return getattr(tool_call, field, default)

    @classmethod
    def _normalize_tool_call(cls, tool_call: Any) -> SimpleNamespace | None:
        function = cls._tool_call_field(tool_call, "function")
        call_id = cls._tool_call_field(tool_call, "id")
        name = cls._tool_call_field(function, "name")
        arguments = cls._tool_call_field(function, "arguments", "")

        if not call_id or not name:
            return None
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False, default=str)

        return SimpleNamespace(
            id=str(call_id),
            function=SimpleNamespace(name=str(name), arguments=arguments),
        )

    @classmethod
    def _serialize_tool_call(cls, tool_call: Any) -> dict[str, Any] | None:
        normalized = cls._normalize_tool_call(tool_call)
        if normalized is None:
            return None
        return {
            "id": normalized.id,
            "type": "function",
            "function": {
                "name": normalized.function.name,
                "arguments": normalized.function.arguments,
            },
        }

    def _run_tool_for_current_turn(self, tool_name: str, **kwargs: Any) -> Any:
        return self.owner.tool_registry.run_tool(tool_name, **kwargs)

    def _parse_tool_calls(self, tool_calls, status_callback=None):
        normalized_calls = []
        parsed_calls = []
        invalid_tool_results = []

        for tool_call in tool_calls:
            normalized = self._normalize_tool_call(tool_call)
            if normalized is None:
                if status_callback:
                    status_callback(
                        "skipped malformed tool call: missing id or function name",
                        is_thinking=False,
                    )
                continue

            normalized_calls.append(normalized)
            try:
                tool_args = json.loads(normalized.function.arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                error = (
                    f"Error: malformed arguments for tool '{normalized.function.name}': "
                    f"{exc}"
                )
                invalid_tool_results.append((normalized.id, error))
                if status_callback:
                    status_callback(
                        f"malformed tool call: {normalized.function.name}",
                        is_thinking=False,
                    )
                continue

            if not isinstance(tool_args, dict):
                error = (
                    f"Error: malformed arguments for tool '{normalized.function.name}': "
                    "expected a JSON object"
                )
                invalid_tool_results.append((normalized.id, error))
                if status_callback:
                    status_callback(
                        f"malformed tool call: {normalized.function.name}",
                        is_thinking=False,
                    )
                continue

            parsed_calls.append((normalized, tool_args))

        return normalized_calls, parsed_calls, invalid_tool_results

    def _try_complete_ask_question_turn(
        self,
        parsed_calls,
        final_tool_calls,
        tool_call_callback=None,
        status_callback=None,
        invalid_tool_results=None,
    ) -> str | None:
        question_call = next(
            (
                (tool_call, tool_args)
                for tool_call, tool_args in parsed_calls
                if tool_call.function.name == ASK_QUESTION_TOOL_NAME
            ),
            None,
        )
        if question_call is None:
            return None

        tool_call, tool_args = question_call
        try:
            question_output = self._run_tool_for_current_turn(
                tool_call.function.name,
                **tool_args,
            )
        except Exception as exc:
            question_output = f"Error executing tool: {exc}"

        label = self.owner.display_tool(tool_call.function.name, tool_args)
        if tool_call_callback:
            tool_call_callback(
                tool_name=tool_call.function.name,
                label=label,
                args=tool_args,
            )
        elif status_callback:
            status_callback(label, is_thinking=False)

        self.owner.add_assistant_message(content="", tool_calls=final_tool_calls)
        tool_outputs = {
            current_tool_call.id: (
                question_output
                if current_tool_call.id == tool_call.id
                else _ASK_QUESTION_SKIPPED
            )
            for current_tool_call, _ in parsed_calls
        }
        tool_outputs.update(dict(invalid_tool_results or []))
        for current_tool_call in final_tool_calls:
            if current_tool_call.id in tool_outputs:
                self.owner.add_tool_message(
                    current_tool_call,
                    tool_outputs[current_tool_call.id],
                )
        self.owner.add_assistant_message(question_output)

        return question_output

    def _emit_tool_call_status(
        self,
        parsed_calls,
        tool_call_callback=None,
        status_callback=None,
    ) -> None:
        for tool_call, tool_args in parsed_calls:
            label = self.owner.display_tool(tool_call.function.name, tool_args)
            if tool_call_callback:
                tool_call_callback(
                    tool_name=tool_call.function.name,
                    label=label,
                    args=tool_args,
                )
            elif status_callback:
                status_callback(label, is_thinking=False)

    def _prepare_subagent_callbacks(
        self,
        tool_args: dict[str, Any],
        stop_event: Event,
        worker_event_callback,
        status_callback,
        permission_callback,
    ) -> str:
        counter = getattr(self.owner, "_subagent_counter", 0) + 1
        self.owner._subagent_counter = counter
        worker_id = f"subagent-{counter}"
        task_text = str(tool_args.get("task", "") or "")
        role = "worker"
        role_name = role.title()

        if worker_event_callback:
            worker_event_callback(
                "worker_spawned",
                {
                    "worker_id": worker_id,
                    "name": role_name,
                    "description": task_text,
                    "role": role,
                },
            )

        def subagent_status(message, is_thinking=False, **kwargs):
            if not worker_event_callback:
                if status_callback:
                    status_callback(message, is_thinking=is_thinking, **kwargs)
                return
            worker_event_callback(
                "worker_detail" if is_thinking else "worker_notification",
                {
                    "worker_id": worker_id,
                    "detail_type": "thinking" if is_thinking else None,
                    "content": message,
                    "status": "running",
                    "summary": message,
                    "timestamp": time.time(),
                },
            )

        def subagent_tool_call(name, label, args):
            if worker_event_callback:
                worker_event_callback(
                    "worker_detail",
                    {
                        "worker_id": worker_id,
                        "detail_type": "tool_call",
                        "content": label,
                        "tool_name": name,
                        "args": args,
                        "timestamp": time.time(),
                    },
                )

        def subagent_tool_output(name, output):
            if worker_event_callback:
                worker_event_callback(
                    "worker_detail",
                    {
                        "worker_id": worker_id,
                        "detail_type": "tool_output",
                        "content": str(output),
                        "tool_name": name,
                        "timestamp": time.time(),
                    },
                )

        tool_args.update(
            _status_callback=subagent_status,
            _tool_call_callback=subagent_tool_call,
            _tool_output_callback=subagent_tool_output,
            _stop_event=stop_event,
            _permission_callback=permission_callback,
            _cwd=self.owner.cwd,
        )
        return worker_id

    def execute_tool_calls(
        self,
        final_tool_calls,
        accumulated_content: str = "",
        status_callback=None,
        todo_display_callback=None,
        tool_call_callback=None,
        tool_output_callback=None,
        stop_event: Event | None = None,
        worker_event_callback=None,
        permission_callback=None,
    ) -> str | None:
        stop_event = stop_event or Event()
        normalized_calls, parsed_calls, invalid_tool_results = self._parse_tool_calls(
            final_tool_calls, status_callback
        )

        ask_question_result = self._try_complete_ask_question_turn(
            parsed_calls,
            normalized_calls,
            tool_call_callback=tool_call_callback,
            status_callback=status_callback,
            invalid_tool_results=invalid_tool_results,
        )
        if ask_question_result is not None:
            return ask_question_result

        self._emit_tool_call_status(
            parsed_calls,
            tool_call_callback=tool_call_callback,
            status_callback=status_callback,
        )
        self.owner.add_assistant_message(
            content=accumulated_content,
            tool_calls=normalized_calls,
        )

        invalid_outputs = dict(invalid_tool_results)
        parsed_args = {tool_call.id: tool_args for tool_call, tool_args in parsed_calls}

        for tool_call in normalized_calls:
            tool_name = tool_call.function.name
            tool_args = parsed_args.get(tool_call.id)
            if tool_args is None:
                self.owner.add_tool_message(tool_call, invalid_outputs[tool_call.id])
                continue

            if stop_event.is_set():
                raise KeyboardInterrupt()

            worker_id = None
            if tool_name == "subagent":
                worker_id = self._prepare_subagent_callbacks(
                    tool_args,
                    stop_event,
                    worker_event_callback,
                    status_callback,
                    permission_callback,
                )

            if tool_name == "load_skill":
                tool_args["_agent"] = self.owner
            if tool_name == "bash":
                tool_args["_permission_callback"] = permission_callback
                tool_args["cwd"] = tool_args.get("cwd") or self.owner.cwd

            try:
                tool_output = self._run_tool_for_current_turn(
                    tool_name,
                    **tool_args,
                )
            except Exception as exc:
                tool_output = f"Error executing tool: {exc}"
                tool_failed = True
            else:
                tool_failed = False

            self.owner.add_tool_message(tool_call, tool_output)

            if tool_failed:
                if worker_id and worker_event_callback:
                    worker_event_callback(
                        "worker_status",
                        {
                            "worker_id": worker_id,
                            "status": "failed",
                            "result": str(tool_output),
                            "timestamp": time.time(),
                        },
                    )
                continue

            if tool_output_callback:
                tool_output_callback(tool_name, tool_output)

            if worker_id and worker_event_callback:
                worker_event_callback(
                    "worker_status",
                    {
                        "worker_id": worker_id,
                        "status": "completed",
                        "result": str(tool_output),
                        "timestamp": time.time(),
                    },
                )

            if (
                tool_name in ("todo_write", "todo_update", "todo_read")
                and todo_display_callback
            ):
                try:
                    todo_text = (
                        tool_output
                        if isinstance(tool_output, str)
                        else json.dumps(tool_output, default=str)
                    )
                    todo_data = json.loads(todo_text)
                    if isinstance(todo_data, dict) and "items" in todo_data:
                        todo_display_callback(todo_data["items"])
                except (TypeError, json.JSONDecodeError):
                    pass

        return None
