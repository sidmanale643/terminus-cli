from src.tools import Grep, FileReader, CommandExecutor, TodoManager, FileCreator, FileEditor, MultipleFileReader, Ls, SubAgent, Lint, MultiEdit

class ToolRegistry:
    def __init__(self):
        self.tool_box = {}
        self.tool_schemas = []
        self.register_all_tools()
        self.generate_tool_schemas()
    
    def register_tool(self, name, tool_obj):
        self.tool_box[name] = tool_obj
    
    def register_all_tools(self):
        self.register_tool(Grep().name, Grep())
        self.register_tool(FileReader().name, FileReader())
        self.register_tool(CommandExecutor().name, CommandExecutor())
        self.register_tool(TodoManager().name, TodoManager())
        self.register_tool(FileCreator().name, FileCreator())
        self.register_tool(FileEditor().name, FileEditor())
        self.register_tool(MultipleFileReader().name, MultipleFileReader())
        self.register_tool(Ls().name, Ls())
        self.register_tool(SubAgent().name, SubAgent())
        self.register_tool(Lint().name, Lint())
        self.register_tool(MultiEdit().name, MultiEdit())
        
    def generate_tool_schemas(self):
        self.tool_schemas = [tool.json_schema() for tool in self.tool_box.values()]
    
    def run_tool(self, tool_name, **kwargs):
        return self.tool_box[tool_name].run(**kwargs)