from textwrap import dedent
from src.models.tool import ToolSchema

class StopWorker(ToolSchema):
    def __init__(self):
        self.name = "stop_worker"

    def description(self):
        return dedent("""
        Stop a running worker agent by its ID.
        Use this when a worker is no longer needed, stuck, or when you want to cancel its task.
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
                            "description": "The ID of the worker to stop, e.g. worker_1",
                        },
                    },
                    "required": ["id"],
                },
            },
        }

    def run(self, id: str):
        # Sync fallback; actual stopping happens in Coordinator.stop_worker
        return f"stop_worker for {id} should be called via coordinator"
