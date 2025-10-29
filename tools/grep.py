import subprocess
from textwrap import dedent
from models.tool import ToolSchema

class Grep(ToolSchema):
    def __init__(self):
        self.name = "grep_search"
    
    def description(self):
        return dedent("""
            Search the codebase for text patterns using grep.
            Searches recursively through all files, excluding common directories.
        """).strip()
    
    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name, 
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {  
                            "type": "string",
                            "description": "The text pattern to search for in the codebase"
                        },
                        "path": {  
                            "type": "string",
                            "description": "File or directory to search in. Defaults to current working directory.If specified, it must be an absolute path.",
                            "default": "."
                        },
                        "glob": {  
                            "type": "string",
                            "description": "Glob pattern to filter files (e.g. `*.js`, `*.{ts,tsx}`). No filter by default. Defaults to None",
                            "default": None
                        },
                        
                    
                    },
                    "required": ["pattern"]
                }
            }
        }
    
    def run(self, pattern: str, path: str = None, glob : str = None):
        if not pattern:
            return "Error: Empty pattern provided. Please provide a search pattern."
        
        query = f"grep -rn --exclude-dir='__pycache__' --exclude-dir='.git' --exclude-dir='node_modules' --exclude-dir='.venv' --exclude='*.ipynb' '{pattern}' {glob} {glob} ."
        output = subprocess.run(query, shell=True, capture_output=True, text=True)
        
        if output.returncode == 0:
            return output.stdout if output.stdout else "No matches found."
        elif output.returncode == 1:
            return "No matches found."
        else:
            return f"Error: {output.stderr if output.stderr else 'Unknown error'}"