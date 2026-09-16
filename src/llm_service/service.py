from typing import Dict, List, Optional

from src.constants import DEFAULT_MODEL, DEFAULT_PROVIDER
from src.llm_service.openrouter import OpenRouterProvider


class LLMService:
    """Synchronous LLM facade for the application's OpenRouter provider."""

    def __init__(self):
        self.provider = OpenRouterProvider()
        self.active_provider_name = DEFAULT_PROVIDER

    def set_api_key(self, api_key: str) -> None:
        self.provider.set_api_key(api_key)

    def generate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
    ):
        if model_name is None:
            model_name = DEFAULT_MODEL
        return self.provider.generate(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model_name=model_name,
            temperature=temperature,
            response_format=response_format,
        )

    def stream(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
    ):
        if model_name is None:
            model_name = DEFAULT_MODEL
        return self.provider.stream(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model_name=model_name,
            temperature=temperature,
            response_format=response_format,
        )
