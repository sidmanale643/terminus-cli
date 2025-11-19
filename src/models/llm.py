from pydantic import BaseModel
from typing import Optional, Any

class ModelConfig(BaseModel):
    model_name : str
    temperature : float

class Response(BaseModel):
    content: str
    tool_calls: Optional[Any] = None
    stop_reason: Optional[str] = "end_turn"
    reasoning: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    prompt_tokens: Optional[int] = None
    response_tokens: Optional[int] = None
    cost: Optional[float] = None

    def count_total_tokens(self) -> int:
        if self.prompt_tokens and self.response_tokens:
            total_tokens = self.prompt_tokens + self.response_tokens
            return total_tokens
        return 0

class Model(BaseModel):
    name : str
    provider : str
    context_size : int
    input_tokens_pricing : float
    output_tokens_pricing : float

class Glm46Exacto(Model):
    name : str = "z-ai/glm-4.6:exacto"
    provider : str = "z-ai"
    context_size : int = 202752
    input_tokens_pricing : float = 0.45
    output_tokens_pricing  : float = 1.90

class Grok4Fast(Model):
    name: str = "x-ai/grok-4-fast"
    provider : str = "x-ai"
    context_size: int = 2000000
    input_tokens_pricing: float = 0.20
    output_tokens_pricing: float = 0.50

class Glm45AirFree(Model):
    name: str = "z-ai/glm-4.5-air:free"
    provider : str = "z-ai"
    context_size: int = 131072
    input_tokens_pricing: float = 0
    output_tokens_pricing: float = 0

class Sonnet_45(Model):
    name: str = "anthropic/claude-sonnet-4.5"
    provider : str = "anthropic"
    context_size: int = 1000000
    input_tokens_pricing: float = 3
    output_tokens_pricing: float = 15

available_models = [Grok4Fast(), Glm45AirFree(), Sonnet_45(), Glm46Exacto()]