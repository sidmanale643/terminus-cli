import json
import os
import re
from threading import Event
from typing import Optional

from dotenv import load_dotenv

from terminus.agent.response import request_llm_response
from terminus.agent.tool_runner import AgentToolRunner
from terminus.context import ContextManager, SKILL_MESSAGE_PREFIX
from terminus.config import DEFAULT_MODEL
from terminus.llm.service import LLMService
from terminus.llm.models import available_models
from terminus.prompts.init_prompt import get_init_prompt
from terminus.prompts.system_prompt import get_system_prompt
from terminus.session import SessionHistory
from terminus.tools.tool_registry import ToolRegistry

load_dotenv(os.path.expanduser("~/.terminus/.env"))
load_dotenv()

MAX_ITERATIONS = 50
COMPACTION_THRESHOLD_RATIO = 0.75


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

        self.llm_service = LLMService()
        self.tool_registry = tool_registry if tool_registry else ToolRegistry()
        self.tool_runner = AgentToolRunner(self)
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
        return AgentToolRunner._tool_call_field(tool_call, field, default)

    @classmethod
    def _normalize_tool_call(cls, tool_call):
        return AgentToolRunner._normalize_tool_call(tool_call)

    @classmethod
    def _serialize_tool_call(cls, tool_call):
        return AgentToolRunner._serialize_tool_call(tool_call)

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
        from ui.display_text import tool_call_label

        return tool_call_label(tool_name or "", tool_args or {})

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
        stop_event = stop_event or Event()
        if stop_event.is_set():
            raise KeyboardInterrupt()

        if not self.context:
            self.add_system_message()

        self.add_user_message(user_message)
        self.iteration = 0

        while self.iteration < self.max_iterations:
            if stop_event.is_set():
                raise KeyboardInterrupt()

            try:
                self._maybe_compact_context(status_callback=status_callback)
                response = request_llm_response(
                    self.llm_service,
                    messages=self.context,
                    tools=self.tool_registry.tool_schemas,
                    model_name=self.model,
                    use_streaming=self.use_streaming,
                    stop_event=stop_event,
                    response_format=response_format,
                    status_callback=status_callback,
                    stream_callback=stream_callback,
                    usage_callback=usage_callback,
                )
            except Exception as e:
                return f"Error occurred while calling LLM due to {e}"

            if response.tool_calls:
                turn_result = self.tool_runner.execute_tool_calls(
                    response.tool_calls,
                    accumulated_content=response.content,
                    status_callback=status_callback,
                    todo_display_callback=todo_display_callback,
                    tool_call_callback=tool_call_callback,
                    tool_output_callback=tool_output_callback,
                    stop_event=stop_event,
                    worker_event_callback=worker_event_callback,
                    permission_callback=permission_callback,
                )
                if turn_result is not None:
                    return turn_result
                self.iteration += 1
                continue

            self.add_assistant_message(response.content)
            return response.content

        return "Max iterations reached. Process terminated."
