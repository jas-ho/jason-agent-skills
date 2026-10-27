---
name: park
description: Park this session - write a dated State/Next/Waiting-on handoff block with a fresh-start command and exact recovery ID to STATUS.md in the project folder, and tell the sessions that should know (requester, dailies hub), so the session can be closed and continued later. Use when the user says /park, "park this", or when a delegated session reaches a decision point or is done.
---

# Park

Write a park block to `STATUS.md` in the project folder, message the live sessions that should know, then tell the user the session can be closed. Park must be safe to receive unattended (the hub sends `/park` via tmux send-keys): never ask questions, never wait for input, do no other work. Running it twice must not stack duplicate blocks or send duplicate messages.

## Steps

1. **Project folder** = the current working directory. Don't search elsewhere.

2. **Title and slug.** In Claude Code, read this session's custom title:

   ```bash
   f=$(ls ~/.claude/projects/*/"$CLAUDE_CODE_SESSION_ID".jsonl 2>/dev/null | head -1)
   [ -n "$f" ] && jq -r 'select(.type=="custom-title") | .customTitle' "$f" 2>/dev/null | tail -1
   ```

   - Title has the form `<slug>/<task>`: use it as is; `<task>` is the part after the first `/`.
   - Otherwise: slug = tmux session name (`tmux display -p -t "$TMUX_PANE" '#S'`) or, outside tmux, the cwd basename; task = a short kebab-case name you pick from the conversation (≤ 20 chars). Recovery uses the exact session ID, and the final message asks the user to `/rename <slug>/<task>`.

3. **Compose the block** from the conversation (one line each, concrete):

   ```markdown
   ## Park YYYY-MM-DD HH:MM · <task>
   - State: <where things stand, incl. key file paths>
   - Next: <the first concrete action on resume>
   - Waiting on: <me (since YYYY-MM-DD) | <person> (since YYYY-MM-DD) | nothing>
   - Decisions: <optional: settled choices the next session must not reopen>
   - Checks: <optional: verification already done, with results>
   - Risks: <optional: unresolved risks or open doubts>
   - Fresh start: <exact command for a new session that reads this block and the named files, without resume/fork>
   - Recovery: <exact resume command with this session's UUID | unavailable (<reason>)>
   - Prior recovery: <optional, one line per earlier session: exact resume command carried from a replaced block>
   - Notified: pending
   ```

   - Keep State, Next and Waiting on as the first three lines: the hub reads blocks with `rg '^## Park' -A4`. Omit an optional line rather than writing "none".
   - Rerun without new work: if a same-day block for this task exists and nothing happened since it (the `/park` arrived twice, or parking again without new turns), take all its lines except the heading and Notified verbatim; only the heading time changes.
   - `me` means the user: a decision or answer only they can give. Name the question in State or Next.
   - Fresh start, from the project directory, without restoring history: Claude `claude -n "<slug>/<task>" "Read STATUS.md, Park <date> <task>, and the named files; continue with Next."`; Codex `codex "Read STATUS.md, Park <date> <task>, and the named files; continue with Next."`; OMP a verified fresh constructor, else a plain instruction to start a new session with that prompt. The fresh session deliberately keeps the `<slug>/<task>` title so its own park replaces this block (step 4); find old sessions by Recovery UUID, not by title. Do not launch it during park. An explicit user request to resume or fork still wins.
   - Recovery is the exact command with this main session's own ID: Claude `claude --resume <$CLAUDE_CODE_SESSION_ID>`; Codex `codex resume <$CODEX_THREAD_ID>`; OMP `omp --resume <exact UUID or absolute .jsonl path>`. Never guess an ID or substitute the newest session; inside a subagent these variables can name the wrong session. Without a verified ID write `unavailable (<reason>)`.
   - Size: the block is a handoff of at most 1k tokens covering goal/deliverable, decisions, constraints, exact files, verification, unresolved risks and next action. Aim for at most 500 words and 4,000 characters including paths and code, less for dense text; link detailed evidence rather than copying it.
   - Context trial: read the dated context trial in `~/.claude/context-coding/ai-tools.md`; if it is absent or expired, keep the session's current choice and say so. It applies only to hub and mechanical sessions (a fresh session with the files and this block could carry on equally well); there the reply recommends the Fresh start when the trial's thresholds are met. Co-edit, synthesis/design and coaching/debrief/personal sessions are out of scope and are never pushed to a fresh start. Park itself never restarts or closes a session.
   - Time from `date '+%Y-%m-%d %H:%M'`. Keep the heading format exact: the hub greps `^## Park` across `~/Projects/**/STATUS.md`.

4. **Write STATUS.md** (newest block on top):
   - Missing: create it with `# Status`, a blank line, then the block.
   - Present: insert the block directly below the `# Status` line (or at the top if there is none).
   - Idempotency: if any `## Park` block with the same date and task already exists, remove it first (a block runs from its heading up to the next `## ` heading or end of file), so the new block replaces it at the top. One block per task per day. Before removing it, keep all its lines for step 3's rerun rule and step 5. Always carry its `Prior recovery:` lines into the new block; if its Recovery command differs from the new block's (a fresh session parking the same task the same day), add that command as another `Prior recovery:` line. Drop exact duplicates, so no recovery ID is ever lost.
   - Leave README.md and all other blocks untouched.
   - In a git work tree (`git rev-parse --is-inside-work-tree` succeeds; otherwise skip this), STATUS.md stays out of git, never staged or committed. If `git ls-files --error-unmatch STATUS.md` shows it is already tracked, leave it and say so in the reply. Otherwise, unless `git check-ignore -q STATUS.md` already ignores it, append its repo-relative path with a leading slash (`/$(git rev-parse --show-prefix)STATUS.md`) to the file `git rev-parse --git-path info/exclude` names, creating its directory first if missing (local to this clone; works in linked worktrees).

5. **Notify** the sessions that should know. Automatic, no questions. Afterwards replace the block's `Notified: pending` line.
   - **Recipients**, from this session's own context:
     1. the requester: whoever spawned, delegated or relayed this task (the `from` of a cross-session message that gave the task, or a brief line such as "From the dailies hub" or "relayed from <session>");
     2. sessions the conversation named as owning affected work (e.g. a project whose files this task found outdated but was not allowed to edit);
     3. the dailies hub, always in copy: the newest live session whose name starts with `dailies/hub` (date in the name decides); skip if this session is the hub.
     Don't guess further recipients from file paths. Never message this session itself. Deduplicate: a session in several roles gets one message.
   - **Match** each against `ListAgents` (load it and `SendMessage` via the host's deferred-tool search if needed). Only live sessions get a message. A named recipient that isn't live: say so in the reply; the hub copy covers it. Both tools must be allowed without a prompt: a permission prompt would hang an unattended park.
   - **Message**, one per recipient: the park block verbatim (every line except Notified) plus the STATUS.md path; so the block's State must carry the concrete IDs (commits, releases, issues). Notes meant for one recipient (e.g. corrections for files this session couldn't edit) are appended only to that recipient's message.
   - **Notified line**: `Notified: <names> (HH:MM)`, names exactly as `ListAgents` prints them, time of the latest send; with gaps `Notified: <names> (HH:MM); unreached: <names> (<reason>)`, or `Notified: none (<reason>)` when nothing went out.
   - **Rerun**: if step 3 reused the kept lines, send only to recipients not listed as notified in the kept Notified line (`pending`, `none` and `unreached` names count as not notified), and the rewritten line lists kept plus new names; otherwise send to all.
   - **No messaging available** (Codex, OMP, or the tools are missing), **no live recipient**, or **a send fails or is denied**: don't retry or wait; list them under `unreached:` (or `Notified: none (<reason>)` when nothing went out) and name the unreached recipients in the reply, so the user or the hub can relay (the hub also greps STATUS.md).

6. **Reply** with the block and one line: `Parked in <path>/STATUS.md. Safe to close this session.` Add the `/rename` hint from step 2 if needed. Then stop.
