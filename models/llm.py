from pydantic import BaseModel
from typing import List

class ModelConfig(BaseModel):
    model_name : str
    temperature : float

class Response(BaseModel):
    content: str
    tool_calls: List[str]
    model: str
    temperature: float
    prompt_tokens: int
    response_tokens: int

    def count_total_tokens(self) -> int:
        total_tokens = self.prompt_tokens + self.response_tokens
        return total_tokens

