# Shared skill repository

Canonical authored skills live in `plugins/<skill>/`. Edit the source package, not generated harness entrypoints or vendor caches. Read the shared `skill-builder` guidance when changing a workflow across Claude Code, Codex and OMP.

## Task routing

Persistent tasks and follow-ups belong in Linear's **Jason workspace and Jason team**. Resolve current project and issue IDs; reuse an existing issue rather than creating a duplicate. If Linear is unavailable, report it without substituting another tracker. Do not use Beads for this repository.

Daily Obsidian plans remain the working surface; the existing backlog and GoalsWon retain legacy items and daily accountability. Do not bulk-migrate legacy items or duplicate Linear tasks. Broader Apart organization tracking stays in Notion.

## Maintenance

- `~/.claude/agent-config.toml` owns selection, host scope and generated discovery paths. Preserve disabled selections and edit their canonical configuration, not generated links.
- Keep changes scoped and preserve other sessions' work. Run checks appropriate to the changed behavior and review the exact staged diff; never bypass commit hooks.
- After settings, hooks or skill enablement changes, run `agent-config audit --runtime <affected-project-dir>` and `agent-config check`. Report unavailable runtime checks explicitly.
- Commit and push completed repository changes through the existing remote, handling upstream changes without discarding unrelated work. Report the commit, checks and any unresolved delivery issue.
- Deploy shared sources before configuration that points to them. The configuration maintenance guide lives in `~/.claude/README.md`. Vault notes reach cairn through Obsidian Sync only.
