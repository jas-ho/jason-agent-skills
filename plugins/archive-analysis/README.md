# Archive Analysis

Archive temporary markdown files while preserving actionable insights.

## Usage

Ask Claude to archive analysis files:
- "Archive these analysis files"
- "Archive COMPARISON.md and NOTES.md"
- "Clean up old markdown files"

## What It Does

1. Discovers untracked/old markdown files
2. Extracts actionable insights to TODO.md
3. Moves files to `archive/` with semantic naming
4. Commits to git, then deletes from working tree

Files remain accessible via git history but don't clutter workspace or pollute agent searches.

## Retrieve Archived Files

```bash
# View archived file
git show <commit>:archive/<filename>

# Restore to working tree
git show <commit>:archive/<filename> > <filename>

# Search archived content
git log --all -p -- "archive/*" | grep -A5 "search term"
```

## CLI

```bash
# Analyze untracked markdown (default)
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze

# Analyze all markdown
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze --mode=explore

# Analyze specific files
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze FILE1.md FILE2.md
```
