"""Detect Claude Code session ranges in .clirec recordings."""

from __future__ import annotations

from cli_replay.session import ANSI_RE, EVENT_OUTPUT, iter_events, read_header

START_MARKER = "Launching Claude Code"
END_MARKER = "Resume this session"


def detect_cc_ranges(filepath: str) -> list[tuple[float, float]]:
    """Scan a .clirec file and return time ranges of Claude Code sessions.

    Each range is a (start_t, end_t) tuple. An unclosed session uses
    the last event's timestamp as its end.
    """
    starts: list[float] = []
    ends: list[float] = []
    last_t = 0.0

    with open(filepath) as f:
        read_header(f)
        for event in iter_events(f):
            last_t = event["t"]
            if event["type"] != EVENT_OUTPUT:
                continue
            visible = ANSI_RE.sub("", event["data"])
            if START_MARKER in visible:
                starts.append(event["t"])
            elif END_MARKER in visible:
                ends.append(event["t"])

    return _pair_ranges(starts, ends, last_t)


def _pair_ranges(
    starts: list[float], ends: list[float], last_t: float
) -> list[tuple[float, float]]:
    """Pair start/end markers into ranges, closing unclosed sessions."""
    ranges: list[tuple[float, float]] = []
    for i, start in enumerate(starts):
        if i < len(ends):
            ranges.append((start, ends[i]))
        else:
            ranges.append((start, last_t))
    return ranges
