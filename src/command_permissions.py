import re
import shlex
from dataclasses import dataclass
from enum import Enum


class PermissionDecision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    REJECT = "reject"


@dataclass(frozen=True)
class PermissionResult:
    decision: PermissionDecision
    reason: str


_READ_ONLY_COMMANDS = {
    "basename",
    "cat",
    "command",
    "cut",
    "date",
    "df",
    "dirname",
    "du",
    "echo",
    "file",
    "find",
    "grep",
    "head",
    "id",
    "ls",
    "md5",
    "md5sum",
    "pwd",
    "rg",
    "sha256sum",
    "stat",
    "tail",
    "tr",
    "type",
    "uname",
    "wc",
    "which",
    "whoami",
}

_READ_ONLY_GIT_COMMANDS = {
    "diff",
    "grep",
    "log",
    "ls-files",
    "rev-parse",
    "shortlog",
    "show",
    "status",
}

_SHELL_SYNTAX = re.compile(r"[|&;<>()`$\n\r]")
_CATASTROPHIC = (
    re.compile(r"(?:^|\s)(?:sudo\s+)?rm\s+[^\n]*(?:-rf|-fr)[^\n]*\s/(?:\s|$)"),
    re.compile(r"(?:^|\s)(?:mkfs(?:\.[a-z0-9]+)?|reboot|shutdown)(?:\s|$)"),
    re.compile(r"(?:^|\s)dd\s+[^\n]*\bof=/dev/"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
)


class CommandPermissionManager:
    def classify(self, command: str) -> PermissionResult:
        text = command.strip()
        if not text:
            return PermissionResult(PermissionDecision.REJECT, "command is empty")

        lowered = " ".join(text.lower().split())
        if any(pattern.search(lowered) for pattern in _CATASTROPHIC):
            return PermissionResult(
                PermissionDecision.REJECT,
                "command is an obvious system-destructive operation",
            )

        if _SHELL_SYNTAX.search(text):
            return PermissionResult(
                PermissionDecision.ASK,
                "command uses shell syntax",
            )

        try:
            argv = shlex.split(text)
        except ValueError:
            return PermissionResult(
                PermissionDecision.ASK,
                "command could not be parsed as simple arguments",
            )

        if not argv:
            return PermissionResult(PermissionDecision.REJECT, "command is empty")

        executable = argv[0].rsplit("/", 1)[-1]
        if executable in _READ_ONLY_COMMANDS:
            if executable == "find" and any(
                arg in {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
                for arg in argv[1:]
            ):
                return PermissionResult(
                    PermissionDecision.ASK,
                    "find action may modify files or run another command",
                )
            return PermissionResult(
                PermissionDecision.ALLOW,
                "simple read-only command",
            )

        if executable == "git" and len(argv) > 1:
            subcommand = next((arg for arg in argv[1:] if not arg.startswith("-")), "")
            if subcommand in _READ_ONLY_GIT_COMMANDS:
                return PermissionResult(
                    PermissionDecision.ALLOW,
                    f"read-only git {subcommand}",
                )
            if subcommand == "branch" and not any(
                arg
                in {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy"}
                for arg in argv[2:]
            ):
                return PermissionResult(
                    PermissionDecision.ALLOW,
                    "read-only git branch listing",
                )
            if subcommand == "tag" and any(arg in {"-l", "--list"} for arg in argv[2:]):
                return PermissionResult(
                    PermissionDecision.ALLOW,
                    "read-only git tag listing",
                )

        if executable == "ruff":
            if "--fix" not in argv and (
                argv[1:2] == ["check"]
                or (argv[1:2] == ["format"] and "--check" in argv)
            ):
                return PermissionResult(
                    PermissionDecision.ALLOW,
                    "read-only ruff check",
                )

        return PermissionResult(
            PermissionDecision.ASK,
            "command is not in the automatic read-only allowlist",
        )
