from pydantic import BaseModel
from typing import Any, Optional

from terminus.config import DEFAULT_MODEL, DEFAULT_PROVIDER


class Response(BaseModel):
    content: str
    tool_calls: Optional[Any] = None
    reasoning: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    response_tokens: Optional[int] = None


class Model(BaseModel):
    name: str
    provider: str
    context_size: int
    input_tokens_pricing: float
    output_tokens_pricing: float


available_models = [
    Model(
        name=DEFAULT_MODEL,
        provider=DEFAULT_PROVIDER,
        context_size=1048576,
        input_tokens_pricing=0.14,
        output_tokens_pricing=0.28,
    ),
]
