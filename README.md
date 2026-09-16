# Terminus CLI

> An AI coding agent that works alongside you right in your terminal.

![Terminus CLI](assets/terminus-cli.png)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Rich](https://img.shields.io/badge/UI-Rich-d70000?logo=python&logoColor=white)](https://github.com/Textualize/rich)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)](https://github.com/sidmanale643/terminus-cli)

Terminus CLI is a development companion for exploring codebases, planning changes, editing files, running commands, and completing multi-step engineering work. It combines a Python agent runtime with a Rich terminal interface, persistent conversation history, configurable model providers, and an extensible tool system.

Terminus runs in the directory you start it from. Ask questions in plain language, reference files with `@path`, or let the agent inspect and modify your project through its built-in tools.

## Features

- **Interactive terminal UI:** A Rich terminal interface with streamed responses, tool activity, status updates, a todo panel, and model and context information.
- **Autonomous agent loop:** The model can inspect the repository, choose tools, evaluate their results, and keep going until a task is complete.
- **Codebase operations:** Read, create, and edit files; search text and paths; list directories; and run shell commands.
- **OpenRouter support:** Use the registered model provider and switch models without leaving the app.
- **Persistent sessions:** Conversation history is stored locally in SQLite and remains available across multi-step work.
- **Automatic context management:** Large tool outputs are trimmed at 50% of the model context window, and conversations are compacted at 75%.
- **Skills and project instructions:** Load reusable skills and repository guidance from the working tree.
- **Optional integrations:** Tavily web search and Daytona sandboxes.
- **Interruptible work:** Press `Ctrl+C` once to cancel the current turn. Press it again within two seconds to exit.

## How Terminus works

```text
Your request
    │
    ▼
Agent chooses an action ──► Tool runs in the current project
    ▲                              │
    └──────── result returned ─────┘
    │
    ▼
Final response
```

The agent repeats this cycle for up to 50 iterations. Tool calls and output are shown in the terminal so you can follow what it is doing. The current directory defines the project scope and where Terminus looks for configuration such as `.env` and `AGENTS.md`.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- An OpenRouter API key

## Installation

Clone the repository and install the Python package:

```bash
git clone https://github.com/sidmanale643/terminus-cli.git
cd terminus-cli

uv sync
uv pip install -e .

cp .env.sample .env
```

An editable install is required. `uv sync` alone does not install the `terminus` command from your local checkout.

Add at least one provider key to `.env`:

```dotenv
# Default provider
OPEN_ROUTER_API_KEY=your_openrouter_api_key
```

> **Important:** Use the underscored `OPEN_ROUTER_API_KEY`. The current `.env.sample` uses `OPENROUTER_API_KEY`, but the OpenRouter provider and the `/connect` command read `OPEN_ROUTER_API_KEY`.

Then run Terminus from the project you want to work on:

```bash
cd /path/to/your/project
terminus
```

## Usage

### Interactive mode

Run `terminus` without a query to open the interactive interface:

```bash
terminus
```

Example prompts:

```text
Explain how authentication works in this repository.
Find the cause of the failing request and fix it.
Add validation to the settings endpoint and run the relevant checks.
Review the current changes for regressions.
```

### One-shot mode

Pass a query as an argument to complete a single task and exit:

```bash
terminus "Summarize this codebase"
terminus "Find unused imports under src"
terminus "Explain the request flow in @src/terminus/__main__.py"
```

You can also use the module entry point:

```bash
uv run python -m terminus "Explain the project architecture"
```

### File references

Prefix a relative path with `@` to load its contents into your request:

```text
Explain @src/terminus/agent/core.py
Compare @src/terminus/llm/service.py and @src/terminus/llm/openrouter.py
Update error handling in @src/terminus/agent/core.py
```

Missing or unreadable references are reported as warnings. File references are resolved from the directory Terminus was started in.

## Commands

These commands are available in interactive mode:

| Command | What it does |
| --- | --- |
| `/help` | Show the command reference. |
| `/context` | Print the current in-memory conversation context. |
| `/history` | Show the five most recent session messages. |
| `/context_size` | Show the current estimated context size. |
| `/compact` | Summarize long conversations and reduce context usage. |
| `/reset` | Clear the current session and start fresh. |
| `/clear` | Clear and redraw the terminal interface. |
| `/models` | Open the model picker and switch the active model and provider. |
| `/connect` | Save the OpenRouter API key to your user-level `~/.terminus/.env`. |
| `/copy` | Copy the last assistant response to the system clipboard. |
| `/skills` | List skills discovered in the project and built-in `.skills/` directories. |
| `/skill [name]` | Pick or load a skill into the current conversation. |
| `/init` | Generate or update the `AGENTS.md` guide for the current project. |
| `/mission <goal>` | Run a durable Scout, Worker, and Verifier mission. Use `/mission list` to inspect saved mission state. |
| `/exit` | Exit Terminus. `exit`, `quit`, and `q` are also accepted. |

Unknown slash commands show an error. The UI also suggests commands as you type.

## Built-in agent tools

| Capability | Tools and behavior |
| --- | --- |
| Browse the project | List directories and find files via the bash tool (`ls`, `rg --files`). |
| Search code | Search file contents via the bash tool with ripgrep (`rg`). |
| Read files | Read entire files or selected line ranges. |
| Modify files | Create new files and apply targeted edits to existing files. |
| Run commands | Execute shell commands in the project with cancellation support. |
| Use a sandbox | Run isolated tasks through Daytona when configured. |
| Search the web | Query Tavily when `TAVILY_API_KEY` is configured. |
| Track work | Create, read, and update structured todo lists during a task. |
| Ask questions | Pause to request information when a decision needs user input. |
| Delegate | Spawn focused subagents for a bounded part of a task. |
| Load skills | Discover and inject a selected `SKILL.md` into the conversation. |

The shell tool is instructed to refuse destructive commands and package installs without explicit user confirmation. Its commands have a 30-second default timeout and a 120-second maximum. The Daytona tool executes code in a separate cloud sandbox.

## Model providers

Terminus currently registers one provider:

| Provider | Environment variable | Notes |
| --- | --- | --- |
| OpenRouter | `OPEN_ROUTER_API_KEY` | Default provider. Provides access to the models listed in the model picker. |

Use `/connect` to save a key to your user-level `~/.terminus/.env`, then `/models` to pick a model. Gemini-branded and other third-party models may be available through OpenRouter, but there is no direct Gemini provider in the codebase.

## Configuration

Terminus loads environment variables from `~/.terminus/.env` (user-level, set via `/connect`) and then from the project's `.env`:

```dotenv
OPEN_ROUTER_API_KEY=your_openrouter_api_key

# Optional web search
TAVILY_API_KEY=your_tavily_api_key

# Optional Daytona sandbox
DAYTONA_API_KEY=your_daytona_api_key
```

### Project instructions

Terminus can include repository guidance in its system prompt:

- `AGENTS.md` provides official build steps, architecture notes, conventions, and agent instructions. Terminus looks for it in the project root and its parent directories.

Run `/init` to have Terminus generate or update an `AGENTS.md` by inspecting the current repository.

### Skills

Skills are reusable instructions stored in the current project's `.skills/` directory or in Terminus's own `.skills/` directory. Each skill is defined by a `SKILL.md` file with YAML frontmatter containing its name, description, and trigger.

```text
.skills/
└── security-review/
    └── SKILL.md
```

Use `/skills` to list discovered skills and `/skill security-review` to load one into the current conversation.

## Sessions and context

Terminus stores chat history in `~/.terminus/chat_history.db` using SQLite. The active session is also kept in memory for fast access.

To keep long-running tasks within the model's context window:

- Raw tool output is trimmed once usage reaches 50%;
- automatic conversation compaction kicks in at 75%;
- `/compact` compacts the conversation manually;
- `/reset` clears the active session and starts fresh.

These limits are based on the declared context size of the selected model.

## Architecture

```text
terminus-cli/
├── src/
│   └── terminus/
│       ├── agent/           # Agent loop, responses, and tool execution
│       ├── cli/             # CLI controller and terminal helpers
│       ├── commands/        # Interactive command registry
│       ├── llm/             # OpenRouter provider, models, and service
│       ├── mission/         # Mission orchestration and durable state
│       ├── prompts/         # Agent, init, and compaction prompts
│       ├── tools/           # Built-in agent tools
│       ├── context.py       # Context measurement and compaction
│       └── session.py       # SQLite-backed conversation history
├── rich_ui/                 # Rich terminal UI (display + mission board)
├── ui/                      # Shared theme tokens
├── tests/                   # Python tests
├── pyproject.toml           # Package metadata and Python dependencies
└── uv.lock                  # Reproducible Python dependency lockfile
```

The CLI renders with Rich (`rich_ui/RichDisplay`). Theme colors and helpers live under `ui/theme.py`.

## Development

Set up an editable development environment:

```bash
uv sync
uv pip install -e .
```

Run the application:

```bash
terminus
terminus "explain the codebase"
uv run python -m terminus
```

Lint the Python code:

```bash
uv run ruff check src/
uv run ruff format --check src/
```

Run tests:

```bash
uv run python tests/test_ask_question.py
uv run python tests/test_bash.py
uv run python tests/test_skills.py
```

Additional tests are available in `tests/`. Some require provider keys or a working terminal environment.

### Adding a tool

1. Add a `ToolSchema` implementation under `src/terminus/tools/`.
2. Export it from `src/terminus/tools/__init__.py`.
3. Register it in `ALL_TOOL_CLASSES` in `src/terminus/tools/tool_registry.py`.
4. Update the prompts and documentation when the user-facing behavior changes.

## Contributing

Contributions are welcome. Before opening a pull request:

1. Fork the repository and create a focused branch.
2. Keep changes small and consistent with the existing architecture.
3. Run the relevant Python checks.
4. Update user-facing documentation for behavior changes.
5. Describe the issue, approach, and how you verified the result in the pull request.

Use [GitHub Issues](https://github.com/sidmanale643/terminus-cli/issues) for bug reports and feature requests.

## License

This repository does not currently include a license file. Until a license is added, copyright law reserves reuse and redistribution rights to the repository owner. If you maintain this project and intend to make it openly reusable, add an OSI-approved license such as MIT, Apache-2.0, or GPL-3.0.

## Support

- Run `/help` inside Terminus for the command reference.
- Search or open an issue on [GitHub Issues](https://github.com/sidmanale643/terminus-cli/issues).
- When reporting a bug, include your Python version, provider, selected model, and a minimal reproduction.
