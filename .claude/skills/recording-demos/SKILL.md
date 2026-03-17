---
name: recording-demos
description: Reviews a user-provided demo script, proposes a clirec-ready version with timing and wait directives, then records on approval. Three phases — review, propose, record.
---

# Recording Demos

## When to Use

When the user provides a list of commands for a terminal demo recording and wants a clean, typo-free recording.

## Phases

### Phase 1: Review

User provides a script (raw commands, notes, or a previous demo-script.txt). Review it for:

- **Missing waits**: Every command that produces output needs `@wait-for!` after it
- **Prompt string**: Identify the project directory name for reliable prompt matching (e.g., `test-store$`)
- **Manual intervention points**: Claude Code sessions, interactive prompts that need human input
- **Reset requirements**: What state does the repo need to be in? Are there untracked artifacts to clean?
- **Timing**: Commands that need visual breathing room vs commands that should flow fast

Present findings to the user as a short list of issues/questions.

### Phase 2: Propose

Generate the complete `demo-script.txt` with all directives. Present it to the user with:

- The full script content
- The reset commands needed before recording
- Any manual intervention points called out
- Estimated recording duration

Wait for user approval or edits before proceeding.

### Phase 3: Record

On approval:

1. Write the script file to the target repo
2. Commit it and update the reset tag so it survives `git reset --hard`
3. Provide the exact commands to run:

```
cd ~/target-repo
git reset --hard <tag>
<cleanup commands for untracked artifacts>
clirec record -s demo-script.txt -o <name>
```

## Script Directive Reference

| Directive | Purpose | Example |
|-----------|---------|---------|
| `command` | Type command + Enter | `ls -la` |
| `@wait-for! "text" N` | Clear buffer, wait for text (max Ns) | `@wait-for! "myproject$" 3` |
| `@wait-for "text" N` | Wait for text without clearing | `@wait-for "[y/N]" 3` |
| `@wait N` | Fixed sleep | `@wait 2` |
| `@speed N` | Keystroke delay in ms | `@speed 40` |
| `@pause N` | Inter-command pause in seconds | `@pause 0.8` |
| `@key name` | Special key (ctrl-c, ctrl-d, enter, tab) | `@key ctrl-c` |

## Rules for Generating Scripts

- Every shell command gets `@wait-for! "projectdir$" 3` after it
- Interactive prompts (y/n) get `@wait-for "prompt text" 3` before the answer
- Claude Code sessions get `@wait-for! "projectdir$" 300` as a manual intervention point
- Default `@speed 40` and `@pause 0.8` at top of script
- Use `@wait 2` after Claude Code `❯` prompt detection to let UI finish rendering
- Add `@pause` after commands whose output the viewer should read (ls, cat, status)

## Common Pitfalls

- **Git-tracked recordings**: `*.clirec` must be in `.gitignore` and untracked, or `git reset --hard` overwrites them
- **Untracked artifacts**: Plan/task files from previous runs survive `git reset --hard` — clean them explicitly
- **Short prompt matches**: `@wait-for "$ "` matches too eagerly — use full prompt like `"myproject$"`
- **DA query garbage**: Raw recordings with Claude Code need post-processing — see `processing-recordings` skill
