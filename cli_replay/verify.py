"""Verify processed recordings via tmux headless playback."""

from __future__ import annotations

import re
import shutil
import time

from cli_replay.process import is_in_cc_range
from cli_replay.redact import build_replacements
from cli_replay.session import read_header
from cli_replay.tmux import capture_pane, kill_session, start_session

_SESSION_NAME = "clirec-verify"
_SNAPSHOT_INTERVAL = 2.0
_CC_SNAPSHOT_INTERVAL = 0.04
_DA_RESPONSE_RE = re.compile(r"\^\[\[[\?0-9;]*c")


def _check_snapshot(
    snapshot_num: int,
    pane: str,
    pii: list[re.Pattern[str]],
    *,
    real_time: float = 0.0,
    speed: int = 50,
    cc_ranges: list[tuple[float, float]] | None = None,
) -> list[str]:
    """Check a single tmux snapshot for issues."""
    failures: list[str] = []
    if _DA_RESPONSE_RE.search(pane):
        failures.append(f"snapshot {snapshot_num}: DA response garbage detected")
    # PII check only applies to shell sections — CC sections are raw
    in_cc = cc_ranges and is_in_cc_range(real_time * speed, cc_ranges or [])
    if not in_cc:
        for pat in pii:
            if pat.search(pane):
                failures.append(f"snapshot {snapshot_num}: PII found: {pat.pattern}")
    return failures


def _build_schedule(
    duration: float,
    speed: int,
    snapshots: int,
    cc_ranges: list[tuple[float, float]],
) -> list[float]:
    """Build a list of sleep intervals for snapshot scheduling.

    When cc_ranges is empty, returns ``snapshots`` uniform intervals.
    When cc_ranges is provided, uses denser intervals during CC sections
    (in real time) and the default interval during shell sections.
    """
    if not cc_ranges:
        interval = max(duration / snapshots, _SNAPSHOT_INTERVAL)
        count = max(int(duration / interval), 1)
        schedule = [interval] * count
        # Cap last interval so total does not exceed duration
        total = sum(schedule)
        if total > duration:
            schedule[-1] -= total - duration
        return schedule

    shell_interval = max(duration / snapshots, _SNAPSHOT_INTERVAL)
    real_ranges = sorted((s / speed, e / speed) for s, e in cc_ranges)

    schedule: list[float] = []
    t = 0.0
    while t < duration:
        in_cc = any(s <= t < e for s, e in real_ranges)
        step = _CC_SNAPSHOT_INTERVAL if in_cc else shell_interval
        step = min(step, duration - t)
        if step <= 0:
            break
        schedule.append(step)
        t += step

    return schedule


def _run_snapshots(
    schedule: list[float],
    pii: list[re.Pattern[str]],
    speed: int,
    cc_ranges: list[tuple[float, float]],
) -> list[str]:
    """Execute snapshot schedule and check each capture."""
    failures: list[str] = []
    elapsed = 0.0
    for i, interval in enumerate(schedule):
        time.sleep(interval)
        elapsed += interval
        failures.extend(
            _check_snapshot(
                i + 1,
                capture_pane(_SESSION_NAME),
                pii,
                real_time=elapsed,
                speed=speed,
                cc_ranges=cc_ranges,
            )
        )
    return failures


def verify_recording(
    filepath: str,
    *,
    speed: int = 50,
    duration: float = 0,
    snapshots: int = 5,
    cc_ranges: list[tuple[float, float]] | None = None,
) -> list[str]:
    """Play a recording in tmux and check snapshots for issues.

    Returns a list of failure messages. Empty list means all checks passed.
    """
    if not shutil.which("tmux"):
        return ["tmux not found — cannot verify rendering"]

    with open(filepath) as f:
        header = read_header(f)

    kill_session(_SESSION_NAME)
    pii = [pattern for pattern, _repl in build_replacements()]
    ranges = cc_ranges or []

    try:
        start_session(
            _SESSION_NAME,
            header.get("width", 80),
            header.get("height", 24),
            filepath,
            speed,
        )
        if duration <= 0:
            from cli_replay.export import compute_duration

            duration = compute_duration(filepath, speed=float(speed))

        schedule = _build_schedule(duration, speed, snapshots, ranges)
        return _run_snapshots(schedule, pii, speed, ranges)
    finally:
        kill_session(_SESSION_NAME)
