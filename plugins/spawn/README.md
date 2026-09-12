# spawn

Branch a Claude Code, Codex, or OMP conversation into fresh, interactive agent
sessions in tmux windows, each seeded with a handoff prompt composed by the
running agent. tmux adaptation of Peter Hartree's Warp-based
[skill--pane](https://github.com/HartreeWorks/skill--pane); spawn mechanics
modeled on the `resume_in_tmux` idiom from `claude-sessions`.

## What it does

- One tmux **window per task**, in a session keyed to the task's directory
  (`session = basename(dir)`; existing session → windows appended, missing →
  created detached). Never steals focus.
- Prompt delivery is race-free: the brief goes to a temp file and the pane's
  _initial command_ reads it into argv (`claude -- "$(cat FILE)"`) — no
  send-keys, no lost keystrokes. The temp file is trashed on clean agent
  exit when a supported trash tool exists; otherwise retained. Failures retain it for recovery.
- On agent failure the window shows the exit status and waits for a keypress
  instead of vanishing.
- Post-spawn status check (~2s), best-effort: detects launch failure and
  Claude Code's folder-trust prompt, and confirms an agent process started
  (not that it is healthy).
- Window names are pinned (`@custom-name` window option + `automatic-rename
off`) so task names survive Claude Code's auto-titling — full protection
  requires the `window-renamed` hook from the companion tmux config; degrades
  to "mostly stable" without it.
- Spawned panes are tagged with `@spawn-agent <agent>` — a pgrep hint for status
  tooling (e.g. agent-status-bar) to identify agent panes behind wrapper
  shells. Harmless where nothing reads it.
- Remote Control (`"remote": true`, claude only) adds
  `--remote-control=<window-name>` so the session is watchable/steerable from
  the phone. Off by
  default; see the "Remote Control" section of SKILL.md for the trade-offs and
  the calibrated decision rule. Asymmetry: codex's Remote Control is a machine
  daemon (`codex remote-control start`), not a per-session flag, so the field
  is rejected for Codex and OMP.

## Environment assumptions

- tmux ≥ 3.4 (tested; argv-form pane commands: `tmux new-window … bash -c '…'`).
- `claude` / `codex` / `omp` on PATH; the script prepends `~/.local/bin` and `~/bin`
  for tmux servers started headless (cron/systemd) with a minimal PATH.
- Claude branch mode (`--fork-session`) requires an exact full UUID from `resume` or `CLAUDE_CODE_SESSION_ID`; a missing identity is rejected.
- Codex branch mode requires an exact full UUID from `resume` or `CODEX_THREAD_ID`; no latest-session fallback.
- OMP resume/fork requires an explicit full UUID or absolute transcript path. Its installed parser supports `--resume` and `--fork`; OMP live continuity is not yet verified in this staged migration.
- Session name `concierge` is reserved for a supervised service and refused;
  edit `RESERVED_SESSIONS` in the script if that doesn't apply to your setup.
- Remote Control (`"remote": true`) needs a Pro/Max/Team/Enterprise login on
  api.anthropic.com (not API keys; not Bedrock/Vertex/Foundry). The session
  exits after ~10 min of desktop sleep/outage — a lifecycle cost, not just a
  convenience. The `--remote-control=<name>` (equals) form is used so the
  flag's optional-name slot cannot swallow the positional prompt or be dropped
  when the name looks like an option.

## Usage (direct)

```bash
python3 scripts/spawn_tmux_agents.py manifest.json   # or '-' for stdin
```

Manifest: JSON array of
`{name, prompt?, agent?, dir?, branch?, resume?, model?, remote?}`
(`name` always required; `prompt` unless agent is none or resume is set) — see
`SKILL.md` for the full format. Output: JSON report (`spawned[]` with tmux
target + status per task) on stdout, warnings on stderr. Exit 0 = spawned,
1 = tmux failure mid-spawn, 2 = validation error (nothing spawned).

## Validation status

Created 2026-07-10. Tested on macOS (tmux 3.5a, Ghostty) and Ubuntu 24.04
(tmux 3.4) with Claude Code 2.1.x.

The September 12 portability changes are covered by offline constructor/validation tests in `tests/test_spawn_commands.py`. Those tests launch only fake harness functions and do not imply a real model session succeeded.
