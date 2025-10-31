import subprocess
from src.models.tool import ToolSchema
from textwrap import dedent

class FileCreator(ToolSchema):
    def __init__(self):
        self.name = "file_creator"
    
    def description(self):
        return dedent("""
        Creates a new file with the given file path and content.
        This tool is useful for creating new files in the codebase.
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
                        "description": "the path of the file to create"
                    }
                },
                "required": ["file_path"]
            }
        }
    }
    
    def run(self, file_path: str):

        process = subprocess.run(
            f"touch {file_path}",
            shell=True,
            capture_output=True,
            text=True
        )

        if process.returncode != 0:
            return f"Error creating file: {process.stderr.strip() or 'Unknown error.'}"

        return f"Created File: {file_path}"
        
