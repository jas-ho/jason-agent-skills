---
name: handoff
description: "Generate a short context brief for continuing this work in a new thread."
---

## Harness and dependencies

Use the current harness's native file, shell, question and worker tools. CC calls its question tool AskUserQuestion; OMP uses ask; Codex uses the question interface actually exposed in the session, with a plain question when unavailable. Tool names in examples describe operations, not a requirement to nest Claude Code. Incoming command arguments are literal user text, never shell code. A skill invocation may supply the same text directly. Check each required CLI/service before its step; keep the workflow available and report missing dependencies. Preserve explicitly optional signal behavior below.

OMP reserves `/handoff` for its native operation; invoke this personal brief as `/session-handoff`. Other clients use their supported command surface. This workflow only writes a brief; it does not transfer ownership of a live session.

# Handoff

Generate a context brief for continuing this work in a new thread.

## Format

```
## Handoff: [Task]
**Context**: [1-2 sentences - what and why]
**Next**: [concrete first action]
```

Add **Files**, **Blockers**, **Time box**, **Tried** only if relevant.

## Principles

- Brief (< 10 lines)
- Actionable (next step is concrete, not vague)
- Self-contained (new thread can start without searching)

Adapt naturally to situation. If stuck, note what was tried; if pausing, note where we left off.

## Usage

`/handoff`: auto-detect task from conversation
`/handoff "task name"`: specify focus explicitly

To launch the continuation directly (new tmux window with an agent already primed with the brief), use the `spawn` skill instead.
