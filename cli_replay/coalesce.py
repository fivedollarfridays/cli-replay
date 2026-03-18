"""Merge near-timestamp output events into single events."""

from __future__ import annotations

from typing import IO

from cli_replay.session import (
    EVENT_OUTPUT,
    SessionEvent,
    iter_events,
    read_header,
    write_event,
    write_header,
)


def coalesce_events(filepath: str, output: IO[str], threshold_ms: float = 5.0) -> int:
    """Merge near-timestamp output events. Returns number of merges performed."""
    threshold_s = threshold_ms / 1000.0
    merge_count = 0
    buffer_t: float = 0.0
    buffer_data: list[str] = []
    buffer_count = 0

    def flush_buffer() -> None:
        nonlocal buffer_data, buffer_count, merge_count
        if buffer_data:
            merged = "".join(buffer_data)
            write_event(
                output, SessionEvent(t=buffer_t, type=EVENT_OUTPUT, data=merged)
            )
            if buffer_count > 1:
                merge_count += 1
            buffer_data = []
            buffer_count = 0

    with open(filepath) as f:
        header = read_header(f)
        write_header(output, header)

        for event in iter_events(f):
            if event["type"] != EVENT_OUTPUT:
                flush_buffer()
                write_event(output, event)
                continue

            if not buffer_data:
                buffer_t = event["t"]
                buffer_data = [event["data"]]
                buffer_count = 1
            # Compare against burst start time (not previous event) —
            # all events within the burst window merge into one.
            elif event["t"] - buffer_t <= threshold_s:
                buffer_data.append(event["data"])
                buffer_count += 1
            else:
                flush_buffer()
                buffer_t = event["t"]
                buffer_data = [event["data"]]
                buffer_count = 1

        flush_buffer()

    return merge_count
