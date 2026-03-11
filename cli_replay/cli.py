"""Entry point for clirec command."""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Any, Callable

from cli_replay import __version__

# Command constants
RECORD = "record"
PLAY = "play"
REDACT = "redact"
REFLOW = "reflow"


def _run_with_output(
    func: Callable[..., Any],
    filepath: str,
    output_file: str | None = None,
    **kwargs: Any,
) -> None:
    """Run a function with optional output file or stdout."""
    if output_file:
        with open(output_file, "w") as out:
            func(filepath=filepath, output=out, **kwargs)
    else:
        func(filepath=filepath, output=sys.stdout, **kwargs)


def _validate_play_args(args: argparse.Namespace) -> None:
    """Validate play subcommand arguments."""
    if args.speed <= 0:
        raise ValueError("speed must be > 0")
    if args.max_delay < 0:
        raise ValueError("max-delay must be >= 0")
    if args.line_delay < 0:
        raise ValueError("line-delay must be >= 0")


def _validate_reflow_args(args: argparse.Namespace) -> None:
    """Validate reflow subcommand arguments."""
    if args.delay <= 0:
        raise ValueError("delay must be > 0")


def _run(args: argparse.Namespace) -> None:
    """Dispatch to record or play with error handling."""
    try:
        if args.command == RECORD:
            from cli_replay.recorder import record

            record(output=args.output)
        elif args.command == PLAY:
            _validate_play_args(args)

            from cli_replay.player import play

            play(
                filepath=args.file,
                speed=args.speed,
                max_delay=args.max_delay,
                show_input=args.input,
                instant=args.instant,
                line_delay=args.line_delay,
            )
        elif args.command == REDACT:
            from cli_replay.redact import redact, redact_inplace

            if args.output:
                _run_with_output(redact, args.file, args.output)
            else:
                redact_inplace(filepath=args.file)
        elif args.command == REFLOW:
            _validate_reflow_args(args)

            from cli_replay.reflow import reflow

            _run_with_output(reflow, args.file, args.output, delay_ms=args.delay)
    except KeyboardInterrupt:
        sys.exit(130)
    except FileNotFoundError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="clirec", description="Record and replay CLI sessions"
    )
    parser.add_argument("--version", action="version", version=f"clirec {__version__}")
    sub = parser.add_subparsers(dest="command")

    rec = sub.add_parser(RECORD, help="Record a terminal session")
    rec.add_argument(
        "-o", "--output", help="Output filename (without .clirec extension)"
    )

    play_parser = sub.add_parser(PLAY, help="Replay a recorded session")
    play_parser.add_argument("file", help="Path to .clirec file")
    play_parser.add_argument(
        "--speed", type=float, default=1.0, help="Playback speed multiplier"
    )
    play_parser.add_argument(
        "--max-delay",
        type=float,
        default=3.0,
        help="Cap gaps between events (seconds)",
    )
    play_parser.add_argument(
        "--input", action="store_true", help="Include input events (off by default)"
    )
    play_parser.add_argument(
        "--instant", action="store_true", help="Ignore timing, dump immediately"
    )
    play_parser.add_argument(
        "--line-delay", type=int, default=0, help="Delay between lines in ms"
    )

    redact_parser = sub.add_parser(
        REDACT, help="Redact sensitive data from a recording"
    )
    redact_parser.add_argument("file", help="Path to .clirec file")
    redact_parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    reflow_parser = sub.add_parser(REFLOW, help="Reflow a recorded session")
    reflow_parser.add_argument("file", help="Path to .clirec file")
    reflow_parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    reflow_parser.add_argument(
        "--delay", type=int, default=40, help="Delay between lines in ms (default: 40)"
    )

    return parser


def main() -> None:
    """Parse arguments and run the appropriate subcommand."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
    else:
        _run(args)
