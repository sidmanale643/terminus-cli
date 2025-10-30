from typing import List, Dict, Optional
from models.llm import Response
from openai import OpenAI
from utils import parse_tool_calls
from llm_service.base_class import LlmProvider
import os


class OpenRouterProvider(LlmProvider):
    def __init__(self, name: str):
        self.name = name

    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "z-ai/glm-4.5-air", 
        temperature: float = 0.3
    ) -> Response:
        """
        Makes a request to OpenRouter API with optional reasoning capabilities.
        """
        api_key = os.getenv("OPEN_ROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPEN_ROUTER_API_KEY environment variable not set")

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        try:
            request_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "extra_body": {}
            }

            # Add tools if provided
            if tools and len(tools) > 0:
                request_params["tools"] = tools
                request_params["tool_choice"] = tool_choice
                request_params["parallel_tool_calls"] = True

            response = client.chat.completions.create(**request_params)

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
            print(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")
            return Response(content="", tool_calls=None, stop_reason="error", reasoning=None)
    
    def stream(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "z-ai/glm-4.6", 
        temperature: float = 0.3,
        stream: bool = True
    ) -> Response:
        """
        Stream a response from OpenRouter.
        """
        api_key = os.getenv("OPEN_ROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPEN_ROUTER_API_KEY environment variable not set")
        

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        try:
            request_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
                "extra_body": {}
            }
            
            # Add tools if provided
            if tools and len(tools) > 0:
                request_params["tools"] = tools
                request_params["tool_choice"] = tool_choice
                request_params["parallel_tool_calls"] = True

            stream = client.chat.completions.create(**request_params)

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

        except Exception as e:
            print(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")
            yield Response(content="", tool_calls=None, stop_reason="error", reasoning=None)

