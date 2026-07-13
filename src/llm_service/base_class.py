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

    def _get_api_key(self, env_var: str, *fallback_env_vars: str) -> str:
        if self._api_key:
            return self._api_key
        env_vars = (env_var, *fallback_env_vars)
        for name in env_vars:
            api_key = os.getenv(name)
            if api_key:
                return api_key
        raise ValueError(f"{' or '.join(env_vars)} environment variable not set")

    @abstractmethod
    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "glm-4.5-air", 
        temperature: float = 0.3,
        trace=None,
        provider_routing: Optional[List[str]] = None,
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
        provider_routing: Optional[List[str]] = None,
    ) -> Response:
        """Async generate. Default implementation delegates to sync generate in a thread.
        Providers should override this for true async I/O."""
        import asyncio
        return await asyncio.to_thread(
            self.generate, messages, tools, tool_choice, model_name, temperature, trace
        )

    def _get_provider_name(self):
        return self.__class__.__name__
