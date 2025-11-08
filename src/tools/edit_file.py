from src.models.tool import ToolSchema 
from textwrap import dedent
import difflib

class FileEditor(ToolSchema):
    def __init__(self):
        self.name = "file_editor"
    
    # ANSI color codes
    RED = '\033[91m'
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    
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
                        "description": "the original content of the file BEFORE editing (used to generate diff)"
                    },
                    "edited_content": {
                        "type": "string",
                        "description": "the new content of the file AFTER editing (this will be written to the file)"
                    },
                },
                "required": ["file_path", "content", "edited_content"]
            }
        }
    }
    
    def format_colored_diff(self, diff_lines):
        """Format diff with colors"""
        result = []
        for line in diff_lines:
            if line.startswith('+') and not line.startswith('+++'):
                result.append(f"{self.GREEN}{line}{self.RESET}")
            elif line.startswith('-') and not line.startswith('---'):
                result.append(f"{self.RED}{line}{self.RESET}")
            elif line.startswith('@@'):
                result.append(f"{self.CYAN}{line}{self.RESET}")
            else:
                result.append(line)
        return '\n'.join(result)
    
    def run(self, file_path : str, content : str, edited_content : str):
    
        try:
            # Generate diff before writing
            original_lines = content.splitlines(keepends=False)
            edited_lines = edited_content.splitlines(keepends=False)
            
            diff = list(difflib.unified_diff(
                original_lines,
                edited_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm=''
            ))
            
            # Write the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(edited_content)
            
            # Format result for display
            if diff:
                colored_diff = self.format_colored_diff(diff)
                # Use visual separator without markdown code fence
                separator = "─" * 60
                result = f"File {file_path} has been edited successfully.\n\n{separator}\n{colored_diff}\n{separator}"
            else:
                result = f"File {file_path} has been edited (no changes detected in diff)."
            
            return result
            
        except Exception as e:
            return f"Error editing file: {e}"