import os
from src.models.tool import ToolSchema
from textwrap import dedent


class FileReader(ToolSchema):
    def __init__(self):
        self.name = "file_reader"

    def description(self):
        return dedent("""
        Reads one or more files from the local filesystem.
        Use file_path for a single file or files for multiple files. If the user
        provides a relative path, pass it as-is; it will be resolved from the
        current working directory. It is okay to read a file that does not exist;
        an error will be returned.

        Usage:
        - The code line numbers will also be provided starting from 1.
        - Use offset and limit to read specific line ranges (e.g. offset=50, limit=30).
        - Prefer file_path/files, but path, file_paths, and paths are accepted as compatibility aliases.
        - If a file does not exist or read file is empty you will be informed so.
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
                            "description": "the path of the file to read",
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "the paths of multiple files to read",
                        },
                        "path": {
                            "type": "string",
                            "description": "compatibility alias for file_path",
                        },
                        "file_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "compatibility alias for files",
                        },
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "compatibility alias for files",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "1-indexed line number to start reading from (default 1)",
                            "minimum": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "maximum number of lines to read (default: read all)",
                            "minimum": 1,
                        }
                    },
                    "required": [],
                },
            },
        }

    def _read_one(self, file_path: str, include_header: bool = False, offset: int = 1, limit: int = None):
        try:
            file_path = os.path.expanduser(file_path)
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                message = "Error: File does not exist" if include_header else f"File does not exist: {file_path}"
                return f"File: {file_path}\n{message}" if include_header else message
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if not lines:
                return f"File: {file_path}\n(empty)" if include_header else "File is empty"

            start = max(0, offset - 1)
            end = start + limit if limit else len(lines)
            selected = lines[start:end]

            numbered = "\n".join(
                f"  {i + start + 1}\t{line.rstrip()}" for i, line in enumerate(selected)
            )
            if include_header:
                return f"File: {file_path}\n{numbered}"
            return f"File Content:\n{numbered}"
        except PermissionError:
            message = "Error: Permission denied" if include_header else f"Error: Permission denied reading {file_path}"
            return f"File: {file_path}\n{message}" if include_header else message
        except Exception as e:
            message = f"Error: {e}" if include_header else f"Error reading file: {e}"
            return f"File: {file_path}\n{message}" if include_header else message

    def run(
        self,
        file_path: str = None,
        path: str = None,
        files: list[str] = None,
        file_paths: list[str] = None,
        paths: list[str] = None,
        offset: int = 1,
        limit: int = None,
    ):
        file_path = file_path or path
        files = files or file_paths or paths

        if files:
            return "\n\n".join(
                self._read_one(path, include_header=True, offset=offset, limit=limit)
                for path in files
            )

        if file_path:
            return self._read_one(file_path, offset=offset, limit=limit)

        return "Error: file_path or files is required"
