from typing import List, Dict, Optional
from src.models.llm import Response
from openai import OpenAI
from src.utils import parse_tool_calls
from src.llm_service.base_class import LlmProvider
import os

from dotenv import load_dotenv

load_dotenv()

class OpenRouterProvider(LlmProvider):
    def __init__(self, name: str):
        self.name = name

    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "z-ai/glm-4.5-air:free", 
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
                "extra_body": {"usage": {"include": True}}   
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
            
            # Extract usage information
            usage = response.usage
            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", 0)
            total_tokens = getattr(usage, "total_tokens", 0)
            
            # Extract reasoning tokens if available
            completion_details = getattr(usage, "completion_tokens_details", None)
            reasoning_tokens = 0
            if completion_details:
                reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0)
            
            # Extract cost information
            cost = getattr(usage, "cost", 0)
            cost_details = getattr(usage, "cost_details", {})
         
            tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))
            stop_reason = "tool_use" if tool_calls else "end_turn"

            print(f"Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, "
                  f"Total: {total_tokens}, Reasoning: {reasoning_tokens}, Cost: ${cost}")

            return Response(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                reasoning=reasoning_text,
                model=response.model,
                temperature=temperature,
                prompt_tokens=prompt_tokens,
                response_tokens=completion_tokens,
                cost=cost
            )

        except Exception as e:
            print(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")
            return Response(
                content="", 
                tool_calls=None, 
                stop_reason="error", 
                reasoning=None,
                model=None,
                temperature=None,
                prompt_tokens=None,
                response_tokens=None
            )
    
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
                "extra_body": {"usage": {"include": True}}
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
                    stop_reason = "tool_use" if (tool_calls and len(tool_calls) > 0) else "end_turn"
                    
                    # Extract usage from chunk if available (usually in the last chunk)
                    usage = getattr(chunk, "usage", None)
                    prompt_tokens = None
                    response_tokens = None
                    reasoning_tokens = 0
                    cost = 0
                    
                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", None)
                        response_tokens = getattr(usage, "completion_tokens", None)
                        
                        # Extract reasoning tokens if available
                        completion_details = getattr(usage, "completion_tokens_details", None)
                        if completion_details:
                            reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0)
                        
                        # Extract cost information
                        cost = getattr(usage, "cost", 0)
                        
                        # Print usage summary when available (final chunk)
                        if prompt_tokens is not None:
                            total_tokens = getattr(usage, "total_tokens", 0)
                            print(f"Stream Usage - Prompt: {prompt_tokens}, Completion: {response_tokens}, "
                                  f"Total: {total_tokens}, Reasoning: {reasoning_tokens}, Cost: ${cost}")
                    
                    yield Response(
                        content=content,
                        tool_calls=tool_calls if len(tool_calls) > 0 else None,
                        stop_reason=stop_reason,
                        reasoning=reasoning_text,
                        model=getattr(chunk, "model", None),
                        temperature=temperature,
                        prompt_tokens=prompt_tokens,
                        response_tokens=response_tokens,
                        cost=cost
                    )

        except Exception as e:
            print(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")
            yield Response(
                content="", 
                tool_calls=None, 
                stop_reason="error", 
                reasoning=None,
                model=None,
                temperature=None,
                prompt_tokens=None,
                response_tokens=None,
                cost=None
            )