#!/usr/bin/env python3
"""Spawn fresh AI-agent sessions into tmux windows.

Reads a JSON manifest of tasks; for each task it writes the handoff prompt to a
temp file, then creates a tmux window (in a session keyed to the task's
directory) whose initial command launches the agent with that prompt as argv.
No send-keys, no keystroke races: the pane command is
`bash -c 'prompt="$(cat FILE)"; if claude -- "$prompt"; then trash FILE; else ...fi'`
(on failure the window is held open and the brief kept for recovery).

Placement convention (matches claude-sessions / the /start skill):
  session name = sanitized basename of the task directory;
  session exists  -> new window appended (without stealing focus),
  session missing -> new detached session created.

Usage:
    spawn_tmux_agents.py <manifest.json>
    spawn_tmux_agents.py -              # read manifest from stdin

Manifest: a JSON array of task objects, each:
    {
      "name":   "short-name",         # required; tmux window name
      "prompt": "...",                # required unless agent is "none" or resume is set
      "agent":  "claude" | "codex" | "omp" | "none",   # default "claude"
      "dir":    "/abs/path",          # default: current working directory
      "branch": false,                # fork a session (shared history)
      "resume": "<session-id>",       # reopen this specific old session
      "model":  "<model>",            # optional override (claude --model / codex -m)
      "remote": false                 # claude only: enable Remote Control (phone/web)
    }

Launch line per (agent x branch x resume):
    claude, fresh          : claude -- "$prompt"
    claude, branch         : claude --resume $CLAUDE_CODE_SESSION_ID --fork-session -- "$prompt"
    claude, resume         : claude --resume <id> [-- "$prompt"]
    claude, resume+branch  : claude --resume <id> --fork-session [-- "$prompt"]
    codex,  fresh          : codex -- "$prompt"
    codex,  branch         : codex fork $CODEX_THREAD_ID -- "$prompt"  (required exact ID)
    codex,  resume         : codex resume <id> [-- "$prompt"]
    codex,  resume+branch  : codex fork <id> [-- "$prompt"]
    omp,    fresh          : omp [--model <model>] -- "$prompt"
    omp,    resume         : omp --resume <exact-id-or-path> [-- "$prompt"]
    omp,    resume+branch  : omp --fork <exact-id-or-path> [-- "$prompt"]
    none                   : plain shell in the directory (no agent launched)

Remote Control (claude only): with "remote": true, the launch line gains
`--remote-control=<window-name>` (the =name form binds the value so the flag's
optional name slot can't swallow the positional prompt; the name becomes the
label in the claude.ai session list). Requires a Pro/Max/Team/
Enterprise login on api.anthropic.com; the session becomes reachable (transcript,
tool output, file paths) from the phone/web, and its process exits after ~10 min
of desktop sleep/outage. codex Remote Control is a machine-level daemon
(`codex remote-control start`), not a per-session flag, so "remote" is rejected
for codex and omp — see SKILL.md.

Output: a JSON report on stdout — one entry per task with the tmux target and
a post-spawn status check. Warnings/errors go to stderr. Exit codes:
0 = all spawned, 1 = tmux failure mid-spawn, 2 = manifest validation error.

Stdlib only. Requires tmux >= 3.4 (tested; argv-form pane commands).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

# Session names that supervised services own; never spawn into them.
RESERVED_SESSIONS = {"concierge"}

SHELL_COMMANDS = {"bash", "zsh", "sh", "fish", "dash"}

VALID_AGENTS = ("claude", "codex", "omp", "none")

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

# Model ids/aliases: letters, digits, then dots/underscores/slashes/colons/dashes.
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$")


def sanitize_session_name(name: str) -> str:
    """tmux session names may not contain '.' or ':'; be conservative and
    collapse anything outside [A-Za-z0-9_-] (tmux target parsing is subtle)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return cleaned or "spawn"


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=False)


def login_shell_path_into_server() -> None:
    """Give the tmux server a login shell's PATH.

    A server created from a non-login command (an ssh one-liner, cron, systemd)
    keeps that command's PATH as its global environment, and every popup and
    run-shell in it inherits the gap (cairn 2026-09-09: ~/.local/bin and ~/bin
    missing, so the session pickers found nothing). Interactive panes are login
    shells and never noticed. Best effort: a failure leaves the server as it was.
    """
    shell = os.environ.get("SHELL") or "/bin/sh"
    marker = "SPAWN_LOGIN_PATH="
    try:
        out = subprocess.run(
            [shell, "-lc", f'printf "{marker}%s\\n" "$PATH"'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    # Delimited, not "the last line": login profiles and .zlogout print whatever they like.
    lines = [
        ln[len(marker) :] for ln in out.stdout.splitlines() if ln.startswith(marker)
    ]
    path = lines[-1].strip() if lines else ""
    if out.returncode == 0 and "/" in path:
        tmux("set-environment", "-g", "PATH", path)


def session_exists(session: str) -> bool:
    # '=' prefix forces exact match (plain -t does prefix matching).
    return tmux("has-session", "-t", f"={session}").returncode == 0


def validate(tasks: list) -> list[str]:
    """Return a list of human-readable errors; empty means the manifest is good."""
    errors: list[str] = []
    if not isinstance(tasks, list) or not tasks:
        return ["manifest must be a non-empty JSON array of task objects"]
    for i, task in enumerate(tasks):
        where = f"task {i + 1}"
        if not isinstance(task, dict):
            errors.append(f"{where}: not an object")
            continue
        name = task.get("name")
        if not name or not str(name).strip():
            errors.append(f"{where}: missing 'name' (window name)")
        agent = (task.get("agent") or "claude").lower()
        if agent not in VALID_AGENTS:
            errors.append(
                f"{where}: unknown agent {agent!r} (expected one of {VALID_AGENTS})"
            )
        resume = task.get("resume")
        if resume is not None and (not isinstance(resume, str) or not resume.strip()):
            errors.append(f"{where}: 'resume' must be a non-empty session-id string")
        elif resume:
            rid = resume.strip()
            # shlex.quote stops shell injection but not option injection
            # (e.g. resume: "--last" would silently pick another session).
            # Full UUIDs identify sessions; OMP also accepts absolute transcript paths.
            if rid.startswith("-") or re.search(r"[\x00-\x1f]", rid):
                errors.append(
                    f"{where}: 'resume' looks like an option or contains "
                    f"control characters: {rid!r}"
                )
            elif agent in ("claude", "codex") and not UUID_RE.fullmatch(rid):
                errors.append(
                    f"{where}: {agent} 'resume' must be a full canonical UUID, "
                    f"got {rid!r}"
                )
            elif agent == "omp" and not (
                UUID_RE.fullmatch(rid)
                or (os.path.isabs(rid) and rid.endswith(".jsonl"))
            ):
                errors.append(
                    f"{where}: omp resume requires a full UUID or absolute transcript .jsonl path"
                )
        if resume and agent == "none":
            errors.append(f"{where}: resume is meaningless with agent 'none'")
        model = task.get("model")
        if model is not None and (
            not isinstance(model, str) or not MODEL_RE.match(model.strip())
        ):
            errors.append(f"{where}: 'model' must be a plain model name, got {model!r}")
        if model and agent == "none":
            errors.append(f"{where}: model is meaningless with agent 'none'")
        remote = task.get("remote")
        # key presence, not get(): distinguishes an absent field from an
        # explicit `"remote": null` (both make .get() return None).
        if "remote" in task and not isinstance(task["remote"], bool):
            errors.append(
                f"{where}: 'remote' must be true or false, got {task['remote']!r}"
            )
        if remote:
            if agent == "none":
                errors.append(f"{where}: remote is meaningless with agent 'none'")
            elif agent in ("codex", "omp"):
                errors.append(
                    f"{where}: remote is claude-only; this launcher has no per-session remote flag for {agent}"
                )
        prompt = task.get("prompt")
        if agent != "none" and not resume and (not prompt or not str(prompt).strip()):
            errors.append(
                f"{where}: missing non-empty 'prompt' (required unless agent is 'none' "
                "or 'resume' is set)"
            )
        directory = task.get("dir") or os.getcwd()
        if not os.path.isabs(directory):
            errors.append(f"{where}: dir must be an absolute path, got {directory!r}")
        elif not os.path.isdir(directory):
            errors.append(f"{where}: dir does not exist: {directory}")
        session = sanitize_session_name(os.path.basename(os.path.normpath(directory)))
        if session in RESERVED_SESSIONS:
            errors.append(
                f"{where}: session {session!r} is reserved (supervised service); "
                "use a different directory"
            )
        if task.get("branch") and agent == "none":
            errors.append(f"{where}: branch is meaningless with agent 'none'")
        if "branch" in task and not isinstance(task["branch"], bool):
            errors.append(f"{where}: 'branch' must be true or false")
        if task.get("branch") and not resume and agent in ("claude", "codex", "omp"):
            key = {"claude": "CLAUDE_CODE_SESSION_ID", "codex": "CODEX_THREAD_ID"}.get(
                agent
            )
            sid = os.environ.get(key, "").strip() if key else ""
            if not UUID_RE.fullmatch(sid):
                errors.append(
                    f"{where}: branch needs an exact owning session UUID; provide resume explicitly or use fresh mode"
                )
    return errors


def build_command(
    agent: str,
    branch: bool,
    resume: str | None,
    model: str | None,
    promptfile: str | None,
    remote_name: str | None = None,
) -> str:
    """The bash command string the new pane runs."""
    if agent not in ("claude", "codex", "omp"):
        raise ValueError(f"unsupported agent: {agent}")
    if remote_name and agent != "claude":
        raise ValueError("remote is supported only for Claude")
    if resume:
        if (
            not isinstance(resume, str)
            or re.search(r"[\x00-\x1f]", resume)
            or resume.startswith("-")
        ):
            raise ValueError("resume requires a safe exact session identity")
        exact = bool(UUID_RE.fullmatch(resume))
        if agent == "omp":
            exact = exact or (os.path.isabs(resume) and resume.endswith(".jsonl"))
        if not exact:
            raise ValueError(
                "resume requires a full UUID or, for OMP, an absolute transcript path"
            )
    elif branch:
        key = {"claude": "CLAUDE_CODE_SESSION_ID", "codex": "CODEX_THREAD_ID"}.get(
            agent
        )
        resume = os.environ.get(key, "").strip() if key else ""
        if not UUID_RE.fullmatch(resume):
            raise ValueError(
                "branch requires an exact owning session UUID; no latest-session fallback"
            )
    arg = ' -- "$prompt"' if promptfile else ""
    if agent == "claude":
        opt = f" --model {shlex.quote(model)}" if model else ""
        # Remote Control: use the `--remote-control=<name>` form. The name slot
        # is OPTIONAL, so the space form `--remote-control <name>` is ambiguous
        # when the name is absent (swallows the positional prompt) or looks like
        # an option (dropped, then the prompt is swallowed); `=` binds the value
        # unambiguously in every case. The name is also the label shown in the
        # claude.ai session list. Both forms verified live against the CLI.
        if remote_name:
            opt += f" --remote-control={shlex.quote(remote_name)}"
        if resume:
            fork = " --fork-session" if branch else ""
            launch = f"claude{opt} --resume {shlex.quote(resume)}{fork}{arg}"
        else:
            launch = f"claude{opt}{arg}"
    elif agent == "codex":
        opt = f" -m {shlex.quote(model)}" if model else ""
        if resume:
            verb = "fork" if branch else "resume"
            launch = f"codex {verb}{opt} {shlex.quote(resume)}{arg}"
        else:
            launch = f"codex{opt}{arg}"
    else:  # omp: installed CLI flag-tables.ts and main.ts createSessionManager
        opt = f" --model {shlex.quote(model)}" if model else ""
        if resume:
            flag = "--fork" if branch else "--resume"
            launch = f"omp{opt} {flag} {shlex.quote(resume)}{arg}"
        else:
            launch = f"omp{opt}{arg}"
    # ~/.local/bin may be missing from the tmux server's PATH (e.g. a server
    # started by cron/systemd on a headless host). On success the pane cleans
    # up its own prompt file; on failure the file is kept for recovery and the
    # window is held open ("exited with status" is the marker check_status
    # looks for — keep them in sync).
    if promptfile:
        pf = shlex.quote(promptfile)
        read_prompt = f'prompt="$(cat {pf})"\n'
        on_success = (
            f"if command -v trash >/dev/null 2>&1; then trash {pf}; "
            f"elif command -v gio >/dev/null 2>&1; then gio trash {pf}; "
            f"else printf 'Handoff brief retained at %s\\n' {pf}; fi"
        )
        preserve = f"printf 'Handoff brief preserved at %s\\n' {pf}; "
    else:
        read_prompt, on_success, preserve = "", ":", ""
    return (
        'export PATH="$HOME/.local/bin:$HOME/bin:$PATH"\n'
        f"{read_prompt}"
        f"if {launch}; then {on_success}; else st=$?; echo; "
        f'echo "{agent} exited with status $st."; '
        f"{preserve}"
        'echo "Press any key to close this window."; read -r -n1; fi'
    )


def spawn(task: dict) -> dict:
    name = str(task["name"]).strip()
    agent = (task.get("agent") or "claude").lower()
    branch = bool(task.get("branch"))
    directory = task.get("dir") or os.getcwd()
    session = sanitize_session_name(os.path.basename(os.path.normpath(directory)))

    resume = (task.get("resume") or "").strip() or None
    model = (task.get("model") or "").strip() or None
    remote = bool(task.get("remote"))
    cmd_args: list[str] = []
    promptfile = None
    if agent != "none":
        prompt = str(task.get("prompt") or "")
        if prompt.strip():
            fd, promptfile = tempfile.mkstemp(prefix="spawn-prompt.")
            with os.fdopen(fd, "w") as fh:
                fh.write(prompt)
        remote_name = name if remote else None
        cmd_args = [
            "bash",
            "-c",
            build_command(agent, branch, resume, model, promptfile, remote_name),
        ]

    fmt = "#{session_name}:#{window_index}|#{pane_id}"
    if session_exists(session):
        # -d: append without switching focus (the user may be attached here).
        result = tmux(
            "new-window",
            "-d",
            "-t",
            f"={session}:",
            "-n",
            name,
            "-c",
            directory,
            "-P",
            "-F",
            fmt,
            *cmd_args,
        )
    else:
        # Only a server this call brings into being gets its PATH set: an existing
        # server's global environment may be deliberate, whatever created it. The
        # check is best effort (a server created by someone else between the two
        # tmux calls would be treated as ours).
        server_was_running = tmux("list-sessions").returncode == 0
        result = tmux(
            "new-session",
            "-d",
            "-s",
            session,
            "-n",
            name,
            "-c",
            directory,
            "-P",
            "-F",
            fmt,
            *cmd_args,
        )
        if result.returncode == 0 and not server_was_running:
            login_shell_path_into_server()
    if result.returncode != 0:
        if promptfile:
            print(f"Handoff brief retained at {promptfile}", file=sys.stderr)
        raise RuntimeError(f"tmux failed for {name!r}: {result.stderr.strip()}")

    target, pane_id = result.stdout.strip().split("|")
    # Pin the window name: @custom-name is defended by the window-renamed hook
    # (if configured); automatic-rename off stops tmux's own renaming and
    # allow-rename off blocks the agent's terminal-title escape sequences.
    pin_results = [
        # Tag only the spawned pane: split panes in the same window may run
        # unrelated commands and must not inherit the agent classification.
        tmux("set-option", "-p", "-t", pane_id, "@spawn-agent", agent),
        tmux("set-option", "-w", "-t", target, "@custom-name", name),
        tmux("set-option", "-w", "-t", target, "automatic-rename", "off"),
        tmux("set-option", "-w", "-t", target, "allow-rename", "off"),
        # Re-assert the name: a fast-starting agent could have retitled the
        # window in the gap between window creation and the option calls.
        tmux("rename-window", "-t", target, name),
    ]
    if any(r.returncode != 0 for r in pin_results):
        print(
            f"spawn: warning: could not pin window name for {name!r} "
            "(agent may rename it)",
            file=sys.stderr,
        )

    return {
        "name": name,
        "agent": agent,
        "branch": branch,
        "resume": resume,
        "model": model,
        "remote": remote,
        "dir": directory,
        "session": session,
        "target": target,
        "pane_id": pane_id,
    }


def pane_child_command(pane_pid: str) -> str | None:
    """Name of a child process of the pane's shell, if any."""
    pgrep = subprocess.run(
        ["pgrep", "-P", pane_pid], capture_output=True, text=True, check=False
    )
    pids = pgrep.stdout.split()
    if not pids:
        return None
    ps = subprocess.run(
        ["ps", "-o", "comm=", "-p", pids[0]],
        capture_output=True,
        text=True,
        check=False,
    )
    return ps.stdout.strip() or "unknown"


def check_status(entry: dict) -> str:
    result = tmux(
        "display-message",
        "-p",
        "-t",
        entry["pane_id"],
        "-F",
        "#{pane_current_command}|#{pane_title}|#{pane_pid}",
    )
    if result.returncode != 0:
        return "window closed — agent crashed at startup"
    command, title, pane_pid = result.stdout.strip().split("|", 2)
    if entry["agent"] == "none":
        return f"shell ready ({command})"
    text = tmux("capture-pane", "-p", "-t", entry["pane_id"]).stdout
    # Failure marker first — a stale "Claude Code" pane title can outlive an
    # exited process and would otherwise mask a launch failure as "up".
    if "exited with status" in text:  # failure marker from build_command
        return "agent failed at launch — window held open with the error, attach to inspect"
    # Remote Control connects a few seconds after launch, past this ~2s check,
    # so don't try to detect it here (a fixed-time scrape mostly reports "not
    # yet" even on success). Just note it was requested; the user confirms on
    # their phone / the pane's footer.
    rc = (
        " · remote control requested (verify on phone or pane)"
        if entry.get("remote")
        else ""
    )
    if "Claude Code" in title:
        return f"up (Claude Code){rc}"
    # claude: "trust this folder"; codex: "Do you trust the contents of this directory"
    if "trust this folder" in text or "Do you trust the contents" in text:
        return "waiting at folder-trust prompt — attach and confirm before it can start"
    # The pane runs a bash wrapper, so pane_current_command shows the shell
    # even when the agent is alive underneath — look for a child process
    # (best-effort: confirms something launched, not that it is healthy).
    child = command if command not in SHELL_COMMANDS else pane_child_command(pane_pid)
    if child:
        return f"up ({child}){rc}"
    return f"agent not detected (pane running {command}) — attach to inspect"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "-":
            raw = sys.stdin.read()
        else:
            with open(sys.argv[1]) as fh:
                raw = fh.read()
    except OSError as exc:
        print(f"spawn: cannot read manifest: {exc}", file=sys.stderr)
        return 2
    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"spawn: invalid manifest JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate(tasks)
    if errors:
        for err in errors:
            print(f"spawn: {err}", file=sys.stderr)
        return 2

    spawned: list[dict] = []
    for task in tasks:
        try:
            spawned.append(spawn(task))
        except RuntimeError as exc:
            print(f"spawn: {exc}", file=sys.stderr)
            # Report what did spawn before failing.
            print(
                json.dumps(
                    {"spawned": spawned, "inside_tmux": bool(os.environ.get("TMUX"))}
                )
            )
            return 1

    time.sleep(2)
    for entry in spawned:
        entry["status"] = check_status(entry)

    print(
        json.dumps(
            {"spawned": spawned, "inside_tmux": bool(os.environ.get("TMUX"))}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
