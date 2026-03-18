"""Shared tmux session helpers for recording playback."""

from __future__ import annotations

import shlex
import subprocess


def start_session(
    session: str, width: int, height: int, filepath: str, speed: int
) -> None:
    """Create a detached tmux session and start playback."""
    subprocess.run(
        [
            "tmux", "new-session", "-d", "-s", session,
            "-x", str(width), "-y", str(height),
        ],
        check=True,
        capture_output=True,
    )
    cmd = f"clirec play {shlex.quote(filepath)} --speed {speed}"
    subprocess.run(
        ["tmux", "send-keys", "-t", session, cmd, "Enter"],
        check=True,
        capture_output=True,
    )


def capture_pane(session: str) -> str:
    """Capture the current tmux pane content."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def kill_session(session: str) -> None:
    """Kill a tmux session if it exists."""
    subprocess.run(
        ["tmux", "kill-session", "-t", session],
        capture_output=True,
    )
