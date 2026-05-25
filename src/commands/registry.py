from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class Command:
    name: str
    description: str
    aliases: list[str] = field(default_factory=list)


class CommandRegistry:
    _commands: ClassVar[dict[str, Command]] = {}

    @classmethod
    def register(cls, name: str, description: str, aliases: list[str] | None = None) -> None:
        cmd = Command(name=name, description=description, aliases=aliases or [])
        cls._commands[name] = cmd
        for alias in cmd.aliases:
            cls._commands[alias] = cmd

    @classmethod
    def all(cls) -> list[Command]:
        seen: set[int] = set()
        result: list[Command] = []
        for cmd in cls._commands.values():
            if id(cmd) not in seen:
                seen.add(id(cmd))
                result.append(cmd)
        return sorted(result, key=lambda c: c.name)

    @classmethod
    def get(cls, name: str) -> Command | None:
        return cls._commands.get(name)

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._commands

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._commands.keys())

    @classmethod
    def command_names(cls) -> list[str]:
        """Return only primary command names (no aliases)."""
        seen: set[int] = set()
        result: list[str] = []
        for cmd in cls._commands.values():
            if id(cmd) not in seen:
                seen.add(id(cmd))
                result.append(cmd.name)
        return sorted(result)


CommandRegistry.register("/help", "Display this help information")
CommandRegistry.register("/plan", "Create an implementation plan")
CommandRegistry.register("/context", "View current conversation context")
CommandRegistry.register("/history", "View recent session history")
CommandRegistry.register("/reset", "Reset session history")
CommandRegistry.register("/context_size", "Display context size")
CommandRegistry.register("/compact", "Compact conversation context")
CommandRegistry.register("/clear", "Clear the console screen", aliases=["clear"])
CommandRegistry.register("/models", "Switch AI model")
CommandRegistry.register("/copy", "Copy last assistant response to clipboard")
CommandRegistry.register("/skills", "List available skills")
CommandRegistry.register("/skill", "Load a skill by name")
CommandRegistry.register("/connect", "Select provider and configure API key")
CommandRegistry.register("/init", "Generate or update AGENTS.md")
CommandRegistry.register("/mode", "Switch between agent and coordinator mode")
CommandRegistry.register("/mcp", "Show or refresh MCP server tools")
CommandRegistry.register("/exit", "Exit the program", aliases=["exit", "quit", "q"])
