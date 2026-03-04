"""Entry point for clirec command."""

from __future__ import annotations

import argparse
import signal
import sys

from cli_replay import __version__


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
        if args.command == "record":
            from cli_replay.recorder import record

            record(output=args.output)
        elif args.command == "play":
            _validate_play_args(args)

            from cli_replay.player import play

            play(
                filepath=args.file,
                speed=args.speed,
                max_delay=args.max_delay,
                no_input=args.no_input,
                instant=args.instant,
                line_delay=args.line_delay,
            )
        elif args.command == "reflow":
            _validate_reflow_args(args)

            from cli_replay.reflow import reflow

            if args.output:
                with open(args.output, "w") as out:
                    reflow(filepath=args.file, output=out, delay_ms=args.delay)
            else:
                reflow(filepath=args.file, output=sys.stdout, delay_ms=args.delay)
    except KeyboardInterrupt:
        sys.exit(130)
    except FileNotFoundError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)


def main() -> None:
    """Parse arguments and run the appropriate subcommand."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = argparse.ArgumentParser(
        prog="clirec", description="Record and replay CLI sessions"
    )
    parser.add_argument("--version", action="version", version=f"clirec {__version__}")
    sub = parser.add_subparsers(dest="command")

    rec = sub.add_parser("record", help="Record a terminal session")
    rec.add_argument(
        "-o", "--output", help="Output filename (without .clirec extension)"
    )

    play_parser = sub.add_parser("play", help="Replay a recorded session")
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
        "--no-input", action="store_true", help="Skip input events"
    )
    play_parser.add_argument(
        "--instant", action="store_true", help="Ignore timing, dump immediately"
    )
    play_parser.add_argument(
        "--line-delay", type=int, default=0, help="Delay between lines in ms"
    )

    reflow_parser = sub.add_parser("reflow", help="Reflow a recorded session")
    reflow_parser.add_argument("file", help="Path to .clirec file")
    reflow_parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    reflow_parser.add_argument(
        "--delay", type=int, default=40, help="Delay between lines in ms (default: 40)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
    else:
        _run(args)
