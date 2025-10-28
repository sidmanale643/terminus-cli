from models.tool import ToolSchema 
from textwrap import dedent

class FileEditor(ToolSchema):
    def __init__(self):
        self.name = "file_editor"
    
    def description():
        return dedent("""modify a file""")
    
    def json_schema():
        return {}
    
    def run(self, file_path : str, content : str):
        return ""

