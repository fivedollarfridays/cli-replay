"""Redact sensitive data from .clirec files."""

from __future__ import annotations

import os
import socket
import tempfile
from typing import IO

from cli_replay.session import (
    SessionEvent,
    iter_events,
    read_header,
    write_event,
    write_header,
)


def _build_replacements() -> list[tuple[str, str]]:
    """Detect username, hostname, home path from environment.

    Returns list of (old, new) replacement tuples ordered longest-first
    to prevent partial replacements. Skips empty/None values.
    """
    user = os.environ.get("USER") or ""
    home = os.environ.get("HOME") or ""
    hostname = socket.gethostname() or ""

    replacements: list[tuple[str, str]] = []

    # Add home path first (longest match)
    if home:
        replacements.append((home, "/home/user"))

    # Add username
    if user:
        replacements.append((user, "user"))

    # Add hostname
    if hostname:
        replacements.append((hostname, "host"))

    return replacements


def _redact_event(
    event: SessionEvent, replacements: list[tuple[str, str]]
) -> SessionEvent:
    """Apply replacements to event data field.

    Returns new SessionEvent with redacted data, preserving t and type.
    Applies replacements in order (longest-first).
    """
    redacted_data = event["data"]
    for old, new in replacements:
        redacted_data = redacted_data.replace(old, new)

    return SessionEvent(t=event["t"], type=event["type"], data=redacted_data)


def redact(*, filepath: str, output: IO[str]) -> None:
    """Read .clirec file and write redacted version to output stream.

    Detects username, hostname, and home path from environment,
    then applies replacements to all event data fields.
    Header is preserved unchanged.
    """
    replacements = _build_replacements()

    with open(filepath) as f:
        header = read_header(f)
        write_header(output, header)
        for event in iter_events(f):
            redacted = _redact_event(event, replacements)
            write_event(output, redacted)


def redact_inplace(*, filepath: str) -> None:
    """Redact a .clirec file in place using atomic write.

    Writes to a temporary file in the same directory, then renames
    over the original (atomic operation). Original is never corrupted.
    """
    # Try to open the source file first to validate readability.
    # This will raise FileNotFoundError if file doesn't exist.
    with open(filepath) as _:
        pass

    # Get directory of the original file for temp file placement
    directory = os.path.dirname(filepath) or "."

    # Create temp file in the same directory
    with tempfile.NamedTemporaryFile(
        mode="w", dir=directory, delete=False, suffix=".clirec"
    ) as tmp:
        tmp_path = tmp.name
        try:
            redact(filepath=filepath, output=tmp)
        except Exception:  # pragma: no cover
            # Clean up temp file on error
            os.unlink(tmp_path)
            raise

    # Atomic rename (on POSIX, overwrites existing file)
    os.replace(tmp_path, filepath)
