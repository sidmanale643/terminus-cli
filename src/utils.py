from openai import OpenAI
from src.tools.tool_registry import ToolRegistry
from pydantic import BaseModel
from typing import Any, List, Dict
from groq import Groq
import os

class Response(BaseModel):
    content: str
    tool_calls: Any
    reasoning: str | None = None


def parse_tool_calls(tool_calls):
    """
    Parse tool calls from LLM response.
    Handles both complete tool calls and streaming deltas.
    Returns a list of tool calls or an empty list if none.
    """
    if tool_calls is None:
        return []
    
    # If it's already a list, return it
    if isinstance(tool_calls, list):
        return tool_calls
    
    # Otherwise return empty list
    return []


def call_llm(messages):
    api_key = os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPEN_ROUTER_API_KEY environment variable not set")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    model_name = "z-ai/glm-4.5-air:free"
    temperature = 0.3

    tool_registry = ToolRegistry()

    tool_schemas = tool_registry.tool_schemas

    request_params = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "tool_choice": "auto",
        "tools": tool_schemas,
    }

    response = client.chat.completions.create(**request_params)
    choice = response.choices[0].message

    content = getattr(choice, "content", "") or ""
    tool_calls = getattr(choice, "tool_calls", None)
    reasoning_text = getattr(choice, "reasoning", None)

    return Response(content=content, tool_calls=tool_calls, reasoning=reasoning_text)


def groq(messages: List[Dict[str, str]], reasoning: bool = False, reasoning_effort: str = "medium"):

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")

    groq_client = Groq(
        api_key=api_key,
    )
    try:
        tool_registry = ToolRegistry()
        
        tools = tool_registry.tool_schemas
        # Build request params conditionally
        request_params = {
            "model": "moonshotai/kimi-k2-instruct-0905",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,  # Prevent parallel tool calls to avoid formatting issues
        }

        if reasoning:
            request_params["include_reasoning"] = True
            request_params["reasoning_effort"] = reasoning_effort

        response = groq_client.chat.completions.create(**request_params)

        content = response.choices[0].message.content or ""
        tool_calls = response.choices[0].message.tool_calls
        reasoning_text = response.choices[0].message.reasoning or None

        return Response(content=content, tool_calls=tool_calls, reasoning=reasoning_text)

    except Exception as e:
        print(f"Error in groq: {e}")
        return Response(content="", tool_calls=None, reasoning=None)
    
