"""PTY capture -> .clirec file."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime, timezone
from types import FrameType
from typing import IO, Callable

from cli_replay.session import (
    EVENT_INPUT,
    EVENT_OUTPUT,
    SUPPORTED_VERSION,
    SessionEvent,
    SessionHeader,
    write_event,
    write_header,
)


def _get_save_dir() -> str:
    """Return the default save directory for recordings."""
    return os.path.join(os.path.expanduser("~"), ".local", "share", "clirec")


def _generate_filename(output: str | None) -> str:
    """Generate a .clirec filename from user input or timestamp."""
    if output is not None:
        name = output.strip()
        if not name:
            raise ValueError("output name cannot be empty or whitespace-only")
        if not name.endswith(".clirec"):
            name += ".clirec"
        return name
    save_dir = _get_save_dir()
    os.makedirs(save_dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    return os.path.join(save_dir, now.strftime("%Y-%m-%d_%H%M%S") + ".clirec")


def _build_header() -> SessionHeader:
    """Build the session header from current terminal state."""
    try:
        size = os.get_terminal_size()
        width, height = size.columns, size.lines
    except OSError:
        width, height = 80, 24
    return SessionHeader(
        version=SUPPORTED_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        width=width,
        height=height,
    )


def _set_pty_size(fd: int, width: int, height: int) -> None:
    """Set the terminal size on a PTY file descriptor."""
    winsize = struct.pack("HHHH", height, width, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _record_loop(
    stdin_fd: int,
    master_fd: int,
    proc: subprocess.Popen[bytes],
    f: IO[str],
    start: float,
) -> int:
    """Run the select-based I/O loop. Returns event count."""
    event_count = 0
    read_fds = [stdin_fd, master_fd]

    while True:
        try:
            rlist, _, _ = select.select(read_fds, [], [], 0.25)
        except (ValueError, OSError):
            break
        if not rlist:
            if proc.poll() is not None:
                break
            continue

        t = round(time.monotonic() - start, 3)

        if stdin_fd in rlist:
            data = os.read(stdin_fd, 4096)
            if not data:
                read_fds = [master_fd]
            else:
                os.write(master_fd, data)
                text = data.decode("utf-8", errors="replace")
                write_event(f, SessionEvent(t=t, type=EVENT_INPUT, data=text))
                event_count += 1

        if master_fd in rlist:
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            os.write(sys.stdout.fileno(), data)
            text = data.decode("utf-8", errors="replace")
            write_event(f, SessionEvent(t=t, type=EVENT_OUTPUT, data=text))
            event_count += 1

    return event_count


def _print_summary(filename: str, event_count: int, duration: float) -> None:
    """Print recording summary to stderr."""
    mins, secs = divmod(int(duration), 60)
    size = os.path.getsize(filename)
    size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
    sys.stderr.write(
        f"Recorded {event_count} events, {mins}m {secs:02d}s -> {filename} ({size_str})\n"
    )
    sys.stderr.flush()


_SignalHandler = Callable[[int, FrameType | None], object] | int | None


def _install_sigwinch(master_fd: int) -> _SignalHandler:
    """Install SIGWINCH handler for PTY resize. Returns old handler."""

    def handler(signum: int, frame: FrameType | None) -> None:
        try:
            size = os.get_terminal_size()
            _set_pty_size(master_fd, size.columns, size.lines)
        except OSError:
            pass

    return signal.signal(signal.SIGWINCH, handler)


def record(*, output: str | None = None) -> None:
    """Record a terminal session to a .clirec file."""
    filename = _generate_filename(output)
    header = _build_header()

    master_fd, slave_fd = pty.openpty()
    _set_pty_size(master_fd, header["width"], header["height"])
    old_sigwinch = _install_sigwinch(master_fd)

    shell = os.environ.get("SHELL", "/bin/sh")
    proc = subprocess.Popen(
        [shell],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    sys.stderr.write(f"Recording to {filename} (exit or Ctrl+D to stop)\n")
    sys.stderr.flush()

    stdin_fd = sys.stdin.fileno()
    is_tty = os.isatty(stdin_fd)
    old_settings = termios.tcgetattr(stdin_fd) if is_tty else None
    start = time.monotonic()

    try:
        if is_tty:
            tty.setraw(stdin_fd)
        with open(filename, "w", buffering=1) as f:
            write_header(f, header)
            event_count = _record_loop(stdin_fd, master_fd, proc, f, start)
    finally:
        signal.signal(signal.SIGWINCH, old_sigwinch)
        if old_settings is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
        os.close(master_fd)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    _print_summary(filename, event_count, time.monotonic() - start)
