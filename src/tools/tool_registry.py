from src.tools import (
    FileReader,
    Bash,
    TodoWrite,
    TodoRead,
    TodoUpdate,
    FileCreator,
    FileEditor,
    SubAgent,
    AskQuestion,
    Sandbox,
    WebSearch,
    LoadSkill,
)

ALL_TOOL_CLASSES = [
    FileReader,
    Bash,
    TodoWrite,
    TodoRead,
    TodoUpdate,
    FileCreator,
    FileEditor,
    SubAgent,
    AskQuestion,
    Sandbox,
    WebSearch,
    LoadSkill,
]


class ToolRegistry:
    def __init__(
        self,
        exclude_tool_names=None,
        cwd=None,
        tools=None,
    ):
        exclude_tool_names = set(exclude_tool_names or [])
        self.tool_box = {}
        self.tool_schemas = []

        if tools is None:
            self._register_tools(self.tool_box, ALL_TOOL_CLASSES, exclude_tool_names)
        else:
            for tool in tools:
                if tool.name not in exclude_tool_names:
                    self.tool_box[tool.name] = tool
        self.tool_schemas = self._generate_schemas(self.tool_box)

    def shutdown(self):
        pass

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
        return await tool.arun(**kwargs)

    def run_tool(self, tool_name, **kwargs):
        return self._run(self.tool_box, tool_name, **kwargs)

    async def run_tool_async(self, tool_name, **kwargs):
        return await self._arun(self.tool_box, tool_name, **kwargs)
