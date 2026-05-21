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
        - Use file_path for the path. Relative paths are resolved from the current working directory. path is accepted as a compatibility alias.
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
                        "path": {
                            "type": "string",
                            "description": "compatibility alias for file_path",
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
        path: str = None,
    ):
        try:
            file_path = file_path or path
            if not file_path:
                return "Error: file_path is required"
            if old_strings is not None or new_strings is not None:
                return self._run_multiple(file_path, old_strings, new_strings)
            if old_string is None or new_string is None:
                return "Error: old_string/new_string or old_strings/new_strings are required"
            file_path = os.path.expanduser(file_path)
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            if old_string not in original_content:
                return (
                    f"Error: The string to replace was not found in {file_path}\n\n"
                    "Make sure to read the file first and use the exact string "
                    "(including whitespace and indentation) that you want to replace."
                )

            occurrence_count = original_content.count(old_string)

            if occurrence_count > 1 and not replace_all:
                return (
                    f"Error: The string appears {occurrence_count} times in {file_path}. "
                    "Either provide more context to make old_string unique, "
                    "or set replace_all=true to replace all occurrences."
                )

            if replace_all:
                new_content = original_content.replace(old_string, new_string)
            else:
                new_content = original_content.replace(old_string, new_string, 1)

            if original_content == new_content:
                return f"No changes made to {file_path} (old_string and new_string are identical)."

            diff = self._make_diff(old_string, new_string, file_path)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            count = occurrence_count if replace_all else 1
            return f"Edited {file_path} ({count} replacement{'s' if count > 1 else ''})\n\n{diff}"

        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except PermissionError:
            return f"Error: Permission denied editing {file_path}"
        except Exception as e:
            return f"Error editing file: {e}"

    def _run_multiple(
        self,
        file_path: str,
        old_strings: list[str] = None,
        new_strings: list[str] = None,
    ):
        if old_strings is None or new_strings is None:
            return "Error: old_strings and new_strings are required."
        if len(old_strings) != len(new_strings):
            return "Error: old_strings and new_strings must have the same length."

        file_path = os.path.expanduser(file_path)
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except PermissionError:
            return f"Error: Permission denied reading {file_path}"

        original = content
        results = []

        for i, (old, new) in enumerate(zip(old_strings, new_strings)):
            if old not in content:
                results.append(f"  [{i + 1}] FAILED: old_string not found")
                return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)

            count = content.count(old)
            if count > 1:
                results.append(
                    f"  [{i + 1}] FAILED: old_string found {count} times (ambiguous)"
                )
                return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)

            content = content.replace(old, new, 1)
            results.append(f"  [{i + 1}] OK")

        if content == original:
            return f"Multi-edit aborted for {file_path}:\n" + "\n".join(results)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            return f"Error: Permission denied writing {file_path}"

        diff = self._make_diff(original, content, file_path)
        return f"Multi-edited {file_path}:\n" + "\n".join(results) + f"\n\n{diff}"
