import subprocess
from models.tool import ToolSchema
from textwrap import dedent

class FileReader(ToolSchema):
    def __init__(self):
        self.name = "file_reader"
    
    def description(self):
        return dedent("""
        Reads and returns the full content of a specified file path.
        This tool is useful for accessing and viewing text files such as logs,
        configuration files, or source code directly from the filesystem.
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
                        "description": "the path of the file to read"
                    }
                },
                "required": ["file_path"]
            }
        }
    }
    
    def run(self, file_path: str):

        file_content = subprocess.run(
            f"cat {file_path}",
            shell=True,
            capture_output=True,
            text=True
        )

        if file_content.returncode != 0:
            return f"Error reading file: {file_content.stderr.strip() or 'Unknown error.'}"

        return f"File Content:\n{file_content.stdout.strip()}"
        
