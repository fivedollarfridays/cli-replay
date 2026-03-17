"""Export .clirec recordings to video via VHS."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterator, NamedTuple

from cli_replay.reflow import split_lines
from cli_replay.player import _compute_delay
from cli_replay.session import (
    EVENT_INPUT,
    SessionEvent,
    iter_events,
    read_header,
)

CHAR_WIDTH_RATIO = 0.6  # monospace char width / font size
CHAR_HEIGHT_RATIO = 1.2  # monospace line height / font size
DEFAULT_SPEED = 1.0  # play subcommand default
DEFAULT_MAX_DELAY = 3.0  # play subcommand default


class MissingDependency(NamedTuple):
    name: str
    install_hint: str


def check_dependencies() -> list[MissingDependency]:
    """Check for required system binaries. Returns empty list if all present."""
    missing: list[MissingDependency] = []
    if not shutil.which("vhs"):
        missing.append(
            MissingDependency(
                "vhs",
                "Install VHS: https://github.com/charmbracelet/vhs#installation",
            )
        )
    if not shutil.which("ffmpeg"):
        missing.append(
            MissingDependency(
                "ffmpeg",
                "Install ffmpeg: https://ffmpeg.org/download.html",
            )
        )
    return missing


@dataclass
class ExportConfig:
    clirec_path: str
    output_path: str
    width: int = 80
    height: int = 24
    font_size: int = 18
    theme: str = "Catppuccin Mocha"
    speed: float = 1.0
    max_delay: float = 3.0
    line_delay: int = 0
    padding: int = 0
    duration_s: float = 10.0
    buffer_s: float = 2.0


def _chars_to_pixels(chars: int, font_size: int, ratio: float) -> int:
    return int(math.floor(chars * font_size * ratio))


def generate_tape(config: ExportConfig) -> str:
    """Generate VHS tape file content from export configuration."""
    width_px = _chars_to_pixels(config.width, config.font_size, CHAR_WIDTH_RATIO)
    height_px = _chars_to_pixels(config.height, config.font_size, CHAR_HEIGHT_RATIO)
    sleep_s = int(math.ceil(config.duration_s + config.buffer_s))

    cmd_parts = ["clirec play", config.clirec_path]
    if config.speed != DEFAULT_SPEED:
        cmd_parts.append(f"--speed {config.speed}")
    if config.max_delay != DEFAULT_MAX_DELAY:
        cmd_parts.append(f"--max-delay {config.max_delay}")
    if config.line_delay > 0:
        cmd_parts.append(f"--line-delay {config.line_delay}")
    play_cmd = " ".join(cmd_parts)

    lines = [
        'Set Shell "bash"',
        f"Set FontSize {config.font_size}",
        f"Set Width {width_px}",
        f"Set Height {height_px}",
        f'Set Theme "{config.theme}"',
        f"Set Padding {config.padding}",
        f'Output "{config.output_path}"',
        "",
        f'Type "{play_cmd}"',
        "Enter",
        f"Sleep {sleep_s}s",
    ]
    return "\n".join(lines) + "\n"


def _derive_output_path(filepath: str, fmt: str) -> str:
    base = os.path.splitext(filepath)[0]
    return f"{base}.{fmt}"


def _run_vhs(tape_content: str) -> None:
    tape_fd, tape_path = tempfile.mkstemp(suffix=".tape")
    try:
        with os.fdopen(tape_fd, "w") as f:
            f.write(tape_content)
        try:
            subprocess.run(
                ["vhs", tape_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else "unknown error"
            raise RuntimeError(f"VHS export failed: {stderr}") from e
    finally:
        os.unlink(tape_path)


def export(
    *,
    filepath: str,
    output: str | None = None,
    format: str = "mp4",
    width: int | None = None,
    height: int | None = None,
    font_size: int = 18,
    theme: str = "Catppuccin Mocha",
    speed: float = 1.0,
    max_delay: float = 3.0,
    line_delay: int = 0,
    padding: int = 0,
    buffer: float = 2.0,
) -> str:
    """Export a .clirec recording to video/GIF via VHS. Returns output path."""
    missing = check_dependencies()
    if missing:
        hints = "; ".join(f"{d.name}: {d.install_hint}" for d in missing)
        raise RuntimeError(f"Missing required tools: {hints}")

    abs_path = os.path.abspath(filepath)
    with open(abs_path) as f:
        header = read_header(f)
        duration = _compute_duration_from_events(
            iter_events(f), speed=speed, max_delay=max_delay, line_delay=line_delay
        )

    output_path = output if output else _derive_output_path(abs_path, format)
    config = ExportConfig(
        clirec_path=abs_path,
        output_path=output_path,
        width=width if width is not None else header["width"],
        height=height if height is not None else header["height"],
        font_size=font_size,
        theme=theme,
        speed=speed,
        max_delay=max_delay,
        line_delay=line_delay,
        padding=padding,
        duration_s=duration,
        buffer_s=buffer,
    )
    _run_vhs(generate_tape(config))
    return output_path


def _compute_duration_from_events(
    events: Iterator[SessionEvent],
    *,
    speed: float,
    max_delay: float,
    line_delay: int,
) -> float:
    line_delay_s = line_delay / 1000.0
    total = 0.0
    prev_t = 0.0
    for event in events:
        if event["type"] == EVENT_INPUT:
            continue
        total += _compute_delay(event["t"], prev_t, speed, max_delay, False)
        if line_delay_s > 0:
            lines = split_lines(event["data"])
            if len(lines) > 1:
                total += (len(lines) - 1) * line_delay_s
        prev_t = event["t"]
    return total


def compute_duration(
    filepath: str,
    *,
    speed: float = 1.0,
    max_delay: float = 3.0,
    line_delay: int = 0,
) -> float:
    """Return the total playback duration in seconds for a .clirec file."""
    with open(filepath) as f:
        read_header(f)
        return _compute_duration_from_events(
            iter_events(f), speed=speed, max_delay=max_delay, line_delay=line_delay
        )
