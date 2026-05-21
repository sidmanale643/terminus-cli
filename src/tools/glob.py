import os
import subprocess
from textwrap import dedent

from src.models.tool import ToolSchema


DEFAULT_LIMIT = 100


class Glob(ToolSchema):
    def __init__(self):
        self.name = "glob"

    def description(self):
        return dedent("""
        Find files by glob pattern using ripgrep file discovery.
        Respects .gitignore by default and returns absolute paths sorted by
        most recently modified first.
        """).strip()

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to match files, e.g. '**/*.py' or 'src/**/*.ts'",
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search in. Defaults to the current working directory.",
                            "default": ".",
                        },
                        "limit": {
                            "type": "integer",
                            "description": f"Maximum number of matching file paths to return. Defaults to {DEFAULT_LIMIT}.",
                            "minimum": 1,
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": ["pattern"],
                },
            },
        }

    def run(self, pattern: str, path: str = None, limit: int = DEFAULT_LIMIT):
        if not pattern or not pattern.strip():
            return "Error: Empty pattern provided. Please provide a glob pattern."

        search_path = self._resolve_path(path)
        if not os.path.exists(search_path):
            return f"Error: Path '{search_path}' does not exist."
        if not os.path.isdir(search_path):
            return f"Error: Path '{search_path}' is not a directory."

        limit_value = self._normalize_limit(limit)
        if isinstance(limit_value, str):
            return limit_value

        try:
            result = subprocess.run(
                ["rg", "--files", "--glob", pattern, search_path],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return "Error: ripgrep (rg) not found. Please install ripgrep: https://github.com/BurntSushi/ripgrep"
        except Exception as exc:
            return f"Error executing glob search: {exc}"

        if result.returncode == 1:
            return "No files found."
        if result.returncode != 0:
            return f"Error: {result.stderr.strip() or 'Unknown error'}"

        matches = [
            os.path.abspath(line.strip())
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        if not matches:
            return "No files found."

        matches.sort(key=self._modified_time, reverse=True)
        return "\n".join(matches[:limit_value])

    def _resolve_path(self, path: str | None) -> str:
        search_path = os.path.expanduser(path or ".")
        if not os.path.isabs(search_path):
            search_path = os.path.abspath(search_path)
        return search_path

    def _normalize_limit(self, limit: int) -> int | str:
        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            return "Error: limit must be an integer."

        if limit_value < 1:
            return "Error: limit must be at least 1."

        return limit_value

    def _modified_time(self, file_path: str) -> float:
        try:
            return os.path.getmtime(file_path)
        except OSError:
            return 0
