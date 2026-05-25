import os
from abc import ABC
from abc import abstractmethod
from typing import List, Dict, Optional
from src.models.llm import Response

class LlmProvider(ABC):
    def __init__(self):
        self._api_key: str | None = None

    def set_api_key(self, key: str) -> None:
        self._api_key = key

    def _get_api_key(self, env_var: str) -> str:
        if self._api_key:
            return self._api_key
        api_key = os.getenv(env_var)
        if not api_key:
            raise ValueError(f"{env_var} environment variable not set")
        return api_key

    @abstractmethod
    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "glm-4.5-air", 
        temperature: float = 0.3,
        trace=None,
    ) -> Response:
        pass
    
    def stream():
        pass

    async def agenerate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "glm-4.5-air", 
        temperature: float = 0.3,
        trace=None,
    ) -> Response:
        """Async generate. Default implementation delegates to sync generate in a thread.
        Providers should override this for true async I/O."""
        import asyncio
        return await asyncio.to_thread(
            self.generate, messages, tools, tool_choice, model_name, temperature, trace
        )

    def _get_provider_name(self):
        return self.__class__.__name__