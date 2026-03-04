"""Entry point for clirec command."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="clirec", description="Record and replay CLI sessions"
    )
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
        "--max-delay", type=float, default=3.0, help="Cap gaps between events (seconds)"
    )
    play_parser.add_argument(
        "--no-input", action="store_true", help="Skip input events"
    )
    play_parser.add_argument(
        "--instant", action="store_true", help="Ignore timing, dump immediately"
    )

    args = parser.parse_args()

    if args.command == "record":
        from cli_replay.recorder import record

        record(output=args.output)
    elif args.command == "play":
        from cli_replay.player import play

        play(
            filepath=args.file,
            speed=args.speed,
            max_delay=args.max_delay,
            no_input=args.no_input,
            instant=args.instant,
        )
    else:
        parser.print_help()
