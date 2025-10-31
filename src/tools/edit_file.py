from typing import Literal
from src.models.tool import ToolSchema 
from textwrap import dedent

class FileEditor(ToolSchema):
    def __init__(self):
        self.name = "file_editor"
    
    def description(self):
        return dedent("""
        Modifies the content of a file.
        This tool is useful for editing files in the codebase.
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
                        "description": "the path of the file to edit"
                    },
                    "content": {
                        "type": "string",
                        "description": "the content to write to the file"
                    },
                    "operation": {
                        "type": "string",
                        "description": "the operation to perform on the file",
                        "enum": ["write", "append"]
                    }
                },
                "required": ["file_path", "content", "operation"]
            }
        }
    }
    
    def run(self, file_path : str, content : str, operation : Literal["write", "append"]):
    
        try:
            if operation == "write":
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            else:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(content)
            return f"File {file_path} has been {operation}ed successfully"
            
        except Exception as e:
            return f"Error editing file: {e}"

        



