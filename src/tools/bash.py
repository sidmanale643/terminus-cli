import os
import subprocess
from textwrap import dedent
from typing import Any, Callable, Dict, Optional

from src.command_permissions import CommandPermissionManager, PermissionDecision
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

        Commands run through bash. Simple read-only commands from the execution
        policy run automatically; shell syntax and state-changing commands
        require explicit approval before they run.

        The policy is an approval gate, not a sandbox. Commands are still
        executed with bash after approval.

        This is the only tool for browsing the filesystem and searching code.
        There are no separate grep/glob/ls tools — use bash for those operations:

        Searching code (use ripgrep, it respects .gitignore and is fastest on large trees):
        - rg --line-number --no-heading --color=never '<pattern>' <path>
        - Restrict to matching files with --glob, e.g. rg --line-number '<pattern>' --glob '*.py' <path>
        - Limit large results with rg's own flags or request approval for a pipeline.

        Finding files by name or glob pattern:
        - rg --files --glob '<pattern>' <path>   (respects .gitignore)
        - Or find <path> -name '*.py' when you need more control

        Listing a directory:
        - ls -la <path>

        For file edits, use the dedicated file_editor tool instead of sed/awk/perl.
        For reading files, use the file_reader tool instead of cat/head/tail.

        Safety notes:
        - Commands run with a configurable timeout (default 30s, max 120s).
        - Pipe long-running or verbose commands through head when you only need a preview.

        Supported examples:
        - pwd
        - git status
        - git diff
        - git log --oneline -5
        - rg --line-number --no-heading 'def run' src/
        - rg --files --glob '*.py' rich_ui/
        - ls -la
        - ruff check src/
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
        _permission_callback: Optional[Callable[[str, str], bool]] = None,
    ) -> str:
        validation_error = self._validate_cwd(cwd)
        if validation_error:
            return validation_error

        timeout_value = self._normalize_timeout(timeout)
        if isinstance(timeout_value, str):
            return timeout_value

        if not command or not command.strip():
            return "Command failed: command must not be empty"

        permission = CommandPermissionManager().classify(command)
        if permission.decision is PermissionDecision.REJECT:
            return f"Command rejected by permission policy: {permission.reason}"
        if permission.decision is PermissionDecision.ASK:
            if _permission_callback is None:
                return (
                    "Command rejected: explicit user permission is required: "
                    f"{permission.reason}"
                )
            if not _permission_callback(command, permission.reason):
                return "Command rejected: user denied permission"

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
