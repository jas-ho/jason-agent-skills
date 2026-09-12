---
name: automation
description: Set up, inspect or troubleshoot scheduled automation on macOS or Linux, including existing Claude, Codex and OMP jobs.
---

# Scheduled automation

Interpret invocation text as setup, troubleshoot or explore; infer from the current request where clear. Use the current harness's native question tool for missing requirements. Confirm only unresolved schedule, destination, ownership or side effects. The host doing the work need not be the CLI that an existing job runs.

## Inspect first

1. Read the current project's instructions and identify the owning code repository. Keep scripts and generated artifacts out of the Obsidian vault.
2. Run `uname -s`, inspect the relevant scheduler and exact job definition. Mac: `launchctl list`, `launchctl print gui/$(id -u)/<label>`, and its plist. Linux: `systemctl --user list-timers --all`, `systemctl --user cat <unit>`, `systemctl --user status <unit>`; inspect system units or crontab only when they own the job. Read cairn's `~/vps-setup/vps-desired-state.md` before changing its managed services.
3. Trace the actual executable, cwd, arguments, PATH, logs and status through the wrapper. Use `command -v` with the job's environment; SSH may omit `~/bin` and `~/.local/bin`.
4. Correlate logs and observed PIDs with the owning scheduler. Long runtime alone is not permission to kill a process. Never kill a live interactive agent or restart cairn's concierge to test automation.
5. For explore, present a few concrete recurring tasks from the current project; avoid a workstation-wide scan without a need.

## Preserve existing jobs

Keep their current CLI and established output parser unless this task explicitly migrates them. CC's `is_error`, `subtype` and `result` fields describe CC JSON; they are not Codex or OMP response schemas. Check the installed CLI help and a disposable captured-format fixture before changing a launcher/parser. Preserve the exact owning job/session ID; never resume the latest session. New unattended jobs must have a finite timeout, explicit cwd/PATH, captured exit status and an observable output condition. Use the CLI's supported scoped unattended permissions; do not add a blanket permission bypass as a generic fix.

- CC: text print mode or its native JSON/stream-JSON result, according to the existing job. JSON success requires the final success result as well as process exit zero.
- Codex: native `codex exec`; if using JSON events, validate the installed event format and final turn completion/error. A thread-started record is not task success.
- OMP: inspect `omp --help` and its installed print/JSON mode; validate recorded assistant/error events. Do not reuse a CC parser.
- Ordinary scripts: propagate actual exit code and verify the intended artifact or external read outcome.

A new adapter is unfinished until its success, CLI failure, malformed/truncated output and timeout fixtures are checked. A workflow remaining discoverable is not evidence that an absent adapter works.

## Mac scheduling

Use the existing `~/bin/job-run` convention; read `~/bin/specs/job-run/README.md` and a current working plist such as `com.jason.garmin-pull.plist`. The runner owns freshness, locking, logs and timeout. Avoid duplicating healthchecks UUIDs, mkdir locks or log paths in new wrappers.

- Plist: `StartInterval` 1800, `RunAtLoad` true; `ProgramArguments` uses the resolved home path to `job-run <name> --every <duration> [--timeout <duration>] [--verify <path>] -- <command...>`.
- Register with `job-register <name> --max-age <duration>` using suitable schedule slack, then validate `plutil -lint` and bootstrap through `launchctl`.
- Check `job-check --list`, runner logs and an actual completed run. A loaded plist with no completed job is only installed.
- Existing self-managed jobs may use `job-mark`; preserve their established contract.
- Missed calendar wake jobs have failed during dark wake here; use the interval runner for recurring jobs. TCC differs between terminal and launchd execution; a successful manual run does not prove scheduled access.

## Cairn scheduling

Use the existing desired-state manifest and its deployment mechanism for managed systemd services/timers. Read the relevant unit and owner before editing. User timers and existing cron jobs keep their intended scheduler; avoid duplicate schedules. Cron times are UTC on this host. Do not install OMP merely to distribute a shared workflow. Report an absent CLI separately from a missing account login.

## Verify and report

Validate syntax first, then use a harmless fixture or dry-run supported by the underlying operation. A manual run that sends messages, creates issues, publishes or otherwise changes external state needs authorization for that effect; setup permission alone is not a connectivity-test excuse. Before replacing a running job's configuration, settle its current ownership and avoid launching a duplicate.

After a scoped change, verify the resulting scheduler definition, runtime environment, exit/result handling and next due time. Preserve unrelated jobs. Report files changed, what actually ran, the last result and remaining prerequisites. Route needed notifications through `ntfy-send` and the existing topic registry; do not invent topics or monitoring accounts.
