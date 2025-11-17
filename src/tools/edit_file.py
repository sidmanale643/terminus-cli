from src.models.tool import ToolSchema 
from textwrap import dedent
import difflib
from rich.console import Console

class FileEditor(ToolSchema):
    def __init__(self):
        self.name = "file_editor"
        self.console = Console()
    
    
    RED = '\033[91m'
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    def description(self):
        return dedent("""
        Performs precise edits in a file.
        Edit file contents by performing precise text replacement operations.

        This tool allows you to make targeted edits to existing files by replacing specific text patterns with new content.

        First read the contents of the file to understand the structure.
        Carefully match patterns and replace only the specific text you want to change.
        Be precise with indentation and whitespace.

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
                    "old_string": {
                        "type": "string",
                        "description": "the old string to replace"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "the new string to replace the old string with"
                    },
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    }
    
    def format_colored_diff(self, diff_lines):
        result = []
        for line in diff_lines:
            
            line = line.rstrip()
            
            if line.startswith('---') or line.startswith('+++'):
                
                result.append(f"{self.BOLD}{self.YELLOW}{line}{self.RESET}")
            elif line.startswith('+'):
                
                result.append(f"{self.GREEN}{line}{self.RESET}")
            elif line.startswith('-'):
                
                result.append(f"{self.RED}{line}{self.RESET}")
            elif line.startswith('@@'):
                
                result.append(f"{self.BOLD}{self.CYAN}{line}{self.RESET}")
            else:
                
                result.append(line)
        return '\n'.join(result)
    
    def ask_for_permission(self, diff_preview, status_callback=None):
        
        # Try to get the StreamingHandler's console if status_callback is provided
        console_to_use = self.console
        handler = None
        
        if status_callback and hasattr(status_callback, '__self__'):
            # status_callback is a bound method, get the handler (StreamingHandler instance)
            handler = status_callback.__self__
            if hasattr(handler, 'console'):
                console_to_use = handler.console
        
        while True:
            # Use the appropriate console for input
            console_to_use.print()  # Add a blank line for spacing
            response = console_to_use.input("[bold bright_red]Apply these changes? (y/n):[/bold bright_red] ").strip().lower()
            if response in ['y', 'yes']:
                # Restart status spinner if it was stopped
                if handler and hasattr(handler, 'status') and handler.status:
                    handler.status.start()
                return True
            elif response in ['n', 'no']:
                # Restart status spinner if it was stopped
                if handler and hasattr(handler, 'status') and handler.status:
                    handler.status.start()
                return False
            else:
                console_to_use.print("[yellow]Please enter 'y' or 'n'[/yellow]")
         

    def run(self, file_path : str, old_string : str, new_string : str, status_callback=None):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            
            if old_string not in original_content:
                return f"{self.RED}Error:{self.RESET} The string to replace was not found in {file_path}\n\nMake sure to read the file first and use the exact string (including whitespace and indentation) that you want to replace."
            
            
            occurrence_count = original_content.count(old_string)
            if occurrence_count > 1:
                return f"{self.YELLOW}Warning:{self.RESET} The string appears {occurrence_count} times in {file_path}\n\nThis will replace ALL occurrences. If you want to replace only one, include more context to make the old_string unique."
            
            
            new_content = original_content.replace(old_string, new_string, 1)


            if original_content == new_content:
                return f"No changes made to {file_path} (old_string and new_string are identical)."

            # Create diff to show user
            original_lines = old_string.splitlines(keepends=True)
            new_lines = new_string.splitlines(keepends=True)
            
            diff = list(difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm='',
                n=3
            ))

            # Format the diff for display
            colored_diff = self.format_colored_diff(diff) if diff else "No visible diff"
            separator = "─" * 80
            diff_preview = f"\n{self.BOLD}{self.CYAN}Proposed changes to:{self.RESET} {file_path}\n\n{separator}\n{colored_diff}\n{separator}\n"
            
            # Show diff to user BEFORE asking for permission
            # Use status_callback if provided (for integration with StreamingHandler)
            if status_callback:
                # Display diff through the streaming handler with keep_stopped=True
                # This keeps the status spinner stopped so we can get user input
                status_callback(diff_preview, is_thinking=False, is_tool_output=True, keep_stopped=True)
            else:
                # Fallback: display directly via console
                from rich.text import Text
                diff_text = Text.from_ansi(diff_preview)
                self.console.print(diff_text)
            
            if self.ask_for_permission(diff_preview, status_callback):
                # User approved - write the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                result = f"{self.GREEN}✓ File edited successfully: {file_path}{self.RESET}"
            else:
                # User rejected the change
                result = f"{self.YELLOW}✗ Changes rejected by user{self.RESET}"

            return result
            
        except FileNotFoundError:
            return f"{self.RED}Error:{self.RESET} File not found: {file_path}"
        except PermissionError:
            return f"{self.RED}Error:{self.RESET} Permission denied when trying to edit: {file_path}"
        except Exception as e:
            return f"{self.RED}Error editing file:{self.RESET} {e}"
    
    