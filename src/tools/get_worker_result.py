from textwrap import dedent
from src.models.tool import ToolSchema


class GetWorkerResult(ToolSchema):
    def __init__(self):
        self.name = "get_worker_result"

    def description(self):
        return dedent("""
        Get the final result of a specific worker if it has completed.
        Returns the worker's ID, name, role, status, provenance, and structured result
        envelope. The result envelope contains a compact handoff with what_was_done,
        evidence, unresolved_risks, exact_next_step, and status. Legacy summary,
        artifacts, findings, and recommended_next_action fields may also be present.
        Returns nothing if the worker does not exist.
        Use this to check on a worker without blocking.
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
                        "worker_id": {
                            "type": "string",
                            "description": "The ID of the worker to get the result for, e.g. worker_1",
                        },
                    },
                    "required": ["worker_id"],
                },
            },
        }

    def run(self, worker_id: str):
        # Sync fallback; actual retrieval happens in Coordinator.get_worker_result
        return f"get_worker_result for {worker_id} should be called via coordinator"
