from abc import ABC
from abc import abstractmethod
from typing import List, Dict, Optional
from models.llm import Response

class LlmProvider(ABC):
    @abstractmethod
    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "glm-4.5-air", 
        temperature: float = 0.3
    ) -> Response:
        pass
    
    def stream():
        pass

    def _get_provider_name(self):
        return self.__class__.__name__