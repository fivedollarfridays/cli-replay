"""Compare two recordings via tmux snapshot diffs."""

from __future__ import annotations

import time
from dataclasses import dataclass

from cli_replay.export import compute_duration
from cli_replay.session import read_header
from cli_replay.tmux import capture_pane, kill_session, start_session


@dataclass
class CompareResult:
    """Result of comparing two recordings."""

    matching: int
    differing: int
    diffs: list[tuple[float, str, str]]  # (timestamp, pane1, pane2)

    @property
    def matched(self) -> bool:
        """True when all snapshots match."""
        return self.differing == 0


def _play_and_capture(
    session: str,
    filepath: str,
    width: int,
    height: int,
    speed: int,
    timestamps: list[float],
) -> list[str]:
    """Play a recording in tmux and capture panes at given timestamps."""
    kill_session(session)
    captures: list[str] = []
    try:
        start_session(session, width, height, filepath, speed)
        for ts in timestamps:
            time.sleep(ts)
            captures.append(capture_pane(session))
    finally:
        kill_session(session)
    return captures


def _compute_timestamps(duration: float, snapshots: int) -> list[float]:
    """Compute evenly spaced sleep intervals for snapshots."""
    interval = max(duration / snapshots, 0.1)
    return [interval] * snapshots


def compare_recordings(
    file1: str,
    file2: str,
    *,
    snapshots: int = 5,
    speed: int = 50,
) -> CompareResult:
    """Compare two recordings via tmux snapshot diffs.

    Recordings are played back sequentially (not simultaneously) in
    separate tmux sessions, and pane snapshots are compared pairwise.
    """
    with open(file1) as f:
        h1 = read_header(f)
    with open(file2) as f:
        h2 = read_header(f)

    if h1["width"] != h2["width"] or h1["height"] != h2["height"]:
        raise ValueError(
            f"Dimensions mismatch: {h1['width']}x{h1['height']} "
            f"vs {h2['width']}x{h2['height']}"
        )

    width, height = h1["width"], h1["height"]
    dur1 = compute_duration(file1, speed=float(speed))
    dur2 = compute_duration(file2, speed=float(speed))
    duration = min(dur1, dur2)

    timestamps = _compute_timestamps(duration, snapshots)

    caps1 = _play_and_capture("clirec-cmp-1", file1, width, height, speed, timestamps)
    caps2 = _play_and_capture("clirec-cmp-2", file2, width, height, speed, timestamps)

    matching = 0
    differing = 0
    diffs: list[tuple[float, str, str]] = []
    elapsed = 0.0
    for ts, c1, c2 in zip(timestamps, caps1, caps2):
        elapsed += ts
        if c1 == c2:
            matching += 1
        else:
            differing += 1
            diffs.append((elapsed, c1, c2))

    return CompareResult(matching=matching, differing=differing, diffs=diffs)
