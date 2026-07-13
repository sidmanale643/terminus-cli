from typing import Literal, Optional
from threading import Event
from types import SimpleNamespace
from src.models.llm import available_models
from src.tools.tool_registry import ToolRegistry
import json
import sys
import time
from src.prompts import PromptManager
from dotenv import load_dotenv
from src.session_manager import SessionHistory
from src.llm_service.service import LLMService
from src.constants import DEFAULT_PROVIDER, DEFAULT_MODEL
from src.context_manager import ContextManager
from src.prompts.init_prompt import get_init_prompt
from src.observability import langfuse as lf_obs
import os
import re
load_dotenv()

MAX_ITERATIONS = 50
TOOL_TRIM_THRESHOLD_RATIO = 0.50
COMPACTION_THRESHOLD_RATIO = 0.75
SKILL_MESSAGE_PREFIX = "Skill loaded:"
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
        self.cwd = cwd
        self.name = name
        self.description = description
        self.use_streaming = use_streaming
        self._subagent_counter = 0
        self.mode = "default"
        self.iteration = 0
        self.max_iterations = max_iterations or MAX_ITERATIONS
        self.available_models = available_models
        pm = PromptManager(cwd=cwd)
        self.system_prompt = system_prompt if system_prompt else pm.get_system_prompt()
        self.planner_prompt = pm.get_planner_prompt()
        self.loaded_skills: dict[str, dict] = {}

        # Initialize LLM Service
        self.llm_service = LLMService()
        self.llm_service.set_active_provider(DEFAULT_PROVIDER)

        self.tool_registry = tool_registry if tool_registry else ToolRegistry(cwd=cwd)
        self.model = DEFAULT_MODEL

        self.context_manager = ContextManager(
            llm_service=self.llm_service,
            model_context_size=200000,
            model_name=self.model,
        )

        self.session_manager = SessionHistory()
        self._load_model_preference()

    def __repr__(self):
        return f"Agent(id={self.id}, name={self.name})"

    @property
    def context(self):
        return self.context_manager.context

    @context.setter
    def context(self, value):
        self.context_manager.context = value
        self.context_manager.update_context_size()

    @property
    def context_size(self):
        return self.context_manager.context_size

    @property
    def model_context_size(self):
        return self.context_manager.model_context_size

    @model_context_size.setter
    def model_context_size(self, value):
        self.context_manager.model_context_size = value

    def set_mode(self, name: Literal["default", "plan"] = "default"):
        if name == "plan":
            self.mode = "plan"
            if self.context:
                self.context_manager.set_system_message(self.planner_prompt)
        else:
            self.mode = "default"
            if self.context:
                self.context_manager.set_system_message(self.system_prompt)

    def init(
        self,
        status_callback=None,
        todo_display_callback=None,
        tool_call_callback=None,
        stop_event=None,
    ):
        """Generate or update AGENTS.md for the current codebase."""
        original_context = self.context.copy()
        original_iteration = self.iteration
        original_mode = self.mode
        original_loaded_skills = self.loaded_skills.copy()

        self.context = []
        self.iteration = 0
        self.mode = "default"
        self.add_system_message()

        prompt = get_init_prompt()
        try:
            result = self.run(
                prompt,
                status_callback=status_callback,
                todo_display_callback=todo_display_callback,
                tool_call_callback=tool_call_callback,
                stop_event=stop_event,
            )
        except Exception as e:
            result = f"Error generating AGENTS.md: {e}"
        finally:
            # Restore the user's conversation state
            self.context = original_context
            self.iteration = original_iteration
            self.mode = original_mode
            self.loaded_skills = original_loaded_skills

        if result.startswith("Error generating AGENTS.md"):
            return result

        result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL)
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)

        filepath = os.path.join(os.getcwd(), "AGENTS.md")
        try:
            with open(filepath, "w") as f:
                f.write(result)
        except Exception as e:
            return f"Error writing AGENTS.md: {e}"
        return f"AGENTS.md generated successfully at {filepath}"

    def add_system_message(self, system_prompt: str = None):
        if system_prompt is None:
            system_prompt = (
                self.planner_prompt if self.mode == "plan" else self.system_prompt
            )
        message = self.context_manager.add_message("system", system_prompt)
        self.session_manager.insert_to_session_history("system", json.dumps(message))

    @staticmethod
    def _skill_message_content(skill: dict) -> str:
        skill_name = skill.get("name", "unknown")
        content = skill.get("content", "")
        return f"{SKILL_MESSAGE_PREFIX} {skill_name}\n\n{content}"

    @staticmethod
    def _skill_name_from_message(message: dict) -> str | None:
        content = message.get("content", "")
        if message.get("role") != "system" or not content.startswith(SKILL_MESSAGE_PREFIX):
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
        self.session_manager.insert_to_session_history("system", json.dumps(message))
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
        self.session_manager.insert_to_session_history("user", json.dumps(message))

    def _load_model_preference(self):
        saved_name = self.session_manager.get_preference("last_model")
        if not saved_name:
            return
        if saved_name == self.model:
            return
        for m in self.available_models:
            inst = m() if isinstance(m, type) else m
            if inst.name == saved_name:
                self.switch_model(inst)
                return

    def switch_model(self, model):
        if model not in self.available_models:
            raise ValueError("Select the correct model")
        self.model = model.name
        service_provider = "groq" if model.provider == "groq" else "openrouter"
        self.llm_service.set_active_provider(service_provider)
        self.llm_service.set_provider_routing(model.openrouter_provider)
        self.context_manager.model_context_size = model.context_size
        self.context_manager.model_name = model.name
        self.session_manager.set_preference("last_model", model.name)

    def add_assistant_message(self, content, tool_calls=None):
        extra = {}
        if tool_calls:
            extra["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in (tool_calls if isinstance(tool_calls, list) else [tool_calls])
            ]
        message = self.context_manager.add_message("assistant", content, **extra)
        self.session_manager.insert_to_session_history("assistant", json.dumps(message))

    def add_tool_message(self, tool_call, tool_output):
        message = self.context_manager.add_message(
            "tool",
            tool_output,
            tool_call_id=tool_call.id,
            name=tool_call.function.name,
        )
        self.session_manager.insert_to_session_history("tool", json.dumps(message))

    def update_context_size(self):
        self.context_manager.update_context_size()

    def _maybe_compact_context(self, status_callback=None):
        if self.context_manager.should_compact(TOOL_TRIM_THRESHOLD_RATIO):
            removed = self.context_manager.trim_raw_tool_outputs()
            if removed and status_callback:
                status_callback(f"trimmed {removed} tool outputs", is_thinking=False)

        if self.context_manager.should_compact(COMPACTION_THRESHOLD_RATIO):
            if status_callback:
                status_callback("compacting context", is_thinking=False)
            result = self.context_manager.compact()
            if result and status_callback:
                status_callback(
                    f"Context compacted: {result['before_count']} → {result['after_count']} messages",
                    is_thinking=False,
                    is_alert=True,
                )

    def get_session_history(self, limit=None):
        return self.session_manager.retrieve_session_history(limit)

    def clear_session(self):
        self.session_manager.clear_session_history()
        self.context_manager.clear()
        self.loaded_skills.clear()
        self.iteration = 0
        self.add_system_message()

    def load_session(self, name):
        chat_history = self.session_manager.retrieve_chat_history(name=name, limit=1)
        if chat_history:
            self.clear_session()
            messages = chat_history[0]["chat_history"]
            self.context_manager.replace_messages(messages)
            self.session_manager.insert_many_to_session_history(
                (message["role"], json.dumps(message)) for message in messages
            )
            self._restore_loaded_skills_from_context()
            return True
        return False

    def display_tool(self, tool_name: str, tool_args: dict = None):
        """Generate a descriptive message for tool usage with specific arguments"""

        if tool_args is None:
            tool_args = {}

        # Generate specific messages based on tool and arguments
        if tool_name == ASK_QUESTION_TOOL_NAME:
            questions = tool_args.get("questions") or []
            count = len(questions)
            if count == 1:
                return "asking a clarifying question"
            return f"asking {count} clarifying questions"

        if tool_name == "file_reader" and "file_path" in tool_args:
            filename = tool_args["file_path"].split("/")[-1]
            return f"reading {filename}"

        elif tool_name == "file_reader" and "files" in tool_args:
            count = len(tool_args["files"])
            return f"reading {count} file{'s' if count > 1 else ''}"

        elif tool_name == "file_creator" and "file_path" in tool_args:
            filename = tool_args["file_path"].split("/")[-1]
            return f"creating {filename}"

        elif tool_name == "file_editor" and "file_path" in tool_args:
            filename = tool_args["file_path"].split("/")[-1]
            if "old_strings" in tool_args:
                return f"performing multiple edits in {filename}"
            return f"editing {filename}"

        elif tool_name == "grep_search" and "pattern" in tool_args:
            pattern = tool_args["pattern"][:30]  # Truncate long patterns
            return f"searching for '{pattern}'"

        elif tool_name == "glob" and "pattern" in tool_args:
            pattern = tool_args["pattern"][:30]
            return f"finding files matching '{pattern}'"

        elif tool_name == "bash" and "command" in tool_args:
            return "executing bash command"

        elif tool_name == "ls" and "directory_path" in tool_args:
            dir_name = tool_args["directory_path"].split("/")[-1] or "root"
            return f"listing {dir_name}"

        elif tool_name == "web_search" and "query" in tool_args:
            query = tool_args["query"][:30]  # Truncate long queries
            return f"searching web for '{query}'"

        elif tool_name == "sandbox" and "code" in tool_args:
            language = tool_args.get("language", "python")
            return f"running {language} code in sandbox"

        elif tool_name == "subagent" and "task" in tool_args:
            return f"delegating: {tool_args['task'][:40]}"

        elif tool_name in ("todo_write", "todo_update") and "task" in tool_args:
            task = tool_args["task"][:40]  # Truncate long task names
            status = tool_args.get("status", "pending")
            if tool_name == "todo_write":
                return f"adding task: {task}"
            elif status == "completed":
                return f"completing task: {task}"
            elif status == "in_progress":
                return f"starting task: {task}"
            else:
                return f"updating task: {task}"

        elif tool_name == "todo_read":
            return "reading todos"

        # Fallback to generic messages
        tool_message = {
            "grep_search": "searching",
            "glob": "finding files",
            "file_reader": "reading",
            "bash": "executing",
            "todo_write": "writing todos",
            "todo_read": "reading todos",
            "todo_update": "updating todos",
            "file_creator": "creating file",
            "file_editor": "editing file",
            "ls": "listing directory",
            "subagent": "delegating to sub-agent",
            "web_search": "searching the web",
        }

        return tool_message.get(tool_name, "calling tool")

    def _tool_schemas_for_current_mode(self):
        if self.mode == "plan":
            return self.tool_registry.plan_tool_schemas
        return self.tool_registry.tool_schemas

    def _run_tool_for_current_turn(self, tool_name: str, is_plan_mode: bool, **kwargs):
        if is_plan_mode:
            return self.tool_registry.run_plan_tool(tool_name, **kwargs)
        return self.tool_registry.run_tool(tool_name, **kwargs)

    def _try_complete_ask_question_turn(
        self,
        parsed_calls,
        final_tool_calls,
        is_plan_mode: bool,
        tool_call_callback=None,
        status_callback=None,
        trace=None,
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
        question_output = self._run_tool_for_current_turn(
            tool_call.function.name,
            is_plan_mode,
            **tool_args,
        )
        if tool_call_callback:
            tool_call_callback(
                tool_name=tool_call.function.name,
                label=self.display_tool(tool_call.function.name, tool_args),
                args=tool_args,
            )
        elif status_callback:
            status_callback(self.display_tool(tool_call.function.name, tool_args), is_thinking=False)

        self.add_assistant_message(content="", tool_calls=final_tool_calls)
        for current_tool_call, _ in parsed_calls:
            if current_tool_call.id == tool_call.id:
                self.add_tool_message(current_tool_call, question_output)
            else:
                self.add_tool_message(
                    current_tool_call,
                    "Skipped because ask_question ended the turn and is waiting for the user's answer.",
                )
        self.add_assistant_message(question_output)
        self.update_context_size()

        if is_plan_mode:
            self.set_mode(name="default")
        if trace:
            try:
                trace.update(
                    output={
                        "response": question_output,
                        "iterations": self.iteration + 1,
                        "ended_by": ASK_QUESTION_TOOL_NAME,
                    }
                )
            except Exception as le:
                print(f"[Langfuse] Failed to update trace: {le}", file=sys.stderr)
        return question_output

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

        # Check if user wants to use planning mode
        is_plan_mode = user_message.strip().startswith("/plan")
        if is_plan_mode:
            self.set_mode(name="plan")
            task = user_message.replace("/plan", "", 1).strip()
            user_message = f"Plan this feature {task}"

            # Notify user about mode switch
            if status_callback:
                status_callback("switched to plan mode", is_thinking=False)

        if not self.context:
            self.add_system_message()
            # print("[INIT] System prompt added to context.")

        self.add_user_message(user_message)
        self.update_context_size()
        self.iteration = 0

        # Create Langfuse trace if observability is enabled
        lf_client = lf_obs.get_langfuse_client()
        trace = None
        if lf_client:
            try:
                trace = lf_client.trace(
                    name="agent-run",
                    input={"user_message": user_message, "mode": self.mode},
                    session_id=self.session_manager.get_session_id(),
                    metadata={
                        "model": self.model,
                        "provider": self.llm_service.active_provider_name,
                        "max_iterations": self.max_iterations,
                    },
                )
            except Exception as e:
                print(f"[Langfuse] Failed to create trace: {e}", file=sys.stderr)

        try:
            while self.iteration < self.max_iterations:
                # print(f"[ITERATION] Iteration {self.iteration + 1}/{self.max_iterations}")

                if stop_event.is_set():
                    raise KeyboardInterrupt()

                try:
                    # Compact context if approaching the model's limit
                    self._maybe_compact_context(status_callback=status_callback)

                    # Get tool schemas for LLM
                    tool_schemas = self._tool_schemas_for_current_mode()

                    if self.use_streaming:
                        accumulated_content = ""
                        streamed_tool_calls = {}
                        for response_chunk in self.llm_service.stream(
                            messages=self.context,
                            tools=tool_schemas,
                            tool_choice="auto",
                            model_name=self.model,
                            temperature=0.3,
                        ):
                            if stop_event.is_set():
                                raise KeyboardInterrupt()

                            if response_chunk.reasoning and status_callback:
                                status_callback(response_chunk.reasoning, is_thinking=True)

                            if response_chunk.content:
                                accumulated_content += response_chunk.content
                                if stream_callback:
                                    stream_callback(response_chunk.content)

                            for tool_call in response_chunk.tool_calls or []:
                                index = getattr(tool_call, "index", 0)
                                current = streamed_tool_calls.setdefault(
                                    index,
                                    {
                                        "id": getattr(tool_call, "id", None),
                                        "name": "",
                                        "arguments": "",
                                    },
                                )
                                current["id"] = getattr(tool_call, "id", None) or current["id"]
                                function = getattr(tool_call, "function", None)
                                if function:
                                    current["name"] += getattr(function, "name", None) or ""
                                    current["arguments"] += getattr(function, "arguments", None) or ""

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
                            trace=trace,
                        )

                        if response.reasoning and status_callback and response.reasoning.strip():
                            status_callback(response.reasoning, is_thinking=True)

                        accumulated_content = response.content or ""
                        final_tool_calls = response.tool_calls or []

                    if stop_event.is_set():
                        raise KeyboardInterrupt()

                    # print("[LLM] LLM response received.")
                except Exception as e:
                    # print(f"[ERROR] Failed to call LLM: {e}")
                    if trace:
                        try:
                            trace.update(output={"error": str(e)})
                        except Exception as le:
                            print(
                                f"[Langfuse] Failed to update trace: {le}",
                                file=sys.stderr,
                            )
                    return f"Error occurred while calling LLM due to {e}"

                # Check if we have tool calls
                if final_tool_calls and len(final_tool_calls) > 0:
                    # Parse all tool arguments first
                    parsed_calls = []
                    for tool_call in final_tool_calls:
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                            parsed_calls.append((tool_call, tool_args))
                        except json.JSONDecodeError:
                            if status_callback:
                                status_callback(f"skipped malformed tool call: {tool_call.function.name}", is_thinking=False)
                            continue

                    ask_question_result = self._try_complete_ask_question_turn(
                        parsed_calls,
                        final_tool_calls,
                        is_plan_mode,
                        tool_call_callback=tool_call_callback,
                        status_callback=status_callback,
                        trace=trace,
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

                    # Execute all tools and collect outputs
                    tool_results = []
                    for tool_call, tool_args in parsed_calls:
                        try:
                            if stop_event.is_set():
                                raise KeyboardInterrupt()

                            # Create span for tool execution if tracing
                            tool_span = None
                            if trace:
                                try:
                                    tool_span = trace.span(
                                        name=tool_call.function.name,
                                        input=tool_args,
                                    )
                                except Exception as le:
                                    print(
                                        f"[Langfuse] Failed to create tool span: {le}",
                                        file=sys.stderr,
                                    )

                            worker_id = None
                            if tool_call.function.name == "subagent" and not is_plan_mode:
                                self._subagent_counter += 1
                                worker_id = f"subagent-{self._subagent_counter}"
                                if worker_event_callback:
                                    worker_event_callback(
                                        "worker_spawned",
                                        {
                                            "worker_id": worker_id,
                                            "name": worker_id,
                                            "description": tool_args.get("task", ""),
                                            "role": "subagent",
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
                                )

                            if tool_call.function.name == "load_skill":
                                tool_args["_agent"] = self

                            tool_output = self._run_tool_for_current_turn(
                                tool_call.function.name,
                                is_plan_mode,
                                **tool_args,
                            )
                            # print(f"[TOOL] Tool '{tool_call.function.name}' executed successfully.")

                            if tool_output_callback:
                                tool_output_callback(tool_call.function.name, tool_output)

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

                            if tool_span:
                                try:
                                    tool_span.end(output=tool_output)
                                except Exception as le:
                                    print(
                                        f"[Langfuse] Failed to end tool span: {le}",
                                        file=sys.stderr,
                                    )

                            # If this is a todo tool call, display the todo list
                            if (
                                tool_call.function.name in ("todo_write", "todo_update", "todo_read")
                                and todo_display_callback
                            ):
                                try:
                                    todo_data = json.loads(tool_output)
                                    if "items" in todo_data:
                                        todo_display_callback(todo_data["items"])
                                except (json.JSONDecodeError, KeyError):
                                    pass  # Silently fail if todo output is not in expected format

                            tool_results.append((tool_call, tool_output, False))
                        except Exception as e:
                            # print(f"[ERROR] Tool execution failed: {e}")
                            tool_error = f"Error executing tool: {str(e)}"
                            if tool_span:
                                try:
                                    tool_span.end(output={"error": str(e)})
                                except Exception as le:
                                    print(
                                        f"[Langfuse] Failed to end tool span: {le}",
                                        file=sys.stderr,
                                    )

                            if worker_id and worker_event_callback:
                                worker_event_callback(
                                    "worker_status",
                                    {
                                        "worker_id": worker_id,
                                        "status": "failed",
                                        "result": str(e),
                                        "timestamp": time.time(),
                                    },
                                )

                            tool_results.append((tool_call, tool_error, True))

                    # Add assistant message with all tool calls
                    self.add_assistant_message(
                        content=accumulated_content, tool_calls=final_tool_calls
                    )

                    # Add all tool messages
                    for tool_call, output, _ in tool_results:
                        self.add_tool_message(tool_call, output)

                    self.update_context_size()
                    self.iteration += 1

                else:
                    # print("[LLM] No tool calls detected. Returning final response.")
                    # print(f"[OUTPUT] Final content: {accumulated_content[:200]}{'...' if len(accumulated_content) > 200 else ''}")

                    self.add_assistant_message(accumulated_content)
                    self.update_context_size()

                    # Reset mode back to default if this was a /plan query
                    if is_plan_mode:
                        self.set_mode(name="default")

                    if trace:
                        try:
                            trace.update(
                                output={
                                    "response": accumulated_content,
                                    "iterations": self.iteration + 1,
                                }
                            )
                        except Exception as le:
                            print(
                                f"[Langfuse] Failed to update trace: {le}",
                                file=sys.stderr,
                            )

                    return accumulated_content

            # print("[STOP] Max iterations reached. Terminating process.")
            # Reset mode back to default if this was a /plan query
            if is_plan_mode:
                self.set_mode(name="default")

            if trace:
                try:
                    trace.update(
                        output={
                            "error": "Max iterations reached",
                            "iterations": self.iteration,
                        }
                    )
                except Exception as le:
                    print(
                        f"[Langfuse] Failed to update trace: {le}",
                        file=sys.stderr,
                    )

            return "Max iterations reached. Process terminated."
        finally:
            if trace:
                try:
                    lf_obs.flush()
                except Exception as le:
                    print(f"[Langfuse] Failed to flush trace: {le}", file=sys.stderr)
