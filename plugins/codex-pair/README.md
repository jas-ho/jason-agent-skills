# codex-pair

A shared CC/Codex/OMP workflow for cross-model REVIEW and IMPLEMENT. Codex-authored work is reviewed by Claude; Claude-authored work is reviewed by Codex. The author and reviewer are different model families, and reviewers never implement their own feedback.

> **Requires the counterpart CLI, authenticated (`claude` or `codex`).** Earlier Codex runs were verified against codex-cli
> 0.153.4 (September 2026, first verified on 0.139.0 in June 2026); flags and
> model behavior drift, so re-verify after major CLI updates. On ChatGPT-plan
> accounts, pinning a model the account is not entitled to is rejected with
> "not supported when using Codex with a ChatGPT account" (observed: `-codex`
> variants on a Plus account, June 2026; `gpt-5.6-sol` on a free-tier account,
> 2026-09-08). `~/.codex/models_cache.json` shows what the account currently
> sees and is a discovery aid, not a guarantee. The skill therefore uses the
> CLI's configured default model (no `-m` pin). ChatGPT plans meter
> account-level rolling windows with model-specific cost against them. On
> Plus both a 5-hour and a weekly window metered (published 5-hour caps:
> gpt-6-astra 5–45 messages, sol 10–100, luna 250–2,000; measured: five
> inlined REVIEW turns on astra used 9% of a 5-hour window on 2026-09-09).
> On Pro 20x (this account since 2026-09-09) the live limits block showed
> only a weekly window. With no credits configured, an exhausted window
> blocks until it resets; switching to a less-limited model may help since
> the caps are per model.

## Distribution

The canonical authored package lives in `jason-agent-skills/plugins/codex-pair`. The shared agent-config manifest installs per-harness links and command entry points; do not copy this package into a second live source tree.

The one-shot, persistent-review, and writable-implementation contracts in SKILL.md supersede the original single launcher. Claude one-shot isolation was exercised on September 22, 2026 with Claude Code 2.1.278; persistent resume and writable implementation were not re-tested in that diagnosis.

## Validation status

- REVIEW mode: battle-tested across many changes (static sites, research
  pipelines, automation scripts, infra plans, research memos, plans and
  prompts) through September 2026. Reviews reliably mix substantive findings
  with the occasional confident misread (2026-09-06/07: four wrong claims about
  scripts in a single infra audit next to three real mechanics findings) — the
  skill's adjudication step exists because of this.
- IMPLEMENT mode: validated once as of June 2026 (a well-specified web feature
  with contract tests; converged in one run, review caught two real flaws the
  tests missed). Treat as a trial pattern until it has survived a few
  differently-shaped tasks.

## Setup-specific gotchas (observed on one setup; verify on yours)

Observed on macOS, codex-cli via volta, ChatGPT-plan auth, June–September 2026:

- The codex-companion Claude Code plugin's rescue subagent fails with a sandbox
  error ("failed to initialize in-process app-server client"; suspected cause,
  from a 2026-05-16 diagnosis, is a nested codex being denied its own
  app-server inside the parent sandbox — not separately demonstrated) and its bundled
  runtime rejects current models (plugin 1.0.6 still maps names to
  `gpt-5.3-codex-spark`-era models, September 2026). Driving the PATH `codex`
  CLI directly avoided those plugin failures in that setup; it did not avoid the sandbox startup failure in the Codex-hosted run below.
- `codex login status` can report logged-in after the refresh token was
  revoked (2026-09-08); the first real `codex exec` then fails. Smoke-test
  with a trivial exec after any account change.
- Background codex jobs finish silently from Claude Code's point of view;
  poll the output file rather than waiting for a completion signal.
- Backgrounding a _foreground_ codex run from the Claude Code UI can kill it
  silently (0-byte output, stdin/TTY detach). Always launch as a background
  task from the start, with `< /dev/null`.
- Some `codex exec` runs that needed file access produced no output for hours. Inlining the complete artifact avoided that failure in those runs; it does not establish the cause of every silent review.

## Codex sandbox startup failure (September 25, 2026)

The former repo checklist prompted an additional same-family Codex review; the required Claude review route was unaffected. From that Codex session on macOS, codex-cli 0.157.0 failed before reviewing Codex-authored work while loading AGENTS.md: `sandbox_apply: Operation not permitted`, filesystem helper exit 71. `codex sandbox /usr/bin/true` failed identically in ordinary and escalated tool calls; the bare probe below also failed in ordinary execution. Inherited confinement is a hypothesis; the enforcing layer is unidentified, and escalation did not resolve the Codex probe. Other agent hosts and `codex exec` were not tested. No version regression or machine-wide failure has been established.

On this startup signature, report that no review occurred. The reviewer’s model family follows the author: use Claude for Codex-authored work, Codex for Claude-authored work. If the required counterpart cannot start, cross-model review stays open; a same-family worker cannot replace it. Supply the complete artifact and relevant context using the skill’s REVIEW contract. Do not relax sandbox settings or sensitive-file denies: the outer policy is not known to match the child’s protections.

For an outside-host control, use a terminal launched directly by the user. Compare `command -v codex` and `codex --version`, then run `codex sandbox /usr/bin/true; echo "exit=$?"`. If it fails, compare the bare probe shown below:

```sh
/usr/bin/sandbox-exec -p '(version 1)(deny default)(allow process*)(allow file-read*)(allow sysctl-read)' /usr/bin/true
echo "exit=$?"
```

Interpret the error, not exit status alone: the same `sandbox_apply` error on both probes points to broader execution policy; bare success with Codex failure points to its invocation/profile. Outside-host success with in-host failure supports a host-context restriction, without identifying the exact layer. A directly launched terminal is an acceptable interim route with existing protections intact. Validate the skill’s one-shot `codex exec` launcher with a tiny inlined prompt before using it for a complete REVIEW artifact; require exit 0, substantive final output and no sandbox/helper error. Separately, verify a bounded real `codex review --commit <sha>` before claiming the dedicated review command is repaired. Classify unrelated stderr warnings separately. Outside-host verification remains pending; this is review-routing guidance, not a verified CLI repair.

## Claude review diagnosis (September 22, 2026)

On Claude Code 2.1.278, a tiny prompt using the old review flags consumed roughly 119,900 input tokens. `--tools ''` removed built-in tools but left about 200 configured MCP tools exposed. The same prompt with `--strict-mcp-config` and no supplied servers used about 11,500 input tokens; safe mode used about 4,900. These controlled comparisons demonstrate substantial MCP schema overhead. They do not identify which request or service caused every historical failure.

The historical workspace review log recorded only a 150-second timeout, so its exact internal failure cannot be reconstructed. A separate successful review took 177 seconds. A streamed replay of the already-inlined workspace artifact was still actively reasoning when a diagnostic 240-second limit expired: silence in buffered print output is insufficient evidence of a hang. A second replay of the same 74,948-byte historical artifact completed successfully in 363.8 seconds with the configured default model, no tools or MCP servers, and a substantive verdict. The revised command isolates self-contained reviews, streams progress, retains errors, and requires a successful terminal result rather than assuming initialization means success.

Safe mode preserves normal authentication and configured model selection. `--bare` is unsuitable as a drop-in replacement for subscription login because it skips OAuth/keychain reads. These changes apply to inlined review jobs, not interactive work or writable implementation. Skill links are unchanged; no account configuration or MCP service was disabled globally.

## Provenance

Distilled from a June 2026 survey of converged community practice
(cross-vendor review gates, Ralph-loop descendants, spec-driven handoffs).
The redaction rule — never show the reviewer the author's self-assessment —
is the best-quantified finding in that corpus (~2–4x effect on review
quality). The writer ≠ reviewer invariant holds across practitioners who run
the roles in either direction; the direction itself is contested, which is
why the skill supports both author/reviewer directions.
