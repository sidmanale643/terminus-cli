"""Structured dispatch tool exposed only to a mission orchestrator."""

from __future__ import annotations

import json

from src.models.tool import ToolSchema


class MissionDispatch(ToolSchema):
    def __init__(self, controller):
        self.name = "mission_dispatch"
        self.controller = controller

    def description(self):
        return (
            "Run one synchronous mission batch and return its structured results. "
            "Use phases in lifecycle order: scouting, executing (or direct verifying "
            "when no changes are needed), verifying, and at most one repairing plus "
            "fresh verifying cycle. The controller validates roles, dependencies, "
            "file scopes, acceptance criteria, transitions, and results."
        )

    def json_schema(self):
        task = {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Unique stable identifier within this mission.",
                },
                "role": {
                    "type": "string",
                    "enum": ["scout", "worker", "verifier"],
                    "description": "Must match the dispatched phase.",
                },
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Short user-facing task name.",
                },
                "instructions": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Bounded, complete assignment for this role agent.",
                },
                "file_scope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                    "description": (
                        "Non-empty repository-relative edit paths for Workers. Paths "
                        "in the same batch should not overlap. Must be empty for Scouts "
                        "and Verifiers."
                    ),
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                    "description": (
                        "Task IDs that must complete first. A repair Worker may depend "
                        "on the failed Verifier whose evidence it is repairing."
                    ),
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "uniqueItems": True,
                    "description": (
                        "Concrete observable conditions this task must prove with "
                        "repository-tool evidence."
                    ),
                },
            },
            "required": [
                "task_id",
                "role",
                "title",
                "instructions",
                "file_scope",
                "dependencies",
                "acceptance_criteria",
            ],
            "additionalProperties": False,
        }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phase": {
                            "type": "string",
                            "enum": ["scouting", "executing", "repairing", "verifying"],
                            "description": "The single lifecycle phase represented by this batch.",
                        },
                        "tasks": {
                            "type": "array",
                            "items": task,
                            "minItems": 1,
                            "description": "One or more role tasks for this phase.",
                        },
                    },
                    "required": ["phase", "tasks"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, phase: str, tasks: list[dict]):
        try:
            result = self.controller.dispatch(phase, tasks)
        except (RuntimeError, ValueError) as exc:
            return json.dumps({"status": "rejected", "error": str(exc)})
        return json.dumps(result)
