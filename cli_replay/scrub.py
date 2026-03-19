"""Scrub unwanted events from .clirec files by pattern matching."""

from __future__ import annotations

import re
from typing import IO

from cli_replay.session import (
    ANSI_RE,
    DA_QUERY_RE,
    SYNC_BEGIN,
    SYNC_FINISH,
    SessionEvent,
    iter_events,
    read_header,
    write_event,
    write_header,
)

# Match \x1b[38;5;246m followed by digits, with optional dim wrapper (\x1b[2m...\x1b[22m)
_COUNTER_RE = re.compile(r"\x1b\[38;5;246m(?:\x1b\[2m)?\d+(?:\x1b\[22m)?")

# Match bold digits inside synchronized update frames: \x1b[1m\d+
_BOLD_DIGIT_RE = re.compile(r"\x1b\[1m(\d+)")

_TITLE_RE = re.compile(r"\x1b\][^\x07]*\x07")

_CLEAN_SPINNER_RE = re.compile(
    r"^[✶✻✽✢·*●]?\s*"
    r"(?:(?:Waddling|Manifesting|Discombobulating)…?)?\s*"
    r"(?:\((?:thinking|[\ds ·↓]+tokens[^)]*)\))?\s*$"
)


def is_clean_spinner(data: str) -> bool:
    """Return True if a sync frame contains only spinner/thinking animation."""
    if SYNC_BEGIN not in data:
        return False
    visible = ANSI_RE.sub("", data).strip()
    if not visible:
        return True
    return bool(_CLEAN_SPINNER_RE.match(visible))


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_RE.sub("", text)


def scrub_data(data: str) -> str:
    """Strip colored digit counter sequences and terminal queries from event data."""
    result = _COUNTER_RE.sub("", data)
    # Strip bold digits inside synchronized update frames
    if SYNC_BEGIN in result or SYNC_FINISH in result:
        result = _BOLD_DIGIT_RE.sub("\x1b[1m", result)
    # Strip terminal queries that cause visible garbage during playback
    result = DA_QUERY_RE.sub("", result)
    # Strip terminal title updates
    result = _TITLE_RE.sub("", result)
    return result


def should_drop(event: SessionEvent, pattern: re.Pattern[str]) -> bool:
    """Return True if this event should be dropped entirely."""
    if event["type"] != "o":
        return False
    visible = strip_ansi(event["data"]).strip()
    return bool(pattern.match(visible))


def scrub(
    *,
    filepath: str,
    output: IO[str],
    pattern: str,
    from_t: float = 0,
    to_t: float = float("inf"),
) -> int:
    """Read a .clirec file and write a version with matching events removed.

    In the specified time range: events matching the pattern are dropped,
    and all synchronized update frames (TUI redraws) are also removed.
    Outside the range, terminal queries and counter digits are stripped
    from all output events.

    Returns the number of dropped events.
    """
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid regex pattern: {e}") from e
    dropped = 0
    with open(filepath) as f:
        header = read_header(f)
        write_header(output, header)
        for event in iter_events(f):
            if event["type"] != "o":
                write_event(output, event)
                continue
            in_range = from_t <= event["t"] <= to_t
            # Drop pattern-matched events
            if in_range and should_drop(event, compiled):
                dropped += 1
                continue
            # Drop sync frames in range
            if in_range and SYNC_BEGIN in event["data"]:
                dropped += 1
                continue
            # Scrub terminal queries and counter digits from all output
            cleaned_data = scrub_data(event["data"])
            if cleaned_data != event["data"]:
                event = SessionEvent(
                    t=event["t"], type=event["type"], data=cleaned_data
                )
            write_event(output, event)
    return dropped
