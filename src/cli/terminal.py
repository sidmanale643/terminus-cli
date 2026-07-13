"""Small, platform-specific terminal helpers."""

import re
import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    """Copy text using the platform clipboard command when available."""
    if sys.platform == "darwin":
        tool = "pbcopy"
    elif sys.platform == "win32":
        tool = "clip"
    elif sys.platform == "linux":
        tool = next(
            (
                candidate
                for candidate in ("wl-copy", "xclip", "xsel")
                if shutil.which(candidate)
            ),
            None,
        )
        if tool is None:
            return False
    else:
        return False

    try:
        process = subprocess.Popen(
            [tool],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.communicate(input=text.encode("utf-8"), timeout=5)
        return process.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sanitize_terminal_input(text: str) -> str:
    """Remove control sequences that can arrive from mouse reporting."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    return "".join(
        character for character in text if character in "\n\t" or ord(character) >= 32
    )
