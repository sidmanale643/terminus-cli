from textwrap import dedent
from src.models.tool import ToolSchema


class AwaitWorkers(ToolSchema):
    def __init__(self):
        self.name = "await_workers"

    def description(self):
        return dedent("""
        Wait for one or more workers to finish and return their results.
        Use this to collect structured worker outputs before synthesizing your final answer.
        You can specify a timeout (in seconds) or wait indefinitely. If no worker IDs are
        provided, waits for ALL currently tracked workers.
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
                        "worker_ids": {
                            "type": "array",
                            "description": "List of worker IDs to wait for. If empty, waits for all workers.",
                            "items": {"type": "string"},
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Maximum time to wait in seconds. If omitted, waits indefinitely.",
                        },
                    },
                },
            },
        }

    def run(self, **kwargs):
        # Sync fallback; actual awaiting happens in Coordinator.await_workers
        return "await_workers should be called via coordinator"

    async def arun(self, **kwargs):
        # Async fallback; actual awaiting happens in Coordinator.await_workers
        return "await_workers should be called via coordinator"
