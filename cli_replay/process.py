"""Process recordings with hybrid shell/CC stitching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import IO

import yaml

from cli_replay.redact import build_replacements, redact_event
from cli_replay.session import (
    DA_QUERY_RE,
    SessionEvent,
    iter_events,
    read_header,
    write_event,
    write_header,
)


@dataclass
class ProcessConfig:
    """Configuration for processing a recording."""

    input_path: str
    output_path: str
    cc_ranges: list[tuple[float, float]]
    cc_version: str | None = None


def load_config(path: str) -> ProcessConfig:
    """Read a YAML config file and return a ProcessConfig."""
    with open(path) as f:
        data = yaml.safe_load(f)

    if "input" not in data:
        msg = "Config missing required key: 'input'"
        raise ValueError(msg)
    if "output" not in data:
        msg = "Config missing required key: 'output'"
        raise ValueError(msg)

    raw_ranges = data.get("cc_ranges", [])
    cc_ranges: list[tuple[float, float]] = []
    for entry in raw_ranges:
        if not isinstance(entry, list) or len(entry) != 2:
            msg = f"Each cc_ranges entry must be a 2-element list, got: {entry}"
            raise ValueError(msg)
        cc_ranges.append((float(entry[0]), float(entry[1])))

    return ProcessConfig(
        input_path=data["input"],
        output_path=data["output"],
        cc_ranges=cc_ranges,
        cc_version=data.get("cc_version"),
    )


def is_in_cc_range(t: float, cc_ranges: list[tuple[float, float]]) -> bool:
    """Return True if timestamp t falls within any CC range (inclusive)."""
    return any(start <= t <= end for start, end in cc_ranges)


def _process_shell_event(
    event: SessionEvent,
    replacements: list[tuple[re.Pattern[str], str]],
) -> SessionEvent:
    """Process a shell-section event: PII redact only."""
    return redact_event(event, replacements)


def process_recording(
    filepath: str,
    config: ProcessConfig,
    output: IO[str],
) -> None:
    """Read a recording and write a processed version with hybrid shell/CC stitching."""
    replacements = build_replacements()
    with open(filepath) as f:
        header = read_header(f)
        write_header(output, header)
        for event in iter_events(f):
            if is_in_cc_range(event["t"], config.cc_ranges):
                # CC: strip DA queries only, everything else raw
                if event["type"] == "o" and DA_QUERY_RE.search(event["data"]):
                    event = SessionEvent(
                        t=event["t"],
                        type=event["type"],
                        data=DA_QUERY_RE.sub("", event["data"]),
                    )
                write_event(output, event)
            else:
                write_event(output, _process_shell_event(event, replacements))
