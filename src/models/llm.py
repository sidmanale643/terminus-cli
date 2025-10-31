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

