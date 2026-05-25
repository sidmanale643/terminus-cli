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

# ─── OpenRouter models ───────────────────────────────────────────────────────

class Gemma4(Model):
    name: str = "google/gemma-4-31b-it:free"
    provider: str = "google"
    context_size: int = 262144
    input_tokens_pricing: float = 0
    output_tokens_pricing: float = 0

class Glm45AirFree(Model):
    name: str = "z-ai/glm-4.5-air:free"
    provider : str = "z-ai"
    context_size: int = 131072
    input_tokens_pricing: float = 0
    output_tokens_pricing: float = 0

class Grok4Fast(Model):
    name: str = "x-ai/grok-4-fast"
    provider : str = "x-ai"
    context_size: int = 2000000
    input_tokens_pricing: float = 0.20
    output_tokens_pricing: float = 0.50

class Minimax(Model):
    name: str = "minimax/minimax-m2.5:free"
    provider : str = "minimax"
    context_size: int = 1000000
    input_tokens_pricing: float = 3
    output_tokens_pricing: float = 15

class Sonnet_45(Model):
    name: str = "anthropic/claude-sonnet-4.5"
    provider : str = "anthropic"
    context_size: int = 1000000
    input_tokens_pricing: float = 3
    output_tokens_pricing: float = 15

class DeepseekV4Flash(Model):
    name: str = "deepseek/deepseek-v4-flash"
    provider: str = "openrouter"
    context_size: int = 1048576
    input_tokens_pricing: float = 0.14
    output_tokens_pricing: float = 0.28

class DeepseekV4FlashFree(Model):
    name: str = "deepseek/deepseek-v4-flash:free"
    provider: str = "openrouter"
    context_size: int = 1048576
    input_tokens_pricing: float = 0
    output_tokens_pricing: float = 0

# ─── Groq models ─────────────────────────────────────────────────────────────

class GptOss120b(Model):
    name: str = "openai/gpt-oss-120b"
    provider: str = "groq"
    context_size: int = 128000
    input_tokens_pricing: float = 0
    output_tokens_pricing: float = 0

available_models = [
    Gemma4(), Glm45AirFree(), Grok4Fast(),
    Minimax(), Sonnet_45(), DeepseekV4Flash(),
    DeepseekV4FlashFree(), GptOss120b(),
]