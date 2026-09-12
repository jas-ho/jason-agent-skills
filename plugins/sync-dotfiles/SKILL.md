---
name: sync-dotfiles
description: Check for dotfile updates, commit changes semantically, and push to remote
---

## Harness and dependencies

Use the current harness's native file, shell, question and worker tools. CC calls its question tool AskUserQuestion; OMP uses ask; Codex uses the question interface actually exposed in the session, with a plain question when unavailable. Tool names in examples describe operations, not a requirement to nest Claude Code. Incoming command arguments are literal user text, never shell code. A skill invocation may supply the same text directly. Check each required CLI/service before its step; keep the workflow available and report missing dependencies. Preserve explicitly optional signal behavior below.

Inspect repository ownership before staging. Shared skill content belongs in jason-agent-skills and generated configuration belongs to agent-config. Preserve other sessions' changes; stage only the intended files. After settings, hooks or selection changes, run `agent-config audit --runtime <affected-project>` before committing. A missing runtime is a stated verification gap. Do not initialize or change another repository merely because it lacks the expected tool.

<!-- Requires: macOS (chezmoi) -->

You are tasked with syncing dotfile changes tracked by chezmoi. Follow these steps:

## 1. Sanity Check for Untracked Important Dotfiles

First, check if there are important dotfiles in the home directory that should be tracked but aren't:

```bash
check-untracked-dotfiles
```

If any important files are untracked, ask the user if they want to add them before proceeding.

## 2. Check for Changes

Run `chezmoi status` to see what has changed. If there are no changes, inform the user and stop.

## 3. Examine Changes and Group Semantically

For each changed file, use `chezmoi diff --reverse <file>` to see what changed.

**Important**: Use `--reverse` because it shows destination → source (what will be committed to git). Without it, `chezmoi diff` shows source → destination (what _applying_ would do), which is the opposite direction and leads to misreading the changes.

Analyze the changes to understand:

- What was modified (e.g., aliases, environment variables, keybindings, theme settings)
- Whether changes are related across files
- What would make a good semantic commit message

## 4. Commit Changes in Logical Groups

Commit changes in logical groups with descriptive commit messages. Examples:

- If `.zshrc` has new aliases → "feat(zsh): add aliases for X and Y"
- If `.gitconfig` has new settings → "feat(git): update user config for X"
- If `.tmux.conf` has keybinding changes → "feat(tmux): update keybindings"
- If multiple files have theme changes → "style: update terminal theme to X"
- If it's a fix → "fix(zsh): correct path configuration"

Use conventional commit format: `<type>(<scope>): <description>`

Types: feat, fix, refactor, style, docs, chore

## 5. Pull Remote Changes and Push

Pull any remote changes first (another machine may have pushed), then push:

```bash
chezmoi git -- pull --rebase
chezmoi git -- push
```

If the rebase has conflicts, abort (`chezmoi git -- rebase --abort`) and inform the user. Don't force-push or auto-resolve.

## 6. Summary

Provide a summary of:

- How many files were updated
- What commits were created
- Whether push was successful
- Any untracked important dotfiles that need attention

## Important Notes

- Always commit each logical change separately - don't batch unrelated changes
- Write clear, descriptive commit messages
- If you're unsure about grouping changes, ask the user
- Never commit sensitive files like SSH keys or AWS credentials
- Use `chezmoi add <file>` to stage changes to the chezmoi source
- Use `chezmoi git -- <command>` for all git operations (avoids directory changes and permission prompts)

## Git Operations via Chezmoi

Always use `chezmoi git --` instead of `cd $(chezmoi source-path) && git ...`:

```bash
# Check status
chezmoi git -- status

# Stage files (use chezmoi's dot_ prefix naming)
chezmoi git -- add dot_zshrc executable_dot_tmux.conf

# Commit
chezmoi git -- commit -m "feat(zsh): add new aliases"

# Push
chezmoi git -- push
```

Note: File names in the chezmoi source use prefixes like `dot_` (for dotfiles) and `executable_` (for executable files). Use `chezmoi source-path ~/.zshrc` to find the exact source file name if needed.

## Getting Help with Chezmoi

If you need help with chezmoi commands:

1. Use `chezmoi --help` to see all available commands
2. Use `chezmoi help <command>` for detailed help on a specific command (e.g., `chezmoi help add`)
3. The built-in help includes examples and all available flags
