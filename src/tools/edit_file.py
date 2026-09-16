import difflib
import os
from src.models.tool import ToolSchema
from textwrap import dedent


class FileEditor(ToolSchema):
    def __init__(self):
        self.name = "file_editor"

    def description(self):
        return dedent("""
        Performs exact string replacements in files.

        Usage:
        - Read the file with file_reader before editing so old_string can be copied exactly.
        - Use file_path for the path. Relative paths are resolved from the current working directory.
        - Use old_string/new_string for a single edit or old_strings/new_strings for multiple edits in one atomic operation.
        - When editing text from file_reader output, preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
        - ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
        - The edit will FAIL if `old_string` is not found in the file with an error.
        - The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`.
        - Multiple edits are applied sequentially. If any replacement fails, no changes are written.
        """)

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "the path of the file to edit",
                        },
                        "old_string": {
                            "type": "string",
                            "description": "the old string to replace",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "the new string to replace the old string with",
                        },
                        "old_strings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "the old strings to replace in order",
                        },
                        "new_strings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "the replacement strings to apply in order",
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "If true, replace all occurrences of old_string. Defaults to false (replace only the first occurrence).",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

    def _make_diff(self, old_text: str, new_text: str, file_path: str) -> str:
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
                n=3,
            )
        )
        return "\n".join(diff) if diff else "(no visible diff)"

    def run(
        self,
        file_path: str = None,
        old_string: str = None,
        new_string: str = None,
        old_strings: list[str] = None,
        new_strings: list[str] = None,
        replace_all: bool = False,
    ):
        if not file_path:
            return "Error: file_path is required"

        multiple = old_strings is not None or new_strings is not None
        if multiple:
            if old_strings is None or new_strings is None:
                return "Error: old_strings and new_strings are required."
            if old_string is not None or new_string is not None:
                return "Error: use either single or multiple edit arguments, not both."
            if replace_all:
                return "Error: replace_all is only supported for a single edit."
            if len(old_strings) != len(new_strings):
                return "Error: old_strings and new_strings must have the same length."
            edits = list(zip(old_strings, new_strings))
        else:
            if old_string is None or new_string is None:
                return "Error: old_string/new_string or old_strings/new_strings are required"
            edits = [(old_string, new_string)]

        file_path = os.path.expanduser(file_path)
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except PermissionError:
            return f"Error: Permission denied reading {file_path}"
        except OSError as exc:
            return f"Error: Could not read {file_path}: {exc}"
        results = []
        new_content = original_content
        total_replacements = 0

        for index, (old, new) in enumerate(edits, start=1):
            if not isinstance(old, str) or not isinstance(new, str):
                message = "old and new edit values must be strings"
                if multiple:
                    results.append(f"  [{index}] FAILED: {message}")
                    return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)
                return f"Error: {message}"

            if old not in new_content:
                if multiple:
                    results.append(f"  [{index}] FAILED: old_string not found")
                    return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)
                return (
                    f"Error: The string to replace was not found in {file_path}\n\n"
                    "Make sure to read the file first and use the exact string "
                    "(including whitespace and indentation) that you want to replace."
                )

            occurrence_count = new_content.count(old)
            if occurrence_count > 1 and not replace_all:
                if multiple:
                    results.append(
                        f"  [{index}] FAILED: old_string found {occurrence_count} times (ambiguous)"
                    )
                    return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)
                return (
                    f"Error: The string appears {occurrence_count} times in {file_path}. "
                    "Either provide more context to make old_string unique, "
                    "or set replace_all=true to replace all occurrences."
                )

            new_content = new_content.replace(old, new, -1 if replace_all else 1)
            total_replacements += occurrence_count if replace_all else 1
            if multiple:
                results.append(f"  [{index}] OK")

        if original_content == new_content:
            if multiple:
                return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)
            return f"No changes made to {file_path} (old_string and new_string are identical)."

        diff = self._make_diff(original_content, new_content, file_path)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except PermissionError:
            return f"Error: Permission denied writing {file_path}"
        except OSError as exc:
            return f"Error: Could not write {file_path}: {exc}"
        if multiple:
            return f"Multi-edited {file_path}:\n" + "\n".join(results) + f"\n\n{diff}"
        return f"Edited {file_path} ({total_replacements} replacement{'s' if total_replacements > 1 else ''})\n\n{diff}"
