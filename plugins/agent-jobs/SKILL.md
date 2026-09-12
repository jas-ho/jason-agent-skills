---
name: agent-jobs
description: Native agent review, adversarial review, rescue, context transfer, setup, status, result, and cancellation. Use for companion-style job operations in Codex or OMP; explicitly cross-model work uses codex-pair.
---

# Native agent jobs

The invocation must forward an operation followed by the user's original arguments: `agent-jobs <review|adversarial-review|rescue|transfer|setup|status|result|cancel> [arguments]`. A slash wrapper supplies that operation explicitly; never infer it from whichever vendor command happened to load this file. Preserve focus text and quoted values. Reject conflicting `--wait`/`--background` or `--resume`/`--fresh` choices. Ask a native question only when missing scope or identity prevents the operation.

This implements equivalent operations using the current harness's workers. CC keeps its selected vendor companion command and runtime as source owner; do not call this skill recursively through that command or transplant its Node internals. If the user actually requests another model family, use the shared `codex-pair` workflow. A native Codex reviewer is not cross-model diversity from a Codex author.

## Identity and lifecycle

Use the native registry as the only job store. Record the exact identity returned by the launch in the conversation and give it to the user together with the operation and scope. No second job database, latest-job fallback, guessed thread ID, or filename-time heuristic. A clear conversation reference to one owned job is sufficient; ambiguous references need clarification.

Read [references/native-tools.md](references/native-tools.md) before constructing the first launch or lifecycle call. Actual advertised tool schemas take precedence over these versioned examples. Setup must distinguish unavailable tool, missing provider login, disabled async messaging, and untested behavior. Do not create a worker merely to check setup.

`--background` launches through the native nonblocking mechanism and returns the ID promptly. `--wait` waits through the owning tool while keeping the user informed. Without a flag, wait for a tiny review or rescue and background broader work when supported; do not repeat a question already answered. A returned launch ID proves scheduling, not success.

## Review and adversarial review

Both operations are read-only: inspect and report, never fix findings, edit files, stage changes, run mutating tests/builds, commit, or invoke an automated formatter. Give the worker that constraint explicitly. Native tool permissions are the actual enforcement boundary; a prompt alone is not an enforced sandbox. Supply the review snapshot inline when the worker does not need tool access. If an enforced read-only worker is required but unavailable, report that capability gap rather than claim isolation.

Select the requested scope before launch. Working-tree and auto scope inspect `git status --short --untracked-files=all`, staged diff, and unstaged diff; read relevant untracked files too. An empty `git diff` does not mean an empty review. Do not stage untracked files to make them visible. Branch scope uses the requested base against HEAD after resolving the ref; do not fetch or guess a base when the intended base is unclear. Report unreadable or excluded files as coverage gaps. Respect denied/secret paths.

Pass intent, scope, the concrete artifact and relevant context without the author's self-assessment. `adversarial-review` additionally asks for realistic counterexamples, failure conditions, and questionable assumptions while preserving the user's focus. Request prioritized findings with file/line evidence, trigger and impact, and a final verdict. Return the worker's complete findings and verdict with its identity; make no fixes as part of this operation. If concurrent edits invalidate the reviewed snapshot, name the snapshot boundary and review only the newly relevant delta.

## Rescue

Diagnosis is read-only by default. An explicit request to implement a fix permits edits and tests only within that scope. Preserve model/effort requests when the native launcher actually supports them; do not translate a vendor alias into a guessed model. Use the host's configured model routing for the task's judgment requirements.

For a follow-up, resolve the exact prior native job and its current state. Send steering to its running owner, or use the native follow-up mechanism for an idle/resumable worker. Do not start a second owner of that session. If the native registry cannot resume it, say so and offer a fresh worker seeded with the preserved context. `--fresh` explicitly requests that new identity. Changing a read-only review into writable rescue requires a clear fix instruction, not merely “continue.”

## Transfer

Transfer means handing explicit context to a new owning native session or worker. It does not convert vendor transcripts into another harness's internal JSON schema. Identify the source by exact session ID or user-selected transcript, inspect it read-only, and prepare a brief containing the user's objective, settled decisions, files/artifacts, unresolved work, and ownership constraints. Read only authorized source material; omit credentials and irrelevant private material.

Launch a fresh native worker with that brief when a worker handoff is requested, and return its new identity plus the source identity. A native child worker is not necessarily an independently resumable interactive CLI session. If the user wants an interactive tmux session, use `spawn` with a fresh explicit brief; never invent a session-import flag. Native fork is an alternative only when the user wants that harness's supported fork semantics. Do not claim lossless history conversion or stop the source session automatically.

## Setup, status, result, cancel

- `setup`: inspect the current tool catalog and native registry readiness, report available operations and gaps. Keep review gates vendor-owned in CC; enabling a gate is a separate supported configuration operation, not a side effect of setup here. Do not install nested Codex when already running natively in Codex.
- `status [id]`: use the native registry. Without an ID, show visible owned jobs; with an ID, show that exact job. Include state, operation/scope when known, duration only if recorded, and actual available follow-ups. Missing history is unknown, not completed.
- `result <id>`: return the stored/delivered final output for that exact native job, including errors, findings and artifact paths. Pending is pending; do not rerun work to manufacture a result. Native results may exist only in the current session/registry; report that retention limit if unavailable.
- `cancel <id>`: interrupt/cancel only the requested owned job using the owning tool and exact returned identity. Then inspect state. Distinguish interrupted, cancelled, already completed and not found. Never kill a tmux server, search-and-kill by model name, or cancel every job as a substitute. Cancellation does not roll back edits or guarantee that every separately launched process stopped.
