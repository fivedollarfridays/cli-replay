""".clirec -> stdout with timing."""

from __future__ import annotations

import sys
import time

from cli_replay.reflow import split_lines
from cli_replay.session import EVENT_INPUT, iter_events, read_header


def _compute_delay(
    current_t: float,
    prev_t: float,
    speed: float,
    max_delay: float,
    instant: bool,
) -> float:
    """Calculate the delay before playing an event."""
    if instant:
        return 0.0
    gap = max((current_t - prev_t) / speed, 0.0)
    return min(gap, max_delay)


def _is_echo(event: dict, prev_event: dict | None, show_input: bool) -> bool:
    """Return True if this output event is just an echo of the prior input."""
    if not show_input or prev_event is None:
        return False
    if event["type"] != "o" or prev_event["type"] != EVENT_INPUT:
        return False
    return event["data"] == prev_event["data"]


def _should_skip(event_type: str, show_input: bool) -> bool:
    """Return True if this event should be skipped."""
    return not show_input and event_type == EVENT_INPUT


def _write_with_line_delay(data: str, delay_s: float) -> None:
    """Write data line-by-line with micro-delays between lines."""
    lines = split_lines(data)
    for i, line in enumerate(lines):
        if i > 0:
            time.sleep(delay_s)
        sys.stdout.write(line)
        sys.stdout.flush()


def play(
    *,
    filepath: str,
    speed: float = 1.0,
    max_delay: float = 3.0,
    show_input: bool = False,
    instant: bool = False,
    line_delay: int = 0,
) -> None:
    """Replay a .clirec session to stdout with timing."""
    line_delay_s = line_delay / 1000.0
    with open(filepath) as f:
        read_header(f)  # validate header, not used in v1
        prev_t = 0.0
        prev_event: dict | None = None
        for event in iter_events(f):
            if _should_skip(event["type"], show_input):
                continue
            if _is_echo(event, prev_event, show_input):
                prev_event = event
                continue
            delay = _compute_delay(event["t"], prev_t, speed, max_delay, instant)
            if delay > 0:
                time.sleep(delay)
            if line_delay_s > 0:
                _write_with_line_delay(event["data"], line_delay_s)
            else:
                sys.stdout.write(event["data"])
                sys.stdout.flush()
            prev_event = event
            prev_t = event["t"]
