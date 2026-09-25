---
name: codex-pair
description: Cross-model pairing between Claude Code and Codex. REVIEW has the other model review a diff, plan, spec, or prompt; IMPLEMENT gives the other model a committed spec and acceptance gate, then the originating agent reviews. Use on "codex/claude review", "second opinion", "red team this", "have the other model implement this", or after any substantial code change before commit.
---

# Cross-model pairing

Two patterns for using the other agent CLI as a counterpart. From Claude Code,
use `codex`; from Codex, use `claude`. The invariant in both:
**author ≠ reviewer, and the reviewer never implements its own feedback.**

Requires the counterpart CLI to be authenticated.

## Routing

| Situation                                                                                      | Mode                                                                          |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Substantial code change exists (default: every one, pre-commit)                                | REVIEW                                                                        |
| Plan, spec, or subagent prompt worth stress-testing                                            | REVIEW (plans benefit most — catches second-order effects before code exists) |
| Well-specifiable feature, testable contract, ≥~3 files or mechanical breadth                   | IMPLEMENT                                                                     |
| Small diff (≤2 files, ≤~30 lines), design/UI judgment, needs interactive verification mid-loop | stay with the current agent, REVIEW after                                     |
| Stuck after 2 failed attempts                                                                  | fresh-eyes diagnosis: REVIEW-style prompt asking for root cause, not fixes    |

## Harness routing and invocation

Use native workers for ordinary independent research or implementation. This skill is the explicit exception for cross-model review: from Codex use Claude; from CC use Codex. From OMP, choose a counterpart with a different model family from the current author (Astra → Claude; Claude → Codex). Do not silently change the requested model or call two Astra workers cross-model diversity. The counterpart CLI must already be authenticated; otherwise report the missing login and continue independent work.

Read the following contracts before constructing the actual command. Replace prompt/output paths with unique files per job, keep stdin closed for detached runs, and use the owning harness's background-process mechanism. Track that process and output explicitly; never wait for a completion event the launcher does not provide.

### One-shot inlined review

These commands cannot support a later resume because persistence is deliberately off:

```bash
# Claude reviewer, isolated inlined context and no built-in or MCP tools.
claude -p --safe-mode --strict-mcp-config --no-session-persistence \
  --tools '' --permission-mode plan --no-chrome --disable-slash-commands \
  --output-format stream-json --verbose --include-partial-messages \
  -- "$(cat /tmp/review-prompt.txt)" \
  < /dev/null > /tmp/claude-review.jsonl 2> /tmp/claude-review.stderr
# Codex reviewer, read-only execution and no saved session.
codex exec --ephemeral -s read-only --skip-git-repo-check \
  -- "$(cat /tmp/review-prompt.txt)" < /dev/null > /tmp/codex-review.txt 2>&1
```

Verify these flags against the installed CLI help. `--tools ''` disables only built-in tools: `--strict-mcp-config` with no supplied servers excludes configured MCP servers. For self-contained reviews, `--safe-mode` also removes unrelated customizations while retaining normal auth, model selection, permissions and managed policy. Inline the relevant project constraints because automatic instruction loading is disabled. Do not substitute `--bare`: it skips subscription OAuth/keychain authentication. If safe mode is unavailable, retain explicit MCP isolation and report any remaining customization load.

Use unique actual paths rather than these fixed example names. A fresh reviewer can evaluate a subsequent complete artifact, but that is a new review, not a resumed thread.

### Persistent review rounds

When follow-up rounds are planned, keep persistence from the first call. For Claude omit `--no-session-persistence`, retain the isolation, tool restrictions and streaming flags above, and record the returned `session_id`. Follow up with `claude -p --resume <exact-id>` and the same restrictions. For Codex omit `--ephemeral`, retain read-only permissions, and request `--json`; capture the returned thread identity from the installed CLI's event schema. Follow up with `codex exec resume <exact-id>` under the same verified read-only configuration. Verify supported options on the installed CLI before constructing a resume command; options are not identical between initial exec and resume.

Never use the latest-session selector, an ambiguous nickname, or a parent session inferred from newest-file timestamps. Missing identity means a fresh review with complete context or an explicit failure to resume, not a guessed continuation. Do not resume a thread still owned by another running process.

### Writable implementation

The implementation launcher is separate. Set the repository as cwd and use its existing scoped write/test permissions. Codex uses `codex exec -s workspace-write --json` with a persistent thread; Claude uses normal available editing and test tools under the repository's approved permission configuration, with `-p --output-format json`. Do not carry review's empty-tool list, plan mode, read-only sandbox, or ephemeral flags into implementation. Do not bypass permissions to make headless execution succeed. If a required tool remains denied, report that limitation rather than treating a prose-only answer as implementation.

Record the exact returned identity and resume only it with the same scope. The counterpart never commits unless separately requested. Keep the authored spec and acceptance gate available in the repository.

### Shared operational rules

- Use the configured default model unless the user selects one or an unavailable default needs a supported replacement.
- For REVIEW, inline the complete artifact and relevant constraints and say “do not read files or run commands.” For code, include the full scoped diff (staged, unstaged and all untracked files in scope), affected interfaces and tests; a summary is insufficient. Record the reviewed commit/diff, supplied context, reviewer and verdict in the completion report. Missing context must be supplied before claiming that scope reviewed.
- Observe streamed progress separately from the final result. Initialization or thinking events prove activity, not completion; require a terminal result with no error and a successful process exit and a substantive response ending in the requested verdict before accepting the review. Preserve stdout and stderr on failure. Extract the final result text for adjudication rather than presenting raw event logs.
- Choose a bounded review budget proportional to the artifact (for example, ten minutes for a substantial multi-file review), and poll via the owning harness without blocking user updates. A 150-second total timeout is too short for some successful reviews. Empty text output alone is not evidence of idleness because print mode can buffer the entire answer. If no progress is observable, inspect errors and isolate startup with a tiny prompt before retrying once; stop only the owned process. Never retry an already inlined prompt merely because its answer has not appeared.
- Keep user updates while a job runs. Interpret CLI errors and nonzero status before trusting the text output.

## REVIEW mode

1. Build the prompt file: relevant context plus the complete artifact and "do NOT read files or run commands". For current code changes, collect `git diff HEAD` and append all untracked files in the review scope; plain `git diff` omits staged and untracked changes. For a committed change, supply its diff and relevant surrounding context.
2. **Redaction rule (best-evidenced finding in the field, ~2-4x review-quality
   effect): never include the author's self-assessment** — no "tests pass",
   no "I addressed X", no PR-style summary. The reviewer gets artifact +
   intent/spec only.
3. Ask for an adversarial stance ("review as the engineer who inherits this
   code and is skeptical of the author") and require a closing line
   `VERDICT: APPROVED` or `VERDICT: REVISE` with prioritized findings.
4. Launch in background; continue other work.
5. On return, **adjudicate — don't auto-apply.** The value is the different
   perspective, not a better one. Check each finding against the actual code;
   substantial reviews typically mix real findings with 1–2 confident misreads
   (verify before "fixing"). Fix what's real.
6. If REVISE: fix, then resume the exact persistent session with what changed (the diff of
   the fix, not your reasoning). Cap at 3 rounds; on stalemate, present both
   positions to the user instead of looping.
   For high-stakes changes (live-deployed, data-touching), after the loop
   converges run one FRESH session over the final diff — incremental rounds
   anchor on earlier rounds and can rubber-stamp.
7. Ship-first-review-trailing is acceptable under time pressure, but the
   verdict must still land; findings become fix-up commits.

## IMPLEMENT mode

The originating agent is product owner + reviewer; the counterpart is the
contracted implementer.

1. **Spec**: write `docs/specs/<feature>.md` — context, file map, requirements,
   explicit out-of-scope. Where the spec leaves room, say so.
2. **Acceptance gate**: executable contract the counterpart must satisfy —
   `tests/checks.sh` running contract tests (fixtures from real data; assert
   presence/absence, not exact formatting — leave design room), syntax checks,
   linters. **Commit spec + gate before the counterpart starts.**
3. Prompt: "Implement `docs/specs/<name>.md`. Iterate until `bash tests/checks.sh`
   exits 0. Do NOT modify anything under tests/ — if a test seems wrong,
   satisfy it and flag it in your summary. Do not git-commit. Keep diffs
   minimal, match each file's style. Summarize design decisions at the end."
4. Run with the counterpart CLI in the repository using scoped write
   permissions. The committed gate + explicit stop condition is the headless
   equivalent of goal mode. On non-convergence, resume the exact session with
   the failure output, max two resumes, then take over.
5. On return: re-run the checks yourself (don't trust the claim). Then review
   the **diff**, not the counterpart's summary (redaction rule in reverse — read the
   summary only after forming your own view). Expect the escapes to be in the
   gap between "asserted" and "well-formed": formatting, races, UX feel.
6. Fix taste-level issues yourself, verify end-to-end (browser/manual where
   relevant), commit with authorship noted ("Implemented by the counterpart against
   `docs/specs/<name>.md`; reviewed and touched up").
7. For high-stakes work: keep one or two acceptance scenarios OUT of the repo
   (holdout) and check them manually at review time — tests in the tree can be
   gamed even without edits, by bending the implementation around them.

## Known failure modes

- Sandbox startup failure: `sandbox_apply: Operation not permitted` (observed with helper exit 71) means no review occurred. Other sandboxed agent hosts may encounter it too; this has not been verified. See [README.md](README.md#codex-sandbox-startup-failure-september-25-2026) before retrying; do not weaken permissions. A same-family worker can supplement review but leaves required cross-model coverage incomplete.
- Silent review: distinguish buffered model reasoning from startup/auth/tool-loading failure using streamed events and stderr. Inlining solves missing artifact access, not every cause of delayed output. See the measured Claude setup diagnosis in README.md.
- The counterpart flagging nonexistent bugs: settle with a test that proves it one way
  or the other, not with argument.
- Setup-specific failure modes (plugin runtimes, account/model restrictions,
  UI backgrounding): see README.md — verify on your own setup before trusting.
