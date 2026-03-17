# Video 2: Planning — Voiceover Script

> Recording: /tmp/video2-planning.clirec (6m08s, 2089 events)
> Redaction: NOT needed (no secrets — "token" hits are budget output only)
> Voice: ElevenLabs Adam Greene v3
> Edit in: Premiere

---

## Script

### [0:00–0:10] Opening — Repo Orientation
*Shell opens, we see the test-store directory*

> "We're picking up where Video 1 left off. The wizard gave us a project skeleton — FastAPI app, product data, basic tests. Now we need to plan what to build."

### [0:10–0:25] Show the Codebase
*`ls` shows the repo contents, then we see the main app file*

> "Here's what we're working with — a simple product catalog API. One endpoint, a few models, and some seed data. The question is: what features do we add, and how do we break the work down?"

### [0:25–0:47] Create Feature Branch
*`bpsai-pair feature add-search --type feature --force` runs*

> "First, we create a feature branch. PairCoder tracks features as named branches with metadata — the type, the scope, the plan that goes with it."

**[0:47–0:52]** *Branch creation completes, git branch shows feature/add-search*

> "Feature branch is live. Now we need a plan."

### [0:52–1:05] Budget Check
*`bpsai-pair budget status` runs, showing token thresholds*

> "Before planning, we check our budget. PairCoder tracks token usage against configurable thresholds — info, warning, critical. We're well under budget, so we're clear to go."

### [1:05–1:35] Enter Containment Mode
*Containment prompt appears, user confirms with 'y', checkpoint created*

> "Now we launch contained auto mode. This is the key concept — PairCoder creates a git checkpoint, stashes everything, and drops Claude into a sandboxed session. It can read the codebase but its changes are isolated. If anything goes wrong, we roll back to the checkpoint."

### [1:35–1:48] Invoke /pc-plan
*Claude Code opens, user types `/pc-plan` and pastes the feature description*

> "We invoke the planning skill with a feature description — add search and filtering to the API. Five features: search endpoint, category filter, price range filter, pagination, and combined integration tests."

### [1:48–3:22] Claude Explores and Plans
*Claude's thinking animation runs — reading files, running bash commands, exploring the codebase. Tool use indicators flash: Read, Bash, Explore agents*

> "Now watch what happens. Claude reads the entire codebase — models, routes, tests, config files. It dispatches explore agents in parallel to understand the architecture. This isn't just reading files — it's building a mental model of how the pieces fit together."

**[~2:20]** *Tool use count climbs — 15, 20, 25+ tool calls visible*

> "Twenty-five tool calls and counting. It's checking the test patterns, the project structure, the existing task definitions. All of this context informs the plan it's about to create."

**[~2:55]** *Thinking time reaches ~1 minute*

> "About a minute of deep thinking. For a five-feature plan with acceptance criteria, dependencies, and complexity estimates — that's fast."

### [3:22–3:40] Plan Output
*Claude outputs the plan summary — 5 tasks with titles, complexity, dependencies*

> "And there it is. Five tasks, properly scoped, with acceptance criteria already defined. Search endpoint, category filter, price range, pagination, and a combined integration test. Each one has a complexity estimate and priority."

### [3:40–3:56] Containment Session Exits
*Session ends, stash warning appears*

> "The contained session exits cleanly. Notice the stash warning — that's the checkpoint system. Our changes were isolated the whole time."

### [3:56–4:20] Verify the Plan
*`bpsai-pair plan list` shows the plan, table renders*

> "Let's verify. Plan list shows our plan — 'Add Product Search and Filtering,' five tasks, status planned. Everything was persisted to disk during the session."

### [4:20–4:45] Browse Tasks
*`bpsai-pair plan tasks` shows all 5 tasks in a table*

> "The task breakdown — T1.1 through T1.5. Search endpoint is P0, the rest are P1. Complexity ranges from 20 to 35. This is what the driver will work from in the next video."

### [4:45–5:15] Inspect a Task
*`bpsai-pair plan status` and `bpsai-pair task show T1.3` display task details with AC*

> "Let's look at one task in detail — T1.3, the price range filter. It has five acceptance criteria: min and max price filtering, edge cases for missing params, and a 400 error for invalid ranges. The gate block demo in the next video will use this exact task."

### [5:15–5:31] Show Acceptance Criteria
*AC list displayed with checkboxes*

> "These acceptance criteria aren't just documentation — they're verification gates. When the driver completes this task, PairCoder checks each criterion before marking it done. If any fail, the task stays open."

### [5:31–5:50] Review Another Task
*T1.1 search endpoint details shown*

> "T1.1 — the search endpoint. Query parameter search, case-insensitive matching against name and description, empty query returns all products. Clean, testable, specific."

### [5:50–6:08] Commit and Tag
*`git commit` and `git tag -f demo-planned` run*

> "We commit the plan artifacts and tag this state as demo-planned. This is the reset point for Video 3 — when we start implementing, we'll reset to exactly this state and let the driver work through each task."

### [6:08] Closing

> "That's planning with PairCoder. Feature description in, scoped task breakdown out — with acceptance criteria, dependencies, and complexity estimates. In the next video, we'll watch the driver implement these tasks using test-driven development, and see what happens when a task fails its gate check."

---

## Production Notes

- **Total VO time:** ~3–4 minutes of narration over 6m08s of footage
- **Speed up:** The 1:48–3:22 thinking section (94 seconds) should be sped up to ~20-30 seconds with VO over it
- **Cuts:** Consider cutting the typo at 4:37 (`bpsai planstatus` → `bpsai-pair plan status`)
- **Lower third:** Add task ID labels when inspecting T1.3 and T1.1
- **Music:** Light ambient under the exploration section, subtle build during plan output
