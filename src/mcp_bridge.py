import asyncio
import json
import os
import re
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models.tool import ToolSchema

try:
    from mcp import ClientSession, StdioServerParameters, types as mcp_types
    from mcp.client.stdio import stdio_client
except Exception:  # pragma: no cover - exercised when optional dependency is absent
    ClientSession = None
    StdioServerParameters = None
    mcp_types = None
    stdio_client = None


MCP_CONFIG_FILE = "terminus.mcp.yaml"
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
TOOL_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass
class McpServerConfig:
    id: str
    command: str
    args: list[str] = field(default_factory=list)
    cwd: str = "."
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    tool_prefix: Optional[str] = None
    timeout_seconds: int = 60


@dataclass
class McpConfig:
    path: Path
    servers: list[McpServerConfig]


@dataclass
class McpServerState:
    config: McpServerConfig
    status: str = "configured"
    tool_count: int = 0
    tools: list[Any] = field(default_factory=list)
    error: Optional[str] = None
    session: Any = None


class McpConfigLoader:
    def __init__(self, cwd: str | os.PathLike[str] | None = None):
        self.cwd = Path(cwd or os.getcwd()).resolve()

    def load(self) -> McpConfig:
        path = self.cwd / MCP_CONFIG_FILE
        if not path.exists():
            return McpConfig(path=path, servers=[])

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid {MCP_CONFIG_FILE}: {exc}") from exc

        servers_raw = raw.get("servers", {})
        if not isinstance(servers_raw, dict):
            raise ValueError(f"Invalid {MCP_CONFIG_FILE}: 'servers' must be a mapping")

        servers = []
        for server_id, item in servers_raw.items():
            if not isinstance(item, dict):
                raise ValueError(f"Invalid MCP server '{server_id}': expected mapping")
            enabled = bool(item.get("enabled", True))
            if not enabled:
                continue
            command = item.get("command")
            if not isinstance(command, str) or not command.strip():
                raise ValueError(f"Invalid MCP server '{server_id}': command is required")
            args = item.get("args", [])
            if args is None:
                args = []
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError(f"Invalid MCP server '{server_id}': args must be a list of strings")
            env = item.get("env", {})
            if env is None:
                env = {}
            if not isinstance(env, dict) or not all(isinstance(k, str) for k in env):
                raise ValueError(f"Invalid MCP server '{server_id}': env must be a string-keyed mapping")
            timeout_seconds = int(item.get("timeout_seconds", 60))
            if timeout_seconds <= 0:
                raise ValueError(f"Invalid MCP server '{server_id}': timeout_seconds must be positive")
            servers.append(
                McpServerConfig(
                    id=str(server_id),
                    command=command,
                    args=args,
                    cwd=self._resolve_cwd(str(item.get("cwd", "."))),
                    env={key: self._interpolate_env(str(value)) for key, value in env.items()},
                    enabled=enabled,
                    tool_prefix=item.get("tool_prefix"),
                    timeout_seconds=timeout_seconds,
                )
            )

        return McpConfig(path=path, servers=servers)

    def _resolve_cwd(self, value: str) -> str:
        path = Path(os.path.expanduser(value))
        if not path.is_absolute():
            path = self.cwd / path
        return str(path.resolve())

    @staticmethod
    def _interpolate_env(value: str) -> str:
        return ENV_PATTERN.sub(lambda match: os.getenv(match.group(1), ""), value)


class McpToolAdapter(ToolSchema):
    def __init__(self, manager: "McpClientManager", server_id: str, tool: Any):
        self.manager = manager
        self.server_id = server_id
        self.original_name = tool.name
        self.name = make_mcp_tool_name(server_id, tool.name)
        self._description = getattr(tool, "description", None) or f"MCP tool {tool.name} from server {server_id}"
        self._input_schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}

    def description(self):
        return self._description

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": normalize_json_schema(self._input_schema),
            },
        }

    def run(self, **kwargs):
        return self.manager.call_tool(self.server_id, self.original_name, kwargs)

    async def arun(self, **kwargs):
        return await self.manager.call_tool_async(self.server_id, self.original_name, kwargs)


class McpClientManager:
    def __init__(self, cwd: str | os.PathLike[str] | None = None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.loader = McpConfigLoader(self.cwd)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._states: dict[str, McpServerState] = {}
        self._adapters: list[McpToolAdapter] = []
        self._warnings: list[str] = []
        self._lock = threading.Lock()

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def discover_tools(self, force_refresh: bool = False) -> list[McpToolAdapter]:
        if self._adapters and not force_refresh:
            return list(self._adapters)
        return self._run_sync(self._discover_tools_async(force_refresh=force_refresh))

    async def discover_tools_async(self, force_refresh: bool = False) -> list[McpToolAdapter]:
        if self._adapters and not force_refresh:
            return list(self._adapters)
        return await self._submit(self._discover_tools_async(force_refresh=force_refresh))

    def call_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        return self._run_sync(self._call_tool_async(server_id, tool_name, arguments))

    async def call_tool_async(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        return await self._submit(self._call_tool_async(server_id, tool_name, arguments))

    def refresh(self) -> list[McpToolAdapter]:
        return self.discover_tools(force_refresh=True)

    def status(self) -> dict[str, Any]:
        config = self.loader.load()
        states = {
            server.id: self._state_payload(self._states.get(server.id), server)
            for server in config.servers
        }
        return {
            "config_path": str(config.path),
            "servers": states,
            "warnings": self.warnings,
            "tool_count": len(self._adapters),
        }

    def tools_by_server(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for adapter in self._adapters:
            grouped.setdefault(adapter.server_id, []).append(adapter.name)
        return grouped

    def shutdown(self) -> None:
        if not self._loop:
            return
        try:
            self._run_sync(self._shutdown_async())
        finally:
            loop = self._loop
            thread = self._thread
            self._loop = None
            self._thread = None
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            if thread and thread.is_alive():
                thread.join(timeout=2)

    async def _discover_tools_async(self, force_refresh: bool = False) -> list[McpToolAdapter]:
        if ClientSession is None or StdioServerParameters is None or stdio_client is None:
            self._warnings = ["MCP support requires the 'mcp' Python package."]
            self._states = {}
            self._adapters = []
            return []

        if force_refresh:
            await self._shutdown_async()

        try:
            config = self.loader.load()
        except ValueError as exc:
            self._warnings = [str(exc)]
            self._states = {}
            self._adapters = []
            return []

        self._warnings = []
        adapters = []
        next_states: dict[str, McpServerState] = {}
        for server in config.servers:
            state = self._states.get(server.id) or McpServerState(config=server)
            state.config = server
            next_states[server.id] = state
            try:
                await self._ensure_connected(state)
                for tool in state.tools:
                    adapters.append(McpToolAdapter(self, server.id, tool))
            except Exception as exc:
                state.status = "error"
                state.error = str(exc)
                self._warnings.append(f"MCP server '{server.id}' unavailable: {exc}")

        self._states = next_states
        self._adapters = adapters
        return list(adapters)

    async def _ensure_connected(self, state: McpServerState) -> None:
        if state.session is not None and state.status == "connected":
            return
        if self._exit_stack is None:
            self._exit_stack = AsyncExitStack()

        state.status = "connecting"
        env = os.environ.copy()
        env.update(state.config.env)
        params_kwargs = {
            "command": state.config.command,
            "args": state.config.args,
            "env": env,
        }
        try:
            params = StdioServerParameters(**params_kwargs, cwd=state.config.cwd)
        except TypeError:
            params = StdioServerParameters(**params_kwargs)

        read_stream, write_stream = await asyncio.wait_for(
            self._exit_stack.enter_async_context(stdio_client(params)),
            timeout=state.config.timeout_seconds,
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await asyncio.wait_for(session.initialize(), timeout=state.config.timeout_seconds)
        tools_response = await asyncio.wait_for(session.list_tools(), timeout=state.config.timeout_seconds)
        state.session = session
        state.tools = list(getattr(tools_response, "tools", []) or [])
        state.tool_count = len(state.tools)
        state.status = "connected"
        state.error = None

    async def _call_tool_async(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        state = self._states.get(server_id)
        if state is None:
            await self._discover_tools_async()
            state = self._states.get(server_id)
        if state is None:
            return f"Error: MCP server '{server_id}' is not configured"
        await self._ensure_connected(state)
        result = await asyncio.wait_for(
            state.session.call_tool(tool_name, arguments),
            timeout=state.config.timeout_seconds,
        )
        return format_mcp_tool_result(result)

    async def _shutdown_async(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            finally:
                self._exit_stack = None
        self._states = {}
        self._adapters = []

    def _state_payload(self, state: McpServerState | None, config: McpServerConfig) -> dict[str, Any]:
        if state is None:
            return {
                "status": "configured",
                "tool_count": 0,
                "command": config.command,
                "cwd": config.cwd,
                "error": None,
            }
        return {
            "status": state.status,
            "tool_count": state.tool_count,
            "command": state.config.command,
            "cwd": state.config.cwd,
            "error": state.error,
        }

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop and self._loop.is_running():
                return self._loop
            loop = asyncio.new_event_loop()
            self._loop = loop
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(loop,),
                name="terminus-mcp-loop",
                daemon=True,
            )
            self._thread.start()
            return loop

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()
        loop.close()

    def _run_sync(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        return future.result()

    async def _submit(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        return await asyncio.wrap_future(future)


def make_mcp_tool_name(server_id: str, tool_name: str) -> str:
    return f"mcp__{sanitize_tool_name(server_id)}__{sanitize_tool_name(tool_name)}"


def sanitize_tool_name(value: str) -> str:
    cleaned = TOOL_NAME_PATTERN.sub("_", value.strip())
    cleaned = cleaned.strip("_-")
    return cleaned or "tool"


def normalize_json_schema(schema: Any) -> dict[str, Any]:
    data = to_jsonable(schema)
    if not isinstance(data, dict):
        return {"type": "object", "properties": {}}
    if data.get("type") != "object":
        data = {"type": "object", "properties": {}, **data}
    data.setdefault("properties", {})
    return data


def format_mcp_tool_result(result: Any) -> str:
    parts = []
    structured = getattr(result, "structuredContent", None)
    if structured:
        parts.append(json.dumps(to_jsonable(structured), ensure_ascii=True, separators=(",", ":")))

    for item in list(getattr(result, "content", []) or []):
        text = _format_mcp_content_item(item)
        if text:
            parts.append(text)

    if not parts:
        parts.append(json.dumps(to_jsonable(result), ensure_ascii=True, separators=(",", ":")))

    output = "\n".join(parts)
    if getattr(result, "isError", False):
        return f"MCP tool returned error:\n{output}"
    return output


def _format_mcp_content_item(item: Any) -> str:
    if mcp_types is not None and isinstance(item, getattr(mcp_types, "TextContent", ())):
        return item.text
    if hasattr(item, "text"):
        return str(item.text)
    if mcp_types is not None and isinstance(item, getattr(mcp_types, "ImageContent", ())):
        data = getattr(item, "data", "") or ""
        return f"[MCP image content: mime={getattr(item, 'mimeType', 'unknown')}, bytes={len(data)}]"
    if hasattr(item, "data") and hasattr(item, "mimeType"):
        data = getattr(item, "data", "") or ""
        return f"[MCP binary content: mime={getattr(item, 'mimeType', 'unknown')}, bytes={len(data)}]"
    if mcp_types is not None and isinstance(item, getattr(mcp_types, "EmbeddedResource", ())):
        resource = getattr(item, "resource", None)
        uri = getattr(resource, "uri", "unknown")
        return f"[MCP embedded resource: uri={uri}]"
    return json.dumps(to_jsonable(item), ensure_ascii=True, separators=(",", ":"))


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
