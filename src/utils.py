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

    
def parse_file_references(user_input: str):
    """
    Parse @filename references from user input.
    Returns a list of file paths and the cleaned message.
    
    Examples:
        "@file.py what does this do?" -> (["file.py"], "what does this do?")
        "compare @a.py and @b.py" -> (["a.py", "b.py"], "compare and")
    """
    import re
    
    # Pattern to match @filename (supports various file extensions and paths)
    pattern = r'@([\w\-./]+(?:\.\w+)?)'
    
    # Find all file references
    file_refs = re.findall(pattern, user_input)
    
    # Remove @ references from the message
    cleaned_message = re.sub(pattern, '', user_input).strip()
    # Clean up extra spaces
    cleaned_message = re.sub(r'\s+', ' ', cleaned_message)
    
    return file_refs, cleaned_message


def load_file_content(file_path):
    """
    Load the content of a file.
    Raises FileNotFoundError if file doesn't exist.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        return file_content
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")


def format_file_context(file_path: str, content: str) -> str:
    """
    Format file content for injection into the message context.
    """
    return f"""

<file path="{file_path}">
{content}
</file>"""


def process_file_references(user_input: str):
    """
    Process user input with @file references.
    Returns enriched message with file contents and list of loaded files.
    
    Returns:
        tuple: (enriched_message, loaded_files, errors)
    """
    file_refs, cleaned_message = parse_file_references(user_input)
    
    if not file_refs:
        return user_input, [], []
    
    loaded_files = []
    errors = []
    file_contexts = []
    
    for file_path in file_refs:
        try:
            content = load_file_content(file_path)
            file_contexts.append(format_file_context(file_path, content))
            loaded_files.append(file_path)
        except Exception as e:
            errors.append(str(e))
    
    # Construct the enriched message
    if file_contexts:
        enriched_message = f"{cleaned_message}\n\n{''.join(file_contexts)}"
    else:
        enriched_message = cleaned_message
    
    return enriched_message, loaded_files, errors


