"""Compatibility entry point for the Terminus CLI."""

from src.cli.application import TerminusCLI, main

__all__ = ["TerminusCLI", "main"]


if __name__ == "__main__":
    main()
