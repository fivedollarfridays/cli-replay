# Diagnostic Report: Video Production Pipeline Inconsistency

**Date:** 2026-03-17
**System:** clirec (CLI recording tool with PTY relay)
**Problem:** Identical inputs produce different quality recordings across runs

---

## 1. System Architecture

### End-to-End Pipeline

```
Reset (video3-reset.sh)
  → Preflight (video3-preflight.sh) — 29 checks
    → Record (clirec record -s video3-session1.txt -o /tmp/video3-session1)
      → Process (clirec process --config yaml --verify)
        → Manual Review (tmux playback at --speed 2)
          → OBS Capture (tmux playback at --speed 1)
```

### Recording Subsystem (recorder.py)

The recorder opens a PTY pair (`pty.openpty()`), spawns a shell on the slave side, and runs a `select()`-based I/O relay loop on the master side.

Key parameters:
- **Read buffer:** `os.read(master_fd, 4096)` — fixed 4096-byte reads (line 118)
- **Select timeout:** 0.25 seconds
- **Timestamp resolution:** milliseconds (`time.monotonic()` rounded to 3 decimal places)

In scripted mode, a daemon thread (`script_feeder`) writes to `master_fd` on its own schedule while the main thread runs the same `select()` loop.

### Script Feeder (script_feeder.py)

Runs in a daemon thread:
- Types commands character-by-character (default 50ms delay, configurable via `@speed`)
- `@wait-for` directives poll an `OutputBuffer` for prompt text synchronization
- User watches CC execution and manually sends Ctrl+Shift+Z to enter/exit CC sessions

### Post-Processing (process.py)

Splits events by CC time ranges from YAML config:
- **Shell events:** PII redaction only (username, hostname, home path)
- **CC events:** Strip DA query sequences (`\x1b[c`, `\x1b[>0q`) only

### Verification (verify.py)

Headless tmux at recording dimensions, plays at 50x, 5 snapshots checking for DA garbage and PII.

---

## 2. Failure History

| Session | Issue | Root Cause | Fixed? |
|---------|-------|-----------|--------|
| 1 | CC exit trigger wrong (`See ya!` vs `Goodbye!`) | Script waited for wrong text | Yes — changed to wait for shell prompt |
| 1 | Script stalled on `@wait-for! "❯" 60` | Buffer cleared before CC drew `❯` | Yes — removed `!` flag |
| 2 | `scrub_data()` stripped numbers from plan names | `_COUNTER_RE` matched bpsai-pair colored digits | Yes — removed scrub from shell processing |
| 2 | DA stripping broke CC TUI | Removing `\x1b[c` from CC data broke terminal state | Yes — CC now raw except DA queries |
| 2 | Verification passed but output garbled | `--instant` check can't detect rendering issues | Yes — added tmux verification |
| 3 | PII check failed on CC sections | Verify snapshots landed in CC section with raw username | Yes — skip PII check when CC TUI markers present |
| 3 | Playback garbled outside tmux | Terminal responds to query sequences | Yes — documented tmux requirement |
| 3 | `kmasty` leaked in shell prompts | Early processing used wrong redaction approach | Yes — PII redact on shell only |
| 4 | Trello cards not in Planned after reset | Reset ran but recording's `ttask done` moved them back after | Yes — timing issue, re-ran reset |
| 4 | Agent used `task update` instead of `ttask done` | Task files missing `trello_card` field | Yes — added field to task files |
| 4 | "No linked card" warning in CC TUI | Agent ignores CLAUDE.md instruction to use `ttask done` | Partially — strengthened CLAUDE.md, but agent behavior is non-deterministic |
| 5 | Missing `b` in `bpsai-pair budget status` | No settle delay after `@wait-for!` resolved | Yes — added `@wait 0.5` |
| **5** | **CC TUI garbled in raw recording** | **PTY read buffer splits escape sequences** | **No — root cause unaddressed** |

---

## 3. Root Cause: Why Results Vary Between Runs

### The PTY Read Buffer Split (PRIMARY)

Line 118 of `recorder.py`:

```python
data = os.read(master_fd, 4096)
```

`os.read()` returns whatever bytes are in the PTY buffer at the instant of the call. Claude Code's TUI writes escape sequences in rapid bursts — cursor positioning, status bar updates, synchronized screen updates. Whether a burst lands in one read or gets split across two depends on:

1. **Kernel scheduling** — when the main thread gets CPU time relative to CC's writes
2. **System load** — current load average is 2.97 (moderate contention on this system)
3. **CC's internal timing** — token streaming, API latency, TUI event loop scheduling

**Measured impact on current recording:**
- 7008 CC output events total
- 153 close-together (<5ms) escape-containing event pairs — **2.2% of events are split**
- 7 confirmed split synchronized update sequences (`\x1b[?2026h` begins in one event, `\x1b[?2026l` ends in the next)

When a synchronized update gets split, the terminal renders the first half (partial cursor positioning + partial text write), then renders the second half after a delay. This produces overlapping status bars, fragmented autocomplete dropdowns, and cursor positioning errors.

### Why the `@wait 0.5` Fix Changed Everything

Adding 0.5 seconds before `bpsai-pair budget status` shifted the script feeder thread's schedule by 500ms relative to all subsequent CC output. Every PTY read boundary shifted. A recording that was clean by luck became garbled because reads now split in the middle of escape sequences instead of between them.

### Non-Deterministic CC Output

Even with identical inputs, Claude Code produces different output timing:
- Network latency to Claude API varies
- Token streaming timing varies
- The agent may take different implementation approaches
- TUI redraw frequency depends on event loop scheduling

The recording captures whatever timing happens to occur. Reproducibility is impossible with a 4096-byte non-coalescing read.

---

## 4. Current Workflow Gaps

### 4.1 Reset

| Exists | Missing |
|--------|---------|
| Trello card reset to Planned | Silent failure swallowing (`2>/dev/null \|\| true`) — no verification that API calls succeeded |
| AC unchecking for all cards | No rate-limit handling or retry |
| Git hard reset to `demo-planned` tag | No tag integrity check (verify commit hash) |
| Preflight checks git state (29 checks) | No `trello_card` link check in task files |
| | No terminal size check (`tput cols`/`tput lines` vs expected) |
| | No Claude Code version check |
| | No archive of previous recordings with quality notes |

### 4.2 Recording

| Exists | Missing |
|--------|---------|
| Script feeder with `@wait-for` sync | **No read coalescing — root cause of garble** |
| Output buffer for text matching | No recording quality validation during/after recording |
| 4096-byte read buffer | Should be 65536+ with drain loop |
| | No recording inside tmux (would eliminate split-sequence problem) |
| | No abort/retry if CC fails to launch |
| | No save folder for versioned recordings with quality notes |

### 4.3 Post-Processing

| Exists | Missing |
|--------|---------|
| CC range splitting by config | No split escape sequence detection or repair |
| DA query stripping | No event coalescing (merge <5ms events into one) |
| PII redaction for shell sections | No post-coalescing step to repair split TUI updates |
| `--verify` flag | Verification runs at 50x — misses transient garble |

### 4.4 Verification

| Exists | Missing |
|--------|---------|
| DA response detection | Only catches settled frames, not transient garble |
| PII detection (shell only) | No slow-playback verification for CC sections |
| tmux headless playback | No golden recording comparison |
| | No split-sequence count check on raw file |
| | No save/archive of verified recordings |

---

## 5. Proposed Remedies

### Tier 1: Fix the Root Cause (Do Now)

**R1. Increase Read Buffer to 65536**
One-line change in `recorder.py` line 118. Larger reads capture more of a TUI burst in a single event.

```python
# Before:
data = os.read(master_fd, 4096)
# After:
data = os.read(master_fd, 65536)
```

Risk: Zero. PTY reads return available data, never block for full buffer.

**R2. Read Coalescing Drain**
After each `os.read()`, continue reading with a short non-blocking drain to capture burst stragglers:

```python
data = os.read(master_fd, 65536)
# Drain any remaining burst data
while select.select([master_fd], [], [], 0.005)[0]:
    data += os.read(master_fd, 65536)
```

Impact: Directly addresses split-sequence problem. Adds ~5ms latency per event — acceptable for recording.

**R3. Post-Recording Event Coalescing**
Add `clirec coalesce` command that merges events within 5ms of each other into single events. Can repair existing garbled recordings without re-recording.

### Tier 2: Improve Reliability

**R4. Record Inside tmux**
Run `clirec record` inside a tmux session at fixed dimensions. tmux processes escape sequences at the multiplexer layer, emitting clean output. Eliminates the entire class of split-sequence issues.

```bash
tmux new-session -s record -x 99 -y 25
# Inside tmux:
clirec record -s video3-session1.txt -o /tmp/video3-session1
```

Risk: Recording captures tmux's rendering, not raw terminal. Needs testing to confirm visual equivalence.

**R5. Recording Archive with Quality Notes**
Create `~/test-store/production/recordings/` with versioned recordings:

```
recordings/
  video3-session1-v1.clirec      # garbled CC autocomplete
  video3-session1-v1.notes.md    # "CC garble in autocomplete dropdown"
  video3-session1-v2.clirec      # clean but missing 'b' keystroke
  video3-session1-v2.notes.md    # "missing b in budget status — CLEAN CC"
  video3-session1-v3.clirec      # current
```

**R6. Split-Sequence Quality Gate**
After recording, count split escape sequences. If above threshold (e.g., >20), flag recording as potentially garbled:

```bash
clirec check-quality recording.clirec  # "WARNING: 153 split escape sequences detected"
```

**R7. Slow-Speed Verification for CC Sections**
Change `--verify` to play CC sections at 2x speed (not 50x) with more frequent snapshots. Catches transient garble that 50x misses.

### Tier 3: Workflow Improvements

**R8. Preflight Terminal Size Check**
Add to `video3-preflight.sh`:
```bash
[ "$(tput cols)" -eq 99 ] && [ "$(tput lines)" -eq 25 ] || echo "✗ Terminal size mismatch"
```

**R9. Remove Silent Failure Swallowing**
Replace `2>/dev/null || true` in reset script with proper error checking.

**R10. Archive Every Recording**
Before overwriting `/tmp/video3-session1.clirec`, copy the current version to the archive with a timestamp. Never lose a clean recording again.

---

## 6. Answers to Diagnostic Questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Terminal dimensions for clean vs garbled? | Same dimensions (99x25) both times |
| 2 | Same Claude Code version? | Yes — v2.1.78 for both |
| 3 | System load during recording? | Load average 2.97, 2.27, 1.38 — moderate contention, 5-day uptime |
| 4 | Can the clean recording be recovered? | No — overwritten, no archive existed |
| 5 | Exact timestamps where garble begins? | 7 confirmed split sync updates at t=81.3, 392.8, 517.3, 636.1, 651.5 + 153 close-together escape pairs |
| 6 | Has R1 (larger buffer) been tested? | No — not yet implemented |
| 7 | Recording inside tmux acceptable? | Yes, as long as it looks the same visually |
| 8 | DA response in recording? | Queries stripped by processing; responses not present in current recording |
| 9 | How much garble is acceptable? | Zero. Must be clean |
| 10 | Are `@wait-for` timeouts sufficient? | Not needed — user manually enters/exits CC via Ctrl+Shift+Z |

---

## 7. Recommended Action Plan

**Immediate (do now, re-record tonight):**
1. Implement R1 + R2 (larger buffer + drain) — 30 minutes
2. Implement R10 (archive recordings before overwriting) — 10 minutes
3. Test with a short recording to verify garble is reduced
4. If clean: full re-record + process + verify

**If R1+R2 don't fix it:**
5. Implement R4 (record inside tmux) — test equivalence
6. If tmux recording looks the same: adopt as standard

**After a clean recording is produced:**
7. Implement R5 (archive with notes) — never lose a clean recording again
8. Implement R6 (split-sequence quality gate) — catch garble automatically
9. Implement R3 (event coalescing) — repair capability for future recordings

---

## 8. Summary

The root cause is `os.read(master_fd, 4096)` splitting Claude Code's TUI escape sequence bursts across multiple events. The 4096-byte buffer is too small for CC's output bursts, and there's no coalescing drain to capture stragglers. The fix is mechanical: larger buffer + drain loop. The clean recording from two sessions ago was clean by luck — the read boundaries happened to fall between escape sequences rather than in the middle of them. The `@wait 0.5` timing change shifted all boundaries, breaking the lucky alignment.

The secondary issue is workflow: no recording archive exists, so the clean recording was lost when overwritten. Every workflow gap identified in section 4 contributed to the repeated loops — silent reset failures, missing preflight checks, verification that can't see garble, no quality gate on raw recordings.
