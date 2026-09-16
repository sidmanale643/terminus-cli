from typing import Any, List, Dict
import json
import os


def parse_file_references(user_input: str):
    if not user_input:
        return [], ""
    import re

    pattern = r"@([\w\-./]+(?:\.\w+)?)"

    file_refs = re.findall(pattern, user_input)

    cleaned_message = re.sub(pattern, "", user_input).strip()

    cleaned_message = re.sub(r"\s+", " ", cleaned_message)

    return file_refs, cleaned_message


def load_file_content(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
        return file_content
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")


def format_file_context(file_path: str, content: str) -> str:
    return f"""

<file path="{file_path}">
{content}
</file>"""


def process_file_references(user_input: str, cwd: str | None = None):
    file_refs, cleaned_message = parse_file_references(user_input)

    if not file_refs:
        return user_input, [], []

    loaded_files = []
    errors = []
    file_contexts = []

    for file_path in file_refs:
        try:
            resolved_path = file_path
            if cwd and not os.path.isabs(resolved_path):
                resolved_path = os.path.join(cwd, resolved_path)
            content = load_file_content(resolved_path)
            file_contexts.append(format_file_context(file_path, content))
            loaded_files.append(file_path)
        except Exception as e:
            errors.append(str(e))

    if file_contexts:
        enriched_message = f"{cleaned_message}\n\n{''.join(file_contexts)}"
    else:
        enriched_message = cleaned_message

    return enriched_message, loaded_files, errors


def summarize_messages(
    messages: List[Dict[str, Any]], llm_service, model_name: str | None = None
) -> str:
    from terminus.prompts.compaction_prompt import get_compaction_prompt

    history = json.dumps(messages, ensure_ascii=False, default=str)

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
    return response.content or ""


def discover_skills(cwd: str | None = None) -> list[dict]:
    import yaml

    if cwd is None:
        cwd = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    kodex_cli_root = os.path.dirname(os.path.dirname(script_dir))

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

            skills.append(
                {
                    "name": skill_name,
                    "description": str(description).strip() if description else "",
                    "trigger": str(trigger).strip() if trigger else "",
                    "allowed_tools": metadata.get("allowed-tools", []),
                    "metadata": metadata,
                    "file": path,
                    "content": content,
                }
            )

    return sorted(skills, key=lambda skill: skill["name"])
