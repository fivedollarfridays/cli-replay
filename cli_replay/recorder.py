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
import threading
import time
import tty
from datetime import datetime, timezone
from types import FrameType
from typing import IO, TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from cli_replay.script_feeder import OutputBuffer

from cli_replay.session import (
    EVENT_INPUT,
    EVENT_OUTPUT,
    SUPPORTED_VERSION,
    SessionEvent,
    SessionHeader,
    write_event,
    write_header,
)


def _generate_filename(output: str | None) -> str:
    """Generate a .clirec filename from user input or timestamp."""
    if output is not None:
        name = output.strip()
        if not name:
            raise ValueError("output name cannot be empty or whitespace-only")
        if not name.endswith(".clirec"):
            name += ".clirec"
        return name
    save_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "clirec")
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


def _log_event(f: IO[str], event: SessionEvent, lock: threading.Lock | None) -> None:
    """Write an event, optionally under a lock."""
    if lock:
        with lock:
            write_event(f, event)
    else:
        write_event(f, event)


def _record_loop(
    stdin_fd: int | None,
    master_fd: int,
    proc: subprocess.Popen[bytes],
    f: IO[str],
    start: float,
    write_lock: threading.Lock | None = None,
    output_buffer: OutputBuffer | None = None,
) -> int:
    """Run the select-based I/O loop. Returns event count."""
    event_count = 0
    read_fds: list[int] = [x for x in [master_fd, stdin_fd] if x is not None]
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
        if stdin_fd is not None and stdin_fd in rlist:
            data = os.read(stdin_fd, 4096)
            if not data:
                read_fds = [master_fd]
            elif output_buffer is not None and b"\x03" in data:  # pragma: no cover
                output_buffer.stop.set()
                break
            else:
                os.write(master_fd, data)
                text = data.decode("utf-8", errors="replace")
                _log_event(
                    f, SessionEvent(t=t, type=EVENT_INPUT, data=text), write_lock
                )
                event_count += 1
        if master_fd in rlist:
            try:
                data = os.read(master_fd, 65536)
            except OSError:
                break
            # Drain burst stragglers within 5ms window (max 10 reads)
            for _ in range(10):
                if not select.select([master_fd], [], [], 0.005)[0]:
                    break
                try:
                    data += os.read(master_fd, 65536)
                except OSError:
                    break
            if not data:
                break
            os.write(sys.stdout.fileno(), data)
            text = data.decode("utf-8", errors="replace")
            _log_event(f, SessionEvent(t=t, type=EVENT_OUTPUT, data=text), write_lock)
            if output_buffer is not None:
                output_buffer.append(text)
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


def _start_script_feeder(
    script: str,
    master_fd: int,
    f: IO[str],
    start: float,
    write_lock: threading.Lock,
    output_buffer: OutputBuffer,
) -> threading.Thread:
    """Launch the script feeder in a daemon thread."""
    from cli_replay.script_feeder import feed_script, parse_script

    directives = parse_script(script)

    def event_writer(t: float, data: str) -> None:
        with write_lock:
            write_event(f, SessionEvent(t=t, type=EVENT_INPUT, data=data))

    def run() -> None:
        time.sleep(0.5)  # wait for shell to be ready
        feed_script(
            directives,
            master_fd,
            event_writer,
            start,
            output_buffer=output_buffer,
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _get_stdin() -> tuple[int | None, list[Any] | None]:
    """Get stdin fd and original terminal settings if available."""
    try:
        fd = sys.stdin.fileno()
    except (OSError, AttributeError):
        return None, None
    if os.isatty(fd):
        return fd, termios.tcgetattr(fd)
    return fd, None


def _spawn_shell(header: SessionHeader) -> tuple[int, subprocess.Popen[bytes]]:
    """Open a PTY, spawn a shell, return (master_fd, proc)."""
    master_fd, slave_fd = pty.openpty()
    _set_pty_size(master_fd, header["width"], header["height"])
    proc = subprocess.Popen(
        [os.environ.get("SHELL", "/bin/sh")],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    return master_fd, proc


def record(*, output: str | None = None, script: str | None = None) -> None:
    """Record a terminal session to a .clirec file."""
    filename = _generate_filename(output)
    header = _build_header()
    master_fd, proc = _spawn_shell(header)
    old_sigwinch = _install_sigwinch(master_fd)
    scripted = script is not None
    if scripted:
        sys.stderr.write(f"Recording (scripted) to {filename}\n")
    else:
        sys.stderr.write(f"Recording to {filename} (exit or Ctrl+D to stop)\n")
    sys.stderr.flush()

    stdin_fd, old_settings = _get_stdin()
    start = time.monotonic()
    write_lock = threading.Lock() if scripted else None
    output_buffer = None

    try:
        if old_settings and stdin_fd is not None:
            tty.setraw(stdin_fd)
        with open(filename, "w", buffering=1) as f:
            write_header(f, header)
            if scripted:
                assert script is not None and write_lock is not None
                from cli_replay.script_feeder import OutputBuffer

                output_buffer = OutputBuffer()
                _start_script_feeder(
                    script, master_fd, f, start, write_lock, output_buffer
                )
            event_count = _record_loop(
                stdin_fd, master_fd, proc, f, start, write_lock, output_buffer
            )
    except KeyboardInterrupt:  # pragma: no cover
        if output_buffer is not None:
            output_buffer.stop.set()
    finally:
        signal.signal(signal.SIGWINCH, old_sigwinch)
        if old_settings and stdin_fd is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
        os.close(master_fd)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    _print_summary(filename, event_count, time.monotonic() - start)
