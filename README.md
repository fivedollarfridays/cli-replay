# clirec

Record and replay terminal sessions. Zero dependencies — Python stdlib only.

## Install

```bash
pip install -e .
```

## Usage

### Record

```bash
clirec record -o my-session
```

Drops you into a recorded shell. Run commands as usual, then `exit` or `Ctrl+D` to stop. The session is saved to `my-session.clirec`.

Omit `-o` to auto-name with a timestamp (`2026-03-04_153000.clirec`).

### Replay

```bash
clirec play my-session.clirec
```

Replays the session to your terminal with original timing preserved, including colors and ANSI escape sequences.

#### Options

| Flag | Description |
|------|-------------|
| `--speed 2` | Playback at 2x speed |
| `--max-delay 1` | Cap pauses between events at 1 second |
| `--no-input` | Skip input events, show output only |
| `--instant` | Dump everything immediately, no delays |

### Examples

```bash
# Record a demo
clirec record -o demo

# Replay at double speed, cap pauses at 2s
clirec play demo.clirec --speed 2 --max-delay 2

# Dump output instantly for piping
clirec play demo.clirec --instant --no-input > output.txt
```

## File Format

Sessions are stored as `.clirec` files — JSON Lines with a header followed by events:

```json
{"version": 1, "timestamp": "2026-03-04T15:30:00Z", "width": 120, "height": 40}
{"t": 0.0, "type": "o", "data": "$ "}
{"t": 0.5, "type": "i", "data": "echo hello\r\n"}
{"t": 0.6, "type": "o", "data": "hello\r\n"}
```

- **Header**: version, ISO timestamp, terminal dimensions
- **Events**: timestamp offset (`t`), type (`o` = output, `i` = input), raw data with ANSI preserved

## How It Works

Recording uses `pty.openpty()` to create a pseudo-terminal, spawns a shell as a child process, and captures all I/O through a `select`-based loop. Terminal settings are saved and restored, and `SIGWINCH` is handled for live terminal resizing.

Playback reads the `.clirec` file, computes delays between events, and writes data to stdout with `time.sleep()` for timing.

## Development

```bash
pip install -e ".[dev]"

# Run tests (96 tests, 100% coverage required)
pytest

# Lint + type check
ruff check . && mypy cli_replay/
```

## Requirements

- Python 3.11+
- Unix/macOS (PTY-based recording requires POSIX)
