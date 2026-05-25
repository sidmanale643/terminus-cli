from typing import Any, Dict, List, Optional
from src.utils import compact

SKILL_MESSAGE_PREFIX = "Skill loaded:"


class ContextManager:
    def __init__(
        self,
        llm_service,
        model_context_size: int = 200000,
        model_name: Optional[str] = None,
    ):
        self.context: List[Dict[str, Any]] = []
        self.context_size: int = 0
        self.message_context_size: List[int] = []
        self.model_context_size = model_context_size
        self.llm_service = llm_service
        self.model_name = model_name

    def add_message(self, role: str, content: str, **kwargs) -> Dict[str, Any]:
        message = {"role": role, "content": content, **kwargs}
        self.context.append(message)
        self.update_context_size()
        return message

    def set_system_message(self, content: str):
        if self.context and self.context[0].get("role") == "system":
            self.context[0]["content"] = content
        else:
            self.context.insert(0, {"role": "system", "content": content})
        self.update_context_size()

    def update_context_size(self):
        sizes = []
        for message in self.context:
            msg_content = message.get("content", "") or ""
            sizes.append(len(msg_content))
        self.message_context_size = sizes
        self.context_size = sum(sizes)

    def should_compact(self, threshold_ratio: float = 0.8) -> bool:
        if not self.context:
            return False
        estimated_tokens = self.context_size / 4
        threshold = self.model_context_size * threshold_ratio
        return estimated_tokens >= threshold

    def compact(self, status_callback=None):
        if len(self.context) <= 2:
            return None
        before_count = len(self.context)
        preserved_system_messages = []
        summarizable_messages = []

        for index, message in enumerate(self.context):
            is_base_system = index == 0 and message.get("role") == "system"
            is_skill_system = (
                message.get("role") == "system"
                and (message.get("content", "") or "").startswith(SKILL_MESSAGE_PREFIX)
            )
            if is_base_system or is_skill_system:
                preserved_system_messages.append(message)
            else:
                summarizable_messages.append(message)

        compacted_messages = compact(
            summarizable_messages,
            self.llm_service,
            model_name=self.model_name,
        )
        if compacted_messages and compacted_messages[0].get("content") == "Previous context summarized below.":
            compacted_messages = compacted_messages[1:]

        self.context = preserved_system_messages + compacted_messages
        self.update_context_size()
        after_count = len(self.context)
        summary = ""
        for message in compacted_messages:
            if message.get("role") == "system":
                summary = message.get("content", "")
                break
        return {
            "before_count": before_count,
            "after_count": after_count,
            "summary": summary,
        }

    def trim(self, keep_slots: int = 15):
        if len(self.context) <= keep_slots + 1:
            return
        system = self.context[0] if self.context[0].get("role") == "system" else None
        recent = self.context[-keep_slots:]
        self.context = [system] + recent if system else recent
        self.update_context_size()

    def trim_raw_tool_outputs(self):
        before = len(self.context)
        self.context = [m for m in self.context if m.get("role") != "tool"]
        self.update_context_size()
        return before - len(self.context)

    def clear(self):
        self.context.clear()
        self.context_size = 0
        self.message_context_size = []
