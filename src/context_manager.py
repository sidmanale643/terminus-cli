import json
import math
from typing import Any, Dict, List, Optional

from src.utils import summarize_messages

SKILL_MESSAGE_PREFIX = "Skill loaded:"
CHARS_PER_TOKEN = 4


class ContextManager:
    def __init__(
        self,
        llm_service,
        model_context_size: int = 200000,
        model_name: Optional[str] = None,
    ):
        self.context: List[Dict[str, Any]] = []
        self.context_size: int = 0
        self.model_context_size = model_context_size
        self.llm_service = llm_service
        self.model_name = model_name

    def add_message(self, role: str, content: Any, **kwargs) -> Dict[str, Any]:
        message = {"role": role, "content": content, **kwargs}
        self.context.append(message)
        size = self._estimate_message_tokens(message)
        self.context_size += size
        return message

    def replace_messages(self, messages: List[Dict[str, Any]]) -> None:
        self.context = [dict(message) for message in messages]
        self.update_context_size()

    @staticmethod
    def _estimate_message_tokens(message: Dict[str, Any]) -> int:
        try:
            serialized = json.dumps(message, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = str(message)
        return max(1, math.ceil(len(serialized) / CHARS_PER_TOKEN))

    def update_context_size(self) -> None:
        self.context_size = sum(
            self._estimate_message_tokens(message) for message in self.context
        )

    def should_compact(self, threshold_ratio: float = 0.8) -> bool:
        if not self.context:
            return False
        threshold = self.model_context_size * threshold_ratio
        return self.context_size >= threshold

    def compact(self):
        if len(self.context) <= 2:
            return None
        before_count = len(self.context)
        preserved_system_messages = []
        summarizable_messages = []

        for index, message in enumerate(self.context):
            is_base_system = index == 0 and message.get("role") == "system"
            is_skill_system = message.get("role") == "system" and (
                message.get("content", "") or ""
            ).startswith(SKILL_MESSAGE_PREFIX)
            if is_base_system or is_skill_system:
                preserved_system_messages.append(message)
            else:
                summarizable_messages.append(message)

        retained_message = (
            summarizable_messages.pop()
            if summarizable_messages and summarizable_messages[-1].get("role") == "user"
            else None
        )
        if not summarizable_messages:
            return None

        summary = summarize_messages(
            summarizable_messages,
            self.llm_service,
            model_name=self.model_name,
        )
        compacted_messages = [{"role": "system", "content": summary}]
        if retained_message:
            compacted_messages.append(retained_message)
        self.context = preserved_system_messages + compacted_messages
        self.update_context_size()
        after_count = len(self.context)
        return {
            "before_count": before_count,
            "after_count": after_count,
            "summary": summary,
        }

    def clear(self) -> None:
        self.context = []
        self.context_size = 0
