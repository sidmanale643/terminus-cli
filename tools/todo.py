from textwrap import dedent
from models.tool import ToolSchema
from pydantic import BaseModel
from typing import Literal, List

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
        Manage a simple todo list: add, update, and view tasks with statuses
        such as 'pending', 'in_progress', or 'completed'.
        Use this tool to create a todo list when the tasks are complex or require multiple steps to complete.
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
                            "description": "The todo task to add or update"
                        },
                        "status": {
                            "type": "string",
                            "description": "The status of the todo task",
                            "enum": ["pending", "completed", "in_progress"]
                        }
                    },
                    "required": ["task", "status"]
                }
            }
        }

    def run(self, task: str, status: Literal["pending", "completed", "in_progress"]):
   
        for todo in self.todos:
            if todo.task == task:
                todo.status = status
                break
        else:
            self.todos.append(TodoItem(task=task, status=status))

        return TodoList(items=self.todos).model_dump_json()
