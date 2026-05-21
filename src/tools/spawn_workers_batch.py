from textwrap import dedent
from src.models.tool import ToolSchema


class SpawnWorkersBatch(ToolSchema):
    def __init__(self):
        self.name = "spawn_workers_batch"

    def description(self):
        return dedent("""
        Spawn multiple worker agents concurrently in a single call.
        Use this instead of multiple individual spawn_worker calls when you need
        to delegate several independent tasks at once. This ensures true parallel
        execution and avoids serializing worker creation across multiple LLM turns.
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
                        "workers": {
                            "type": "array",
                            "description": "List of worker configurations to spawn in parallel",
                            "items": {
                                "type": "object",
                                "properties": {
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
                    },
                    "required": ["workers"],
                },
            },
        }

    def run(self, **kwargs):
        """Execution is handled by Coordinator.spawn_workers(); this stub
        satisfies the abstract base class and prevents accidental use.
        """
        raise NotImplementedError(
            "SpawnWorkersBatch is schema-only. Use Coordinator.spawn_workers() instead."
        )

    async def arun(self, **kwargs):
        """Async variant — same redirect as run()."""
        raise NotImplementedError(
            "SpawnWorkersBatch is schema-only. Use Coordinator.spawn_workers() instead."
        )
