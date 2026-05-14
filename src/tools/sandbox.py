from textwrap import dedent
from src.models.tool import ToolSchema

SUPPORTED_LANGUAGES = ["python", "typescript", "javascript"]


class Sandbox(ToolSchema):
    def __init__(self):
        self.name = "sandbox"

    def description(self):
        return dedent("""
            Execute arbitrary code securely in an isolated, cloud-hosted Daytona sandbox.
            Each call creates a fresh sandbox with the selected language runtime,
            runs the provided code, and returns stdout combined with stderr.
            Use this to run untrusted or AI-generated code, test snippets, or
            perform tasks in an isolated environment without affecting the host.
            Requires DAYTONA_API_KEY env var.
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
                        "code": {
                            "type": "string",
                            "description": "Source code to execute inside the sandbox. Must be valid in the chosen language."
                        },
                        "language": {
                            "type": "string",
                            "enum": SUPPORTED_LANGUAGES,
                            "description": "Programming language runtime for the sandbox. Each language runs in its own interpreter environment.",
                            "default": "python"
                        },
                        "ephemeral": {
                            "type": "boolean",
                            "description": "If true, the sandbox is destroyed right after code execution (no cleanup needed). If false, the sandbox persists until its auto-stop interval elapses.",
                            "default": True
                        },
                    },
                    "required": ["code"]
                }
            }
        }

    def run(self, code: str, language: str = "python", ephemeral: bool = True):
        import os
        from daytona import Daytona, DaytonaConfig, CreateSandboxFromSnapshotParams

        api_key = os.environ.get("DAYTONA_API_KEY")
        if not api_key:
            return "Error: DAYTONA_API_KEY environment variable is not set."

        if language not in SUPPORTED_LANGUAGES:
            return (
                f"Error: Unsupported language '{language}'. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
            )

        try:
            config = DaytonaConfig(api_key=api_key)
            daytona = Daytona(config)
            params = CreateSandboxFromSnapshotParams(
                language=language,
                ephemeral=ephemeral,
            )
            sandbox = daytona.create(params)
            response = sandbox.process.code_run(code)
            if response.exit_code != 0:
                return f"Exit code: {response.exit_code}\n{response.result}"
            return response.result
        except Exception as e:
            return f"Error executing in sandbox: {str(e)}"
