---
name: spawn
description: Branch the current conversation into fresh agent sessions in tmux windows. Use when the user says "spawn a session/window for X", "peel this off into its own session", "branch/fork this into a new window", or wants to hand tasks to parallel interactive Claude/Codex/OMP sessions they can steer. Also "delegate X" / "run X in the background in its own session": delegated mode runs it on a hidden tmux server until it parks. For a quick fire-and-forget subtask whose result comes back here, use the host's subagent mechanism instead.
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
     task. The script pins it against auto-renaming, and fresh/branch Claude
     launches get the title `<session>/<name>` (`claude -n`), so the session
     is findable later with `claude --resume <session>` from that folder.
     A fresh start from a park block reuses the title, so several sessions
     can share it; exact recovery uses the UUID in the park block.
   - **Mode**: `"thinking"` (default) for sessions the user steers live; they
     go to the default tmux server. `"delegated"` for research/admin/
     implementation work that runs to a decision point on its own; it goes to
     a separate server (`tmux -L delegated`) that the user's pickers and status
     bar don't show. Use delegated when the user says "delegate", "in the
     background", or the task needs no live steering.
   - **Remote Control** (`"remote": true`, claude only): enables Claude Code's
     Remote Control so the user can watch and steer the spawned session from
     their phone or claude.ai/code. **On by default for every claude spawn**
     (Jason, 09.10.2026): set `"remote": true` unless an exception under
     "Remote Control" below applies. codex has no per-session equivalent (its Remote Control is a
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
   - one line per window: name, agent, resolved directory, Remote Control
     on/off (and why, if off), and the script's status (flag any window whose
     agent did not come up);
   - how to get there: `tmux switch-client -t <session>` (inside tmux) or
     `tmux attach -t <session>` (outside); for delegated windows
     `tmux -L delegated attach -t <session>` (from a plain terminal, not
     inside another tmux client);
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
- **Git end state** — branch, remote, push, history rewrite or not, deploy; carry the
  push authorization this conversation actually has. A brief may allow pushing
  to a private remote the user set up, so CI runs. Every commit there follows
  the commit-review rule (`Reviewed-by:` trailer).
- **Hub ownership** — what related work stays in the originating thread, so
  the child doesn't duplicate it.
- **A clear first action** so the agent starts productively.
- **Verification and risks** — checks already run with results, unresolved
  risks, and, when this brief continues earlier work, the exact old session
  UUID with its resume command (from the main session only; inside a subagent
  the session-ID variables can name the wrong session).
- **Delegated mode only**: name one deliverable, its acceptance check and its
  stop condition, then end the brief with these two paragraphs verbatim:
  "Stop rule: after two failed repair cycles against the same acceptance
  gate, stop and return the evidence and the open decision; continue only
  after stating a concrete new hypothesis and the check that would
  distinguish it. Reuse accepted artifacts; re-review only changed material
  and affected interfaces. Mandatory independent commit reviews still apply."
  and "Work to a decision point without waiting on the user; collect open
  questions into one bundle. When you reach a decision point or are done,
  end with /park."

Keep the brief at most 1k tokens: aim for at most 500 words and 4,000 characters including paths and code, less for dense text; link detailed evidence rather than copying it. Fresh mode uses neither `resume` nor `branch`; an explicit user request for either still wins. Design-to-implementation is a natural point to park and continue fresh; the context trial and provider budget live in `~/.claude/context-coding/ai-tools.md`.

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
    "name": "vendor-research",
    "mode": "delegated",
    "prompt": "<full standalone brief ending with the /park instruction>"
  },
  {
    "name": "page-round",
    "agent": "codex",
    "mode": "delegated",
    "approval": "never",
    "prompt": "<full standalone brief; the prompt also identifies the thread for codex-watch>"
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
its default model), `remote` `false`, `mode` `"thinking"`, `permission_mode`
unset (claude only: `default`, `acceptEdits`, `plan` or `auto`; set it only
when carrying a known mode over, as session-teleport does). `approval` and `sandbox` are unset by default (Codex only: `-a never | on-request`, `-s read-only | workspace-write`). Choose the host and complete acceptance requirements before launching:

| Codex job                                         | Mac                                                                                  | cairn                                                                                                |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Bounded staged review / implementation            | `codex-run review-staged / implement`; implement requires reviewed jason replacement | Same launcher; implement needs installed host profile                                                |
| Research / hosted search                          | `codex-run research`: read allowlist, shell network off, hosted search live          | Same; probe-validated host profile required                                                          |
| Research requiring shell HTTP                     | `codex-run research-net`: read allowlist, shell network enabled                      | Same; probe-validated host profile required                                                          |
| Browser acceptance                                | `codex-run browser`; supervisor owns denied steps                                    | Supervisor supplies a validated browser environment; launcher refuses                                |
| Interactive read-only                             | Manifest read-only has broad reads; use profile-backed exec for restricted research  | Same                                                                                                 |
| Interactive write/test                            | Only after supervisor probes/replaces jason: `approval: never`, sandbox unset        | No `jason` profile: use `codex-run implement`; the manifest cannot select config profiles            |
| SSH, protected config, launchd/systemd, heavy-run | Supervising session owns these steps                                                 | Same; wrap the actual heavy workload once, verify its cgroup, do not nest heavy-run inside the child |

Unattended Codex jobs use `approval: never`; any acceptance step that needs escalation belongs to the supervisor. Old network-enabled research and root-broad jason require supervisor replacement and fresh sessions; resume refuses replaced policies. Spawn TUIs do not run the launcher checks, so Mac write/test waits for the probed jason replacement. Hosted search remains an outbound channel. Unknown secrets inside allowed trees can be read; Linux glob matching is bounded and snapshots at process startup. Before the host probe passes, use `--profile-source` only with `--dry-run`; source launches remain unverified until then. Use the full launch table and install steps in `~/.claude/context-coding/ai-tools.md` and `~/.claude/codex-profiles/README.md`. For bounded jobs pass `--cwd DIR --prompt-file FILE`; only implement accepts `--add-dir` for required cache/output roots. Plain `sandbox: read-only` permits broad reads; explicit `sandbox: workspace-write` replaces jason and loses its read boundary/credential denies as well as its extra roots/network. Use profile-backed bounded exec for restricted research. Codex-run implement supplies a private tool-temp directory; the manifest cannot pass the equivalent shell-config overrides, so direct TUI tool acceptance stays with the supervisor per the profile README. Keep spawn for TUI windows; bounded exec jobs use `codex-run` with the harness background mechanism. Never assume that leaving `sandbox` unset supplies write/network access on cairn. Do not use broad trust entries for non-git cwd. A child that cannot satisfy the privileged part of an acceptance gate must hand it to the named supervisor.

For exec runs, the `codex-run: meta=...` / `codex-run: watch=...` lines identify the job before startup; run the printed watcher. Report “running” only after `thread.started`. For a TUI, run `codex-watch [-L delegated] SESSION:WINDOW`: it reads the spawn pane registration first, binds the launch to its rollout, and caches the thread for both watch and send. Legacy panes fall back to command-line prompt/resume matching. Record that ID after startup. Pass `--thread ID` for promptless launches, ambiguous matching or in-TUI thread switches (plus `-L delegated` for delegated windows). If matching is ambiguous, stop and obtain a proven ID; never choose the newest rollout. A window's existence is not thread startup. Preserve staged-only review and closed stdin for any direct exec/resume calls. Resume bounded jobs with `codex-run resume RUN.meta.json --prompt-file FILE`; use exact identity, never `--last`.

### Codex pane identity contract

The writer is `scripts/spawn_tmux_agents.py`; the reader is `~/bin/codex-watch` (`codex-send` is its symlink). Before Codex launches, the wrapper writes pane-local `@codex-spawn` JSON, schema `version: 1`: `launch_id` (32 hex characters), `mode` (`fresh`, `fork`, `resume`; the reader also writes `explicit`), runtime `pane_pid`, epoch `started_at`, canonical `cwd` and effective `codex_home`. Resume records `resume_id`; fork records `parent_id`. Fresh/fork briefs with text end with `[codex-spawn:LAUNCH_ID]`, a short model-visible tracking line. Promptless forks remain idle and require `--thread`; resumes need no footer. Registration is best-effort and does not change the agent's exit/cleanup behavior or the tmux server's CODEX_HOME.

On the first watch/send, a unique matching user rollout is cached as `binding: {thread_id, pid, started_at, explicit}`; the latter PID/start identify the Codex process. Fresh matching excludes forked rollouts, and fork matching requires `forked_from_id` equal to the recorded parent. Unknown fork formats or duplicate markers require `--thread`; no newest-file inference. Supervisor live acceptance must check that TUI forks emit user-thread metadata with `forked_from_id` and preserve the marker line; those runtime details remain unverified here. The reader validates the pane PID, Codex process, CODEX_HOME and rollout header. An explicit `codex-watch TARGET --thread UUID` also binds older panes after validating the rollout against the pane cwd (or the recorded exact resume ID). It replaces stale/malformed registration when validation succeeds. Before a rebind is validated, the reader invalidates the old cache and launch fallback. If caching cannot be verified, the explicit ID still selects the rollout for that invocation and prints a warning; keep passing it. Later calls without `--thread` fail closed. A different CODEX_HOME leaves its owner's registration untouched and aborts before sending; failed invalidation also aborts. Use the same `-L SOCKET` throughout. The binding lives in tmux only, not in Codex config.

After in-TUI `/new` or `/resume`, use `--thread` again: those switches can keep the same process, so launch metadata cannot discover the new active thread. Until rebound, the cached thread remains the old one, so send busy checks and confirmation can consult the wrong rollout. Rebind before sending. To discard registration manually, clear only that pane's option with `tmux [-L SOCKET] set-option -p -u -t TARGET @codex-spawn`. Process inspection/foreground checks still require supervisor capabilities; `--thread` does not bypass them. Cache writes share the send lock. Concurrent identical resolutions are idempotent; a changed registration during resolution requires retrying. Deploying reader and writer separately is safe: old readers ignore the option and new readers retain legacy matching. Supervisor runs agent-config apply/check/audit after the shared skill change.

## Remote Control

`"remote": true` adds `--remote-control=<session>/<window-name>` to a claude launch line,
enabling Claude Code's Remote Control: the session registers with claude.ai and
becomes watchable/steerable from the user's phone or claude.ai/code (the
session title is the label shown there). Verified working for fresh, resume, and branch
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

**Default — deciding `remote` per task.** On for every claude spawn (Jason's
standing instruction, 09.10.2026). Leave it off only when:

- the user says so for this spawn ("no remote", "local only");
- the task is private/sensitive (therapy notes, private financials, credentials
  in scope): leave it off and say so in one line, so the user can turn it on;
- the agent is codex or OMP (the script rejects it).

The laptop-sleep caveat stays true (RC exits after ~10 min of sleep), but it is
no reason to skip it. Say in the summary that it is on (the post-spawn status
line notes `· remote control requested`; Remote Control finishes connecting a
few seconds later, so the user confirms it on their phone or the pane's footer).

## Notes

- On Linux, a tmux server the script starts gets its own systemd user scope with OOM score 100 (`systemd-run --user --scope -p Delegate=yes -- choom -n 100`), so sessions spawned from inside a service (the concierge on cairn) survive its restarts; it falls back to a plain server without a user systemd. A thinking spawn from any non-default server's pane (delegated, the concierge's own server) goes to the default server.
- Session names `.`/`:` are sanitized to `-`; the name `concierge` is
  reserved (supervised service) and the script refuses it.
- Requires tmux and the selected agent CLI on each host. Verify that host’s installed CLI supports the documented constructor before claiming continuity; OMP live fork/resume continuity remains untested here.
  (the agent pane prepends `~/.local/bin` and `~/bin` to its PATH, and when the
  script creates a session it sets the server's global PATH from a login
  shell, so popups and `run-shell` in a server born from an ssh one-liner
  still find `~/bin` tools; cairn 2026-09-09).
  It never spawns across machines — run it on the machine whose tmux you
  want the windows in. To move the current session to the other host, use
  the `session-teleport` skill (it calls this launcher over there).
- If tmux isn't installed or can't start, relay the script's stderr and give
  the user the composed brief(s) instead, so the handoff isn't lost.
- Don't read the spawned sessions' state by scraping their panes afterwards;
  the child sessions own their work. If the user asks how one is doing,
  `tmux capture-pane -p -t <target> | tail -40` is acceptable for a status
  glance. For what sits in a session's input box (typed text vs Claude's dim
  suggestion, or an open question/permission menu), run
  `agent-input [--host cairn]` instead: plain capture-pane drops the styling
  that tells them apart.

## Migration validation (2026-09-12)

OMP fresh, exact-ID resume, and exact-ID/path fork construction is based on installed OMP 18.1.18: `src/cli/flag-tables.ts` parses `--fork`, and `src/main.ts:createSessionManager` uses `SessionManager.forkFrom` for UUID/path sources. The flag is not shown in the short help display. Constructor fixtures cover all three harnesses without launching real sessions. OMP live startup, forked-context continuity, and follow-up remain to be exercised by the integrating owner; do not claim those checks have passed.
