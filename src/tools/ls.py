import subprocess
import os
from src.models.tool import ToolSchema
from textwrap import dedent

class Ls(ToolSchema):
    def __init__(self):
        self.name = "ls"
    
    def description(self):
        return dedent("""
        Lists files and directories in a given path. Use directory_path for the path.
        Relative paths are resolved from the current working directory. directory
        and path are accepted as compatibility aliases.
        You can optionally provide an array of glob patterns to ignore with the ignore parameter. 
        You should generally prefer the Glob and Grep tools, if you know which directories to search.
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
                    "directory_path": {
                        "type": "string",
                        "description": "the path of the directory to list"
                    },
                    "directory": {
                        "type": "string",
                        "description": "compatibility alias for directory_path"
                    },
                    "path": {
                        "type": "string",
                        "description": "compatibility alias for directory_path"
                    }
                },
                "required": ["directory_path"]
            }
        }
    }
    
    def run(self, directory_path: str = None, directory: str = None, path: str = None):
        directory_path = directory_path or directory or path
        if not directory_path:
            return "Error: directory_path is required."
        directory_path = os.path.expanduser(directory_path)
        if not os.path.isabs(directory_path):
            directory_path = os.path.abspath(directory_path)
        # Validate the path exists
        if not os.path.exists(directory_path):
            return f"Error: Path '{directory_path}' does not exist."
        
        if not os.path.isdir(directory_path):
            return f"Error: Path '{directory_path}' is not a directory."

        # Use list form to avoid shell injection
        try:
            result = subprocess.run(
                ["ls", "-la", directory_path],  # Safer: no shell=True
                capture_output=True,
                text=True,
                check=False
            )
        except Exception as e:
            return f"Error executing ls command: {str(e)}"

        if result.returncode != 0:
            return f"Error listing directory: {result.stderr.strip() or 'Unknown error.'}"

        return f"Directory contents of '{directory_path}':\n{result.stdout.strip()}"
