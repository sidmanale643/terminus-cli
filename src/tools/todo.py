from textwrap import dedent
from src.models.tool import ToolSchema
from pydantic import BaseModel
from typing import Literal, List, Optional

class TodoItem(BaseModel):
    task: str
    status: Literal["pending", "completed", "in_progress"]

class TodoList(BaseModel):
    items: List[TodoItem]

class TodoManager(ToolSchema):
    def __init__(self):

        self.name = "todo"
        self.todos: List[TodoItem] = []  

    def description(self):
        return dedent("""
        Manage a todo list: add, update, and view tasks with statuses such as 'pending', 'in_progress', or 'completed'.

        When to use this tool:
        - When you are planning a task that requires multiple steps to complete
        - When you are tracking the progress of a task
        - When you are managing a list of tasks
        - When you are tracking the progress of a task

        Instead of creating a list one by one, try to create an array of tasks at the beginning and then append new tasks later as required.

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
                            "description": "A single todo task to add or update (use this OR tasks, not both)"
                        },
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Multiple todo tasks to add at once (use this OR task, not both)"
                        },
                        "status": {
                            "type": "string",
                            "description": "The status of the todo task(s)",
                            "enum": ["pending", "completed", "in_progress"]
                        }
                    },
                    "required": ["status"]
                }
            }
        }

    def run(self, status: Literal["pending", "completed", "in_progress"], task: Optional[str] = None, tasks: Optional[List[str]] = None):
        """
        Add or update todo tasks. Can handle single task or multiple tasks.
        
        Args:
            status: The status for the task(s)
            task: A single task (optional)
            tasks: Multiple tasks (optional)
        """
        # Determine which parameter was provided
        task_list = []
        if task:
            task_list = [task]
        elif tasks:
            task_list = tasks
        else:
            return TodoList(items=self.todos).model_dump_json()
        
        # Process each task
        for task_item in task_list:
            # Check if task already exists
            existing_todo = None
            for todo in self.todos:
                if todo.task == task_item:
                    existing_todo = todo
                    break
            
            if existing_todo:
                # Update existing task
                existing_todo.status = status
            else:
                # Add new task
                self.todos.append(TodoItem(task=task_item, status=status))

        return TodoList(items=self.todos).model_dump_json()
