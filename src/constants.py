import os

TERMINUS_DIR = os.path.expanduser("~/.terminus")
DEFAULT_DATABASE_DIR = TERMINUS_DIR
TODO_FILE = os.path.join(TERMINUS_DIR, "todos.json")

DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_PROVIDER = "openrouter"