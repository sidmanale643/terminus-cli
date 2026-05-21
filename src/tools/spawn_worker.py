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
                        "role": {
                            "type": "string",
                            "enum": ["explorer", "implementer", "verifier", "summarizer"],
                            "description": "Specialized role for the worker. Choose the narrowest role that fits the task.",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "The task prompt to send to the worker agent. Include the compact handoff requirement: what_was_done, evidence, unresolved_risks, exact_next_step.",
                        },
                    },
                    "required": ["name", "description", "prompt", "role"],
                },
            },
        }

    def run(self, **kwargs):
        """Execution is handled by Coordinator.spawn_worker(); this stub
        satisfies the abstract base class and prevents accidental use.
        """
        raise NotImplementedError(
            "SpawnWorker is schema-only. Use Coordinator.spawn_worker() instead."
        )

    async def arun(self, **kwargs):
        """Async variant — same redirect as run()."""
        raise NotImplementedError(
            "SpawnWorker is schema-only. Use Coordinator.spawn_worker() instead."
        )
