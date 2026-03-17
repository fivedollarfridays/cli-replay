# Current State

> Last updated: 2026-03-17

## Active Plan

**Plan:** plan-2026-03-demo-reset
**Title:** Reliable demo reset loop for test-store video recordings
**Status:** In Progress
**Type:** chore

## Previous Plan (Complete)

**Plan:** plan-2026-03-auto-redact — Sprint 4 fully complete. 145 tests, 100% coverage.

## Current Focus

Sprint 5 — Demo reset loop. T5.1 → T5.2 → T5.3 (sequential, each depends on prior).

## Task Status

### Sprint 3 (Complete)

| Task | Description | Status | Cx |
|------|-------------|--------|-----|
| T3.1 | split_lines pure function + tests | ✅ done | 15 |
| T3.2 | Event splitting + reflowed iteration + tests | ✅ done | 20 |
| T3.3 | Player line-delay support + tests | ✅ done | 25 |
| T3.4 | CLI --line-delay flag + validation + tests | ✅ done | 15 |
| T3.5 | clirec reflow command + integration tests | ✅ done | 30 |

### Sprint 4 (Auto-Redact)

| Task | Description | Status | Cx |
|------|-------------|--------|-----|
| T4.1 | build_replacements pure function + tests | ✅ done | 15 |
| T4.2 | redact_event pure function + tests | ✅ done | 15 |
| T4.3 | redact main function + file I/O + tests | ✅ done | 20 |
| T4.4 | CLI redact subcommand + validation + tests | ✅ done | 15 |
| T4.5 | In-place file redaction + integration tests | ✅ done | 20 |

## What Was Just Done

- **T5.1 done** (auto-updated by hook)

- **Code Review & Quality Improvements** — Ran `/simplify` skill with 3 agents (code reuse, quality, efficiency). Fixed TOCTOU race condition in `redact_inplace()` by validating file readability first. Added command constants (RECORD, PLAY, REDACT, REFLOW) to eliminate magic strings in CLI dispatch. All 145 tests passing, architecture green. Commit: af06b1a.

- **T4.5 done** (auto-updated by hook)

- **T4.4 done** (auto-updated by hook)

- **T4.3 done** (auto-updated by hook)

- **T4.2 done** (auto-updated by hook)

- **T4.2 done** — Implemented `_redact_event()` pure function in `cli_replay/redact.py`. Applies list of (old, new) replacements to event data field, preserving t and type. Returns new SessionEvent. 5 tests cover: username in prompt, path replacement, hostname replacement, no-match, ANSI escape sequences preserved. 137 tests passing, arch check green.

## What Was Just Done (Continued)

- **T4.3 done** — Implemented `redact()` main function in `cli_replay/redact.py`. Orchestrates file I/O: reads .clirec, detects sensitive data from environment, applies redactions to all events, writes to output stream. Follows reflow.py pattern. 3 tests cover: fixture redaction, header preservation, multi-event round-trip. 140 tests passing, arch check green.

## Sprint 5 (Demo Reset Loop)

| Task | Description | Status | Cx |
|------|-------------|--------|-----|
| T5.1 | Fix demo-planned git tag to pre-implementation state | ✅ done | 10 |
| T5.2 | Update video3-reset.sh to run preflight and fail loudly | ✅ done | 10 |
| T5.3 | Create reset-demo skill for test-store | ⏳ pending | 15 |

## What Was Just Done

- **T5.2 done** — Updated `video3-reset.sh` to call `video3-preflight.sh` after git reset. Exits 1 with "❌ Reset failed" if any check fails, prints "✅ Ready to record" on full pass (29/29 checks). Committed to `demo-planned` tag at `257a99d`.

- **T5.1 done** — Fixed `demo-planned` tag in `~/test-store`. Created `temp-demo-planned` branch at `0fb5ac7` (pre-implementation), applied 4 "See ya!" trigger fixes to `video3-session1.txt`, committed, force-updated `demo-planned` tag to new commit `2dcbd3c`. All ACs verified: no `tests/test_search.py`, no search in `src/main.py`, 4× See ya! in script, clean tree after reset.

## What's Next

T5.2 — update `video3-reset.sh` to call `video3-preflight.sh` after reset and exit 1 with "❌ Reset failed" if any check fails.

## Completion Summary

**Sprint 4 — Auto-Redact Personal Data in Recordings — COMPLETE**

All 5 tasks done (85 Cx total):
- T4.1: `_build_replacements()` — detect & order replacements
- T4.2: `_redact_event()` — apply redactions to event data
- T4.3: `redact()` — main file I/O orchestration
- T4.4: CLI redact subcommand — arg parsing & dispatch
- T4.5: In-place redaction — atomic temp-file-and-rename pattern

Features:
- `clirec redact file.clirec` — writes redacted output to stdout
- `clirec redact file.clirec -o clean.clirec` — writes to separate file
- In-place: `clirec redact file.clirec` (no `-o`) — overwrites file atomically
- Auto-detects USER, HOSTNAME, HOME from environment
- Zero-config, idempotent, ANSI-safe
- 145 tests, 100% coverage, architecture green

## Blockers

None currently.
