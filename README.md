![Terminus CLI](assets/image.png)

# Terminus CLI

AI-powered CLI agent with intelligent automation for coding tasks, file operations, and web search.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg) ![License](https://img.shields.io/badge/license-MIT-green.svg)

## Quick Start

```bash
git clone https://github.com/sidmanale643/terminus-cli.git
cd terminus-cli
uv venv && source .venv/bin/activate
uv pip install -r pyproject.toml
cp .env.sample .env  # Add your API keys
python main.py
```

## API Keys

Create `.env` file:
```env
GROQ_API_KEY=your_groq_key_here      # Primary LLM
GEMINI_API_KEY=your_gemini_key_here  # Alternative LLM
TAVILY_API_KEY=your_tavily_key_here # Web search
```

Get keys: [Groq](https://groq.com) [Gemini](https://makersuite.google.com/app/apikey) [Tavily](https://tavily.com)

## Usage

Interactive mode:
```bash
python main.py
```

Single query:
```bash
python main.py "List Python files in current directory"
```

Commands: `/help` `/context` `/clear` `/exit`

## Tools

- Command execution
- File operations (create, read, edit)
- Grep search
- Directory listing
- Web search
- Task management
- Sub-agent delegation

## Architecture

```
terminus-cli/
├── main.py     # CLI interface
├── agent.py    # Core agent logic
├── llm.py      # LLM integrations
├── tools/      # Tool implementations
└── prompts/    # System prompts
```

## Development

```bash
uv pip install -e ".[dev]"
python -m pytest tests/
ruff format . && ruff check .
```

## License

MIT - see [LICENSE](LICENSE) file for details.

---

**Made with love by the Terminus CLI Team**