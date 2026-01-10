---
name: safe-commit
description: Validate code quality and commit changes. Supports Python, Shell, and Markdown. Use for code commits.
allowed-tools: [Bash, Read, Grep, AskUserQuestion]
---

# Safe Commit

Automatically fix code quality issues and validate changes before committing.

## How It Works

The script auto-fixes everything it can (formatting, fixable lint issues), then runs validators and shows you their raw output. You read the tool output directly, decide if there are problems, and proceed accordingly.

**Key Philosophy**: You're an intelligent agent - the script doesn't parse tool output or interpret "errors" vs "success." It just shows you what ruff, mypy, shellcheck, etc. say, and you decide.

**Note on tool selection:** The script prefers project-managed tools (via `uv run --group dev` if `pyproject.toml` exists) over global tools, which allows mypy to see project dependencies and validate imports properly.

## Workflow

### 1. Stage Your Changes

**IMPORTANT:** Stage files before running validation:

```bash
git add <files-to-commit>
```

The script validates **only staged changes**. If you run it without staging, you'll get:
```
Exit code 1: No staged changes to commit
```

### 2. Run Validation

```bash
~/.claude/skills/safe-commit/safe_commit.sh
```

The script will:
- Auto-fix all fixable issues (formatting, auto-fixable lint errors)
- Re-stage any files that were modified during auto-fixing
- Run validators and show their full output
- Check for safety concerns (local files, sensitive files)
- Show commit size statistics

**If you see `MISSING_TOOLS:`** - Some validators are unavailable. Validation will be limited but script continues.

### 3. Review Output and Fix Issues

Read the validator output directly and **fix any problems found**:

**Clean output** - proceed with commit:
```
=== Validating: script.py ===
--- ruff check (via project env) ---
All checks passed!

--- mypy (via project env) ---
Success: no issues found in 1 source file
```

**Errors found** - fix them before committing:
```
=== Validating: script.py ===
--- ruff check ---
script.py:10:5: F821 Undefined name `foo`

--- mypy ---
script.py:10: error: Name 'foo' is not defined
```
→ Undefined variable on line 10 - **edit the file to fix it**, then re-run validation

**Important**:
- **Always fix errors** - Don't proceed with broken code unless you have a very good reason
- **Explain any exceptions** - If you skip an error, tell the user why
- Use Edit tool to fix issues, then re-stage and re-run safe-commit

**Special cases**:
- **Local files detected** → Hard block, must unstage them
- **Sensitive files detected** → Ask user to confirm before committing
- **Auto-fixed files** → Review `git diff --cached` to see what changed

### 4. Generate Commit Message

- Use conventional format (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`)
- Focus on WHY, not just WHAT
- Check recent style: `git log -5 --oneline`
- Ask user for confirmation

### 5. Execute Commit

```bash
git commit -m "your message here"
```

## What the Script Does

The script uses language-specific tools for formatting, linting, and validation:

**Python:**

- Auto-fix: `ruff format` (formatter) + `ruff check --fix` (linter with auto-fix)
- Validate: `ruff check` (linter) + `mypy` (type checker)

**Shell:**

- Auto-fix: `shfmt -w` (formatter)
- Validate: `shellcheck` (linter)

**Markdown:**

- Auto-fix: `markdownlint --fix` + `prettier --write` or `mdformat` (formatters)
- Validate: `markdownlint` (linter)

**Auto-fixes (re-stages automatically):**

- All fixable issues are automatically corrected and re-staged
- Modified files are automatically added back to the staging area

**Hard blocks (exits with error):**

- Local files (*.local.*)
- No staged changes
- Not in a git repository

**Shows in output (you interpret):**

- Linting errors (ruff, shellcheck, markdownlint)
- Type errors (mypy)
- All other validation results
- **Line-length warnings are informational** - don't block on MD013 in markdown

**Warns (doesn't block):**

- Sensitive files (.env, credentials, .pem)
- Large commits (>300 lines)

## Splitting Commits

If changes are unrelated, stage them separately:

```bash
# First commit
git add <first-group-of-files>
~/.claude/skills/safe-commit/safe_commit.sh
git commit -m "first commit"

# Second commit
git add <second-group-of-files>
~/.claude/skills/safe-commit/safe_commit.sh
git commit -m "second commit"
```

To unstage files already staged:
```bash
git restore --staged <unwanted-files>
```

## Important

- **Fix errors before committing** - Don't proceed with broken code
- **Review validator output** - You interpret what tools report, but act on errors
- **Never commit .local.* files** - Hard blocked by script
- **Always read the diff** - Understand what's changing
- **Check auto-fixes** - Review what was automatically fixed
- **Think about coherence** - Should changes be in separate commits?

## Troubleshooting

If the script itself seems broken or needs improvement, see [TESTING.md](TESTING.md) for how to test and validate changes to the safe-commit skill.
