"""Split multi-line events into per-line events with interpolated timestamps."""

from __future__ import annotations

from typing import IO, Iterator

from cli_replay.session import (
    SessionEvent,
    iter_events,
    read_header,
    write_event,
    write_header,
)


def split_lines(data: str) -> list[str]:
    """Split data on newline boundaries, preserving delimiters."""
    if not data:
        return []
    parts = data.split("\n")
    result: list[str] = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            result.append(part + "\n")
        elif part:
            result.append(part)
    return result


def split_event(event: SessionEvent, delay_s: float) -> list[SessionEvent]:
    """Split a multi-line event into per-line events with interpolated timestamps."""
    lines = split_lines(event["data"])
    if len(lines) <= 1:
        return list(
            SessionEvent(t=event["t"], type=event["type"], data=line) for line in lines
        )
    return [
        SessionEvent(
            t=round(event["t"] + i * delay_s, 3),
            type=event["type"],
            data=line,
        )
        for i, line in enumerate(lines)
    ]


def iter_reflowed_events(
    events: Iterator[SessionEvent], delay_s: float
) -> Iterator[SessionEvent]:
    """Yield events with multi-line events split into per-line events."""
    for event in events:
        yield from split_event(event, delay_s)


def reflow(*, filepath: str, output: IO[str], delay_ms: int) -> None:
    """Read a .clirec file and write a reflowed version."""
    delay_s = delay_ms / 1000.0
    with open(filepath) as f:
        header = read_header(f)
        write_header(output, header)
        for event in iter_reflowed_events(iter_events(f), delay_s):
            write_event(output, event)
