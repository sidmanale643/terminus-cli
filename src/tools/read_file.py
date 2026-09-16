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
                        "offset": {
                            "type": "integer",
                            "description": "1-indexed line number to start reading from (default 1)",
                            "minimum": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "maximum number of lines to read (default: read all)",
                            "minimum": 1,
                        },
                    },
                    "required": [],
                },
            },
        }

    def _read_one(
        self,
        file_path: str,
        include_header: bool = False,
        offset: int = 1,
        limit: int = None,
    ):
        file_path = os.path.expanduser(file_path)
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        def format_error(message: str) -> str:
            return f"File: {file_path}\n{message}" if include_header else message

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except PermissionError:
            return format_error(
                "Error: Permission denied"
                if include_header
                else f"Error: Permission denied reading {file_path}"
            )
        except FileNotFoundError:
            return format_error(
                "Error: File does not exist"
                if include_header
                else f"File does not exist: {file_path}"
            )
        except OSError as exc:
            return format_error(
                f"Error: {exc}" if include_header else f"Error reading file: {exc}"
            )

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

    def run(
        self,
        file_path: str = None,
        files: list[str] = None,
        offset: int = 1,
        limit: int = None,
    ):
        if files:
            return "\n\n".join(
                self._read_one(path, include_header=True, offset=offset, limit=limit)
                for path in files
            )

        if file_path:
            return self._read_one(file_path, offset=offset, limit=limit)

        return "Error: file_path or files is required"
