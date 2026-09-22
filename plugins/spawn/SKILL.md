---
name: spawn
description: Branch the current conversation into fresh agent sessions in tmux windows. Use when the user says "spawn a session/window for X", "peel this off into its own session", "branch/fork this into a new window", or wants to hand tasks to parallel interactive Claude/Codex/OMP sessions they can steer. Not for fire-and-forget background work; use the host's subagent mechanism for that.
---

# Spawn agent sessions in new tmux windows

Branch the current conversation into one or more fresh agent sessions, each in
its own tmux window, seeded with a handoff prompt. Useful when a session ends
with a menu of next actions, or has become a hub accumulating side-tasks, and
the user wants to peel work off into parallel _interactive_ sessions without
losing the current thread.

The mechanism is bundled: `scripts/spawn_tmux_agents.py` creates the windows
and launches the agents race-free (prompt passed as argv via a temp file — no
send-keys). This skill's job is to translate the request into a good handoff
prompt per task, then call that script.

## Workflow

1. **Resolve the tasks.** If the request references list numbers ("1 and 3",
   "do 2"), map them to the most recent enumerated list in the conversation.
   Otherwise treat the free-text request as the task(s). If numbers are
   referenced but no enumerated list exists, ask which tasks rather than
   guessing. One window is spawned per task.

2. **Read the modifiers** from the request:
   - **Agent**: default to the current host (`claude` from Claude Code,
     `codex` from Codex, `omp` from OMP). Use the other host only if the user asks. Always put
     the resolved `agent` in the manifest because the bundled script's
     compatibility default is `claude`.
     `none` if the user says they'll drive the window themselves ("no agent",
     "I'll take it from there") — the window opens with a plain shell.
   - **Branch**: set `"branch": true` if the user says "branch" or "fork" —
     the new session then forks the _current_ one (shared history) instead of
     starting fresh. Only branch from the main session. Claude uses
     `CLAUDE_CODE_SESSION_ID`; Codex uses `CODEX_THREAD_ID`. For OMP, explicitly set `resume` to the current full session UUID or absolute transcript path; the launcher does not guess OMP identity. Inside a
     subagent, these can identify the wrong conversation. When the relevant
     current-session ID is unavailable or you are unsure, use fresh mode with
     a full standalone prompt.
   - **Resume**: set `"resume": "<session-id>"` if the user wants a _specific
     old session_ reopened in the window ("reopen/resume session X", "continue
     the votingfacts session in a window"). Prompt becomes optional — include
     one only if the user gives a directive for the resumed session.
     For Claude, `resume` must be a full session UUID (short ids do not work)
     and `dir` MUST be that session's own project directory (resume is
     project-scoped); resolve a nickname to the UUID by content (session-search search),
     or take the newest session in that project's `~/.claude/projects/` dir
     only when the user clearly means the latest one — otherwise ask.
     For Codex, resolve a thread name to its full UUID before launch. For OMP, use a full UUID or an absolute `.jsonl` transcript path; prefixes and picker shortcuts are not accepted by this launcher. Resume only a session without another running owner. Combine with
     `"branch": true` to fork the old session instead of continuing it.
   - **Model**: set `"model"` only when the user explicitly names one
     ("with opus"); otherwise omit it and let the selected agent CLI use
     its default. Do not change the requested harness or model based on
     routing guidance alone. If already-available routing guidance (e.g.
     the routing section of `context-coding/ai-tools.md`, when loaded)
     identifies a worthwhile alternative to sample, mention it briefly in
     the post-spawn summary as an option for a future run. Never delay,
     block, or auto-reroute the current spawn to consult routing guidance.
   - **Directory**: default to the current working directory — do not infer
     or look anything up. If the user names a project or path, resolve it
     (search `~/Projects` / `~/Code` only if needed); never invent a path.
     `dir` must be absolute and existing. The directory determines placement:
     session name = basename of dir; existing session gains windows, missing
     session is created (the same convention as claude-sessions and /start).
   - **Window name**: derive a short kebab-case task name (≤ 20 chars) per
     task. The script pins it against auto-renaming.
   - **Remote Control** (`"remote": true`, claude only): enables Claude Code's
     Remote Control so the user can watch and steer the spawned session from
     their phone or claude.ai/code. See "Remote Control" below for when to set
     it — it is **off by default** and is a deliberate, per-task choice, not a
     blanket on. codex has no per-session equivalent (its Remote Control is a
     machine daemon); the script rejects `"remote": true` for Codex and OMP.

3. **Compose the prompt per task** — the part only the running agent can do
   well, because it has the conversation context the new session lacks:
   - **Fresh mode** (default): a standalone handoff brief. The new agent
     starts with zero context (see checklist below).
   - **Branch mode**: a terse directive ("Now focus on: …"). The fork carries
     the full history — do not restate what it already has.

4. **Write the manifest** to a temp JSON file and run the bundled script
   (`scripts/spawn_tmux_agents.py` under this skill's base directory):

   ```bash
   python3 <skill-base-dir>/scripts/spawn_tmux_agents.py /path/to/manifest.json
   ```

   (Also accepts the manifest on stdin via `-`.) The script prints a JSON
   report with a per-window status check.

5. **Fire immediately** — no confirmation. Exception: "show me first" /
   "dry run" → print the composed prompt(s) plus resolved agent/dir per task
   and wait. After spawning, report:
   - one line per window: name, agent, resolved directory, and the script's
     status (flag any window whose agent did not come up);
   - how to get there: `tmux switch-client -t <session>` (inside tmux) or
     `tmux attach -t <session>` (outside);
   - when handing off hub work: a one-line division of labor — each spawned
     session owns its own open questions ("ask and answer there, not here"),
     and note anything that stays owned by this thread.

   The script does not steal focus; the user switches over when ready.

## Optional macOS desktop

After the launch report, use the shared `workspace` skill when a successfully spawned task deserves a separate desktop. Pass the report's `session` as `--tmux-session`; do not infer it from the task name or launch another agent. Follow that skill's reuse and prepare-and-return policy. Multiple tasks in one directory share a tmux session, so a new desktop may show its current window rather than the spawned `target`; report that target without changing other clients' selections. If desktop setup fails, keep the running agent and report the desktop failure separately. On other hosts, retain the tmux-only flow.

## Handoff brief checklist (fresh mode)

A fresh session has none of this conversation's context. Each brief must stand
alone and include:

- **Role framing** — one sentence: what this session is for.
- **The specific task** — what to produce, concretely; include tracker
  references (e.g. Linear issue IDs) when they exist.
- **Context and decisions** from this conversation — the why, constraints,
  prior choices, key facts.
- **File pointers** — absolute paths to read first; if the task is centered
  on one file the user is editing, make the first action `invoke the co-edit skill on <file>`.
- **Guardrails** — operations that need the user's explicit approval in the
  new session.
- **Hub ownership** — what related work stays in the originating thread, so
  the child doesn't duplicate it.
- **A clear first action** so the agent starts productively.

Keep it focused — enough to act, not a transcript dump.

## Manifest format

A JSON array, one object per task. `name` (window name) is the only
unconditional requirement; `prompt` is required unless `agent` is `"none"` or
`resume` is set:

```json
[
  {
    "name": "github-audit",
    "agent": "claude",
    "dir": "/Users/me/Projects/scratchpad/apart-exit",
    "prompt": "<full standalone handoff brief>"
  },
  {
    "name": "crux-questions",
    "branch": true,
    "model": "opus",
    "prompt": "Now focus on: draft the crux questions for Monday."
  },
  {
    "name": "old-thread",
    "resume": "2aa5c423-68d4-4419-b94f-727438e7167c",
    "dir": "/Users/me/Projects/that-sessions-project"
  },
  {
    "name": "watch-remotely",
    "remote": true,
    "prompt": "Long-running build; I'll check from my phone."
  }
]
```

The script's compatibility default is `agent: "claude"`, but this skill always
sets `agent` to the resolved current/requested host. Other defaults: `dir`
current working directory, `branch` `false`, `resume`/`model` unset (CLI picks
its default model), `remote` `false`.

## Remote Control

`"remote": true` adds `--remote-control=<window-name>` to a claude launch line,
enabling Claude Code's Remote Control: the session registers with claude.ai and
becomes watchable/steerable from the user's phone or claude.ai/code (the window
name is the label shown there). Verified working for fresh, resume, and branch
spawns. Requires a Pro/Max/Team/Enterprise login on api.anthropic.com (not API
keys, not Bedrock/Vertex/Foundry). Codex and OMP are rejected by this launcher. Codex Remote Control is a
machine-wide daemon (`codex remote-control start`), not a per-session flag.

Trade-offs (verified against Claude Code docs + the installed CLI, 2026-07-13):

- **Exposure**: the session transcript, tool output, and file paths become
  reachable from the phone/web (to the authenticated owner only). This is the
  main reason not to default it on — sensitive or personal work (therapy notes,
  private financials, credentials in scope) should stay local unless the user
  asks.
- **Lifecycle cost**: a Remote Control session's process **exits after ~10 min**
  of the desktop sleeping or losing network. On a laptop that will sleep, a
  remote-enabled fire-and-walk-away spawn is _more_ likely to die than a plain
  one, not less. Best fit: the machine stays awake (desktop, or a host that
  won't sleep) and the user genuinely intends to check from elsewhere.
- **Permissions**: prompts can be answered from the phone, across all permission
  modes — useful for a long task the user wants to unblock while away.
- **Billing/latency**: no separate charge (uses the existing subscription);
  transport is TLS via the normal Claude API, no material added latency.
- A few commands stay desktop-only when driving remotely (`/resume`, `/plugin`,
  `/cwd*`); everyday steering and `/model`/`/config` work from the phone.

**Calibrated line — deciding `remote` per task.** Default off. Then:

- **Explicit request** ("make it remote", "I'll watch from my phone", "enable
  Remote Control") → enable it. If the task touches sensitive content, note the
  exposure in one line so the user can reconsider, but follow the instruction.
- **A cue, not a request** ("I'm heading out", "I'll be away") → this signals
  _interest_, not consent to expose the session, and does not tell you the
  machine will stay awake (RC dies after ~10 min of sleep). Ask one short
  question — "want it remote-controllable from your phone? (the machine needs
  to stay awake)" — rather than assuming.
- **Proactive** (no signal from the user) → enable only when all hold: the task
  is a long unattended run, checking from elsewhere is clearly useful, nothing
  about it is sensitive, and the machine won't sleep. Otherwise leave it off.

Never enable it for private/sensitive work without an explicit ask, for quick
tasks, or when the machine is a laptop about to close. When you do enable it,
say so in the summary (the post-spawn status line notes `· remote control
requested`; Remote Control finishes connecting a few seconds later, so the user
confirms it on their phone or the pane's footer) so a wrong call is caught fast.

## Notes

- Session names `.`/`:` are sanitized to `-`; the name `concierge` is
  reserved (supervised service) and the script refuses it.
- Requires tmux and the selected agent CLI on each host. Verify that host’s installed CLI supports the documented constructor before claiming continuity; OMP live fork/resume continuity remains untested here.
  (the agent pane prepends `~/.local/bin` and `~/bin` to its PATH, and when the
  script creates a session it sets the server's global PATH from a login
  shell, so popups and `run-shell` in a server born from an ssh one-liner
  still find `~/bin` tools; cairn 2026-09-09).
  It never spawns across machines — run it on the machine whose tmux you
  want the windows in.
- If tmux isn't installed or can't start, relay the script's stderr and give
  the user the composed brief(s) instead, so the handoff isn't lost.
- Don't read the spawned sessions' state by scraping their panes afterwards;
  the child sessions own their work. If the user asks how one is doing,
  `tmux capture-pane -p -t <target> | tail -40` is acceptable for a status
  glance.

## Migration validation (2026-09-12)

OMP fresh, exact-ID resume, and exact-ID/path fork construction is based on installed OMP 18.1.18: `src/cli/flag-tables.ts` parses `--fork`, and `src/main.ts:createSessionManager` uses `SessionManager.forkFrom` for UUID/path sources. The flag is not shown in the short help display. Constructor fixtures cover all three harnesses without launching real sessions. OMP live startup, forked-context continuity, and follow-up remain to be exercised by the integrating owner; do not claim those checks have passed.
