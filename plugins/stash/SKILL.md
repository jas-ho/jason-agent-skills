---
name: stash
description: "Idea parking lot (stored at ~/.claude/user-stash.md) - capture ideas, bookmark conversations, triage/prioritize"
---

## Harness and dependencies

Use the current harness's native file, shell, question and worker tools. CC calls its question tool AskUserQuestion; OMP uses ask; Codex uses the question interface actually exposed in the session, with a plain question when unavailable. Tool names in examples describe operations, not a requirement to nest Claude Code. Incoming command arguments are literal user text, never shell code. A skill invocation may supply the same text directly. Check each required CLI/service before its step; keep the workflow available and report missing dependencies. Preserve explicitly optional signal behavior below.

## Exact session bookmarks

Use an exact ID from the current host session metadata: CC may use `~/.claude/user-scripts/claude-session-id --resume`; Codex uses `codex resume <current-thread-id>`; OMP uses `omp --session <exact-current-session-file>` when verified by the installed CLI. Do not run the CC resolver in another harness. If the current ID/path cannot be established, save a context brief without a runnable resume command and say why. Never select the newest session or `--last`. Keep the existing shared stash path, regardless of harness.

# Idea Stash Command

User provided arguments: invocation text

You are helping the user manage their idea stash - a parking lot for ideas, conversation bookmarks, and things to work on later.

## Storage Location

`~/.claude/user-stash.md`

## Determine Mode

Based on `invocation text` and conversation context:

1. **If `invocation text` is "show"** → Show mode
2. **If `invocation text` is "triage"** → Triage mode
3. **If `invocation text` contains "done" or "complete"** → Mark done mode (e.g., "done backup system")
4. **If `invocation text` has other text** → Quick capture mode
5. **If `invocation text` is empty AND conversation has prior context** → Bookmark prompt
6. **If `invocation text` is empty AND fresh conversation** → Interactive menu

## Mode: Show

Display a summary of active stash items (not full content):

1. Read `~/.claude/user-stash.md`
2. Parse items between the header and `## Completed` section
3. For each item, show:
   - Title
   - Type
   - Captured date
   - One-line summary if available
4. Do NOT show completed items by default
5. If user asks, can show completed items too

Format as a simple numbered list (NOT a table - tables wrap poorly in terminals):

```
1. Backup System Setup & Storage Cleanup
   paused-conversation | 2025-12-10
   Robust automated backups, cleaner pCloud organization

2. Claude Code Skills Prioritization
   paused-conversation | 2025-12-10
   Choose highest-leverage skills based on workflow bottlenecks
```

## Mode: Triage

Interactive prioritization session:

1. Read `~/.claude/user-stash.md` and display summary of active items
2. Ask: "What are you in the mood for?" or "How much time/energy do you have?"
3. If user mentions capacity constraints, consider loading relevant files from `~/.claude/context-personal/` (your judgment on which files help)
4. Based on response, recommend items to work on
5. Support iteration:
   - "Tell me more about X" → Show full details of that item
   - "Mark X as done" → Move to completed section
   - "Remove X" → Delete item entirely
   - "Deprioritize X" → Add note or move down

## Mode: Mark Done

Move an item to the Completed section:

1. Find the item matching the user's description
2. Add `[DONE]` prefix to the title
3. Add `- **Completed:** YYYY-MM-DD` line
4. Move the entire item block to after `## Completed`
5. Confirm what was marked done

## Mode: Quick Capture

Capture a new idea from the provided text:

1. Parse `invocation text` to understand the idea
2. If unclear, ask ONE clarifying question (keep friction low)
3. Determine type:
   - `idea` - general idea or feature request
   - `known-fix` - specific improvement with clear direction
   - `paused-conversation` - bookmarked conversation to continue
   - `raw-dump` - unprocessed thoughts needing later review
4. Create item with structure below
5. Prepend to active items section (most recent first)
6. If this is a mid-conversation capture (not a fresh session), ask: "Want to bookmark this conversation too so you can resume later?" If yes, resolve the owning harness's exact session using **Exact session bookmarks** above and add that resume command to the item; if identity is unavailable, save a context brief without a runnable command.
7. Confirm capture with brief summary

## Mode: Bookmark Prompt (mid-conversation)

Offer to bookmark the current conversation:

1. Summarize what the conversation has been about
2. Ask: "Want me to bookmark this conversation to continue later?"
3. If yes:
   - Resolve the owning harness's exact session using **Exact session bookmarks** above; never use the Claude resolver from Codex or OMP.
   - Create item with type `paused-conversation`
   - Include the verified resume command, or a context brief and the missing-identity explanation if no exact command is available.
4. If no, ask what else they'd like to do with stash

## Mode: Interactive Menu (fresh conversation)

Use the native question tool to present options:

1. "Triage/prioritize" - review stash and decide what to work on
2. "Show stash" - see what's parked
3. "Capture new idea" - add something to the stash

Order reflects likely intent for fresh conversation (triage first).

## Item Structure

**Active item:**

```markdown
## [Title/Summary]

- **Type:** idea | paused-conversation | known-fix | raw-dump
- **Captured:** YYYY-MM-DD
- **Value/Impact:** [one line on what this enables, if clear]
- **Blockers:** [if any dependencies or blockers]
- **Resume:** `[verified resume command for the owning harness]` [paused-conversation only; omit if exact identity is unavailable]

[Description/context in free text]
```

**Completed item:**

```markdown
## [DONE] [Title/Summary]

- **Type:** idea | paused-conversation | known-fix | raw-dump
- **Completed:** YYYY-MM-DD
- **Captured:** YYYY-MM-DD

[Original description, possibly summarized]
```

## Important Guidelines

- **Keep friction LOW** - quick capture is the priority
- **Don't over-structure** - free text is fine, Claude can interpret later
- **Grep-friendly** - `[DONE]` prefix on completed items allows filtering
- **Summaries first** - show mode displays titles/types, not full content
- **Respect the user's time** - one clarifying question max during capture
- **Session identity** - follow **Exact session bookmarks** for the owning harness; if identity cannot be verified, save context without a runnable resume command.
