import os
import heapq
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
            process = subprocess.Popen(
                ["rg", "--files", "--glob", pattern, search_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
        except FileNotFoundError:
            return "Error: ripgrep (rg) not found. Please install ripgrep: https://github.com/BurntSushi/ripgrep"
        except Exception as exc:
            return f"Error executing glob search: {exc}"

        newest = []
        assert process.stdout is not None
        for line in process.stdout:
            candidate = os.path.abspath(line.strip())
            if not candidate:
                continue
            item = (self._modified_time(candidate), candidate)
            if len(newest) < limit_value:
                heapq.heappush(newest, item)
            elif item > newest[0]:
                heapq.heapreplace(newest, item)
        stderr = process.stderr.read() if process.stderr else ""
        returncode = process.wait()

        if returncode == 1:
            return "No files found."
        if returncode != 0:
            return f"Error: {stderr.strip() or 'Unknown error'}"
        if not newest:
            return "No files found."
        return "\n".join(path for _, path in sorted(newest, reverse=True))

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
