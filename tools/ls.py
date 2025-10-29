import subprocess
import os
from models.tool import ToolSchema
from textwrap import dedent

class Ls(ToolSchema):
    def __init__(self):
        self.name = "ls"
    
    def description(self):
        return dedent("""
        Lists the contents of a directory. Shows all files and subdirectories
        in the specified path. Use this to explore the file structure.
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