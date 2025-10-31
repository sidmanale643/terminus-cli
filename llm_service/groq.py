from typing import List, Dict, Optional
from models.llm import Response
from groq import Groq
from utils import parse_tool_calls
from llm_service.base_class import LlmProvider
import os


class GroqProvider(LlmProvider):
    def __init__(self, name: str):
        self.name = name

    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "moonshotai/kimi-k2-instruct-0905", 
        temperature: float = 0.3
    ) -> Response:
        """
        Makes a request to Groq API with optional reasoning capabilities.
        """
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        
        groq_client = Groq(api_key=api_key)
        
        try:
            request_params = {
                "model": model_name,
                "messages": messages,
                "tools": tools or [],
                "tool_choice": tool_choice,
                "temperature": temperature,
            }

            response = groq_client.chat.completions.create(**request_params)

            choice = response.choices[0].message
            content = getattr(choice, "content", "") or ""
            reasoning_text = getattr(choice, "reasoning", None)
            
            tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))
            stop_reason = "tool_use" if tool_calls else "end_turn"

            return Response(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                reasoning=reasoning_text
            )

        except Exception as e:
            raise Exception(f"Error in GroqProvider: {type(e).__name__}: {e}")
    
    def stream(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "moonshotai/kimi-k2-instruct-0905", 
        temperature: float = 0.3,
        stream : bool = True
    ) -> Response:
        """
        Stream a response from Groq.
        """
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        
        groq_client = Groq(api_key=api_key)
        
        try:
            request_params = {
                "model":  "moonshotai/kimi-k2-instruct-0905",
                "messages": messages,
                "tools": tools or [],
                "tool_choice": tool_choice,
                "temperature": temperature,
                "stream" : True,
            }

            stream = groq_client.chat.completions.create(**request_params)

            for chunk in stream:
                choice = chunk.choices[0].delta 
                content = getattr(choice, "content", "") or ""
                reasoning_text = getattr(choice, "reasoning", None)
                
                tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))

                if content or (tool_calls and len(tool_calls) > 0) or reasoning_text:
                    # Only set tool_use if there are actually tool calls (non-empty list)
                    stop_reason = "tool_use" if (tool_calls and len(tool_calls) > 0) else "end_turn"
                    
                    yield Response(
                        content=content,
                        tool_calls=tool_calls if len(tool_calls) > 0 else None,
                        stop_reason=stop_reason,
                        reasoning=reasoning_text
                    )

        except Exception:
            yield Response(content="", tool_calls=None, stop_reason="error", reasoning=None)
