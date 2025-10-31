from src.models.tool import ToolSchema
from textwrap import dedent

class SubAgent(ToolSchema):
    def __init__(self):
        self.name = "subagent"
        self.subagent = None  # Lazy initialization

    def description(self):
        return dedent("""
        Delegates a complex task to a separate agent instance with its own context.
        Use this to offload tasks that would consume too much of the main agent's 
        context window, such as reading large files, processing verbose outputs, 
        or performing multi-step operations.
        
        The subagent has access to all the same tools as the main agent but operates
        independently with its own conversation history.

        Use this tool when you want to keep the main agent's context window clean and focused on the current task.
        """).strip()
    
    def json_schema(self):
        return {
        "type": "function",
        "function": {
            "name": self.name, 
            "description": self.description(),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The task assigned by the main agent for the subagent to complete"
                    }
                },
                "required": ["task"]
            }
        }
    }

    def run(self, task: str):
        try:
            # Import here to avoid circular import
            from src.agent import Agent
            
            # Create fresh agent instance for each task
            self.subagent = Agent()
            
            # Initialize with system prompt
            self.subagent.add_system_message()
            
            # Run the delegated task
            result = self.subagent.run(user_message=task)
            
            return result
            
        except Exception as e:
            error_msg = f"Subagent execution failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return error_msg