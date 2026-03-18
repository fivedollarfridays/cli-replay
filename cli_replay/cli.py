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
SCRUB = "scrub"
COALESCE = "coalesce"
COMPARE = "compare"
PIPELINE = "pipeline"
CHECK_QUALITY = "check-quality"
VALIDATE_SEQUENCES = "validate-sequences"


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


def _run_scrub(args: argparse.Namespace) -> None:
    """Run the scrub subcommand."""
    from cli_replay.scrub import scrub

    to_t = args.to if args.to is not None else float("inf")
    kwargs = dict(pattern=args.pattern, from_t=args.from_t, to_t=to_t)
    if args.output:
        with open(args.output, "w") as out:
            dropped = scrub(filepath=args.file, output=out, **kwargs)
    else:
        dropped = scrub(filepath=args.file, output=sys.stdout, **kwargs)
    sys.stderr.write(f"Scrubbed {dropped} event(s)\n")


def _run_post(args: argparse.Namespace) -> None:
    """Dispatch post-processing subcommands."""
    if args.command == COALESCE:
        from cli_replay.coalesce import coalesce_events

        with open(args.output, "w") as out:
            coalesce_events(args.file, out)
    elif args.command == COMPARE:
        from cli_replay.compare import compare_recordings

        result = compare_recordings(
            args.file1, args.file2, snapshots=args.snapshots
        )
        if not result.matched:
            sys.stderr.write(f"{result.differing} snapshot(s) differ\n")
            sys.exit(1)
    elif args.command == PIPELINE:
        from cli_replay.pipeline import run_pipeline

        run_pipeline(args.config)
    elif args.command == CHECK_QUALITY:
        from cli_replay.quality import check_quality

        qr = check_quality(args.file)
        if not qr.passed:
            sys.stderr.write(
                f"WARNING: {qr.split_escapes} split escapes, "
                f"{qr.split_sync_updates} split syncs\n"
            )
            sys.exit(1)
        sys.stderr.write("PASS: no split sequences detected\n")
    elif args.command == VALIDATE_SEQUENCES:
        from cli_replay.quality import validate_sequences

        sr = validate_sequences(args.file)
        if not sr.valid:
            sys.stderr.write(
                f"FAIL: {sr.incomplete_csi} incomplete CSI, "
                f"{sr.unmatched_sync} unmatched sync\n"
            )
            sys.exit(1)
        sys.stderr.write(f"Valid: {sr.total_sequences} sequences OK\n")


def _run(args: argparse.Namespace) -> None:
    """Dispatch to the appropriate subcommand with error handling."""
    try:
        if args.command == RECORD:
            from cli_replay.recorder import record

            record(output=args.output, script=args.script)
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
        elif args.command == SCRUB:
            _run_scrub(args)
        else:
            _run_post(args)
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
    rec.add_argument("-s", "--script", help="Script file for automated input")

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

    _add_reflow_parser(sub)
    _add_scrub_parser(sub)
    _add_post_parsers(sub)

    return parser


def _add_reflow_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Add the reflow subcommand parser."""
    reflow_parser = sub.add_parser(REFLOW, help="Reflow a recorded session")
    reflow_parser.add_argument("file", help="Path to .clirec file")
    reflow_parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    reflow_parser.add_argument(
        "--delay", type=int, default=40, help="Delay between lines in ms (default: 40)"
    )


def _add_scrub_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Add the scrub subcommand parser."""
    scrub_parser = sub.add_parser(SCRUB, help="Remove events matching a pattern")
    scrub_parser.add_argument("file", help="Path to .clirec file")
    scrub_parser.add_argument(
        "--pattern", required=True, help="Regex to match against visible text"
    )
    scrub_parser.add_argument(
        "--from",
        type=float,
        default=0,
        dest="from_t",
        help="Start of time range (seconds)",
    )
    scrub_parser.add_argument(
        "--to", type=float, default=None, help="End of time range (seconds)"
    )
    scrub_parser.add_argument("-o", "--output", help="Output file (default: stdout)")


def _add_post_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Add post-processing subcommand parsers."""
    coal = sub.add_parser(COALESCE, help="Merge near-timestamp events")
    coal.add_argument("file", help="Path to .clirec file")
    coal.add_argument("-o", "--output", required=True, help="Output file")

    cmp = sub.add_parser(COMPARE, help="Compare two recordings via tmux snapshots")
    cmp.add_argument("file1", help="First .clirec file")
    cmp.add_argument("file2", help="Second .clirec file")
    cmp.add_argument("--snapshots", type=int, default=5, help="Number of snapshots")

    pipe = sub.add_parser(PIPELINE, help="Run full post-processing pipeline")
    pipe.add_argument("--config", required=True, help="Pipeline config YAML")

    cq = sub.add_parser(CHECK_QUALITY, help="Check recording for split sequences")
    cq.add_argument("file", help="Path to .clirec file")

    vs = sub.add_parser(VALIDATE_SEQUENCES, help="Validate escape sequence completeness")
    vs.add_argument("file", help="Path to .clirec file")


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
