"""Small, platform-specific terminal helpers.

Mouse handling is intentionally aligned with the previous React/Ink UI
(``ui/react/src/mouse.ts``): same enable modes, SGR + legacy parsers, and the
rule that mouse frames never become typed input.
"""

import re
import shutil
import subprocess
import sys
from collections.abc import Callable

# Match React ``enableSgrMouseReporting``:
#   1000 = button tracking, 1002 = button-event tracking, 1006 = SGR coords.
MOUSE_REPORTING_ON = "\x1b[?1000h\x1b[?1002h\x1b[?1006h"
MOUSE_REPORTING_OFF = "\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l"

# React ``TRANSCRIPT_WHEEL_ROWS``.
_SCROLL_STEP = 2
# React ``scrollButtonStart``.
_WHEEL_BUTTON_MIN = 64

# Residual sequences that can still appear if a previous process left mouse
# reporting on, or if a partial CSI was dropped mid-stream.
_SGR_MOUSE_FRAGMENT = re.compile(r"\x1b?\[?<\d+;\d+;\d+[Mm]")
_LEGACY_MOUSE_CHUNK = re.compile(r"\x1b\[M...", re.DOTALL)
_CSI_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC_SEQUENCE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")


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
    """Remove control / mouse sequences that can arrive from the terminal.

    Mirrors React ``isSgrMouseInput`` stripping: full SGR frames, legacy X10
    frames, and orphan CSI tails after a dropped ESC.
    """
    text = _LEGACY_MOUSE_CHUNK.sub("", text)
    text = _SGR_MOUSE_FRAGMENT.sub("", text)
    text = _CSI_SEQUENCE.sub("", text)
    text = _OSC_SEQUENCE.sub("", text)
    return "".join(
        character for character in text if character in "\n\t" or ord(character) >= 32
    )


def is_wheel_button(button: int) -> bool:
    """React ``isWheelButton`` — any button code >= 64 is a wheel event."""
    return button >= _WHEEL_BUTTON_MIN


def wheel_direction_delta(button: int) -> int:
    """React ``wheelDirection``: even button → up (+), odd → down (−)."""
    if not is_wheel_button(button):
        return 0
    # (button & 1) === 0 → up; else down.
    return _SCROLL_STEP if (button & 1) == 0 else -_SCROLL_STEP


def terminal_scroll_delta(sequence: bytes, page_rows: int = 10) -> int:
    """Translate a CSI mouse-wheel, arrow, or paging sequence into viewport rows.

    Positive delta scrolls into older transcript history; negative returns toward
    the live edge.

    SGR / legacy button decoding matches React ``parseSgrMouseWheel``:
    only press events (``M``), button >= 64, direction from the low bit.
    """
    if sequence in (b"[A", b"OA"):
        return _SCROLL_STEP
    if sequence in (b"[B", b"OB"):
        return -_SCROLL_STEP
    if sequence == b"[5~":
        return max(1, page_rows)
    if sequence == b"[6~":
        return -max(1, page_rows)

    # SGR mouse: CSI < button ; x ; y M  (press only — React ignores ``m``)
    match = re.fullmatch(rb"\[<(\d+);(\d+);(\d+)M", sequence)
    if match:
        return wheel_direction_delta(int(match.group(1)))

    # urxvt / mode-1015 style: CSI button ; x ; y M
    match = re.fullmatch(rb"\[(\d+);\d+;\d+M", sequence)
    if match:
        return wheel_direction_delta(int(match.group(1)))

    return 0


def legacy_mouse_scroll_delta(payload: bytes) -> int:
    """Translate the 3-byte X10/legacy mouse payload (React ``parseLegacyMouseWheel``)."""
    if len(payload) < 1:
        return 0
    return wheel_direction_delta(payload[0] - 32)


def read_terminal_line(
    on_change: Callable[[str], None] | None = None,
    on_scroll: Callable[[int], None] | None = None,
) -> str:
    """Read one POSIX terminal line without echoing terminal control sequences.

    Behavior matches the React UI contract:

    * When ``on_scroll`` is set, enable the same SGR mouse modes React used so
      trackpad / wheel events arrive as parseable CSI instead of raw junk.
    * Every mouse frame (SGR + legacy X10) is consumed and never becomes typed
      text — the React equivalent of ``if (isSgrMouseInput(input)) return``.
    * Wheel presses drive ``on_scroll``; clicks and releases are swallowed.
    """
    if not sys.stdin.isatty() or not sys.stdout.isatty() or sys.platform == "win32":
        return input()

    import codecs
    import os
    import select
    import termios
    import time

    input_fd = sys.stdin.fileno()
    output = sys.stdout
    original = termios.tcgetattr(input_fd)
    attributes = termios.tcgetattr(input_fd)
    attributes[3] &= ~(termios.ICANON | termios.ECHO)
    attributes[6][termios.VMIN] = 1
    attributes[6][termios.VTIME] = 0
    decoder = codecs.getincrementaldecoder(sys.stdin.encoding or "utf-8")(
        errors="replace"
    )
    characters: list[str] = []
    echo_input = on_change is None
    # Composer wants scroll; menu prompts keep native terminal selection.
    track_mouse = on_scroll is not None

    def publish() -> None:
        if on_change is not None:
            on_change("".join(characters))

    def read_bytes(count: int, timeout: float = 0.05) -> bytes:
        """Read up to ``count`` bytes, waiting at most ``timeout`` seconds total."""
        collected = bytearray()
        deadline = time.monotonic() + timeout
        while len(collected) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not select.select([input_fd], [], [], remaining)[0]:
                break
            chunk = os.read(input_fd, count - len(collected))
            if not chunk:
                break
            collected.extend(chunk)
        return bytes(collected)

    def consume_escape_sequence() -> bytes:
        sequence = bytearray()
        # Slightly longer window once we know this is a CSI (``[``) so a slow
        # terminal does not split an SGR mouse frame across the timeout and
        # dump the tail into the character buffer.
        deadline = time.monotonic() + 0.05
        while len(sequence) < 128:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([input_fd], [], [], remaining)[0]:
                return bytes(sequence)
            byte = os.read(input_fd, 1)
            if not byte:
                return bytes(sequence)
            sequence.extend(byte)
            first = sequence[0]
            last = sequence[-1]
            if first == ord("["):
                if len(sequence) == 1:
                    deadline = time.monotonic() + 0.12
                if len(sequence) > 1 and 0x40 <= last <= 0x7E:
                    return bytes(sequence)
                continue
            if first == ord("O") and len(sequence) >= 2:
                return bytes(sequence)
            if first == ord("]") and (last == 0x07 or sequence.endswith(b"\x1b\\")):
                return bytes(sequence)
            if first not in (ord("["), ord("O"), ord("]")):
                return bytes(sequence)
        return bytes(sequence)

    def handle_scroll(delta: int) -> None:
        if delta and on_scroll is not None:
            on_scroll(delta)

    try:
        termios.tcsetattr(input_fd, termios.TCSADRAIN, attributes)
        if track_mouse:
            output.write(MOUSE_REPORTING_ON)
        else:
            output.write(MOUSE_REPORTING_OFF)
        output.flush()
        publish()
        while True:
            byte = os.read(input_fd, 1)
            if not byte:
                raise EOFError
            value = byte[0]
            if value in (10, 13):
                if echo_input:
                    output.write("\r\n")
                    output.flush()
                return "".join(characters)
            if value == 27:
                sequence = consume_escape_sequence()
                # Legacy X10 mouse: ESC [ M Cb Cx Cy — React ``legacyMousePattern``.
                # The three payload bytes are printable and must never reach the
                # composer (this was the main trackpad spam source).
                if sequence == b"[M":
                    payload = read_bytes(3, timeout=0.12)
                    handle_scroll(legacy_mouse_scroll_delta(payload))
                    continue
                # SGR / arrows / paging / any other CSI: never typed.
                handle_scroll(terminal_scroll_delta(sequence))
                continue
            if value in (8, 127):
                if characters:
                    characters.pop()
                    if echo_input:
                        output.write("\b \b")
                        output.flush()
                    publish()
                continue
            if value == 4:
                if not characters:
                    raise EOFError
                continue
            if value == 21:
                if echo_input and characters:
                    output.write("\b \b" * len(characters))
                    output.flush()
                characters.clear()
                publish()
                continue
            # Drop other C0 controls (except those handled above).
            if value < 32:
                continue
            decoded = decoder.decode(byte)
            if decoded and all(ord(character) >= 32 for character in decoded):
                characters.extend(decoded)
                if echo_input:
                    output.write(decoded)
                    output.flush()
                publish()
    finally:
        output.write(MOUSE_REPORTING_OFF)
        output.flush()
        termios.tcsetattr(input_fd, termios.TCSADRAIN, original)
