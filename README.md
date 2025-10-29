# Terminus CLI 🤖

A powerful AI-powered command-line interface agent that helps developers with coding tasks through intelligent tool usage and conversational interaction.

## Overview

Terminus CLI is an advanced coding assistant that combines the power of Large Language Models (LLMs) with a comprehensive toolkit of development utilities. It provides an interactive terminal interface where users can ask questions, request code analysis, perform file operations, and get help with various programming tasks.

## Key Features

- **Interactive CLI Interface**: Rich terminal UI with styled output and progress indicators
- **AI-Powered Agent**: Uses Groq API for fast and efficient language model interactions
- **Comprehensive Tool Suite**: 10+ development tools for file operations, code analysis, and task management
- **Context Management**: Intelligent conversation context tracking with usage visualization
- **Sub-agent Delegation**: Ability to delegate complex tasks to specialized sub-agents
- **Task Management**: Built-in todo system for tracking and planning development tasks
- **File Operations**: Read, write, edit, and search files with powerful pattern matching
- **Command Execution**: Safe terminal command execution with output capture
- **Multi-file Support**: Read and process multiple files simultaneously

## Architecture

### Core Components

- **Agent (`agent.py`)**: Central AI agent that orchestrates tool usage and manages conversation context
- **CLI Interface (`main.py`)**: Rich terminal interface with styled output and user interaction
- **Tool Registry (`tools/tool_registry.py`)**: Manages and executes available development tools
- **Prompt Manager (`prompts/manager.py`)**: Handles system prompts and prompt engineering

### Available Tools

1. **Grep Search** - Search codebase for text patterns
2. **File Reader** - Read and display file contents
3. **File Creator** - Create new files with specified content
4. **File Editor** - Modify existing files (write/append operations)
5. **Command Executor** - Execute terminal commands safely
6. **Todo Manager** - Manage task lists and track progress
7. **Multiple File Reader** - Read multiple files simultaneously
8. **Directory Listing** - List directory contents
9. **Sub-agent** - Delegate complex tasks to specialized agents
10. **Web Search** - Search the web for information (when needed)

## Installation

### Prerequisites

- Python 3.11 or higher
- Groq API key

### Setup

1. Clone the repository:
```bash
git clone https://github.com/sidmanale643/terminus-cli.git
cd terminus-cli
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
# or using the lock file:
pip install uv
uv pip install -r uv.lock
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your Groq API key
```

## Usage

### Interactive Mode

Run the CLI in interactive mode:

```bash
python main.py
```

This will start the Terminus CLI with a rich terminal interface. You can:

- Type your questions or requests naturally
- Use commands like `/help`, `/context`, `/clear`, `/exit`
- Ask for code analysis, file operations, or development help
- The agent will automatically use appropriate tools to assist you

### Single Query Mode

Run a single query from the command line:

```bash
python main.py "search for all Python files containing 'class Agent'"
```

### Quick Commands

- `/help` - Display help information
- `/context` - View current conversation context
- `/clear` - Clear the console screen
- `/exit` or `quit` - Exit the program

## Configuration

### Environment Variables

Create a `.env` file in the root directory with:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### Context Management

The agent maintains conversation context with:
- Maximum context size: 128,000 tokens
- Context usage displayed as a visual progress bar
- Automatic context management to stay within limits

## Examples

### File Operations

```
> Read the contents of main.py
> Create a new file called config.json with database settings
> Edit the README.md file to add a new section
```

### Code Analysis

```
> Search for all functions that handle user input
> Find all TODO comments in the codebase
> Show me the structure of the tools directory
```

### Development Tasks

```
> Help me plan the implementation of a new feature
> Create a todo list for refactoring the agent module
> Search for potential bugs in the error handling code
```

### System Information

```
> What tools are available?
> Show me the current directory structure
> List all Python files in the project
```

## Development

### Project Structure

```
terminus-cli/
├── main.py                 # CLI interface and entry point
├── agent.py               # Core AI agent logic
├── utils.py               # Utility functions
├── tools/                 # Tool implementations
│   ├── tool_registry.py   # Tool management
│   ├── grep.py           # Search functionality
│   ├── read_file.py      # File reading
│   ├── edit_file.py      # File editing
│   └── ...
├── prompts/               # Prompt management
│   ├── system_prompt.py  # System instructions
│   └── manager.py        # Prompt handling
├── models/               # Data models
├── ui/                   # User interface components
├── pyproject.toml        # Project dependencies
└── README.md            # This file
```

### Adding New Tools

To add a new tool:

1. Create a new tool class in the `tools/` directory
2. Inherit from the base tool class
3. Implement the required methods (`run`, `json_schema`)
4. Register the tool in `tool_registry.py`

### Tool Development Guidelines

- Tools should be atomic and focused on a single task
- Always include proper error handling
- Return clear, actionable results
- Follow the existing tool interface patterns
- Include comprehensive docstrings

## API Reference

### Agent Class

The main `Agent` class in `agent.py` provides:

- `run(user_message)`: Process a user message and return response
- `add_user_message(content)`: Add user message to context
- `add_assistant_message(content, tool_calls)`: Add assistant response
- `update_context_size()`: Calculate and update context usage

### Tool Interface

All tools implement:

- `run(**kwargs)`: Execute the tool with given parameters
- `json_schema()`: Return JSON schema for function calling
- `name`: Tool name for registration

## Error Handling

The system includes comprehensive error handling:

- **LLM Errors**: Graceful handling of API failures
- **Tool Errors**: Detailed error messages for tool execution failures
- **Context Errors**: Management of context size limitations
- **User Input Errors**: Validation and helpful error messages

## Performance

- **Context Efficiency**: Intelligent context management to maximize token usage
- **Tool Caching**: Results are cached when appropriate
- **Iterative Processing**: Multi-step problem solving with iteration limits
- **Resource Management**: Proper cleanup and resource handling

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/sidmanale643/terminus-cli.git
cd terminus-cli
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Testing

Run tests with:

```bash
python -m pytest tests/
```

## Troubleshooting

### Common Issues

1. **API Key Issues**: Ensure your Groq API key is valid and has sufficient credits
2. **Context Limitations**: Large codebases may exceed context limits - use targeted searches
3. **Tool Errors**: Check tool parameters and file paths for correctness
4. **Permission Issues**: Ensure proper file permissions for read/write operations

### Debug Mode

Enable debug logging by setting:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with [Groq](https://groq.com) for fast LLM inference
- Uses [Rich](https://github.com/Textualize/rich) for beautiful terminal output
- Inspired by modern CLI tools and AI assistants

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/sidmanale643/terminus-cli/issues) page.

---

**Terminus CLI** - Your intelligent coding companion in the terminal! 🚀