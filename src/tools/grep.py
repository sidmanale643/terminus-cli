import subprocess
from textwrap import dedent
from src.models.tool import ToolSchema

class Grep(ToolSchema):
    def __init__(self):
        self.name = "grep_search"
    
    def description(self):
        return dedent("""
            Search the codebase for text patterns using ripgrep (rg).
            Searches recursively through all files with intelligent filtering.
            Ripgrep is faster than grep and automatically respects .gitignore.
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
                            "description": "Glob patterns to filter files (e.g. `*.js`, `*.{ts,tsx}`). No filter by default. Defaults to None",
                            "default": None
                        },
                        
                    
                    },
                    "required": ["pattern"]
                }
            }
        }
    
    def run(self, pattern: str, path: str = None, glob: str = None):
        if not pattern:
            return "Error: Empty pattern provided. Please provide a search pattern."
        
        # Build ripgrep command
        query_parts = ["rg", "--line-number", "--no-heading", "--color=never"]
        
        # Add glob pattern if provided
        if glob:
            query_parts.extend(["--glob", glob])
        
        # Add pattern
        query_parts.append(pattern)
        
        # Add path (default to current directory)
        search_path = path if path else "."
        query_parts.append(search_path)
        
        # Execute the command
        try:
            result = subprocess.run(query_parts, capture_output=True, text=True)
            
            if result.returncode == 0:
                return result.stdout if result.stdout else "No matches found."
            elif result.returncode == 1:
                return "No matches found."
            else:
                return f"Error: {result.stderr if result.stderr else 'Unknown error'}"
        except FileNotFoundError:
            return "Error: ripgrep (rg) not found. Please install ripgrep: https://github.com/BurntSushi/ripgrep"