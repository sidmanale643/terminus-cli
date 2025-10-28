# Kodex CLI

A CLI-based AI coding agent powered by LLMs that assists with various coding tasks through a tool-based architecture.

## Overview

Kodex CLI (internally called `terminus-cli`) is an intelligent coding assistant that leverages Large Language Models to help developers with file operations, code searches, command execution, and task management. The agent operates through an iterative process, using a set of specialized tools to complete user requests.

## Features

- **AI-Powered Agent**: Utilizes LLMs (via OpenRouter) to understand and execute coding tasks
- **Tool-Based Architecture**: Modular design with specialized tools for different operations
- **Iterative Execution**: Continues working until task completion (up to 50 iterations)
- **Task Management**: Built-in TODO system for complex multi-step tasks
- **File Operations**: Read, create, and edit files
- **Code Search**: Grep functionality for searching through codebases
- **Command Execution**: Execute shell commands directly from the agent

## Available Tools

The agent comes with the following built-in tools:

- **FileReader**: Read and display file contents
- **FileCreator**: Create new files
- **FileEditor**: Edit existing files
- **Grep**: Search for patterns in files
- **CommandExecutor**: Execute shell commands
- **TodoManager**: Manage task lists for complex operations

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd kodex-cli
```

2. Install dependencies using `uv`:
```bash
uv sync
```

Or with pip:
```bash
pip install -r requirements.txt
```

## Configuration

The project requires API keys for LLM providers. Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
GROQ_API_KEY=your_groq_key_here
```

## Usage

### Basic Usage

Run the agent with a task:

```python
from main import Agent

agent = Agent()
result = agent.run("Your task description here")
print(result)
```

### Example Tasks

```python
# Create a new file
agent.run("Create a new file called example.py with a hello world function")

# Search for patterns
agent.run("Find all TODO comments in the codebase")

# Execute commands
agent.run("Run the test suite and show me the results")
```

## Project Structure

```
kodex-cli/
├── main.py                 # Main agent implementation
├── llm.py                  # LLM service configuration
├── utils.py                # Utility functions for LLM calls
├── pyproject.toml          # Project dependencies
├── models/
│   ├── llm.py             # LLM model definitions
│   └── tool.py            # Base tool schema
├── prompt_manager/
│   └── system_prompt.py   # System prompts for the agent
└── tools/
    ├── __init__.py        # Tool exports
    ├── tool_registry.py   # Tool registration and management
    ├── cmd_executor.py    # Command execution tool
    ├── create_file.py     # File creation tool
    ├── edit_file.py       # File editing tool
    ├── grep.py            # Search tool
    ├── read_file.py       # File reading tool
    └── todo.py            # Task management tool
```

## How It Works

1. **Initialization**: The agent initializes with a tool registry containing all available tools
2. **User Input**: User provides a task description
3. **LLM Processing**: The agent sends the task to the LLM with available tool schemas
4. **Tool Execution**: If the LLM requests a tool, the agent executes it and returns results
5. **Iteration**: Steps 3-4 repeat until the task is complete or max iterations reached
6. **Response**: Final result is returned to the user

## Agent Behavior

- Automatically creates TODO lists for tasks requiring 3+ steps
- Provides detailed explanations of changes being made
- Returns output in markdown format
- Maximum 50 iterations per task to prevent infinite loops
- Verbose logging for debugging and transparency

## Dependencies

- Python >= 3.11
- openai >= 2.6.1
- openrouter >= 1.0
- pydantic >= 2.12.3
- ipykernel >= 7.0.1

## Development

### Adding New Tools

1. Create a new tool class inheriting from `ToolSchema` in the `tools/` directory
2. Implement required methods: `description()`, `json_schema()`, and `run()`
3. Register the tool in `tools/tool_registry.py`
4. Export the tool in `tools/__init__.py`

Example:
```python
from models.tool import ToolSchema

class MyTool(ToolSchema):
    def __init__(self):
        self.name = "my_tool"
    
    def description(self):
        return "Description of what this tool does"
    
    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param": {
                            "type": "string",
                            "description": "Parameter description"
                        }
                    },
                    "required": ["param"]
                }
            }
        }
    
    def run(self, param: str):
        # Tool implementation
        return "Result"
```

## Contributing

Contributions are welcome! Please follow these guidelines:
- Write clear, descriptive commit messages
- Add tests for new tools
- Update documentation for new features
- Follow existing code style and structure

## License

[Add your license information here]

## Support

For issues, questions, or contributions, please [open an issue](link-to-issues) on the project repository.

