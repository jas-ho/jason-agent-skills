# codex-pair

A shared CC/Codex/OMP workflow for explicitly cross-model pairing with the Claude or Codex CLI. Two
modes: **REVIEW** (codex reviews a diff, plan, or prompt that Claude authored;
verdict protocol, bounded rounds, session-resume so later rounds verify fixes)
and **IMPLEMENT** (Claude writes a spec plus an executable acceptance gate,
codex implements until the checks pass, Claude reviews the diff hard). The
invariant behind both: the author is never the reviewer, and the reviewer never
implements its own feedback — the models have decorrelated error distributions,
and that's where the value comes from.

> **Requires the `codex` CLI, authenticated.** Verified against codex-cli
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

The updated one-shot, persistent-review, and writable-implementation contracts in SKILL.md supersede the original single launcher. They have been inspected against the installed CLI help; this staged migration has not yet exercised a new real counterpart run.

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
  CLI directly avoids both.
- `codex login status` can report logged-in after the refresh token was
  revoked (2026-09-08); the first real `codex exec` then fails. Smoke-test
  with a trivial exec after any account change.
- Background codex jobs finish silently from Claude Code's point of view;
  poll the output file rather than waiting for a completion signal.
- Backgrounding a _foreground_ codex run from the Claude Code UI can kill it
  silently (0-byte output, stdin/TTY detach). Always launch as a background
  task from the start, with `< /dev/null`.
- `codex exec` runs that need to read files themselves can hang for hours with
  0-byte output. Inlining the content into the prompt avoids this entirely.

## Provenance

Distilled from a June 2026 survey of converged community practice
(cross-vendor review gates, Ralph-loop descendants, spec-driven handoffs).
The redaction rule — never show the reviewer the author's self-assessment —
is the best-quantified finding in that corpus (~2–4x effect on review
quality). The writer ≠ reviewer invariant holds across practitioners who run
the roles in either direction; the direction itself is contested, which is
why the skill has a routing table instead of a fixed assignment.
