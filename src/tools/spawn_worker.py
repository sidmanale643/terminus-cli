from textwrap import dedent
from src.models.tool import ToolSchema


class SpawnWorker(ToolSchema):
    def __init__(self):
        self.name = "spawn_worker"

    def description(self):
        return dedent("""
        Spawn a subordinate worker agent to handle a specific task.
        Use this when you need to delegate work that can be done in parallel
        or by a specialized agent with its own context.
        """)

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "The id of the worker, like worker_1, worker_2 ......",
                        },
                        "name": {
                            "type": "string",
                            "description": "The name of the worker agent",
                        },
                        "description": {
                            "type": "string",
                            "description": "A brief description of what the worker will do",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "The task prompt to send to the worker agent",
                        },
                    },
                    "required": ["name", "description", "prompt"],
                },
            },
        }

    def run(self, id: str, name: str, description: str, prompt: str):
        from src.agent import Agent

        try:
            worker = Agent(id=id, name=name, description=description)
            result = worker.run(prompt)
            return result
        except Exception as e:
            return f"Error spawning worker '{name}': {e}"
