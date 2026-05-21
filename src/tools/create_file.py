import os
from src.models.tool import ToolSchema
from textwrap import dedent


class FileCreator(ToolSchema):
    def __init__(self):
        self.name = "file_creator"

    def description(self):
        return dedent("""
        Creates a new file at the given path with optional content.
        If the file already exists, it will be overwritten.
        Parent directories will be created automatically if they don't exist.
        Use file_path for the path. Relative paths are resolved from the current
        working directory. path is accepted as a compatibility alias.
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
                        "file_path": {
                            "type": "string",
                            "description": "the absolute path of the file to create",
                        },
                        "path": {
                            "type": "string",
                            "description": "compatibility alias for file_path",
                        },
                        "content": {
                            "type": "string",
                            "description": "the content to write to the file. Defaults to empty string.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

    def run(self, file_path: str = None, content: str = "", path: str = None):
        try:
            file_path = file_path or path
            if not file_path:
                return "Error: file_path is required"
            file_path = os.path.expanduser(file_path)
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            parent = os.path.dirname(file_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Created file: {file_path}"
        except PermissionError:
            return f"Error: Permission denied creating {file_path}"
        except Exception as e:
            return f"Error creating file: {e}"
