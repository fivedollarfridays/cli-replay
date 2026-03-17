---
name: processing-recordings
description: Post-processes clirec recordings for video production by scrubbing TUI artifacts, redacting PII, and stitching clean shell sections with raw Claude Code sections.
---

# Processing Recordings

## When to Use

After recording a terminal session with `clirec record`, when preparing the recording for video production. Handles three problems: Claude Code TUI artifacts, terminal query garbage, and PII redaction.

## Known Issues in Raw Recordings

| Issue | Cause | Fix |
|-------|-------|-----|
| `^[[?61;...` garbage | DA1 terminal query `\x1b[c]` in output triggers terminal response | `clirec scrub` strips DA queries |
| Stray numbers in thinking section | Claude Code token counter updates via `\x1b[38;5;246m` | `clirec scrub` strips colored digits |
| Garbled TUI during thinking | Sync frame cursor movements (`\x1b[?2026h`) stomp on previous text | Drop all output events in Claude Code time range |
| Username/hostname in prompts | Raw recording contains PII | `clirec redact` with word-boundary-aware replacement |
| Short hostname breaks words | `Rig` replaced inside `ADVISORY` | Redactor uses word boundaries for strings under 5 chars |

## Processing Pipeline

### Option A: Shell-only recording (no Claude Code)

For recordings without Claude Code sessions:

```bash
clirec scrub recording.clirec --pattern '^\d{1,4}$' --from 0 --to 9999 -o clean.clirec
clirec redact clean.clirec
```

### Option B: Hybrid recording (shell + Claude Code)

Claude Code TUI cannot be replayed cleanly through clirec. The solution: stitch clean redacted shell sections with raw Claude Code (DA queries stripped only).

```python
import json, re

DA_RE = re.compile(r'\x1b\[>0q|\x1b\[c')

# Load original and scrubbed+redacted files
with open('recording.clirec') as f:
    header = json.loads(f.readline())
    raw_events = [json.loads(line) for line in f if line.strip()]

with open('recording-clean.clirec') as f:
    clean_header = json.loads(f.readline())
    clean_events = [json.loads(line) for line in f if line.strip()]

# Define Claude Code time range (find from recording)
CLAUDE_START = 34   # "Launching Claude Code..."
CLAUDE_END = 381    # "Resume this session..."

before = [e for e in clean_events if e['t'] < CLAUDE_START]
after = [e for e in clean_events if e['t'] > CLAUDE_END]

# Claude section: strip only DA queries
claude = []
for e in raw_events:
    if CLAUDE_START <= e['t'] <= CLAUDE_END:
        if e['type'] == 'o' and DA_RE.search(e['data']):
            e = dict(e)
            e['data'] = DA_RE.sub('', e['data'])
        claude.append(e)

with open('recording-final.clirec', 'w') as out:
    out.write(json.dumps(clean_header) + '\n')
    for ev in before + claude + after:
        out.write(json.dumps(ev) + '\n')
```

### Finding the Claude Code time range

```bash
python3 -c "
import json, re
ANSI_RE = re.compile(r'\x1b\[[^a-zA-Z]*[a-zA-Z]|\x1b\][^\x07]*\x07')
with open('recording.clirec') as f:
    f.readline()
    for line in f:
        ev = json.loads(line)
        if ev['type'] == 'o':
            v = ANSI_RE.sub('', ev['data']).strip()
            if 'Launching Claude Code' in v:
                print(f'START: t={ev[\"t\"]:.1f}')
            if 'Resume this session' in v:
                print(f'END: t={ev[\"t\"]:.1f}')
"
```

## Playback Verification

Always verify before delivering:

```bash
# Quick check — dumps to terminal instantly
clirec play recording-final.clirec --instant

# Real-time check at speed
clirec play recording-final.clirec --speed 3
```

## OBS Recording Workflow

For the final video, record playback with OBS to capture proper terminal rendering:

```bash
# Start OBS recording, then:
clirec play recording-final.clirec --speed 1
```

The hybrid file gives OBS clean shell commands with proper redaction and raw Claude Code TUI that renders correctly in the live terminal (even though it can't be replayed cleanly).
