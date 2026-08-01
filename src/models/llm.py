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
    openrouter_provider : Optional[list] = None

# ─── OpenRouter models ───────────────────────────────────────────────────────

class DeepseekV4Flash0731(Model):
    name: str = "deepseek/deepseek-v4-flash-0731"
    provider: str = "openrouter"
    context_size: int = 1048576
    input_tokens_pricing: float = 0.14
    output_tokens_pricing: float = 0.28

available_models = [
    DeepseekV4Flash0731(),
]
