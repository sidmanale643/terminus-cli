import json
import os
from textwrap import dedent
from typing import List, Literal, Optional

from terminus.tools.base import ToolSchema
from terminus.config import TODO_FILE

VALID_STATUSES = {"pending", "in_progress", "completed"}


class TodoStorageError(RuntimeError):
    pass


def _load_todos() -> List[dict]:
    if not os.path.exists(TODO_FILE):
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise TodoStorageError(f"Unable to read {TODO_FILE}: {exc}") from exc

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise TodoStorageError(f"Invalid todo file format: {TODO_FILE}")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("task"), str)
        or item.get("status") not in VALID_STATUSES
        for item in items
    ):
        raise TodoStorageError(f"Invalid todo item in {TODO_FILE}")
    return items


def _save_todos(items: List[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(TODO_FILE), exist_ok=True)
        with open(TODO_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2)
    except OSError as exc:
        raise TodoStorageError(f"Unable to write {TODO_FILE}: {exc}") from exc


def _dump_items(items: List[dict]) -> str:
    return json.dumps({"items": items})


def _select_tasks(
    task: Optional[str], tasks: Optional[List[str]]
) -> tuple[Optional[List[str]], Optional[str]]:
    if task is not None and tasks is not None:
        return None, "Error: provide task or tasks, not both"

    selected = [task] if task is not None else tasks
    if not selected:
        return None, "Error: task or tasks is required"
    if not isinstance(selected, list) or any(
        not isinstance(item, str) or not item.strip() for item in selected
    ):
        return None, "Error: task values must be non-empty strings"
    return selected, None


class TodoWrite(ToolSchema):
    def __init__(self):
        self.name = "todo_write"

    def description(self):
        return dedent("""
        Add one or more new tasks to the todo list.

        When to use:
        - When starting a new multi-step task and you want to track progress.
        - When planning work and breaking it into smaller steps.

        Instead of adding one by one, prefer passing an array of tasks.
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
                        "task": {
                            "type": "string",
                            "description": "A single todo task to add (use this OR tasks, not both)",
                        },
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Multiple todo tasks to add at once (use this OR task, not both)",
                        },
                        "status": {
                            "type": "string",
                            "description": "Initial status for the task(s)",
                            "enum": ["pending", "in_progress", "completed"],
                            "default": "pending",
                        },
                    },
                },
            },
        }

    def run(
        self,
        task: Optional[str] = None,
        tasks: Optional[List[str]] = None,
        status: Literal["pending", "in_progress", "completed"] = "pending",
    ):
        task_list, error = _select_tasks(task, tasks)
        if error:
            return error
        if status not in VALID_STATUSES:
            return f"Error: invalid todo status: {status}"

        try:
            items = _load_todos()
            existing_tasks = {item["task"] for item in items}

            for t in task_list:
                if t not in existing_tasks:
                    items.append({"task": t, "status": status})
                    existing_tasks.add(t)

            _save_todos(items)
            return _dump_items(items)
        except TodoStorageError as exc:
            return f"Error: {exc}"


class TodoRead(ToolSchema):
    def __init__(self):
        self.name = "todo_read"

    def description(self):
        return dedent("""
        Read the current todo list from the todos file.
        Returns all tasks with their statuses.
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
        try:
            return _dump_items(_load_todos())
        except TodoStorageError as exc:
            return f"Error: {exc}"


class TodoUpdate(ToolSchema):
    def __init__(self):
        self.name = "todo_update"

    def description(self):
        return dedent("""
        Update the status of one or more existing tasks in the todo list.
        Tasks are matched by exact task name.

        When to use:
        - Mark a task as in_progress when you start working on it.
        - Mark a task as completed when it is finished.
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
                        "task": {
                            "type": "string",
                            "description": "A single existing task to update (use this OR tasks, not both)",
                        },
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Multiple existing tasks to update at once (use this OR task, not both)",
                        },
                        "status": {
                            "type": "string",
                            "description": "The new status for the task(s)",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["status"],
                },
            },
        }

    def run(
        self,
        status: Literal["pending", "in_progress", "completed"],
        task: Optional[str] = None,
        tasks: Optional[List[str]] = None,
    ):
        task_list, error = _select_tasks(task, tasks)
        if error:
            return error
        if status not in VALID_STATUSES:
            return f"Error: invalid todo status: {status}"

        try:
            items = _load_todos()
            matched = set()
            for t in task_list:
                for item in items:
                    if item["task"] == t:
                        item["status"] = status
                        matched.add(t)
                        break

            unmatched = [t for t in task_list if t not in matched]
            _save_todos(items)

            result = {"items": items}
            if unmatched:
                result["unmatched"] = unmatched
            return json.dumps(result)
        except TodoStorageError as exc:
            return f"Error: {exc}"
