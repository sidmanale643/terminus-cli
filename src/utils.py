from typing import Any, List, Dict
import json
import os


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
    from src.prompts.compaction_prompt import get_compaction_prompt

    if len(messages) <= 2:
        return messages[:]

    retained_message = messages[-1] if messages[-1].get("role") == "user" else None
    messages_to_summarize = messages[:-1] if retained_message else messages
    history = json.dumps(messages_to_summarize, ensure_ascii=False, default=str)

    summarize_prompt = (
        f"{get_compaction_prompt()}\n\n"
        "<conversation_history_json>\n"
        f"{history}\n"
        "</conversation_history_json>"
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

    if retained_message:
        compacted.append(retained_message)

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
    
