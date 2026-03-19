"""Post-processing CLI subcommands for clirec."""

from __future__ import annotations

import argparse
import sys

# Command constants
COALESCE = "coalesce"
COMPARE = "compare"
PIPELINE = "pipeline"
CHECK_QUALITY = "check-quality"
VALIDATE_SEQUENCES = "validate-sequences"


def run_post(args: argparse.Namespace) -> None:
    """Dispatch post-processing subcommands."""
    if args.command == COALESCE:
        from cli_replay.coalesce import coalesce_events

        with open(args.output, "w") as out:
            coalesce_events(args.file, out)
    elif args.command == COMPARE:
        from cli_replay.compare import compare_recordings

        result = compare_recordings(args.file1, args.file2, snapshots=args.snapshots)
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


def add_post_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
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

    vs = sub.add_parser(
        VALIDATE_SEQUENCES, help="Validate escape sequence completeness"
    )
    vs.add_argument("file", help="Path to .clirec file")
