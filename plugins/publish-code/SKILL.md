---
name: publish-code
description: Prepare and publish an open-source project. Use when user wants to open-source a repo, make a project public, or prepare code for release.
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, AskUserQuestion]
---

# Publish Code

Guide a repository from private to public. Adapts to user intent - from "just make it public" to "want contributors."

## Workflow

```
1. QUICK SCAN     (2-3s) → Gather context
2. SMART QUESTION        → What's your goal?
3. TARGETED WORK         → Based on intent
4. PUBLISH               → Make public, optional announcements
```

## Phase 1: Quick Scan

Run these checks synchronously (~2-3 seconds total):

```bash
# Git state - dirty?
git status --porcelain | head -5

# Remote exists?
git remote -v

# Already public? What is it?
gh repo view --json visibility,description,url 2>/dev/null || echo "No GitHub remote"

# What files exist?
ls -la LICENSE* README* CONTRIBUTING* 2>/dev/null
ls pyproject.toml package.json Cargo.toml go.mod 2>/dev/null
```

**Parse results into context:**
- `is_dirty`: Has uncommitted changes?
- `has_remote`: Connected to GitHub?
- `is_public`: Already visible to world?
- `has_license`: LICENSE file exists?
- `has_readme`: README exists?
- `language`: Python/Node/Rust/Go/other
- `description`: One-line summary from GitHub or README first line

## Phase 2: Smart Question

Use AskUserQuestion with context baked into the question:

**Example (adapt based on scan results):**

> "This is a Python CLI tool, currently private, has README but no license.
> What's your goal?"

Options:
1. **Just make it public** - Minimal: add license, quick sanity check, flip visibility
2. **Make it usable by others** - Standard: license, README polish, install docs, portability check
3. **Want community/contributors** - Full: above + CONTRIBUTING.md, issue templates, CI

**Adapt the question:**
- If already public: "Already public. Want to improve discoverability?"
- If dirty state: "You have uncommitted changes. Commit first, or proceed anyway?"
- If no remote: "No GitHub remote. Want to create one?"

## Phase 3: Targeted Work

### Path A: Minimal ("just make it public")

**1. Add LICENSE if missing**

Ask which license:
- **MIT** - Simple, permissive. Best for utilities/libraries.
- **Apache-2.0** - Adds patent protection. Better for applications.

Fetch from GitHub API and substitute placeholders:

```bash
gh api /licenses/mit --jq '.body' | sed "s/\[year\]/$(date +%Y)/g" | sed 's/\[fullname\]/Jason Hoelscher-Obermaier/g' > LICENSE
```

For Apache-2.0:
```bash
gh api /licenses/apache-2.0 --jq '.body' > LICENSE
# Apache doesn't need year/name substitution in the license file itself
```

**2. Quick sanity check**

Read README and any config files. Look for:
- Hardcoded `/Users/jason/` paths (flag for review)
- Apart Research / apartresearch references (should these be generalized?)
- API keys or secrets (STOP if found)
- Notion database IDs, Discord channel IDs (org-specific?)

This is Claude reading files, not mechanical grep. Use judgment.

**3. Make public**

```bash
gh repo edit --visibility public --accept-visibility-change-consequences
gh repo view --json visibility,url
```

Done. No announcements needed for minimal path.

---

### Path B: Standard ("usable by others")

Everything in Minimal, plus:

**1. README quality check**

Read full README. Verify it has:
- [ ] One-line description at top
- [ ] Installation instructions (with actual commands)
- [ ] Usage example (working code or CLI invocation)
- [ ] License mention

If missing sections, offer to add them. Keep it concise.

**2. Portability audit**

Run the audit script (located alongside this SKILL.md):

```bash
./audit.py [repo-path]
```

The script uses **gitleaks** for secrets if installed (comprehensive, scans git history), otherwise falls back to simple pattern matching.

Review output for:
- `hardcoded_paths`: Fix or document
- `potential_secrets`: STOP and address
- Missing `.gitignore` patterns

**3. Claude review of key files**

Read these files and flag anything that assumes personal/org context:
- README.md (intro and examples)
- Config files (config.toml, settings.py, etc.)
- Example files

Look for:
- Personal research interests (should be examples, not Jason's actual interests)
- Apart-specific terminology (Sprint, Studio, Fellowship)
- Hardcoded Notion/Discord/Slack references
- Vienna/Austrian-specific content (flag, might be intentional like skitour)

**4. GitHub topics**

If no topics set, suggest relevant ones:

```bash
gh repo edit --add-topic python --add-topic cli-tool
```

**5. Make public + optional announcement**

Make public, then offer to draft a tweet:

```
🚀 Just open-sourced [name]!

[One-line description]

GitHub: [url]
```

Keep it simple. User can embellish.

---

### Path C: Full ("want contributors")

Everything in Standard, plus:

**1. CONTRIBUTING.md**

Create if missing:

```markdown
# Contributing

## Setup

[Clone and install instructions]

## Development

[How to run tests, lint, etc.]

## Pull Requests

1. Fork the repo
2. Create a branch
3. Make changes
4. Submit PR
```

Keep it short. Long CONTRIBUTING.md files go unread.

**2. Issue templates**

Create `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug Report
about: Report a bug
labels: bug
---

**What happened?**

**Steps to reproduce**

**Expected behavior**

**Environment**
- OS:
- Version:
```

Create `.github/ISSUE_TEMPLATE/feature_request.md`:

```markdown
---
name: Feature Request
about: Suggest an idea
labels: enhancement
---

**Problem**

**Proposed solution**
```

**3. Announcements**

Offer to draft for multiple platforms:

**Hacker News (Show HN):**
```
Show HN: [Name] – [description]

[2-3 sentences: what it does, why it exists]

GitHub: [url]

Looking for feedback on [specific aspect].
```

**Reddit:**
```
[Name] - [description] [open source]

Just open-sourced this tool that [solves X].

Quick start: [install command]

GitHub: [url]
```

Present drafts for user approval. Never post without explicit confirmation.

---

## Jason-Specific Patterns

When reviewing, specifically check for:

| Pattern | What to flag |
|---------|--------------|
| `/Users/jason/` | Hardcoded path - make relative |
| `Apart Research`, `apartresearch` | Org reference - generalize? |
| `Sprint`, `Studio`, `Fellowship` | Apart terminology |
| Notion DB IDs (`xxxxxxxx-xxxx-...`) | Org-specific config |
| Discord channel names | Should be configurable |
| Research interest lists | Should be examples, not personal |
| `@apartresearch.com` emails | Remove or generalize |

## Important Rules

- **NEVER make public without explicit user confirmation**
- **NEVER post announcements without user approval**
- **STOP immediately if real secrets found** (API keys, tokens)
- **Ask, don't assume** - if unsure whether something is personal/sensitive, ask
- **80/20** - Don't over-polish. Ship it.

## Quick Reference

**License cheat sheet:**
| License | Best for |
|---------|----------|
| MIT | Libraries, utilities, quick tools |
| Apache-2.0 | Applications, anything with patent concerns |

**Announcement priority (for dev tools):**
1. Twitter/X (quick, low friction)
2. Hacker News (high impact if it lands)
3. Reddit (targeted subreddits)
