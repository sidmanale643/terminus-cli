from typing import Optional
from threading import Event
from types import SimpleNamespace
from src.models.llm import available_models
from src.tools.tool_registry import ToolRegistry
import json
import time
from src.prompts.system_prompt import get_system_prompt
from dotenv import load_dotenv
from src.session_manager import SessionHistory
from src.llm_service.service import LLMService
from src.constants import DEFAULT_MODEL
from src.context_manager import ContextManager, SKILL_MESSAGE_PREFIX
from src.prompts.init_prompt import get_init_prompt
import os
import re

load_dotenv(os.path.expanduser("~/.terminus/.env"))
load_dotenv()

MAX_ITERATIONS = 50
COMPACTION_THRESHOLD_RATIO = 0.75
ASK_QUESTION_TOOL_NAME = "ask_question"


class Agent:
    def __init__(
        self,
        cwd=None,
        id=None,
        name=None,
        system_prompt=None,
        description=None,
        tool_registry=None,
        max_iterations=None,
        use_streaming: bool = False,
    ):
        """
        Initialize the Agent

        Args:
        cwd: Optional working directory to use in system prompt. If None, uses os.getcwd()
        """
        self.id = id
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.name = name
        self.description = description
        self.use_streaming = use_streaming
        self._subagent_counter = 0
        self.iteration = 0
        self.max_iterations = (
            MAX_ITERATIONS if max_iterations is None else max_iterations
        )
        self.available_models = available_models
        self.system_prompt = system_prompt or get_system_prompt(self.cwd)
        self.loaded_skills: dict[str, dict] = {}

        # Initialize LLM Service
        self.llm_service = LLMService()
        self.tool_registry = tool_registry if tool_registry else ToolRegistry()
        self.model = DEFAULT_MODEL

        model_context_size = next(
            (
                model.context_size
                for model in self.available_models
                if model.name == self.model
            ),
            200000,
        )
        self.context_manager = ContextManager(
            llm_service=self.llm_service,
            model_context_size=model_context_size,
            model_name=self.model,
        )

        self.session_manager = SessionHistory()
        self._record_session_history = True
        self._load_model_preference()

    def __repr__(self):
        return f"Agent(id={self.id}, name={self.name})"

    @property
    def context(self):
        return self.context_manager.context

    @context.setter
    def context(self, value):
        self.context_manager.replace_messages(value)

    @property
    def context_size(self):
        return self.context_manager.context_size

    @property
    def model_context_size(self):
        return self.context_manager.model_context_size

    @model_context_size.setter
    def model_context_size(self, value):
        self.context_manager.model_context_size = value

    def init(
        self,
        status_callback=None,
        todo_display_callback=None,
        tool_call_callback=None,
        stop_event=None,
        permission_callback=None,
    ):
        """Generate or update AGENTS.md for the current codebase."""
        original_context = self.context.copy()
        original_iteration = self.iteration
        original_loaded_skills = self.loaded_skills.copy()
        original_recording = self._record_session_history

        self.context = []
        self.iteration = 0
        self._record_session_history = False
        self.add_system_message()

        prompt = get_init_prompt()
        try:
            result = self.run(
                prompt,
                status_callback=status_callback,
                todo_display_callback=todo_display_callback,
                tool_call_callback=tool_call_callback,
                stop_event=stop_event,
                permission_callback=permission_callback,
            )
        except Exception as e:
            result = f"Error generating AGENTS.md: {e}"
        finally:
            # Restore the user's conversation state
            self.context = original_context
            self.iteration = original_iteration
            self.loaded_skills = original_loaded_skills
            self._record_session_history = original_recording

        if result.startswith("Error generating AGENTS.md"):
            return result

        result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL)
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)

        filepath = os.path.join(self.cwd, "AGENTS.md")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result)
        except Exception as e:
            return f"Error writing AGENTS.md: {e}"
        return f"AGENTS.md generated successfully at {filepath}"

    def add_system_message(self, system_prompt: str = None):
        if system_prompt is None:
            system_prompt = self.system_prompt
        message = self.context_manager.add_message("system", system_prompt)
        self._record_message(message)
        return message

    def _record_message(self, message: dict) -> None:
        if self._record_session_history:
            self.session_manager.record_message(message)

    @staticmethod
    def _skill_message_content(skill: dict) -> str:
        skill_name = skill.get("name", "unknown")
        content = skill.get("content", "")
        return f"{SKILL_MESSAGE_PREFIX} {skill_name}\n\n{content}"

    @staticmethod
    def _skill_name_from_message(message: dict) -> str | None:
        content = message.get("content", "")
        if message.get("role") != "system" or not content.startswith(
            SKILL_MESSAGE_PREFIX
        ):
            return None
        first_line = content.splitlines()[0]
        return first_line.removeprefix(SKILL_MESSAGE_PREFIX).strip() or None

    def _restore_loaded_skills_from_context(self):
        self.loaded_skills.clear()
        for message in self.context:
            skill_name = self._skill_name_from_message(message)
            if skill_name:
                self.loaded_skills[skill_name] = {"name": skill_name}

    def get_loaded_skill_names(self) -> set[str]:
        if not self.loaded_skills:
            self._restore_loaded_skills_from_context()
        return set(self.loaded_skills)

    def load_skill(self, skill: dict) -> bool:
        skill_name = skill.get("name", "unknown")
        if skill_name in self.get_loaded_skill_names():
            return False

        if not self.context:
            self.add_system_message()

        message = self.context_manager.add_message(
            "system",
            self._skill_message_content(skill),
        )
        self._record_message(message)
        self.loaded_skills[skill_name] = skill
        return True

    def annotate_skills(self, skills: list[dict]) -> list[dict]:
        loaded_names = self.get_loaded_skill_names()
        return [
            {
                **skill,
                "loaded": skill.get("name") in loaded_names,
            }
            for skill in skills
        ]

    def add_user_message(self, content):
        message = self.context_manager.add_message("user", content)
        self._record_message(message)
        return message

    def _load_model_preference(self):
        saved_name = self.session_manager.get_preference("last_model")
        if not saved_name:
            return
        if saved_name == self.model:
            return
        for model in self.available_models:
            if model.name == saved_name:
                self.switch_model(model)
                return

    def switch_model(self, model):
        if model not in self.available_models:
            raise ValueError("Select the correct model")
        self.model = model.name
        self.context_manager.model_context_size = model.context_size
        self.context_manager.model_name = model.name
        self.session_manager.set_preference("last_model", model.name)

    @staticmethod
    def _tool_call_field(tool_call, field, default=None):
        if isinstance(tool_call, dict):
            return tool_call.get(field, default)
        return getattr(tool_call, field, default)

    @classmethod
    def _normalize_tool_call(cls, tool_call):
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
    def _serialize_tool_call(cls, tool_call):
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

    def add_assistant_message(self, content, tool_calls=None):
        extra = {}
        if tool_calls:
            serialized_calls = [
                self._serialize_tool_call(tool_call)
                for tool_call in (
                    tool_calls if isinstance(tool_calls, list) else [tool_calls]
                )
            ]
            extra["tool_calls"] = [call for call in serialized_calls if call]
            if not extra["tool_calls"]:
                extra = {}
        message = self.context_manager.add_message("assistant", content, **extra)
        self._record_message(message)
        return message

    def add_tool_message(self, tool_call, tool_output):
        normalized = self._normalize_tool_call(tool_call)
        if normalized is None:
            raise ValueError("tool messages require a valid tool call id and name")
        if not isinstance(tool_output, str):
            tool_output = json.dumps(tool_output, ensure_ascii=False, default=str)
        message = self.context_manager.add_message(
            "tool",
            tool_output,
            tool_call_id=normalized.id,
            name=normalized.function.name,
        )
        self._record_message(message)
        return message

    def _maybe_compact_context(self, status_callback=None):
        if not self.context_manager.should_compact(COMPACTION_THRESHOLD_RATIO):
            return
        if status_callback:
            status_callback("compacting context", is_thinking=False)
        compacted = self.context_manager.compact()
        if compacted:
            if status_callback:
                status_callback(
                    f"Context compacted: {compacted['before_count']} → {compacted['after_count']} messages",
                    is_thinking=False,
                    is_alert=True,
                )

    def get_session_history(self, limit=None):
        return self.session_manager.retrieve_session_history(limit)

    def clear_session(self, add_system: bool = True):
        self.session_manager.clear_session_history()
        self.context_manager.clear()
        self.loaded_skills.clear()
        self.iteration = 0
        if add_system:
            self.add_system_message()

    def display_tool(self, tool_name: str, tool_args: dict = None):
        """Generate a human-readable label for tool usage (never raw JSON)."""
        from ui.display_text import tool_call_label

        return tool_call_label(tool_name or "", tool_args or {})

    def _tool_schemas(self):
        return self.tool_registry.tool_schemas

    def _run_tool_for_current_turn(self, tool_name: str, **kwargs):
        return self.tool_registry.run_tool(tool_name, **kwargs)

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
        if tool_call_callback:
            tool_call_callback(
                tool_name=tool_call.function.name,
                label=self.display_tool(tool_call.function.name, tool_args),
                args=tool_args,
            )
        elif status_callback:
            status_callback(
                self.display_tool(tool_call.function.name, tool_args), is_thinking=False
            )

        self.add_assistant_message(content="", tool_calls=final_tool_calls)
        tool_outputs = {
            current_tool_call.id: (
                question_output
                if current_tool_call.id == tool_call.id
                else "Skipped because ask_question ended the turn and is waiting for the user's answer."
            )
            for current_tool_call, _ in parsed_calls
        }
        tool_outputs.update(dict(invalid_tool_results or []))
        for current_tool_call in final_tool_calls:
            if current_tool_call.id in tool_outputs:
                self.add_tool_message(
                    current_tool_call,
                    tool_outputs[current_tool_call.id],
                )
        self.add_assistant_message(question_output)

        return question_output

    def _parse_tool_calls(self, tool_calls, status_callback=None):
        """Normalize calls and keep malformed calls paired with an error result."""
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
                error = f"Error: malformed arguments for tool '{normalized.function.name}': {exc}"
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

    def run(
        self,
        user_message,
        status_callback=None,
        todo_display_callback=None,
        tool_call_callback=None,
        tool_output_callback=None,
        stop_event: Optional[Event] = None,
        worker_event_callback=None,
        stream_callback=None,
        response_format: dict | None = None,
        usage_callback=None,
        permission_callback=None,
    ):
        """
        Run the agent with a user message

        Args:
        user_message: The user's input message
        status_callback: Optional callback function to update status
        todo_display_callback: Optional callback function to display todo list updates
        worker_event_callback: Optional callback function to emit subagent lifecycle events
        """
        # print(f"[RUN] Starting agent run with user message: '{user_message}'")

        stop_event = stop_event or Event()

        # Respect any pending stop requests before starting
        if stop_event.is_set():
            raise KeyboardInterrupt()

        if not self.context:
            self.add_system_message()
        # print("[INIT] System prompt added to context.")

        self.add_user_message(user_message)
        self.iteration = 0

        while self.iteration < self.max_iterations:
            # print(f"[ITERATION] Iteration {self.iteration + 1}/{self.max_iterations}")

            if stop_event.is_set():
                raise KeyboardInterrupt()

            try:
                # Compact context if approaching the model's limit
                self._maybe_compact_context(status_callback=status_callback)

                # Get tool schemas for LLM
                tool_schemas = self._tool_schemas()

                if self.use_streaming:
                    accumulated_content = ""
                    streamed_tool_calls = {}
                    for response_chunk in self.llm_service.stream(
                        messages=self.context,
                        tools=tool_schemas,
                        tool_choice="auto",
                        model_name=self.model,
                        temperature=0.3,
                        response_format=response_format,
                    ):
                        if stop_event.is_set():
                            raise KeyboardInterrupt()
                        chunk_error = self._tool_call_field(response_chunk, "error")
                        if chunk_error:
                            raise RuntimeError(f"LLM stream error: {chunk_error}")
                        if (
                            self._tool_call_field(response_chunk, "stop_reason")
                            == "error"
                        ):
                            raise RuntimeError("LLM stream ended with an error")

                        if usage_callback and (
                            response_chunk.prompt_tokens is not None
                            or response_chunk.response_tokens is not None
                        ):
                            usage_callback(
                                {
                                    "provider": self.llm_service.active_provider_name,
                                    "requested_model": self.model,
                                    "response_model": response_chunk.model,
                                    "prompt_tokens": response_chunk.prompt_tokens,
                                    "response_tokens": response_chunk.response_tokens,
                                }
                            )

                        if response_chunk.reasoning and status_callback:
                            status_callback(response_chunk.reasoning, is_thinking=True)

                        if response_chunk.content:
                            accumulated_content += response_chunk.content
                            if stream_callback:
                                stream_callback(response_chunk.content)

                        for tool_call in response_chunk.tool_calls or []:
                            index = self._tool_call_field(tool_call, "index", 0)
                            if index is None:
                                index = 0
                            current = streamed_tool_calls.setdefault(
                                index,
                                {
                                    "id": self._tool_call_field(tool_call, "id"),
                                    "name": "",
                                    "arguments": "",
                                },
                            )
                            current["id"] = (
                                self._tool_call_field(tool_call, "id") or current["id"]
                            )
                            function = self._tool_call_field(tool_call, "function")
                            if function:
                                current["name"] += (
                                    self._tool_call_field(function, "name") or ""
                                )
                                current["arguments"] += (
                                    self._tool_call_field(function, "arguments") or ""
                                )

                    final_tool_calls = [
                        SimpleNamespace(
                            id=value["id"],
                            function=SimpleNamespace(
                                name=value["name"], arguments=value["arguments"]
                            ),
                        )
                        for _, value in sorted(streamed_tool_calls.items())
                    ]
                else:
                    response = self.llm_service.generate(
                        messages=self.context,
                        tools=tool_schemas,
                        tool_choice="auto",
                        model_name=self.model,
                        temperature=0.3,
                        response_format=response_format,
                    )

                    if usage_callback:
                        usage_callback(
                            {
                                "provider": self.llm_service.active_provider_name,
                                "requested_model": self.model,
                                "response_model": response.model,
                                "prompt_tokens": response.prompt_tokens,
                                "response_tokens": response.response_tokens,
                            }
                        )

                    if (
                        response.reasoning
                        and status_callback
                        and response.reasoning.strip()
                    ):
                        status_callback(response.reasoning, is_thinking=True)

                    accumulated_content = response.content or ""
                    final_tool_calls = list(response.tool_calls or [])

                if stop_event.is_set():
                    raise KeyboardInterrupt()

                # print("[LLM] LLM response received.")
            except Exception as e:
                # print(f"[ERROR] Failed to call LLM: {e}")
                return f"Error occurred while calling LLM due to {e}"

            # Check if we have tool calls
            if final_tool_calls and len(final_tool_calls) > 0:
                normalized_calls, parsed_calls, invalid_tool_results = (
                    self._parse_tool_calls(final_tool_calls, status_callback)
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

                # Update status for each tool call
                for tool_call, tool_args in parsed_calls:
                    status_message = self.display_tool(
                        tool_call.function.name, tool_args
                    )
                    if tool_call_callback:
                        tool_call_callback(
                            tool_name=tool_call.function.name,
                            label=status_message,
                            args=tool_args,
                        )
                    elif status_callback:
                        status_callback(status_message, is_thinking=False)

                # Store the assistant call before executing tools so each
                # persisted call is followed by a matching tool result.
                self.add_assistant_message(
                    content=accumulated_content, tool_calls=normalized_calls
                )

                invalid_outputs = dict(invalid_tool_results)
                parsed_args = {
                    tool_call.id: tool_args for tool_call, tool_args in parsed_calls
                }

                for tool_call in normalized_calls:
                    tool_name = tool_call.function.name
                    tool_args = parsed_args.get(tool_call.id)
                    if tool_args is None:
                        # Malformed arguments still get a protocol-valid result.
                        self.add_tool_message(tool_call, invalid_outputs[tool_call.id])
                        continue

                    if stop_event.is_set():
                        raise KeyboardInterrupt()

                    worker_id = None
                    if tool_name == "subagent":
                        self._subagent_counter += 1
                        worker_id = f"subagent-{self._subagent_counter}"
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
                                    status_callback(
                                        message, is_thinking=is_thinking, **kwargs
                                    )
                                return
                            worker_event_callback(
                                "worker_detail"
                                if is_thinking
                                else "worker_notification",
                                {
                                    "worker_id": worker_id,
                                    "detail_type": "thinking" if is_thinking else None,
                                    "content": message,
                                    "status": "running",
                                    "summary": message,
                                    "timestamp": time.time(),
                                },
                            )

                        def subagent_tool_call(tool_name, label, args):
                            if worker_event_callback:
                                worker_event_callback(
                                    "worker_detail",
                                    {
                                        "worker_id": worker_id,
                                        "detail_type": "tool_call",
                                        "content": label,
                                        "tool_name": tool_name,
                                        "args": args,
                                        "timestamp": time.time(),
                                    },
                                )

                        def subagent_tool_output(tool_name, output):
                            if worker_event_callback:
                                worker_event_callback(
                                    "worker_detail",
                                    {
                                        "worker_id": worker_id,
                                        "detail_type": "tool_output",
                                        "content": str(output),
                                        "tool_name": tool_name,
                                        "timestamp": time.time(),
                                    },
                                )

                        tool_args.update(
                            _status_callback=subagent_status,
                            _tool_call_callback=subagent_tool_call,
                            _tool_output_callback=subagent_tool_output,
                            _stop_event=stop_event,
                            _permission_callback=permission_callback,
                            _cwd=self.cwd,
                        )

                    if tool_name == "load_skill":
                        tool_args["_agent"] = self
                    if tool_name == "bash":
                        tool_args["_permission_callback"] = permission_callback
                        tool_args["cwd"] = tool_args.get("cwd") or self.cwd

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

                    # Keep the assistant/tool exchange adjacent and complete.
                    self.add_tool_message(tool_call, tool_output)

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

                    # If this is a todo tool call, display the todo list.
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

                self.iteration += 1

            else:
                # print("[LLM] No tool calls detected. Returning final response.")
                # print(f"[OUTPUT] Final content: {accumulated_content[:200]}{'...' if len(accumulated_content) > 200 else ''}")

                self.add_assistant_message(accumulated_content)

                return accumulated_content

        # print("[STOP] Max iterations reached. Terminating process.")
        return "Max iterations reached. Process terminated."
