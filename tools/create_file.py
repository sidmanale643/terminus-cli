import subprocess
from models.tool import ToolSchema
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

        file_content = subprocess.run(
            f"touch {file_path}",
            shell=True,
            capture_output=True,
            text=True
        )

        if file_content.returncode != 0:
            return f"Error reading file: {file_content.stderr.strip() or 'Unknown error.'}"

        return f"File Content:\n{file_content.stdout.strip()}"
        
