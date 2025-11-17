# Terminus CLI

> AI-powered development companion for the command line

![Terminus CLI](assets/image.png)

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)](https://github.com/sidmanale643/terminus-cli)

Terminus CLI is an AI-powered tool that automates coding tasks, manages files, and streamlines your development workflow directly from the command line.

## Features

- **Project Awareness**: Analyzes and understands your entire codebase structure
- **Natural Language Interface**: Interact using plain English descriptions of tasks
- **Intelligent File Operations**: Read, write, edit, and create files with AI guidance
- **Codebase Search & Analysis**: Powerful search tools to find and analyze code patterns
- **Multi-LLM Support**: Integrates with Groq, OpenRouter, and extensible for others
- **Persistent Session Memory**: Retains context across interactions for efficient workflows
- **Tool Ecosystem**: Built-in tools for linting, task management, and system commands
- **Customizable Behavior**: Project-specific instructions via `terminus.md`

## Quick Start

### Prerequisites
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended for fast dependency management; pip works too)

### Installation

#### Option 1: Global Install with pipx (Recommended)

pipx provides isolated, system-wide access:

```bash
# Install pipx (if needed)
# macOS: brew install pipx
# Ubuntu: python3 -m pip install --user pipx
pipx ensurepath

# Install from GitHub
pipx install git+https://github.com/sidmanale643/terminus-cli.git

# Or from local directory (after cloning)
# pipx install -e /path/to/local/terminus-cli
```

#### Option 2: Virtual Environment Setup (Development)

```bash
git clone https://github.com/sidmanale643/terminus-cli.git
cd terminus-cli

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync

# Install in editable mode
uv pip install -e .

# Setup environment file
cp .env.sample .env
# Edit .env with your API keys (see below)
```

To run: `terminus` (if installed) or `python -m src.main`.

### Configuration

Create or edit `.env` in your project root or home directory:

```env
# Required for LLM access
GROQ_API_KEY=your_groq_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Optional: Default model
DEFAULT_MODEL=groq/llama3-8b-8192  # Or openrouter/model-name
```

Obtain keys from:
- [Groq Console](https://console.groq.com/keys)
- [OpenRouter](https://openrouter.ai/keys)

## Usage Examples

### Starting Terminus

Navigate to your project and launch:

```bash
cd /path/to/your/project
terminus
```

This opens an interactive session where Terminus uses the current directory as context.

### Interactive Session

```bash
terminus> List all Python files in the src directory
terminus> Explain how the agent.py file works
terminus> Add a new function to utils.py for data validation
```

### One-Shot Queries

For single commands without interactive mode:

```bash
terminus "Search for unused imports in the codebase"
terminus "Generate a unit test for the login function in auth.py"
```

### Referencing Files

Use `@` to point to specific files:

```bash
terminus "Optimize the code in @src/agent.py"
terminus "Document the classes in @src/models/schema.py"
```

## Built-in Commands

Available in interactive mode:

| Command | Description |
|---------|-------------|
| `/help` | Display help and available commands |
| `/context` | Show current session context |
| `/history` | View conversation history |
| `/reset` | Reset context and start over |
| `/exit` | Exit the application |
| `/todo` | View or manage task lists |

### Custom Instructions with `terminus.md`

Tailor Terminus behavior per project by creating `terminus.md` in the root:

```markdown
# Project-Specific Instructions

## Coding Standards
- Use type hints everywhere (PEP 484)
- Adhere to PEP 8 formatting
- Prefer async patterns for I/O operations

## Preferences
- Avoid global variables
- Use existing dependencies from pyproject.toml
- Prioritize security in file operations
```

Terminus loads this file automatically, incorporating instructions into its responses.

## Architecture Overview

```
terminus-cli/
├── pyproject.toml      # Dependencies and build config
├── uv.lock             # Lockfile for dependencies
├── src/
│   ├── __init__.py
│   ├── agent.py        # Core AI agent logic
│   ├── constants.py    # Constants and configurations
│   ├── main.py         # CLI entry point
│   ├── session_manager.py  # Session management
│   ├── tools/          # Tool definitions (file I/O, search, exec, etc.)
│   ├── llm_service/    # LLM client integrations
│   ├── models/         # Pydantic models for data handling
│   ├── prompts/        # Prompt templates
│   └── utils/          # Shared utilities
├── ui/                 # Terminal interface (prompts, output formatting)
├── notebooks/          # Exploratory Jupyter notebooks
├── assets/             # Project assets (images, etc.)
├── README.md           # Documentation
├── .env.sample         # Config template
└── .gitignore          # Git ignore patterns
```

The agent uses a tool-calling architecture, delegating tasks to specialized functions for safe, precise operations.

## Development Guide

### Running the Application

- Interactive: `terminus`
- Debug: `python -m src.main --debug`

### Testing

```bash
uv run pytest tests/
uv run pytest --cov src/
```

### Linting and Formatting

Ruff is configured in `pyproject.toml`:

```bash
# Check
uv run ruff check .

# Format
uv run ruff format .

# Lint and auto-fix
uv run ruff check --fix .
```

### Adding Tools or Features

1. Implement in `src/tools/`
2. Register in `agent.py`
3. Add tests in `tests/`
4. Update README if user-facing

## Contributing

We welcome contributions! Please:

1. Fork the repo and create a feature branch
2. Ensure code passes linting and tests
3. Update documentation
4. Submit a PR with a clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for details (create if needed).

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE).

## Support and Feedback

- **Issues**: [GitHub Issues](https://github.com/sidmanale643/terminus-cli/issues)
- **Discussions**: [GitHub Discussions](https://github.com/sidmanale643/terminus-cli/discussions)
- **In-App**: Type `/help` for quick assistance
- **Feedback**: Report at the issues page above

---

Terminus CLI: Empowering CLI-driven development with AI intelligence.