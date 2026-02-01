# Testing the Safe-Commit Skill

This document describes how to test and validate changes to the safe-commit skill itself.

## Quick Test

Generate test cases:

```bash
.claude/skills/safe-commit/safe_commit.sh --generate-tests
```

This creates a `.safe-commit-tests/` directory with files covering all major scenarios.

## Test Scenarios

The generator creates these test files:

### 1. Clean Python File

```bash
git add .safe-commit-tests/clean.py && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: All checks passed, validation complete

### 2. Python with Fixable Issues

```bash
git add .safe-commit-tests/fixable.py && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Auto-fixed and re-staged, then passes validation

### 3. Python with Lint Error

```bash
git add .safe-commit-tests/lint_error.py && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Shows ruff/mypy error about undefined variable

### 4. Python with Type Error

```bash
git add .safe-commit-tests/type_error.py && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Shows mypy type error clearly

### 5. Clean Shell Script

```bash
git add .safe-commit-tests/clean.sh && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: No shellcheck warnings

### 6. Shell with Issues

```bash
git add .safe-commit-tests/shell_issue.sh && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Shows shellcheck warnings about unquoted variables

### 7. Local File (Hard Block)

```bash
git add .safe-commit-tests/config.local.py && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Exits with error, "LOCAL FILES DETECTED (commit blocked)"

### 8. Sensitive File (Warning)

```bash
git add .safe-commit-tests/.env.example && .claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Shows warning but allows commit

### 9. Path Handling Test

```bash
cd .claude/skills && git add ../../.safe-commit-tests/clean.py && ../../.claude/skills/safe-commit/safe_commit.sh
```

**Expected**: Works correctly from subdirectory, shows git root

## What to Check

When testing changes to the script, verify:

1. **Auto-fixing works**: Files with fixable issues are corrected and re-staged
2. **Output is clear**: Validator output is well-structured and easy to read
3. **No false positives**: "All checks passed!" doesn't trigger errors
4. **Path handling**: Works from any directory in the repo
5. **Hard blocks work**: Local files actually block the commit
6. **Exit codes**: Script exits 1 only for hard blocks, 0 otherwise

## Cleanup

After testing:

```bash
rm -rf .safe-commit-tests
git restore --staged .safe-commit-tests 2>/dev/null || true
```

## Manual Testing

You can also test with real staged changes:

1. Make changes to a file
2. Stage it: `git add <file>`
3. Run: `.claude/skills/safe-commit/safe_commit.sh`
4. Review the output
5. Unstage if needed: `git restore --staged <file>`

## Expected Output Format

The script should produce output like:

```
ℹ === Safe Commit Validation ===
ℹ Running pre-flight checks...
ℹ Git root: /path/to/repo
✓ Found 1 staged file(s)
ℹ Auto-fixing staged files...
ℹ Running validators...

=== Validating: script.py ===
--- ruff check ---
All checks passed!

--- mypy ---
Success: no issues found in 1 source file

ℹ Running security and safety checks...
ℹ Commit size: +10 -2 lines (12 total)
STATS: +10 -2 (12 total)

=== Summary ===
Files staged: 1

ℹ Validation complete - review output above
```

## Debugging Issues

If the script behaves unexpectedly:

1. Check which tools are available: run `ruff --version`, `mypy --version`, etc.
2. Look for `MISSING_TOOLS:` warnings in output
3. Verify you're in a git repository: `git status`
4. Check git root detection: look for "Git root:" in output
5. Run validators manually to compare output: `ruff check <file>`

## Adding New Test Cases

To add a new test scenario, edit `generate_test_cases()` in `safe_commit.sh`:

```bash
# Add after existing test cases
cat >"$test_dir/your_test.py" <<'EOF'
# Your test code here
EOF
```

Then add the test scenario to the printed instructions.
