---
name: session-teleport
description: Move the current live Claude Code or Codex session to Jason's other host (Mac <-> cairn) and resume it there, with Remote Control from the Mac to cairn. Use for "teleport/move/hand off this session to cairn/the Mac", "continue this on cairn so I can close the laptop", or picking up a cairn session on the Mac. Not claude.ai cloud sessions (`claude --teleport`) and not branching into a new window (spawn).
---

# Session teleport

`session-teleport` (in `~/bin` on both hosts) snapshots this session's transcript, copies it to the other host, installs it under the mapped cwd (`/Users/jason` <-> `/home/jason`) and resumes it there in a tmux window, with Remote Control for Claude. The first prompt over there tells the resumed agent it changed hosts. `session-teleport -h` has the full behaviour, options and exit codes; read it only when a case below doesn't cover what happened.

1. Run `session-teleport push` (the default HOST is the other machine). Add `--message "<next step>"` when Jason said what should happen next, so the resumed agent continues instead of only orienting. Use `--no-remote` if Jason doesn't want Remote Control.
2. Exit code 0: show any `Warning:` lines and the `Context:` lines that are not all-clear (missing or different files, uncommitted or unpushed git work that did not travel), then post the printed closing line as your final message and tell Jason to exit this session. If the closing line says NOT READY (e.g. a folder-trust prompt, which Remote Control cannot answer), say that the new copy needs one attach before he walks away. Stop working here: this copy is stale from now on.
3. Exit code 3 (the other host is unreachable; cairn cannot reach the Mac yet): post the printed `session-teleport pull ...` command as your closing line. Jason runs it on the other host, where the session resumes in the foreground.
4. Exit code 4 (refused): relay the reason. If the cwd is missing on the destination, ask Jason where to resume and rerun with `--cwd DIR`. Use `--replace` only after Jason confirms that the other copy's extra history can be archived. The concierge is never teleported.
5. Exit code 5 (delivery or launch failed, or its outcome is unknown): relay the message. A rerun of the same command will not start a second copy of a running session; otherwise give Jason the printed manual resume command.

If a prompt starting with `[session-teleport]` arrives, you are the resumed copy. Follow it: orient briefly, recheck host-specific assumptions, and do not retry the teleport that brought you here.
