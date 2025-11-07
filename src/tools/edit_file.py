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
        This tool has access to the original content of the file and the sections/sections of the file that need to be edited. The tool then returns the wholed new edited file.
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
                        "description": "the new content to write to the file"
                    },
                    "edited_content": {
                        "type": "string",
                        "description": "the content of the file after the edit"
                    },
                    "operation": {
                        "type": "string",
                        "description": "the operation to perform on the file",
                        "enum": ["write", "append"]
                    }
                },
                "required": ["file_path", "content", "operation", "edited_content"]
            }
        }
    }
    
    def run(self, file_path : str, content : str, operation : Literal["write", "append"], edited_content : str):
    
        try:
            if operation == "write":
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(edited_content)
            
            else:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(edited_content)
            return f"File {file_path} has been {operation}ed successfully"
            
        except Exception as e:
            return f"Error editing file: {e}"

        



