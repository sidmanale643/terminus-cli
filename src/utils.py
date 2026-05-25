from openai import OpenAI
from src.tools.tool_registry import ToolRegistry
from pydantic import BaseModel
from typing import Any, List, Dict
from groq import Groq
from types import SimpleNamespace
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


def merge_stream_tool_calls(existing: list[Any] | None, delta_tool_calls: Any) -> list[Any]:
    """
    Merge streaming tool call deltas into a stable list of tool-call-like objects.

    OpenAI-compatible providers often stream tool calls in fragments keyed by
    ``index`` with partial ``id``, ``function.name``, and ``function.arguments``.
    This helper reconstructs the full calls so the agent loop can execute the
    tool after streaming completes.
    """
    merged = list(existing or [])
    incoming = parse_tool_calls(delta_tool_calls)

    for delta in incoming:
        index = getattr(delta, "index", None)
        if index is None:
            index = len(merged)

        while len(merged) <= index:
            merged.append(
                SimpleNamespace(
                    id="",
                    type="function",
                    function=SimpleNamespace(name="", arguments=""),
                )
            )

        current = merged[index]

        delta_id = getattr(delta, "id", None)
        if delta_id:
            current.id = delta_id

        delta_type = getattr(delta, "type", None)
        if delta_type:
            current.type = delta_type

        delta_function = getattr(delta, "function", None)
        if delta_function is None and isinstance(delta, dict):
            delta_function = delta.get("function")

        if delta_function is None:
            continue

        delta_name = getattr(delta_function, "name", None)
        if delta_name is None and isinstance(delta_function, dict):
            delta_name = delta_function.get("name")
        if delta_name:
            current.function.name = delta_name

        delta_arguments = getattr(delta_function, "arguments", None)
        if delta_arguments is None and isinstance(delta_function, dict):
            delta_arguments = delta_function.get("arguments")
        if delta_arguments:
            current.function.arguments += delta_arguments

    return merged


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
    if not user_input:
        return [], ""
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

def compact(messages: List[Dict[str, Any]], llm_service, model_name: str | None = None) -> List[Dict[str, Any]]:

    if len(messages) <= 2:
        return messages[:]

    # Exclude the most recent user message so it isn't lost
    history = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[:-1]
    )

    summarize_prompt = (
        "<reminder>\n"
        "You have currently exhausted your current context window limit. "
        "Summarize all the previous details concisely, preserving key facts, "
        "decisions, and the current task state.\n"
        "</reminder>\n\n"
        f"<conversation_history>\n{history}\n</conversation_history>"
    )

    response = llm_service.generate(
        messages=[{"role": "system", "content": summarize_prompt}],
        model_name=model_name,
        temperature=0.3,
    )
    summary = response.content or ""

    compacted = [
        {"role": "system", "content": "Previous context summarized below."},
        {"role": "system", "content": summary},
    ]

    if messages and messages[-1]["role"] == "user":
        compacted.append(messages[-1])

    return compacted

def discover_skills(cwd: str | None = None) -> list[dict]:
    """Discover skills from local .skills/ and terminus-cli/.skills/."""
    import yaml

    if cwd is None:
        cwd = os.getcwd()

    # Determine kodex-cli root (parent of src/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kodex_cli_root = os.path.dirname(script_dir)

    skills_dirs = []
    local_skills_dir = os.path.join(cwd, ".skills")
    if os.path.isdir(local_skills_dir):
        skills_dirs.append(local_skills_dir)

    kodex_cli_skills_dir = os.path.join(kodex_cli_root, ".skills")
    if os.path.isdir(kodex_cli_skills_dir) and kodex_cli_skills_dir not in skills_dirs:
        skills_dirs.append(kodex_cli_skills_dir)

    skills: list[dict] = []
    seen_names: set[str] = set()

    for skills_dir in skills_dirs:
        for entry in sorted(os.listdir(skills_dir)):
            path = os.path.join(skills_dir, entry)

            if os.path.isdir(path):
                skill_file = os.path.join(path, "SKILL.md")
                if os.path.isfile(skill_file):
                    path = skill_file
                else:
                    continue
            elif not os.path.isfile(path):
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue

            if not content.startswith("---"):
                continue

            try:
                _, frontmatter, _ = content.split("---", 2)
                metadata = yaml.safe_load(frontmatter) or {}
            except (ValueError, yaml.YAMLError):
                continue

            skill_name = str(metadata.get("name", "")).strip()
            if not skill_name:
                continue
            if skill_name in seen_names:
                continue
            seen_names.add(skill_name)

            description = metadata.get("description", "")
            trigger = metadata.get("trigger", "")

            skills.append({
                "name": skill_name,
                "description": str(description).strip() if description else "",
                "trigger": str(trigger).strip() if trigger else "",
                "allowed_tools": metadata.get("allowed-tools", []),
                "metadata": metadata,
                "file": path,
                "content": content,
            })

    return sorted(skills, key=lambda skill: skill["name"])
    
