"""Capability-limited tools used by mission agents."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

from src.models.tool import ToolSchema
from src.tools import AskQuestion, FileCreator, FileEditor, FileReader


class MissionAskQuestion(AskQuestion):
    def description(self):
        return (
            "Pause the mission for user input only when a missing user choice "
            "materially blocks safe progress and cannot be resolved from repository "
            "evidence. Ask the smallest number of questions needed. Each question "
            "must provide exactly three viable options."
        )


def normalize_scope(cwd: str, scope: list[str]) -> list[Path]:
    """Resolve a declared scope and reject paths outside the repository root."""
    root = Path(cwd).expanduser().resolve()
    normalized: list[Path] = []
    for raw in scope:
        if any(char in raw for char in "*?[]"):
            raise ValueError(f"wildcards are not allowed in file_scope: {raw}")
        path = Path(raw).expanduser()
        resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"file_scope escapes the repository: {raw}")
        normalized.append(resolved)
    return normalized


def scopes_overlap(cwd: str, first: list[str], second: list[str]) -> bool:
    first_paths = normalize_scope(cwd, first)
    second_paths = normalize_scope(cwd, second)
    return any(
        left == right or left in right.parents or right in left.parents
        for left in first_paths
        for right in second_paths
    )


class RepoSearch(ToolSchema):
    def __init__(self, cwd: str):
        self.name = "repo_search"
        self.cwd = cwd

    def description(self):
        return (
            "Search text inside the current repository, or list repository files, "
            "without changing them. Set files_only=true to list files; in that mode "
            "query is ignored. Paths are repository-relative and cannot escape the "
            "repository root."
        )

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Literal text or regular expression to search for. "
                                "Ignored when files_only=true."
                            ),
                        },
                        "path": {
                            "type": "string",
                            "default": ".",
                            "description": "Repository-relative file or directory to search.",
                        },
                        "files_only": {
                            "type": "boolean",
                            "default": False,
                            "description": "List files instead of searching file contents.",
                        },
                    },
                },
            },
        }

    def run(self, query: str = "", path: str = ".", files_only: bool = False):
        target = _safe_repo_path(self.cwd, path)
        command = (
            ["rg", "--files", str(target)]
            if files_only
            else ["rg", "-n", "--", query, str(target)]
        )
        result = subprocess.run(
            command, cwd=self.cwd, text=True, capture_output=True, timeout=30
        )
        output = result.stdout or result.stderr
        return output[:50000] or "No matches found."


class CheckRunner(ToolSchema):
    ALLOWED_PREFIXES = (
        ("uv", "run", "pytest"),
        ("uv", "run", "python", "-m", "pytest"),
        ("uv", "run", "python", "-m", "unittest"),
        ("uv", "run", "python", "-m", "compileall"),
        ("uv", "run", "ruff", "check"),
        ("pytest",),
        ("python", "-m", "pytest"),
        ("python", "-m", "unittest"),
        ("python", "-m", "compileall"),
        ("ruff", "check"),
        ("npm", "test"),
        ("npm", "run", "test"),
        ("npm", "run", "lint"),
        ("npm", "run", "build"),
        ("npm", "run", "typecheck"),
    )

    def __init__(self, cwd: str, on_run: Callable[[str], None] | None = None):
        self.name = "check_runner"
        self.cwd = cwd
        self.on_run = on_run

    def description(self):
        return (
            "Run one allowlisted verification command without shell operators or "
            "mutation flags. Accepted commands are uv run pytest, uv run python -m "
            "pytest, uv run python -m unittest, uv run python -m compileall, uv run "
            "ruff check, direct uv run python tests/<file>.py, and the equivalent "
            "pytest/python/ruff forms, plus npm test and npm run test, lint, build, "
            "or typecheck. Use working_directory instead of cd."
        )

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "working_directory": {
                            "type": "string",
                            "default": ".",
                            "description": "Repository-relative directory for the check.",
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    def run(self, command: str, working_directory: str = "."):
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return f"Error: invalid check command: {exc}"
        if len(args) >= 4 and args[0] == "cd" and args[2] == "&&":
            if working_directory != ".":
                return "Error: specify a working directory only once"
            working_directory = args[1]
            args = args[3:]
        if any(arg in {"&&", "||", ";", "|", ">", ">>", "<"} for arg in args):
            return "Error: shell operators are not allowed in check commands"
        try:
            target = _safe_repo_path(self.cwd, working_directory)
        except ValueError as exc:
            return f"Error: {exc}"
        if not target.is_dir():
            return f"Error: check working directory does not exist: {working_directory}"
        direct_test = (
            len(args) >= 4
            and tuple(args[:3]) == ("uv", "run", "python")
            and args[3].startswith("tests/")
            and args[3].endswith(".py")
        )
        if not direct_test and not any(
            tuple(args[: len(prefix)]) == prefix for prefix in self.ALLOWED_PREFIXES
        ):
            return "Error: command is not an allowed read-only check"
        if any(arg in {"--fix", "--format", "-w", "--write"} for arg in args):
            return "Error: mutation flags are not allowed"
        if self.on_run:
            relative = target.relative_to(Path(self.cwd).resolve())
            prefix = f"cd {relative} && " if str(relative) != "." else ""
            self.on_run(f"{prefix}{shlex.join(args)}")
        try:
            result = subprocess.run(
                args, cwd=target, text=True, capture_output=True, timeout=300
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"Error: check could not run: {exc}"
        output = (result.stdout + result.stderr)[-50000:]
        return f"exit_code={result.returncode}\n{output}"


class ScopedFileCreator(FileCreator):
    def __init__(
        self,
        cwd: str,
        scope: list[str],
        on_change: Callable[[str], None],
        on_before_change: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.cwd = cwd
        self.scope = normalize_scope(cwd, scope)
        self.on_change = on_change
        self.on_before_change = on_before_change

    def description(self):
        return (
            "Create or overwrite a file only inside this Worker's declared repository "
            "file scope. Use a repository-relative file_path. Parent directories are "
            "created automatically. Read an existing file before overwriting it."
        )

    def run(self, file_path: str = None, content: str = "", path: str = None):
        requested = file_path or path
        try:
            resolved = _require_in_scope(self.cwd, requested, self.scope)
        except ValueError as exc:
            return f"Error: {exc}"
        if self.on_before_change:
            self.on_before_change(str(resolved))
        output = super().run(file_path=str(resolved), content=content)
        if output.startswith("Created file:"):
            self.on_change(str(resolved))
        return output


class ScopedFileReader(FileReader):
    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd

    def description(self):
        return (
            "Read one or more text files inside the current repository without "
            "changing them. Repository-relative paths are resolved from the mission "
            "working directory, and paths outside the repository are rejected. Use "
            "offset and limit for targeted line ranges."
        )

    def run(
        self,
        file_path: str = None,
        path: str = None,
        files: list[str] = None,
        file_paths: list[str] = None,
        paths: list[str] = None,
        **kwargs,
    ):
        requested = files or file_paths or paths
        try:
            if requested:
                resolved = [str(_safe_repo_path(self.cwd, item)) for item in requested]
                return super().run(files=resolved, **kwargs)
            resolved = _safe_repo_path(self.cwd, file_path or path)
        except ValueError as exc:
            return f"Error: {exc}"
        return super().run(file_path=str(resolved), **kwargs)


class ScopedFileEditor(FileEditor):
    def __init__(
        self,
        cwd: str,
        scope: list[str],
        on_change: Callable[[str], None],
        on_before_change: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.cwd = cwd
        self.scope = normalize_scope(cwd, scope)
        self.on_change = on_change
        self.on_before_change = on_before_change

    def description(self):
        return (
            "Apply exact string replacements only inside this Worker's declared "
            "repository file scope. Read the file first, use repository-relative "
            "file_path values, and preserve exact whitespace. Multiple replacements "
            "are atomic."
        )

    def run(self, file_path: str = None, path: str = None, **kwargs):
        requested = file_path or path
        try:
            resolved = _require_in_scope(self.cwd, requested, self.scope)
        except ValueError as exc:
            return f"Error: {exc}"
        if self.on_before_change:
            self.on_before_change(str(resolved))
        output = super().run(file_path=str(resolved), **kwargs)
        if output.startswith(("Edited ", "Multi-edited ")):
            self.on_change(str(resolved))
        return output


def read_only_tools(cwd: str, on_check: Callable[[str], None] | None = None):
    return [ScopedFileReader(cwd), RepoSearch(cwd), CheckRunner(cwd, on_check)]


def worker_tools(
    cwd: str,
    scope: list[str],
    on_change: Callable[[str], None],
    on_check: Callable[[str], None],
    on_before_change: Callable[[str], None] | None = None,
):
    return [
        *read_only_tools(cwd, on_check),
        ScopedFileCreator(cwd, scope, on_change, on_before_change),
        ScopedFileEditor(cwd, scope, on_change, on_before_change),
    ]


def _safe_repo_path(cwd: str, raw: str) -> Path:
    root = Path(cwd).resolve()
    path = Path(raw).expanduser()
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("path escapes the repository")
    return resolved


def _require_in_scope(cwd: str, raw: str | None, scope: list[Path]) -> Path:
    if not raw:
        raise ValueError("file_path is required")
    path = _safe_repo_path(cwd, raw)
    if not scope:
        raise ValueError("worker has no declared file scope")
    if not any(path == allowed or allowed in path.parents for allowed in scope):
        raise ValueError(f"path is outside the worker file scope: {raw}")
    return path
