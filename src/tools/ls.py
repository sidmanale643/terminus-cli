import subprocess
import os
from src.models.tool import ToolSchema
from textwrap import dedent

class Ls(ToolSchema):
    def __init__(self):
        self.name = "ls"
    
    def description(self):
        return dedent("""
        Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path.
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
                    }
                },
                "required": ["directory_path"]
            }
        }
    }
    
    def run(self, directory_path: str):
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