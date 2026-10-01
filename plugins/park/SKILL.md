---
name: park
description: Park this session - write a dated State/Next/Waiting-on/Resume block to STATUS.md in the project folder so the session can be closed and resumed later. Use when the user says /park, "park this", or when a delegated session reaches a decision point or is done.
---

# Park

Write a park block to `STATUS.md` in the project folder, then tell the user the session can be closed. Park must be safe to receive unattended (the hub sends `/park` via tmux send-keys): never ask questions, never wait for input, do no other work. Running it twice must not stack duplicate blocks.

## Steps

1. **Project folder** = the current working directory. Don't search elsewhere.

2. **Title and slug.** In Claude Code, read this session's custom title:

   ```bash
   f=$(ls ~/.claude/projects/*/"$CLAUDE_CODE_SESSION_ID".jsonl 2>/dev/null | head -1)
   [ -n "$f" ] && jq -r 'select(.type=="custom-title") | .customTitle' "$f" 2>/dev/null | tail -1
   ```

   - Title has the form `<slug>/<task>`: use it as is; `<task>` is the part after the first `/`.
   - Otherwise: slug = tmux session name (`tmux display -p -t "$TMUX_PANE" '#S'`) or, outside tmux, the cwd basename; task = a short kebab-case name you pick from the conversation (≤ 20 chars). Resume falls back to the session ID, and the final message asks the user to `/rename <slug>/<task>`.

3. **Compose the block** from the conversation (one line each, concrete):

   ```markdown
   ## Park YYYY-MM-DD HH:MM · <task>
   - State: <where things stand, incl. key file paths>
   - Next: <the first concrete action on resume>
   - Waiting on: <me (since YYYY-MM-DD) | <person> (since YYYY-MM-DD) | nothing>
   - Resume: claude --resume "<slug>/<task>"
   ```

   - `me` means the user: a decision or answer only they can give. Name the question in State or Next.
   - Resume line without a prefixed title: `claude --resume <session-id>` (`$CLAUDE_CODE_SESSION_ID`); Codex: `codex resume <$CODEX_THREAD_ID>`.
   - Time from `date '+%Y-%m-%d %H:%M'`. Keep the heading format exact: the hub greps `^## Park` across `~/Projects/**/STATUS.md`.

4. **Write STATUS.md** (newest block on top):
   - Missing: create it with `# Status`, a blank line, then the block.
   - Present: insert the block directly below the `# Status` line (or at the top if there is none).
   - Idempotency: if any `## Park` block with the same date and task already exists, remove it first (a block runs from its heading up to the next `## ` heading or end of file), so the new block replaces it at the top. One block per task per day.
   - Leave README.md and all other blocks untouched.

5. **Reply** with the block and one line: `Parked in <path>/STATUS.md. Safe to close this session.` Add the `/rename` hint from step 2 if needed. Then stop.
