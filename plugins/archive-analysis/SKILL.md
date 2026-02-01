---
name: archive-analysis
description: Clean up workspace by archiving one-time analysis files. Auto-discovers untracked markdown files, extracts insights to task tracking, and moves files to archive/ with chronological naming. Use when user wants to clean up workspace or archive temporary documentation.
allowed_tools: [Bash, Read, Write, Edit, Grep, Glob]
---

# Archive Analysis Skill

Archive temporary markdown files while preserving insights. Files are committed to git then deleted from working tree to avoid context pollution for agents doing codebase searches.

## When to Use

- "Archive these analysis files"
- "Clean up old markdown files"
- "Archive FILENAME.md"

Avoid triggering on generic "clean up my workspace" - be more specific about markdown/analysis files.

## Workflow

### 1. Discover Files

**Untracked markdown (default):**

```bash
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze --mode=untracked
```

**All markdown (comprehensive):**

```bash
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze --mode=explore
```

**Specific files:**

```bash
uv run ~/.claude/skills/archive-analysis/archive_utils.py analyze FILE1.md FILE2.md
```

### 2. Decide What to Archive

**Archive:** One-time analysis, session notes, drafts, old reports, prepared prompts
**Keep:** README, TODO, ARCHITECTURE, templates, actively referenced docs

### 3. Present Plan & Get Approval

```
Found 2 untracked analysis files:

Recommend archiving:
- COMPARISON.md (9 KB) - team vote analysis
- NOTES.md (5 KB) - session notes

Archive as: 2024-11-24-tin-votes-*

Insights to extract:
- Add to TODO.md: "Complete assessments for 7 topics"

Proceed?
```

### 4. Execute

1. Extract insights to TODO.md (or detected task system)
2. Create `archive/` and `archive/index.md` if needed
3. Move files: `mv FILE.md archive/YYYY-MM-DD-description-FILE.md`
4. Update `archive/index.md` with entry
5. Commit: `git add archive/ TODO.md && git commit -m "docs: archive [description]"`
6. Get commit hash, update index.md with hash
7. Delete archived files: `git rm archive/YYYY-MM-DD-*.md && git commit -m "docs: remove archived files from working tree"`

### 5. Report

```
Archived 2 files (in git history, removed from working tree):
- COMPARISON.md → commit abc123
- NOTES.md → commit abc123

Insights added to TODO.md.
Retrieve with: git show abc123:archive/FILENAME.md
```

## Key Rules

- **Flat structure:** `archive/YYYY-MM-DD-description-FILE.md` (no subfolders)
- **Always ask** before archiving
- **Extract insights first** before archiving
- **Two commits:** Add to archive, then delete (preserves in history, cleans working tree)
- **Check references:** Warn if file is referenced elsewhere

## Why Delete After Commit?

Files committed then deleted remain in git history but don't pollute agent context when searching the codebase. Retrieve with `git show <commit>:archive/<file>`.
