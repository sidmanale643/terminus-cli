from src.tools import (
    Grep,
    Glob,
    FileReader,
    Bash,
    TodoWrite,
    TodoRead,
    TodoUpdate,
    FileCreator,
    FileEditor,
    Ls,
    SubAgent,
    AskQuestion,
    SendNotification,
    SpawnWorker,
    SpawnWorkersBatch,
    StopWorker,
    ListWorkers,
    AwaitWorkers,
    GetWorkerResult,
    Sandbox,
    WebSearch,
    LoadSkill,
)
from src.mcp_bridge import McpClientManager

ALL_TOOL_CLASSES = [
    Grep,
    Glob,
    FileReader,
    Bash,
    TodoWrite,
    TodoRead,
    TodoUpdate,
    FileCreator,
    FileEditor,
    Ls,
    SubAgent,
    AskQuestion,
    SendNotification,
    Sandbox,
    WebSearch,
    LoadSkill,
]

PLAN_MODE_TOOL_NAMES = frozenset(
    {
        "ls",
        "glob",
        "grep_search",
        "file_reader",
        "web_search",
        "load_skill",
        "ask_question",
        "todo_write",
        "todo_read",
        "todo_update",
    }
)

COORDINATOR_TOOL_CLASSES = [
    SpawnWorker,
    SpawnWorkersBatch,
    StopWorker,
    ListWorkers,
    AwaitWorkers,
    GetWorkerResult,
    SendNotification,
    WebSearch,
]


class ToolRegistry:
    def __init__(
        self,
        exclude_tool_names=None,
        exclude_coordinator_tool_names=None,
        cwd=None,
        mcp_manager=None,
        enable_mcp=True,
    ):
        exclude_tool_names = set(exclude_tool_names or [])
        exclude_coordinator_tool_names = set(exclude_coordinator_tool_names or [])
        self.tool_box = {}
        self.coordinator_tool_box = {}
        self.tool_schemas = []
        self.coordinator_tool_schemas = []
        self.mcp_manager = (
            mcp_manager if mcp_manager is not None else McpClientManager(cwd=cwd)
        )
        self.mcp_warnings = []

        self._register_tools(self.tool_box, ALL_TOOL_CLASSES, exclude_tool_names)
        if enable_mcp:
            self._register_mcp_tools(exclude_tool_names)
        self.tool_schemas = self._generate_schemas(self.tool_box)
        self.plan_tool_schemas = self._generate_schemas(
            {
                name: tool
                for name, tool in self.tool_box.items()
                if name in PLAN_MODE_TOOL_NAMES
            }
        )

        self._register_tools(
            self.coordinator_tool_box,
            COORDINATOR_TOOL_CLASSES,
            exclude_coordinator_tool_names,
        )
        self.coordinator_tool_schemas = self._generate_schemas(
            self.coordinator_tool_box
        )

    def _register_mcp_tools(self, exclude_names=None):
        exclude_names = set(exclude_names or [])
        try:
            for tool in self.mcp_manager.discover_tools():
                if tool.name in exclude_names:
                    continue
                self.tool_box[tool.name] = tool
            self.mcp_warnings = self.mcp_manager.warnings
        except Exception as exc:
            self.mcp_warnings = [f"MCP discovery failed: {exc}"]

    def refresh_mcp_tools(self):
        existing_mcp_tools = [
            name for name in self.tool_box if name.startswith("mcp__")
        ]
        for name in existing_mcp_tools:
            self.tool_box.pop(name, None)
        for tool in self.mcp_manager.refresh():
            self.tool_box[tool.name] = tool
        self.mcp_warnings = self.mcp_manager.warnings
        self.tool_schemas = self._generate_schemas(self.tool_box)
        self.plan_tool_schemas = self._generate_schemas(
            {
                name: tool
                for name, tool in self.tool_box.items()
                if name in PLAN_MODE_TOOL_NAMES
            }
        )
        return self.mcp_manager.status()

    def mcp_status(self):
        return self.mcp_manager.status()

    def mcp_tools_by_server(self):
        return self.mcp_manager.tools_by_server()

    def shutdown(self):
        self.mcp_manager.shutdown()

    @staticmethod
    def _register_tools(registry, classes, exclude_names=None):
        exclude_names = set(exclude_names or [])
        for cls in classes:
            tool = cls()
            if tool.name in exclude_names:
                continue
            registry[tool.name] = tool

    @staticmethod
    def _generate_schemas(registry):
        seen = set()
        schemas = []
        for tool in registry.values():
            if tool.name in seen:
                continue
            seen.add(tool.name)
            schemas.append(tool.json_schema())
        return schemas

    @staticmethod
    def _run(registry, tool_name, **kwargs):
        return registry[tool_name].run(**kwargs)

    @staticmethod
    async def _arun(registry, tool_name, **kwargs):
        tool = registry[tool_name]
        if hasattr(tool, "arun"):
            return await tool.arun(**kwargs)
        # Fallback: run sync tool in thread
        import asyncio

        return await asyncio.to_thread(tool.run, **kwargs)

    def run_tool(self, tool_name, **kwargs):
        return self._run(self.tool_box, tool_name, **kwargs)

    def run_plan_tool(self, tool_name, **kwargs):
        if tool_name not in PLAN_MODE_TOOL_NAMES:
            return (
                f"Error: Tool '{tool_name}' is not available in plan mode. "
                "Plan mode is read-only and cannot edit files, create files, "
                "run commands, execute code, or delegate implementation work."
            )
        return self._run(self.tool_box, tool_name, **kwargs)

    def run_coordinator_tool(self, tool_name, **kwargs):
        return self._run(self.coordinator_tool_box, tool_name, **kwargs)

    async def run_tool_async(self, tool_name, **kwargs):
        return await self._arun(self.tool_box, tool_name, **kwargs)

    async def run_plan_tool_async(self, tool_name, **kwargs):
        if tool_name not in PLAN_MODE_TOOL_NAMES:
            return (
                f"Error: Tool '{tool_name}' is not available in plan mode. "
                "Plan mode is read-only and cannot edit files, create files, "
                "run commands, execute code, or delegate implementation work."
            )
        return await self._arun(self.tool_box, tool_name, **kwargs)

    async def run_coordinator_tool_async(self, tool_name, **kwargs):
        return await self._arun(self.coordinator_tool_box, tool_name, **kwargs)
