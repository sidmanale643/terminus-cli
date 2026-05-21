import os
import subprocess
from textwrap import dedent
from typing import Any, Callable, Dict, Optional

from src.models.tool import ToolSchema


DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120


class Bash(ToolSchema):
    """
    Tool for executing bash commands and returning the output.
    """

    def __init__(self):
        self.name = "bash"

    def description(self) -> str:
        return dedent("""
        Executes a bash command and returns its output, error, and exit status.

        Supports all bash features: pipes, redirects, command substitution,
        command chaining, and shell built-ins.

        IMPORTANT — DO NOT run destructive commands:
        - Do NOT run rm, mv, chmod, chown, dd, kill, killall, mkfs, pkill, reboot, shutdown, sudo, truncate, or any command that modifies, moves, or deletes files or system state.
        - Do NOT run git reset, git push --force, git clean, or any git operation that rewrites history or deletes work.
        - Do NOT run npm install, pip install, uv add, or any package installation without explicit user confirmation.
        - Do NOT run any command that could harm the user's system or data.

        For file edits, use the dedicated file_editor tool instead of sed/awk/perl.
        For reading files, use the file_reader tool instead of cat/head/tail.
        For searching code, use the grep_search tool instead of grep/rg.

        Safety notes:
        - Commands run with a configurable timeout.
        - Prefer dedicated tools for reading files, listing directories, and search.

        Supported examples:
        - pwd
        - git status
        - git diff
        - git log --oneline -5
        - echo hello | tr a-z A-Z
        - python3 -m py_compile src/main.py
        - ruff check src/
        - npm run build
        - cat file.txt | grep pattern
        """)

    def json_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "the bash command to run",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "optional working directory for the command",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": (
                                "optional timeout in seconds "
                                f"(1-{MAX_TIMEOUT_SECONDS}, default {DEFAULT_TIMEOUT_SECONDS})"
                            ),
                            "minimum": 1,
                            "maximum": MAX_TIMEOUT_SECONDS,
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        status_callback: Optional[Callable[..., Any]] = None,
    ) -> str:
        validation_error = self._validate_cwd(cwd)
        if validation_error:
            return validation_error

        timeout_value = self._normalize_timeout(timeout)
        if isinstance(timeout_value, str):
            return timeout_value

        if not command or not command.strip():
            return "Command failed: command must not be empty"

        try:
            if status_callback:
                status_callback("executing bash command", is_thinking=False)
            result = subprocess.run(
                command,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout_value,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout_value} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

        if result.returncode == 0:
            return (
                result.stdout
                if result.stdout
                else "(command executed successfully, no output)"
            )

        error_msg = f"Command failed with exit code {result.returncode}"
        if result.stderr:
            error_msg += f"\nError: {result.stderr}"
        if result.stdout:
            error_msg += f"\nOutput: {result.stdout}"
        return error_msg

    def _validate_cwd(self, cwd: Optional[str]) -> Optional[str]:
        if cwd is None:
            return None
        if not os.path.exists(cwd):
            return f"Command failed: cwd does not exist: {cwd}"
        if not os.path.isdir(cwd):
            return f"Command failed: cwd is not a directory: {cwd}"
        return None

    def _normalize_timeout(self, timeout: int) -> int | str:
        try:
            timeout_value = int(timeout)
        except (TypeError, ValueError):
            return "Command failed: timeout must be an integer"

        if timeout_value < 1 or timeout_value > MAX_TIMEOUT_SECONDS:
            return (
                "Command failed: timeout must be between "
                f"1 and {MAX_TIMEOUT_SECONDS} seconds"
            )

        return timeout_value
