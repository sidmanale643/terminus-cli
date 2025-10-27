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
        """)

    def json_schema(self) -> Dict[str, Any]:
        """
        Defines the expected input schema for the command executor.
        """
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

    def run(self, command: str) -> Dict[str, Any]:
        """
        Executes the given command and returns a structured response.
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
