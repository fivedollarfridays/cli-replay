"""Parse and feed scripted commands for automated recording."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from cli_replay.session import ANSI_RE


@dataclass
class TypeCommand:
    """A command line to type character by character."""

    text: str


@dataclass
class WaitDirective:
    """Pause for a number of seconds."""

    seconds: float


@dataclass
class KeyDirective:
    """Send a special key."""

    key_name: str


@dataclass
class SpeedDirective:
    """Set keystroke delay in milliseconds."""

    ms: int


@dataclass
class PauseDirective:
    """Set inter-command pause in seconds."""

    seconds: float


@dataclass
class WaitForDirective:
    """Wait until specific text appears in output."""

    text: str
    timeout: float = 30.0
    clear: bool = False


Directive = (
    TypeCommand
    | WaitDirective
    | KeyDirective
    | SpeedDirective
    | PauseDirective
    | WaitForDirective
)


class OutputBuffer:
    """Thread-safe buffer for observing shell output."""

    def __init__(self) -> None:
        self._buf: str = ""
        self._lock = threading.Lock()
        self._event = threading.Event()
        self.stop = threading.Event()

    def append(self, text: str) -> None:
        """Append text to the buffer (called from main thread)."""
        with self._lock:
            self._buf += text
        self._event.set()

    def contains(self, text: str) -> bool:
        """Check if buffer contains the given text (ANSI-stripped)."""
        with self._lock:
            clean = ANSI_RE.sub("", self._buf)
            return text in clean

    def clear(self) -> None:
        """Clear the buffer."""
        with self._lock:
            self._buf = ""
        self._event.clear()

    def wait_for(self, text: str, timeout: float = 30.0) -> bool:
        """Block until text appears in buffer or timeout. Returns True if found."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.stop.is_set():
                return False
            if self.contains(text):
                return True
            self._event.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:  # pragma: no cover
                break
            self._event.wait(timeout=min(remaining, 0.25))
        return self.contains(text)


KEY_MAP: dict[str, bytes] = {
    "ctrl-c": b"\x03",
    "ctrl-d": b"\x04",
    "enter": b"\r",
    "tab": b"\t",
}


def _strip_inline_comment(line: str) -> str:
    """Remove trailing inline comment from a line."""
    idx = line.find("  #")
    if idx >= 0:
        return line[:idx].rstrip()
    return line


def _parse_line(line: str) -> Directive:
    """Parse a single script line into a directive."""
    if line.startswith("@"):
        parts = line.split(None, 1)
        directive_name = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if directive_name in ("@wait-for", "@wait-for!"):
            clear = directive_name.endswith("!")
            parts_quoted = arg.split('"')
            if len(parts_quoted) < 3:
                raise ValueError('@wait-for requires quoted text: @wait-for "text"')
            text = parts_quoted[1]
            rest = parts_quoted[2].strip()
            timeout = float(rest) if rest else 30.0
            return WaitForDirective(text=text, timeout=timeout, clear=clear)
        if directive_name == "@wait":
            return WaitDirective(seconds=float(arg))
        if directive_name == "@key":
            key = arg.strip()
            if key not in KEY_MAP:
                raise ValueError(f"unknown key: {key!r}")
            return KeyDirective(key_name=key)
        if directive_name == "@speed":
            return SpeedDirective(ms=int(arg))
        if directive_name == "@pause":
            return PauseDirective(seconds=float(arg))
        raise ValueError(f"unknown directive: {directive_name!r}")
    return TypeCommand(text=_strip_inline_comment(line))


EventWriter = Callable[[float, str], None]

DEFAULT_KEYSTROKE_MS = 50
DEFAULT_PAUSE = 0.5


def _write_char(
    char: str,
    master_fd: int,
    event_writer: EventWriter,
    start_time: float,
) -> None:
    """Write a single character to the pty and log it."""
    os.write(master_fd, char.encode("utf-8"))
    t = round(time.monotonic() - start_time, 3)
    event_writer(t, char)


def _is_stopped(output_buffer: OutputBuffer | None) -> bool:
    """Check if the stop flag is set."""
    return output_buffer is not None and output_buffer.stop.is_set()


def _interruptible_sleep(seconds: float, output_buffer: OutputBuffer | None) -> None:
    """Sleep that exits early if stop is set."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _is_stopped(output_buffer):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:  # pragma: no cover
            return
        time.sleep(min(remaining, 0.1))


def feed_script(
    directives: list[Directive],
    master_fd: int,
    event_writer: EventWriter,
    start_time: float,
    keystroke_delay_ms: int = DEFAULT_KEYSTROKE_MS,
    inter_command_pause: float = DEFAULT_PAUSE,
    output_buffer: OutputBuffer | None = None,
) -> None:
    """Execute directives by writing to master_fd with realistic timing."""
    delay_s = keystroke_delay_ms / 1000.0

    for directive in directives:
        if _is_stopped(output_buffer):
            return
        if isinstance(directive, TypeCommand):
            for char in directive.text:
                if _is_stopped(output_buffer):
                    return
                _write_char(char, master_fd, event_writer, start_time)
                time.sleep(delay_s)
            _write_char("\r", master_fd, event_writer, start_time)
            _interruptible_sleep(inter_command_pause, output_buffer)
        elif isinstance(directive, WaitDirective):
            _interruptible_sleep(directive.seconds, output_buffer)
        elif isinstance(directive, WaitForDirective):
            if output_buffer:
                if directive.clear:
                    output_buffer.clear()
                output_buffer.wait_for(directive.text, directive.timeout)
        elif isinstance(directive, KeyDirective):
            key_bytes = KEY_MAP[directive.key_name]
            char = key_bytes.decode("utf-8", errors="replace")
            _write_char(char, master_fd, event_writer, start_time)
        elif isinstance(directive, SpeedDirective):
            delay_s = directive.ms / 1000.0
        elif isinstance(directive, PauseDirective):
            inter_command_pause = directive.seconds


def parse_script(path: str) -> list[Directive]:
    """Parse a script file into a list of directives."""
    directives: list[Directive] = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            directives.append(_parse_line(stripped))
    return directives
