import subprocess
from src.models.tool import ToolSchema
from textwrap import dedent

class FileReader(ToolSchema):
    def __init__(self):
        self.name = "file_reader"
    
    def description(self):
        return dedent("""
    Reads a file from the local filesystem. You can access any file directly by using this tool.
    Assume this tool is able to read all files on the machine. 
    If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

    Usage:
    - The code line numbers will also be provided starting from 1.
    - The file_path parameter must be an absolute path, not a relative path
    - If a file does not exist or read file is empty you will be informed so.
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
            f"cat -n {file_path}",
            shell=True,
            capture_output=True,
            text=True
        )

        if file_content.returncode != 0:
            error_msg = file_content.stderr.strip()
            if "No such file or directory" in error_msg:
                return f"File does not exist"
            return f"Error reading file: {error_msg or 'Unknown error.'}"

        if not file_content.stdout.strip():
            return "File is empty"

        return f"File Content:\n{file_content.stdout.strip()}"
        
