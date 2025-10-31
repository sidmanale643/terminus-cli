import re
import subprocess
from src.models.tool import ToolSchema
import json
from textwrap import dedent

class Lint(ToolSchema):
    def __init__(self):
        self.name = "lint"

    def _clean_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)

    def description(self):
        return dedent("""
        Lint (and optionally fix) the codebase using Ruff.
        This tool is useful for linting the codebase and fixing linting errors.
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
                        "codebase": {"type": "string"},
                        "fix": {"type": "boolean", "default": False}
                    },
                    "required": ["codebase"]
                }
            }
        }

    def run(self, codebase: str, fix: bool = False):
        try:
            cmd = ["ruff", "check", codebase]
            if fix:
                cmd.append("--fix")

            process = subprocess.run(cmd, capture_output=True, text=True)

            stdout_clean = self._clean_ansi(process.stdout.strip())
            stderr_clean = self._clean_ansi(process.stderr.strip())

            return json.dumps({
                "status": "success" if process.returncode == 0 else "error",
                "stdout": stdout_clean,
                "stderr": stderr_clean,
                "exit_code": process.returncode,
                "command_executed": " ".join(cmd)
            })

        except FileNotFoundError:
            return json.dumps({
                "status": "error",
                "stderr": "Ruff is not installed. Please install it using `pip install ruff`.",
                "exit_code": 1
            })

        except Exception as e:
            return json.dumps({
                "status": "error",
                "stderr": str(e),
                "exit_code": 1
            })
