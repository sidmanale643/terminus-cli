from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class Command:
    name: str
    description: str
    usage: str = ""
    aliases: list[str] = field(default_factory=list)


class CommandRegistry:
    _commands: ClassVar[dict[str, Command]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        description: str,
        usage: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        cmd = Command(
            name=name.strip().lower(),
            description=description,
            usage=usage or name.strip().lower(),
            aliases=[alias.strip().lower() for alias in aliases or []],
        )
        cls._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            cls._commands[alias] = cmd

    @classmethod
    def all(cls) -> list[Command]:
        commands = {command.name: command for command in cls._commands.values()}
        return sorted(commands.values(), key=lambda command: command.name)

    @classmethod
    def resolve(cls, name: str) -> Command | None:
        return cls._commands.get(name.strip().lower())

    @classmethod
    def command_token(cls, text: str) -> str:
        return text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""

    @classmethod
    def is_command(cls, text: str) -> bool:
        token = cls.command_token(text)
        return bool(token) and (token.startswith("/") or cls.resolve(token) is not None)

    @classmethod
    def get(cls, name: str) -> Command | None:
        return cls.resolve(name)

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return cls.resolve(name) is not None

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._commands.keys())

    @classmethod
    def command_names(cls) -> list[str]:
        return [command.name for command in cls.all()]


CommandRegistry.register("/help", "Show the command reference")
CommandRegistry.register(
    "/mission",
    "Run, list, or replay durable Mission Control tasks",
    "/mission <goal> | /mission list | /mission replay <id>",
)
CommandRegistry.register("/context", "View current conversation context")
CommandRegistry.register("/history", "View recent session history")
CommandRegistry.register("/reset", "Reset session history")
CommandRegistry.register("/context_size", "Display context size")
CommandRegistry.register("/compact", "Compact conversation context")
CommandRegistry.register("/clear", "Clear the console screen", aliases=["clear"])
CommandRegistry.register("/models", "Switch AI model")
CommandRegistry.register("/copy", "Copy last assistant response to clipboard")
CommandRegistry.register("/skills", "List available skills")
CommandRegistry.register("/skill", "Choose or load a skill by name", "/skill [name]")
CommandRegistry.register("/connect", "Select provider and configure API key")
CommandRegistry.register("/init", "Generate or update AGENTS.md")
CommandRegistry.register(
    "/exit", "Exit the program", aliases=["exit", "/quit", "quit", "q"]
)
