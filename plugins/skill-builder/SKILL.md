---
name: skill-builder
description: Create or adapt shared authored skills for Claude Code, Codex, and OMP using the existing source and distribution conventions. Use when explicitly invoking skill-builder or making a workflow portable across these harnesses; use a native creator for ordinary single-harness skill creation.
---

# Shared skill authoring

Use this as the portability supplement to the active harness's native skill-creation guidance. Keep Codex's own skill-creator available; do not replace it or broaden this workflow into unrelated plugin/configuration work.

## Source and scope

For Jason's authored shared workflows, the canonical source is `jason-agent-skills/plugins/<skill-name>/`. The existing `agent-config` manifest distributes individual links, enabled selectors, and compatibility entry points. External repositories keep their own sources. Do not copy a second live authored source into a harness directory or edit vendor caches.

Preserve whether a workflow is user-wide or project-scoped. Project-only knowledge stays scoped to its project. When the user has already chosen the location or enabled state, use that decision. Shared defaults have explicit target/host exceptions; missing dependencies do not silently disable a requested skill.

## Shared package

Each package needs `SKILL.md` with `name` and a discriminating `description`. Preserve existing supported metadata. Add scripts, references, or assets only when the workflow needs them. Resolve bundled files relative to the actual loaded skill directory, not `~/.claude/skills` or a particular machine's home path.

```text
skill-name/
  SKILL.md
  scripts/       only deterministic operations the workflow needs
  references/    substantial conditional guidance
  assets/        templates or other output resources
```

Keep personal workflow facts when they are the actual purpose of a personal skill. Make required private context/dependencies explicit; a portable skill must report an unavailable dependency rather than invent its contents. Do not remove meaningful user-specific constraints merely to make the prose generic.

## What belongs in an adapter

Use ordinary native read/write/shell/question/subagent tools by their actual schemas. Avoid mandatory fictional tool names and model aliases from another harness. Prefer native workers for ordinary delegation; cross-model CLI pairing is an explicit workflow exception. A copied CC `allowed-tools`, `context`, `agent`, or `user-invocable` field is not evidence of equivalent permissions or lifecycle behavior elsewhere.

Keep domain decisions shared. Isolate only real differences: exact session identity/resume, process supervision, native event delivery, permission enforcement, command argument expansion, or service authentication. Do not build a universal runtime to translate every tool. Replace CC inline shell preexecution with an explicit shell step; treat invocation arguments as actual user input, preserving spaces and literal symbols.

Preserve established invocation policy. When a target needs different metadata, use its supported mechanism and consult that target's current documentation. Codex's optional `agents/openai.yaml` can describe invocation policy and dependencies; it does not install or authenticate those dependencies. Exact slash compatibility belongs to the reconciler's thin wrappers; this package holds the substantive workflow once.

## Mechanical code and verification

Use scripts for repeated parsing, guarded writes, output processing, or process construction. The agent interprets intent and adjudicates findings. Keep machine-oriented scripts non-interactive with useful exit status and structured output. For this Python environment use uv/PEP 723 or standard-library-only scripts; do not introduce a global pip installation.

Scale checks to the change. Validate frontmatter and all referenced relative assets. For session or command constructors, use fixtures to prove argument preservation, exact identity, failure behavior, and no unintended process launch. Avoid tests that only reproduce headings or wording. Never run a real send, publish, login, or destructive operation merely to demonstrate that a skill loads.

Report four separate facts: installed, discovered, dependency-ready, and operationally exercised. Date/version empirical harness claims. A help command can establish syntax but not successful authenticated work; an offline constructor test cannot establish live lifecycle behavior.

For a substantive shared skill revision, use an independent review when available and authorized. Review realistic behavior and scope, then apply only supported findings. Distribution and settings changes go through `agent-config`; before committing affected configuration, run its required runtime audit. Do not claim unfinished targets work or leave the skill hidden solely because an external service needs setup.
