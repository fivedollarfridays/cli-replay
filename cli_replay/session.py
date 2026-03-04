"""Read/write .clirec session format (JSON Lines)."""

from __future__ import annotations

import json
from typing import IO, Any, Iterator, TypedDict


SUPPORTED_VERSION = 1
EVENT_INPUT = "i"
EVENT_OUTPUT = "o"
VALID_EVENT_TYPES = (EVENT_INPUT, EVENT_OUTPUT)


class SessionHeader(TypedDict):
    version: int
    timestamp: str
    width: int
    height: int


class SessionEvent(TypedDict):
    t: float
    type: str
    data: str


def validate_header(data: dict[str, Any]) -> SessionHeader:
    """Validate and return a session header dict."""
    for field in ("version", "timestamp", "width", "height"):
        if field not in data:
            raise ValueError(f"missing required header field: {field}")
    if data["version"] != SUPPORTED_VERSION:
        raise ValueError(
            f"unsupported version: {data['version']} (expected {SUPPORTED_VERSION})"
        )
    return SessionHeader(
        version=data["version"],
        timestamp=data["timestamp"],
        width=data["width"],
        height=data["height"],
    )


def validate_event(data: dict[str, Any]) -> SessionEvent:
    """Validate and return a session event dict."""
    for field in ("t", "type", "data"):
        if field not in data:
            raise ValueError(f"missing required event field: {field}")
    if data["type"] not in VALID_EVENT_TYPES:
        raise ValueError(
            f"invalid event type: {data['type']!r} (expected one of {VALID_EVENT_TYPES})"
        )
    return SessionEvent(t=data["t"], type=data["type"], data=data["data"])


def write_header(f: IO[str], header: SessionHeader) -> None:
    """Write session header as a JSON line."""
    f.write(json.dumps(header) + "\n")


def write_event(f: IO[str], event: SessionEvent) -> None:
    """Write a session event as a JSON line."""
    f.write(json.dumps(event) + "\n")


def read_header(f: IO[str]) -> SessionHeader:
    """Read and validate the header from the first line of a .clirec file."""
    line = f.readline()
    if not line.strip():
        raise ValueError("empty or missing header: file appears empty")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON in header: {e}") from e
    return validate_header(data)


def iter_events(f: IO[str]) -> Iterator[SessionEvent]:
    """Yield validated session events from remaining lines of a .clirec file."""
    for line in f:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON in event: {e}") from e
        yield validate_event(data)
