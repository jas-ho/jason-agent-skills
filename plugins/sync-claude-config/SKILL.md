---
name: sync-claude-config
description: Check for Claude config updates, commit changes semantically, and push to remote
---

# Sync shared agent configuration

## Harness and dependencies

Use the current harness's native file, shell, question and worker tools. CC calls its question tool AskUserQuestion; OMP uses ask; Codex uses the question interface actually exposed in the session, with a plain question when unavailable. Tool names in examples describe operations, not a requirement to nest Claude Code. Incoming command arguments are literal user text, never shell code. A skill invocation may supply the same text directly. Check each required CLI/service before its step; keep the workflow available and report missing dependencies. Preserve explicitly optional signal behavior below.

Inspect repository ownership before staging. Shared skill content belongs in jason-agent-skills and generated configuration belongs to agent-config. Preserve other sessions' changes; stage only the intended files. After settings, hooks or selection changes, run `agent-config audit --runtime <affected-project>` before committing. A missing runtime is a stated verification gap. Do not initialize or change another repository merely because it lacks the expected tool.

You are tasked with syncing Claude configuration changes in the `~/.claude` directory. Follow these steps:

## 1. Check Git Status

First, verify the expected checkout:

```bash
config_root=$(cd ~/.claude && pwd -P) || exit 1
repo_root=$(git -C "$config_root" rev-parse --show-toplevel 2>/dev/null) || repo_root=""
if [ "$repo_root" != "$config_root" ]; then
  echo "ERROR: ~/.claude is not the expected Git checkout"
  exit 1
fi
```

Stop and report this error. Do not initialize a replacement repository.

Run `git -C ~/.claude status` to see what has changed. If there are no changes, inform the user and stop.

**Important**: Always use `git -C ~/.claude` instead of `cd ~/.claude && git`. Claude Code blocks `cd && git` compound commands as a hardcoded security measure (bare repository attack prevention), which cannot be overridden by permission rules.

## 2. Show Untracked Important Files

Check if any important files should be added:

```bash
git -C ~/.claude ls-files --others --exclude-standard | grep -E '\.(md|json)$|^commands/' | head -20
```

Classify each result by ownership before offering to add it. Never stage generated `AGENTS.md` files, generated skill or command entrypoints, external-repository links, or the live `settings.json`. Edit and stage the canonical source or manifest instead.

## 3. Examine Changes and Group Semantically

For changed files, use `git diff` to see what changed. Analyze:

- **Commands**: New, modified, or deleted slash commands
- **Settings**: Changes exported by `agent-config apply` to the tracked `settings.<kernel>.json` snapshot; `settings.json` is live host state and must never be staged
- **Global instructions**: Updates to CLAUDE.md
- **Configs**: Plugin or agent configurations

Group related changes together.

### Skip Noise Changes

**`plugins/known_marketplaces.json`**: Only commit if plugins were added/removed. Skip if only `lastUpdated` timestamps changed.

To check if changes are substantive:

```bash
git -C ~/.claude diff plugins/known_marketplaces.json | grep -v '"lastUpdated"' | grep '^[+-]' | grep -v '^[+-]{' | grep -v '^[+-]}' | grep -v '^[+-]\s*$' | grep -v '^---' | grep -v '^+++'
```

If this outputs nothing, the changes are timestamp-only - skip committing this file.

### Reconcile derived and per-host config (always, before committing)

After all CLAUDE.md edits are final, run the reconciler. It regenerates `~/.codex/AGENTS.md` from the `[codex.agents_md]` section list in `~/.claude/agent-config.toml`, reconciles the shared workflow catalog and generated skill/command entrypoints for Claude Code, Codex and OMP, installs the repo's git hooks (pre-commit: gitleaks + no outside-repo symlinks), exports the live settings.json to the tracked `settings.<kernel>.json` snapshot, and reports settings parity drift against the other host:

```bash
~/.claude/user-scripts/agent-config apply
~/.claude/user-scripts/agent-config check
~/.claude/user-scripts/agent-config audit --runtime "$PWD"
```

- Nonzero exit with `ERROR`/`ABORT` (renamed CLAUDE.md heading not in the section list, AGENTS.md over budget, missing/ambiguous root, invalid skill metadata, FOREIGN real file at a destination, credential-looking value in settings): STOP and report the exact line. Renaming a `##` heading in CLAUDE.md means editing `[codex.agents_md].sections` in the same commit.
- `SETTINGS`/`KEY` drift lines mean the two hosts' settings differ on a key not listed in `host_only`: tell the user which key; fixing it means editing the live settings.json on the right host (never the snapshot) or adding the key to `host_only` with a reason. Hooks are compared per event with home paths normalized; a hook that exists on one host only goes on the other host too (same command with that host's home; the comparison ignores entries matching `host_only_hooks`, currently the Orca desktop and jcode hooks).
- `STALE`/`UNDECLARED` lines are symlinks the manifest does not know; ask before removing anything.
- Declare shared workflows under `[workflows.<id>]` in `agent-config.toml`, with canonical source, target/host scope, commands and dependencies. Add ignore rules for generated paths that Git does not already ignore; never commit a link outside the repository. Run `agent-config report --json` before changing selection. Its `selector_requirements` describe the native Claude, Codex and OMP prerequisites; update only those fields through supported configuration while preserving unrelated state and existing disables. Apply checks these selectors and does not write them for you. Codex disables must cover the resolved source path. Cairn receives OMP configuration and skills now, while OMP installation remains deferred.
- Treat a shared-source pull as a live deployment. Add new shared paths without removing the old ones, deploy the sources, then deploy the manifest; retire old paths only after every applicable host has reconciled. Reconciliation must run after the relevant repository pulls complete successfully. A first cutover needs exact legacy-path adoption as well as selector setup; never remove a rollout hold until its preflight and apply/check pass. Commits go through the pre-commit hook; never use `--no-verify`.

## 4. Commit Changes in Logical Groups

Commit changes with descriptive messages following conventional commit format:

**Examples:**

- New command: `feat(commands): add sync-claude-config command`
- Updated command: `feat(commands): enhance link-artifacts with error handling`
- Settings snapshot change: `feat(settings): enable always-thinking mode`
- Instructions: `docs(claude): update global instructions for code reviews`
- Multiple commands: `feat(commands): add backup and restore commands`
- Fix: `fix(commands): correct path handling in sync-dotfiles`

**Format:** `<type>(<scope>): <description>`

**Types:**

- `feat` - New functionality or commands
- `fix` - Bug fixes
- `refactor` - Code improvements
- `docs` - Documentation (CLAUDE.md)
- `chore` - Maintenance tasks

**Scopes:**

- `commands` - Slash commands
- `settings` - tracked `settings.<kernel>.json` snapshots, never live `settings.json`
- `claude` - CLAUDE.md
- `plugins` - Plugin configs
- `agents` - Agent definitions

## 5. Add and Commit

For each logical group:

```bash
git -C ~/.claude add <files>
git -C ~/.claude commit -m "<commit message>"
```

## 6. Pull Remote Changes and Push (if configured)

Check if remote is configured:

```bash
git -C ~/.claude remote -v
```

If remote exists, pull any remote changes first (another machine may have pushed), then push:

```bash
git -C ~/.claude pull --rebase
git -C ~/.claude push
```

If the rebase has conflicts, abort (`git -C ~/.claude rebase --abort`) and inform the user. Don't force-push or auto-resolve.

If no remote, ask user if they want to add one (e.g., private GitHub repo).

## 7. Summary

Provide a summary:

- Files changed
- Commits created (with messages)
- Push status
- Any untracked important files

## Important Notes

- **Keep commits atomic**: One logical change per commit
- **Review before committing**: Never commit secrets, tokens, or sensitive data
- **Check .gitignore**: The top level of ~/.claude is an allowlist (`/*` plus `!` lines); a new authored top-level file needs a `!` line, a new CLI runtime dir goes under the known-runtime list. `agent-config check` reports anything caught only by the catch-all as UNLISTED
- **Remote repository**: Consider a private repo for your configs
- **Generated files**: Never stage generated instructions, links, or live settings; commit their canonical source or manifest

## Security Checklist

Before committing, verify you're not committing:

- API tokens or keys
- Session history with sensitive info
- Private conversation data
- Machine-specific paths with sensitive info

## Missing checkout

If `~/.claude` is not the expected checkout, stop and report it. This maintenance skill never initializes the repository, performs a blanket `git add -A`, creates an initial commit, or replaces its remote.
