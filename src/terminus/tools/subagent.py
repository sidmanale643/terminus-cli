from terminus.tools.base import ToolSchema
from textwrap import dedent


class SubAgent(ToolSchema):
    def __init__(self):
        self.name = "subagent"

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
                            "description": "The task assigned by the main agent for the subagent to complete",
                        }
                    },
                    "required": ["task"],
                },
            },
        }

    def run(
        self,
        task: str,
        _status_callback=None,
        _stop_event=None,
        _tool_call_callback=None,
        _tool_output_callback=None,
        _permission_callback=None,
        _cwd=None,
    ):
        try:
            from terminus.agent import Agent

            subagent = Agent(cwd=_cwd)
            result = subagent.run(
                user_message=task,
                status_callback=_status_callback,
                tool_call_callback=_tool_call_callback,
                tool_output_callback=_tool_output_callback,
                stop_event=_stop_event,
                permission_callback=_permission_callback,
            )

            return result

        except Exception as e:
            error_msg = f"Subagent execution failed: {str(e)}"
            return error_msg
