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
    YELLOW = '\033[93m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    def description(self):
        return dedent("""
        Modifies the content of a file by providing both the original and edited versions.
        This tool requires TWO separate parameters:
        1. 'content' - The EXACT original content of the file (read this from file_reader first)
        2. 'edited_content' - The NEW modified content you want to write to the file
        The tool will generate a diff comparing these two versions and write the edited_content to the file.

        IMPORTANT: Never add emojis unless specifically asked to do so by the user.

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
                        "description": "The ORIGINAL UNMODIFIED content of the file BEFORE any edits. This must match the current file content exactly. Use file_reader to get this first."
                    },
                    "edited_content": {
                        "type": "string",
                        "description": "The NEW MODIFIED content to write to the file AFTER your edits. This should be different from 'content' parameter and contain all your changes."
                    },
                },
                "required": ["file_path", "content", "edited_content"]
            }
        }
    }
    
    def format_colored_diff(self, diff_lines):
        """Format diff with colors and better readability"""
        result = []
        for line in diff_lines:
            # Strip trailing whitespace for display but preserve the line content
            line = line.rstrip()
            
            if line.startswith('---') or line.startswith('+++'):
                # File headers in bold yellow
                result.append(f"{self.BOLD}{self.YELLOW}{line}{self.RESET}")
            elif line.startswith('+'):
                # Additions in green
                result.append(f"{self.GREEN}{line}{self.RESET}")
            elif line.startswith('-'):
                # Deletions in red
                result.append(f"{self.RED}{line}{self.RESET}")
            elif line.startswith('@@'):
                # Line numbers in cyan bold
                result.append(f"{self.BOLD}{self.CYAN}{line}{self.RESET}")
            else:
                # Context lines
                result.append(line)
        return '\n'.join(result)
    
    def run(self, file_path : str, content : str, edited_content : str):
    
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
           
            # Write the new content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(edited_content)
            
            # Generate diff using splitlines for proper line-by-line comparison
            original_lines = original_content.splitlines(keepends=True)
            edited_lines = edited_content.splitlines(keepends=True)
            
            diff = list(difflib.unified_diff(
                original_lines,
                edited_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm='',
                n=3  # 3 lines of context
            ))

            if diff:
                colored_diff = self.format_colored_diff(diff)
                separator = "─" * 80
                result = f"\n{self.BOLD}{self.GREEN}✓ File edited successfully:{self.RESET} {file_path}\n\n{separator}\n{colored_diff}\n{separator}\n"
            else:
                result = f"File {file_path} has been edited (no changes detected in diff)."
            
            return result
            
        except Exception as e:
            return f"Error editing file: {e}"
    
    