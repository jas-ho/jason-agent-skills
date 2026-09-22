---
name: start
description: Route new work to the right project folder in ~/Projects/. Creates project folders with README.md frontmatter, searches for existing projects, and opens tmux sessions. Use when the user says /start, describes new work, or needs to find where a topic belongs.
---

# Start: Route New Work to Project Folders

Route new work to the right project folder in `~/Projects/`. Search for existing projects, create new ones with proper scaffolding, write inception context, and open tmux sessions.

## Workflow

### Step 1: Parse Description

Extract from the user's input:

- **Topic**: what the work is about
- **Deadline/venue**: any mentioned dates, conferences, venues
- **Collaborators**: any mentioned people
- **Implied category**: research, work, life, ops, reading

If the user's description is too vague to route, ask one clarifying question using the host's user-input mechanism.

### Step 2: Smart Project Search

Check if a matching project already exists. Run all three searches:

```bash
# Exact directory match (fast)
fd -t d "<keyword>" ~/Projects --max-depth 2

# Recently visited (supplement, not comprehensive)
zoxide query --list 2>/dev/null | grep -i "<keyword>" || true

# Semantic search in README.md frontmatter + content
rg -il "<keyword>" ~/Projects --type md --max-depth 3
```

If no README.md files exist yet (new workspace), fall back to `fd -t d` + `ls ~/Projects/*/`.

Try multiple keywords derived from the topic. Don't rely on a single search term.

### Step 3: Present Findings

- **Exact match found**: ask "Found existing project at `~/Projects/research/foo/`. Use this, or create new?"
- **Partial match**: ask "Related project exists at X. Create subfolder there, or new project?"
- **No match**: proceed to Step 4

### Step 4: Suggest Category + Name

**Category routing:**

Read the category-level CLAUDE.md files for routing heuristics:

```bash
# Check which categories have routing rules
for dir in ~/Projects/*/; do
  if [ -f "$dir/CLAUDE.md" ]; then
    echo "=== $dir ==="
    head -30 "$dir/CLAUDE.md"
  fi
done
```

If no CLAUDE.md files exist or they lack routing rules, use these defaults:

- `research/`: papers, benchmarks, evaluations, hackathons (intellectual output for external stakeholders)
- `work/`: grants, contracts, funding, events, peer review, career dev, coaching, internal tooling
- `life/`: family, housing, hobbies, legal, tax, personal life management
- `ops/`: dotfiles, system config, automation
- `reading/`: reading notes, literature reviews (standalone)

If ambiguous between two categories, present the top two options through the host's user-input mechanism, with reasoning for each.

**Naming convention:**

- Default: `kebab-case` (2-4 words, lowercase, no underscores)
- Time-bounded work: `YYYY-MM_kebab-case` (e.g., `2026-03_icml-submission`)
- ALWAYS lowercase
- NEVER use underscores except after the date prefix

**Paper detection:** If the user mentions "paper", "submission", "deadline", or a venue name, suggest `research/` category and note in START.md that `/paper-collab` can set up the collaboration timeline.

### Step 5: Confirm

Use the host's native user-input mechanism for the unresolved location choice; honor any category/name already explicitly approved in this conversation:

- Category: `research/`
- Name: `multi-agent-eval`
- Time-bounded: yes/no (affects naming)

Create the folder once its location is authorized. Do not repeat a confirmation that the user has already supplied.

### Step 6: Create Folder + Scaffold

Create the project directory and populate it:

```bash
mkdir -p ~/Projects/<category>/<project-name>
zoxide add ~/Projects/<category>/<project-name>
```

**README.md** with YAML frontmatter:

```markdown
---
title: <title from user description>
status: active
category: <research | work | life | ops | reading>
created: <YYYY-MM-DD>
tags: [<lowercase-kebab-case tags>]
repo: ~/Code/<repo-name> # if applicable, omit if not
collaborators: [<Name (role)>] # if applicable, omit if not
venue: <venue name> # research papers only, omit if not
deadline: <YYYY-MM-DD> # if time-bounded, omit if not
---

# <Title>

<User's description of the project, cleaned up into a paragraph or two.>
```

**Additional scaffolding:**

- For `research/` projects: also create `literature/` subfolder
- For projects with a repo reference: include the `repo:` field in frontmatter

### Step 7: Write Inception Context

Append a timestamped entry to `START.md` in the project folder:

```markdown
## [YYYY-MM-DD HH:MM] - Started

**User's request:** <Full description the user provided>

**Context gathered:**

- <Search results, related projects found, decisions made>

**Suggested next steps:**

- <e.g., "Run /paper-collab to set up collaboration timeline">
- <e.g., "Check ~/Projects/research/related-project/ for related work">

---
```

If START.md already exists, ALWAYS append the new entry at the end. NEVER overwrite existing content.

### Step 8: Prepare the Working Context

On the Mac, use the shared `workspace` skill when this is a substantial, clearly separate task. Let it decide desktop reuse/creation. Before creating a desktop, prepare the project session below and pass its exact name as `--tmux-session`; this keeps the same session convention as `spawn`. Let the skill handle prepare-and-return behavior. If desktop setup is unavailable before submitting a create, use the tmux-only flow. Once submitted, preserve partial work and report failures rather than starting a second setup path.

Use the project folder's kebab-case name as the tmux session name. When creating a desktop, or when a tmux server already exists, reuse that exact session (`tmux has-session -t "=<project-name>"`) or create it detached with `tmux new-session -d -s "<project-name>" -c "<project-path>"`. Otherwise report the project path without starting a server. In the tmux-only flow, switch the current client only when the user wants to move there; otherwise report the session.

### Step 9: Print Confirmation

Print a summary:

- Project path (absolute)
- Desktop name/ID and tmux session when prepared, or any setup limitation
- "START.md written for the next session"
- If paper project: "Run `/paper-collab` to set up collaboration timeline and calendar reminders"

## Important Rules

- **NEVER** create a project folder without user confirmation
- **ALWAYS** search for existing projects before suggesting creation
- **ALWAYS** append to START.md, never overwrite
- Category routing heuristics live in category CLAUDE.md files; read them, don't hardcode fallback rules unless no CLAUDE.md exists

## Integration with /paper-collab

- **No overlap**: `/start` handles folder creation + metadata; `/paper-collab` handles collaboration workflow (timeline, calendar, Discord)
- **Handoff**: `/start` suggests `/paper-collab` in START.md for research papers; it does NOT auto-invoke `/paper-collab`
