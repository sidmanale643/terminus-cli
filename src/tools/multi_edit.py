from typing import List
from .edit_file import FileEditor

class MultiEdit:
    def __init__(self):
        self.name = "multi_edit_file"
        self.file_editor = FileEditor()
    
    def description(self):
        return """
        This is 'multi_edit' file tool built on top of the 'edit_file' tool.
        Use this tool when you want to make multiple edits in a single file,
        """

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
                    "old_strings": {
                        "type": "array",
                        "description": "the old string to replace"
                    },
                    "new_string": {
                        "type": "array",
                        "description": "the new string to replace the old string with"
                    },
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    }
    

    def run(self, file_path, old_string = List[str], new_string = List[str]):

        for old_string, new_string in zip(old_string, new_string):
            self.file_editor.run(file_path= file_path, old_string = old_string, new_string= new_string)
        
        return "All edits were succesful"


