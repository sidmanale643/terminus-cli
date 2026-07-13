from typing import Literal, List, Dict, Optional
from src.llm_service.groq import GroqProvider
from src.llm_service.openrouter import OpenRouterProvider
# from src.llm_service.litellm import LiteLLMProvider
from src.llm_service.base_class import LlmProvider
from src.constants import DEFAULT_PROVIDER


class LLMService:
    def __init__(self):

        self.providers: Dict[str, LlmProvider] = {}
        self._register_all_providers()

        self.active_provider = DEFAULT_PROVIDER
        self.active_provider_name = DEFAULT_PROVIDER
        self.provider_routing = None

    def register_provider(self, name: str, provider: LlmProvider ):

        self.providers[name] = provider
     
    def _register_all_providers(self):

        self.register_provider("groq", GroqProvider("groq"))
        self.register_provider("openrouter", OpenRouterProvider("openrouter"))
        #self.register_provider("litellm", LiteLLMProvider("litellm"))

    def set_active_provider(self, name: Literal["groq", "zhipu", "openrouter", "litellm"]):
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not registered. Available providers: {list(self.providers.keys())}")
        
        self.active_provider = self.providers[name]
        self.active_provider_name = name

    def set_provider_api_key(self, provider_name: str, api_key: str) -> None:
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not registered. Available providers: {list(self.providers.keys())}")
        self.providers[provider_name].set_api_key(api_key)

    def set_provider_routing(self, routing):
        self.provider_routing = routing

    def _get_available_providers(self):
        return list(self.providers.keys())

    def _resolve_provider(self):
        if isinstance(self.active_provider, str):
            return self.providers[self.active_provider]
        return self.active_provider

    def _resolve_model(self, model_name: Optional[str] = None):
        if model_name is not None:
            return model_name
        if self.active_provider_name == "groq":
            return "moonshotai/kimi-k2-instruct-0905"
        return "minimax/minimax-m2.5:free"
   
    def generate(self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        trace=None,
        ):

        provider = self._resolve_provider()
        model_name = self._resolve_model(model_name)

        response = provider.generate(messages, tools, tool_choice, model_name, temperature, trace, provider_routing=self.provider_routing)
        return response

    async def agenerate(self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        trace=None,
        ):
        """Async generate dispatch."""
        provider = self._resolve_provider()
        model_name = self._resolve_model(model_name)

        response = await provider.agenerate(messages, tools, tool_choice, model_name, temperature, trace, provider_routing=self.provider_routing)
        return response

    def stream(self,         
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: Optional[str] = None, 
        temperature: float = 0.3
        ):  
        
        provider = self._resolve_provider()
        model_name = self._resolve_model(model_name)

        return provider.stream(messages, tools, tool_choice, model_name, temperature, provider_routing=self.provider_routing)
