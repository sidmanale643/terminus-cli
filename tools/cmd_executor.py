from textwrap import dedent
from models.tool import ToolSchema
import subprocess
from typing import Dict, Any

class CommandExecutor(ToolSchema):
    """
    Tool for safely executing terminal commands and returning the output.
    """

    def __init__(self):
        self.name = "command_executor"

    def description(self) -> str:
        return dedent("""
        Executes terminal commands and returns their output, error, and exit status.
        Useful for interacting with the underlying system or running scripts.

        AVAILABLE COMMANDS:
        - cd - change directory
        - mkdir - create a new directory
        - touch - create a new file
        - rm - remove a file or directory
        - cp - copy a file or directory
        - mv - move a file or directory
        - git status - git status
        - git log - git log
        - git diff - git diff
        - git pull - git pull
        """)

    def json_schema(self) -> Dict[str, Any]:
 
        return {
        "type": "function",
        "function": {
            "name": self.name, 
            "description": self.description(),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "the command to run"
                    }
                },
                "required": ["command"]
            }   
        }
    }

    def run(self, command: str, cwd: str = None) -> Dict[str, Any]:

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd
            )
            
            if result.returncode == 0:
                return result.stdout if result.stdout else "(command executed successfully, no output)"
            else:
              
                error_msg = f"Command failed with exit code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nError: {result.stderr}"
                if result.stdout:
                    error_msg += f"\nOutput: {result.stdout}"
                return error_msg
                
        except Exception as e:
            return f"Error executing command: {str(e)}"
