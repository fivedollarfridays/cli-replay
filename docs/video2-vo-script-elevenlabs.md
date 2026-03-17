# Video 2: Planning — ElevenLabs VO Script

> Recording: ~/test-store/video2-planning.clirec (6m08s raw, edited to <2:00)
> Voice: ElevenLabs Adam Greene v3
> Format: Plain text segments for ElevenLabs API, no markdown or stage directions

---

## Segments

### Segment 1 — Opening + Codebase [0:00–0:08]

Welcome back to PairCoder. We left off with a project skeleton — FastAPI app, product data, basic tests. Now we need to plan what to build.

### Segment 2 — Feature Branch + Budget [0:08–0:18]

We create a feature branch, check our token budget — we're under threshold — and launch contained auto mode. That creates a git checkpoint and sandboxes Claude's session so changes are isolated.

### Segment 3 — Invoke Planning Skill [0:18–0:25]

We pass in a feature description — add search and filtering. Five features: search endpoint, category filter, price range filter, pagination, and integration tests.

### Segment 4 — Claude Explores and Plans [0:25–0:40]

Claude reads the entire codebase, dispatches explore agents in parallel, and builds a plan. Twenty-five-plus tool calls, about a minute of thinking — compressed here to a few seconds.

### Segment 5 — Plan Output [0:40–0:50]

Five tasks, properly scoped. Search endpoint, category filter, price range, pagination, and a combined integration test — each with complexity estimates and priority.

### Segment 6 — Verify Tasks [0:50–1:10]

The task breakdown — T1.1 through T1.5. P0 and P1 priorities, complexity from twenty-five to thirty-five. This is what the driver works from in the next video.

### Segment 7 — Inspect a Task [1:10–1:30]

T1.3, the price range filter — eight acceptance criteria covering edge cases, validation, and composition with other filters. These aren't just documentation. They're verification gates. If any fail, the task stays open.

### Segment 8 — Commit and Closing [1:30–1:50]

We commit, tag it as demo-planned, and that's our reset point. Feature description in, scoped task breakdown out. Next video — the driver implements these tasks with TDD, and we see what happens when a gate check fails.

---

## ElevenLabs Production Notes

- **Total segments:** 8
- **Estimated narration:** ~90 seconds over <2:00 of footage
- **Voice settings:** Stability 0.50, Similarity 0.75, Style 0.35
- **Claude Code section (Seg 4):** Heavy speed-up (8–10x), VO plays over fast-forwarded terminal
- **Cuts:** Drop the typo at original 4:23, drop separate budget check and containment setup — consolidate into Segment 2
- **Segment gaps:** 0.3–0.5s silence between segments (tighter than long-form)
- **Post-processing:** Normalize loudness to -16 LUFS for YouTube
