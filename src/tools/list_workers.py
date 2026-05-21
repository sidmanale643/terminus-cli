from textwrap import dedent
from src.models.tool import ToolSchema


class ListWorkers(ToolSchema):
    def __init__(self):
        self.name = "list_workers"

    def description(self):
        return dedent("""
        List all active workers and their current statuses.
        Use this to check which workers are running, completed, failed, or stopped.
        Returns a summary of each worker including its ID, name, role, description,
        status, notification count, latest notification, and whether its result has
        already been consumed by the coordinator.
        """)

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    def run(self):
        # Sync fallback; actual listing happens in Coordinator.list_workers
        return "list_workers should be called via coordinator"
