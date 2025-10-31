from typing import Literal, List, Dict, Optional
from src.llm_service.groq import GroqProvider
from src.llm_service.openrouter import OpenRouterProvider
from src.llm_service.base_class import LlmProvider
from src.constants import DEFAULT_PROVIDER


class LLMService:
    def __init__(self):

        self.providers: Dict[str, LlmProvider] = {}
        self._register_all_providers()

        self.active_provider = DEFAULT_PROVIDER
        self.active_provider_name = DEFAULT_PROVIDER

    def register_provider(self, name: str, provider: LlmProvider ):

        self.providers[name] = provider
     
    def _register_all_providers(self):

        self.register_provider("groq", GroqProvider("groq"))
        self.register_provider("openrouter", OpenRouterProvider("openrouter"))

    def set_active_provider(self, name: Literal["groq", "zhipu", "openrouter"]):
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not registered. Available providers: {list(self.providers.keys())}")
        
        self.active_provider = self.providers[name]
        self.active_provider_name = name

    def _get_available_providers(self):
        return list(self.providers.keys())
   
    def generate(self,         
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: Optional[str] = None, 
        temperature: float = 0.3
        ):
        
        # If active_provider is a string (default case), use it as key, otherwise it's already a provider instance
        if isinstance(self.active_provider, str):
            provider = self.providers[self.active_provider]
        else:
            provider = self.active_provider
        
        # Use provider-specific default models if model_name not specified
        if model_name is None:
            if self.active_provider_name == "groq":
                model_name = "moonshotai/kimi-k2-instruct-0905"
            elif self.active_provider_name == "openrouter":
                model_name = "z-ai/glm-4.6"
            else:
                model_name = "z-ai/glm-4.6"  
            
        response = provider.generate(messages, tools, tool_choice, model_name, temperature)
        return response
    
    def stream(self,         
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: Optional[str] = None, 
        temperature: float = 0.3
        ):  
        
        # Use the active provider for streaming
        if isinstance(self.active_provider, str):
            provider = self.providers[self.active_provider]
        else:
            provider = self.active_provider
        
        # Use provider-specific default models if model_name not specified
        if model_name is None:
            if self.active_provider_name == "groq":
                model_name = "moonshotai/kimi-k2-instruct-0905"
            elif self.active_provider_name == "openrouter":
                model_name = "z-ai/glm-4.6"
            else:
                model_name = "z-ai/glm-4.6"  # fallback default
        
        return provider.stream(messages, tools, tool_choice, model_name, temperature)
