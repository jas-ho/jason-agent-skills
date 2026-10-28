---
name: codex-pair
description: Cross-model pairing between Claude Code and Codex. REVIEW has the other model review a diff, plan, spec, or prompt; IMPLEMENT gives the other model a committed spec and acceptance gate, then the originating agent reviews. Use on "codex/claude review", "second opinion", "red team this", "have the other model implement this", or before every commit (the commit-review rule), and for structure reviews of a whole codebase before pinning it.
---

# Cross-model pairing

Two patterns for using the other agent CLI as a counterpart. From Claude Code,
use `codex`; from Codex, use `claude`. The invariant in both:
**author ≠ reviewer, and the reviewer never implements its own feedback.**

Requires the counterpart CLI to be authenticated.

## Routing

| Situation                                                                                       | Mode                                                                          |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Anything staged for a commit (every commit; the commit hook refuses one without `Reviewed-by:`) | REVIEW                                                                        |
| Plan, spec, or subagent prompt worth stress-testing                                             | REVIEW (plans benefit most — catches second-order effects before code exists) |
| Well-specifiable feature, testable contract, ≥~3 files or mechanical breadth                    | IMPLEMENT                                                                     |
| Small diff (≤2 files, ≤~30 lines), design/UI judgment, needs interactive verification mid-loop  | implement with the current agent; REVIEW before the commit                    |
| Code about to be pinned for counted results, a release or a decision                            | CODEBASE                                                                      |
| Stuck after 2 failed attempts                                                                   | fresh-eyes diagnosis: REVIEW-style prompt asking for root cause, not fixes    |

## Harness routing and invocation

Use native workers for ordinary independent research or implementation. Who reviews (the other model family by default, the exceptions, and pins) is decided in `~/.claude/context-coding/ai-tools.md` "Who reviews"; this skill supplies the mechanics. From Codex the cross-model counterpart is Claude; from CC it is Codex; from OMP, a different model family from the current author (Astra → Claude; Claude → Codex). Do not silently change the requested model or call two Astra workers cross-model diversity. The counterpart CLI must already be authenticated; otherwise report the missing login and continue independent work.

Read the following contracts before constructing the actual command. Replace prompt/output paths with unique files per job, close stdin with `< /dev/null` on every `codex exec` call unless the prompt is piped in (resume and implementation runs included; open stdin can hang it forever), and use the owning harness's background-process mechanism. Track that process and output explicitly; never wait for a completion event the launcher does not provide.

### One-shot inlined review

These direct inlined commands cannot support a later resume because persistence is deliberately off. For a staged commit, use `codex-run review-staged --cwd REPO --prompt-file FILE`: it captures only the staged artifact plus status and keeps metadata for an exact resume. The assembled prompt is capped at 100 KiB; split larger reviews. Check its staged hash before committing, per `~/.claude/codex-profiles/README.md`.

```bash
# Claude reviewer, isolated inlined context and no built-in or MCP tools.
timeout 900 claude -p --safe-mode --strict-mcp-config --no-session-persistence \
  --tools '' --permission-mode default --no-chrome --disable-slash-commands \
  --output-format stream-json --verbose --include-partial-messages \
  -- "$(cat /tmp/review-prompt.txt)" \
  < /dev/null > /tmp/claude-review.jsonl 2> /tmp/claude-review.stderr
# Codex plan/spec reviewer, read-only execution and no saved session.
# For staged commits use codex-run review-staged --cwd REPO --prompt-file FILE.
test -s /tmp/review-prompt.txt && timeout 900 codex exec --ephemeral -s read-only \
  --cd "$PWD" --skip-git-repo-check --json -o /tmp/codex-review.md \
  -- "$(cat /tmp/review-prompt.txt)" < /dev/null > /tmp/codex-review.jsonl 2> /tmp/codex-review.err
```

Never start a reviewer in plan mode: with no tools available it loops on plan-mode tool calls it cannot make and never answers (2026-10-19). `timeout` (seconds, set to the review budget below: 900 fits most reviews, give an xhigh plan review 1800) makes a stuck call exit 124 instead of needing a process hunt; treat 124 as a failed review. Verify these flags against the installed CLI help. `--tools ''` disables only built-in tools: `--strict-mcp-config` with no supplied servers excludes configured MCP servers. For self-contained reviews, `--safe-mode` also removes unrelated customizations while retaining normal auth, model selection, permissions and managed policy. Inline the relevant project constraints because automatic instruction loading is disabled. Do not substitute `--bare`: it skips subscription OAuth/keychain authentication. If safe mode is unavailable, retain explicit MCP isolation and report any remaining customization load.

Use unique actual paths rather than these fixed example names. A fresh reviewer can evaluate a subsequent complete artifact, but that is a new review, not a resumed thread.

### Persistent review rounds

When follow-up rounds are planned, keep persistence from the first call. For Claude omit `--no-session-persistence`, retain the isolation, tool restrictions and streaming flags above, and record the returned `session_id`. Follow up with `claude -p --resume <exact-id>` and the same restrictions. For staged Codex review rounds use `codex-run review-staged`, then `codex-run resume RUN.meta.json --prompt-file FILE`; it retains the explicit read-only policy and refuses a changed staged artifact. For direct plan/spec rounds omit `--ephemeral`, retain read-only permissions and closed stdin, request `--json`, and record the exact thread ID, cwd, policy and output paths. Verify resume flags against installed help; `-s` belongs before `resume` (omitting it can restore a writable default), and non-git resume needs `--skip-git-repo-check`. Prefer the launcher wherever its mode fits.

Never use the latest-session selector, an ambiguous nickname, or a parent session inferred from newest-file timestamps. Missing identity means a fresh review with complete context or an explicit failure to resume, not a guessed continuation. Do not resume a thread still owned by another running process.

### Writable implementation

Use `codex-run implement --cwd REPO --prompt-file FILE` for a bounded Codex implementation, or `codex-run browser` for Mac browser acceptance. The host table in `~/.claude/context-coding/ai-tools.md` is authoritative: Mac explicitly selects `jason`; cairn needs its `implement.config.toml`, because plain exec there is read-only. For a Mac linked worktree, launch from the main checkout and name the worktree in the prompt. Supervisor-owned steps include SSH, protected config writes, launchd/systemd, heavy-run and any denied acceptance check. Claude uses its normal editing/test permissions with `-p --output-format json`. Only implement accepts `--add-dir` for required cache/output directories; it also supplies and records a private per-attempt tool-temp directory. Do not carry review's empty-tool list, read-only sandbox or ephemeral flags into implementation, or bypass permissions to make it succeed.

Research uses `codex-run research` for hosted web search with shell network off, or `research-net` only when shell HTTP is required. Both use the reviewed read boundary after the supervisor passes the host probe and installs profiles. Before that, use `--profile-source` only with `--dry-run`; a source launch is unverified until the host probe passes. Old network-enabled research and root-broad Mac jason require replacement and fresh sessions; resume refuses replaced policies. Hosted search remains an outbound channel. Unknown secrets inside allowed roots can be read; Linux glob matching is bounded and snapshots at process startup. Detailed boundaries and install gates: `~/.claude/codex-profiles/README.md`.

The launcher prints metadata and a `codex-watch` command before startup; start the watcher under the harness monitor. Resume with `codex-run resume RUN.meta.json --prompt-file FILE`, which keeps recorded policy/cwd/model/roots and creates fresh logs. Say “running” only after `thread.started`, and require a successful exit, terminal event and final answer. Read the report to determine whether the acceptance gate actually passed. For failed/cancelled runs inspect metadata state/error/child exit and the `.err` file; without a recorded thread, start a fresh job. Exit meanings and plugin rescue watching (completed/failed/cancelled) are in ai-tools.md and the profile README.

Record the exact returned identity and resume only it with the same scope. The counterpart never commits unless separately requested. Keep the authored spec and acceptance gate available in the repository.

### Shared operational rules

- Use the configured default model unless the user selects one or an unavailable default needs a supported replacement.
- For REVIEW, inline the complete artifact and relevant constraints and say “do not read files or run commands.” For a commit, the artifact is exactly what is staged (`git diff --cached`), shown next to the list of what is left unstaged or untracked (`git status --short`), so the reviewer can flag what is missing as well as what should not go in; add affected interfaces and tests as context. A summary is insufficient. Record the reviewed diff, supplied context, reviewer and verdict in the completion report, and in the commit as `Reviewed-by: <reviewer> <VERDICT>`. Missing context must be supplied before claiming that scope reviewed.
- Observe streamed progress separately from the final result. Initialization or thinking events prove activity, not completion; require a terminal result with no error and a successful process exit and a substantive response ending in the requested verdict before accepting the review. Preserve stdout and stderr on failure. Extract the final result text for adjudication rather than presenting raw event logs.
- Choose a bounded review budget proportional to the artifact (for example, ten minutes for a substantial multi-file review), enforce it with `timeout`, and poll via the owning harness without blocking user updates. A 150-second total timeout is too short for some successful reviews. Empty text output alone is not evidence of idleness because print mode can buffer the entire answer. If no progress is observable, inspect errors and isolate startup with a tiny prompt before retrying once; stop only the owned process. Never retry an already inlined prompt merely because its answer has not appeared.
- Effort: Codex's configured default (high) for commit and doc reviews. Pass `-c model_reasoning_effort=xhigh` only for a plan review of a substantial change and the fresh final review of a high-stakes diff.
- Inlined reviews stay inlined: a reviewer that may read files re-reads the repository every round (400k-950k input tokens per round, measured 2026-10-16). If it needs more context, add those files to the prompt.
- Ask for everything at once: "List every finding now, prioritised; later rounds only check the fixes and what they touch."
- Keep user updates while a job runs. Interpret CLI errors and nonzero status before trusting the text output.

## REVIEW mode

1. Build the prompt file: the requirements (spec, issue, user request) plus the complete artifact and "do NOT read files or run commands". For a commit: run any formatter or check that modifies files first, stage, then capture `git diff --cached` and `git status --short` (the unstaged and untracked list, names only). Commit exactly what was reviewed: no `commit -a`, pathspec commits or edits between review and commit. For a committed change, supply its diff and relevant surrounding context.
2. **Redaction rule (best-evidenced finding in the field, ~2-4x review-quality
   effect): never include the author's self-assessment** — no "tests pass",
   no "I addressed X", no PR-style summary. The reviewer gets artifact +
   intent/spec only.
3. Ask for an adversarial stance ("review as the engineer who inherits this
   code and is skeptical of the author") and require a closing line
   `VERDICT: APPROVED` or `VERDICT: REVISE` with prioritized findings.
4. Launch in background; continue other work, but do not stage or unstage anything in that repo until the reviewed commit is made (keep other work unstaged or in another worktree).
5. On return, **adjudicate — don't auto-apply.** The value is the different
   perspective, not a better one. Check each finding against the actual code;
   substantial reviews typically mix real findings with 1–2 confident misreads
   (verify before "fixing"). Fix what's real.
6. If REVISE: fix, then resume the exact persistent session with what changed (the diff of
   the fix, not your reasoning: `git diff` of the fix before staging it, plus the refreshed
   `git status --short`), never the whole artifact again. A fresh session (the one-shot
   launch forms above) gets the current full staged diff plus the prior findings and the fix
   diff, with "only check the fixes and what they touch". Changes made after a review get their own review, and the
   trailer records the final round's verdict. Cap at 3 rounds; on stalemate, present both
   positions to the user instead of looping.
   For high-stakes changes (live-deployed, data-touching), after the loop
   converges run one FRESH session over the final diff — incremental rounds
   anchor on earlier rounds and can rubber-stamp.
7. Commit with the verdict as a trailer, one line per reviewer:
   `--trailer 'Reviewed-by: codex APPROVED'`. Under time pressure the review gets
   shorter, never skipped.

## IMPLEMENT mode

The originating agent is product owner + reviewer; the counterpart is the
contracted implementer.

1. **Spec**: write `docs/specs/<feature>.md` — context, file map, requirements,
   explicit out-of-scope. Where the spec leaves room, say so.
2. **Acceptance gate**: executable contract the counterpart must satisfy —
   `tests/checks.sh` running contract tests (fixtures from real data; assert
   presence/absence, not exact formatting — leave design room), syntax checks,
   linters. **REVIEW spec + gate, then commit them before the counterpart starts.**
3. Prompt: "Implement `docs/specs/<name>.md`. Iterate until `bash tests/checks.sh`
   exits 0. Do NOT modify anything under tests/. If a test contradicts
   the spec's general behavior, implement the general behavior, leave that
   test failing and report it; never add special cases to make it pass. Do not git-commit. Keep diffs
   minimal, match each file's style. Summarize design decisions at the end."
4. Run with the counterpart CLI in the repository using scoped write
   permissions. The committed gate + explicit stop condition is the headless
   equivalent of goal mode. On non-convergence, resume the exact session with
   the failure output, max two resumes, then take over.
5. On return: re-run the checks yourself (don't trust the claim). Then review
   the **diff**, not the counterpart's summary (redaction rule in reverse — read the
   summary only after forming your own view). Expect the escapes to be in the
   gap between "asserted" and "well-formed": formatting, races, UX feel,
   and special cases keyed to test values (usually a wrong test or spec).
6. Fix taste-level issues yourself, verify end-to-end (browser/manual where
   relevant). Your review covers the counterpart's diff; your own touch-ups need
   an independent review too (a fresh subagent or the counterpart in REVIEW mode).
   Commit with the `Reviewed-by:` trailers and authorship noted ("Implemented by the counterpart against
   `docs/specs/<name>.md`; reviewed and touched up").
7. For high-stakes work: keep one or two acceptance scenarios OUT of the repo
   (holdout) and check them manually at review time — tests in the tree can be
   gamed even without edits, by bending the implementation around them.

## CODEBASE mode

Before code is first pinned for counted results, a release or a decision, and again before a later pin if the structure changed since: a structure-only review of the whole runnable system, sibling repos and scoring scripts included. Not a diff review; diff reviews per commit stay as before. Reviewers per `ai-tools.md` "Who reviews"; a project's CLAUDE.md may set what counts as a pin and whether a pin gets a second reviewer. For research code, check against `~/.claude/context-coding/research-code.md` plus the project's listed exceptions.

1. Inline the requirements, the README, the file tree and every source file of the runnable system (or as much as fits, with the rest listed); for repos too large to inline, give a reviewer that can read files read-only access instead and say which paths are in scope.
2. Prompt: "Think like a really grumpy senior engineer who is fed up with AI slop and wants to fully understand every important branching point and architecture decision. For each one: can a skeptical reviewer of the resulting paper or decision get a clear answer from the code and README? List what is redundant, duplicated, dead, unexplained, or more complex than the requirements need." End with `VERDICT: APPROVED` or `VERDICT: REVISE`.
3. Adjudicate as in REVIEW, then simplify; the simplifications are ordinary commits with their own diff reviews.

## Known failure modes

- Sandbox startup failure: `sandbox_apply: Operation not permitted` (observed with helper exit 71) means no review occurred. Other sandboxed agent hosts may encounter it too; this has not been verified. See [README.md](README.md#codex-sandbox-startup-failure-september-25-2026) before retrying; do not weaken permissions. A same-family worker can supplement review but leaves cross-model coverage incomplete; fall back per ai-tools.md "Who reviews" and name the gap in the report.
- App-server initialization EPERM before `thread.started` occurred in the restricted Mac Codex supervisor on 2026-10-28. No model run started and no thread exists to resume; retain stderr and request a fresh launch from the supervising session with the needed capabilities. Do not weaken permissions.
- Writing/network or browser acceptance fails: check the selected host/mode and recorded policy in `codex-run` metadata against the table in ai-tools.md. Cairn plain exec is read-only. Do not mechanically “drop -s” there. Use implement `--add-dir` for required cache/output roots. Linked-worktree git writes on either host and Mac browser escalation can need supervisor completion; report the exact denied acceptance step.
- Silent review: distinguish buffered model reasoning from startup/auth/tool-loading failure using streamed events and stderr. Inlining solves missing artifact access, not every cause of delayed output. See the measured Claude setup diagnosis in README.md.
- The counterpart flagging nonexistent bugs: settle with a test that proves it one way
  or the other, not with argument.
- Setup-specific failure modes (plugin runtimes, account/model restrictions,
  UI backgrounding): see README.md — verify on your own setup before trusting.
