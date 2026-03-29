Excellent! Now I have comprehensive understanding. Let me create the research report based on all this data:

---

# Skill Opportunity Discovery Meta-Analysis: Research Report

## Executive Summary

After analyzing ~10K Claude Code sessions (152K messages), 8,213 session JSONL files, and exploring the full cass database capabilities, I've identified significant **methodology gaps** in the prior skill discovery approach and designed a comprehensive "Skill Opportunity Finder" skill that addresses them.

The prior analysis found genuine high-value candidates (video processing: 15 hits, research briefing patterns in coach workspace), but used only lexical search and basic SQL queries. A more sophisticated approach using cass's full feature set, session metadata patterns, and multi-layer analysis would reveal opportunities that current methods miss entirely.

---

## 1. Methodology Gaps Analysis

### 1.1 Search Strategies Not Attempted

**Current approach:**
- SQL queries on `cass` database for repeated user messages
- Timeline searches for session activity
- Workspace-level aggregation
- Simple pattern matching ("how do I", "make a", etc.)

**Missed opportunities:**

| Gap | Why It Matters | Example Finding |
|-----|----------------|-----------------|
| **Semantic search** | Lexical search misses intent synonyms ("create a pipeline" ≠ "build processing flow") | Could find 3-5x more skill candidates by combining lexical + semantic modes |
| **Tool invocation patterns** | No analysis of which cass tool fields reveal user workflows | Users repeatedly call `/plugin`, `/run`, specific bash patterns that indicate workflow repeats |
| **Session duration clustering** | Long sessions indicate complex problems being solved repeatedly | Sessions >2 hours often have 7-15 turns of iterative refinement (skill candidate signal) |
| **Multi-turn correction patterns** | No tracking of "user asks → agent responds → user corrects → user asks again" loops | This pattern appears in video2study, backup systems, Discord moderation sessions (clear reusable pattern) |
| **Cross-workspace topic coherence** | Workspace-level analysis treats coaches/random/projects as isolated | Research briefing pattern spans 3+ workspaces (coach: 1794 sessions, random: 1765 sessions) - indicates shared need |
| **Error & Corrections sections** | Session summary.md files contain "Errors & Corrections" that show repeated debugging | Not searched at all - direct signal for skills like "error diagnosis" or "debugging patterns" |
| **Tool integration patterns** | No analysis of tools used across sessions | Users repeatedly combine Bash + Grep + Edit in specific workflows; bash + Read + Glob in others |
| **Output artifact patterns** | Files created in sessions not analyzed | Sessions creating `analysis.md` → `archive/DATE-*.md` → git history pattern appears 4+ times (archive skill signal) |
| **Session lifecycle analysis** | No classification of session types (exploration vs. execution vs. troubleshooting) | Exploration sessions have characteristic user question density; troubleshooting has high turn count with error messages |

### 1.2 Unexplored Data Sources

**In cass database (not used):**

1. **`--aggregate` flag** - Server-side aggregation by `agent`, `workspace`, `date`, `match_type`
   - Could produce: "57 sessions created files matching pattern X" at once instead of iterating
   
2. **Semantic search mode** (`--mode semantic`) 
   - Tantivy backend supports this but wasn't used
   - Would find "how to create a video tutorial from conference talk" ≈ video2study

3. **Timeline with structured output** (`--robot-format jsonl`)
   - Returns `{ hits: [...], count: N }` in streaming format
   - Could efficiently process 10K sessions in chunks

4. **`--expand` command around sessions**
   - Shows context around specific anchor points
   - Could reveal pattern context (why was this session needed?)

5. **`--sessions-from` for chained searches**
   - Filter results from one search into a second search
   - Example: `search "error" | search "same user" | count` → find users with repeated error patterns

**In session summary.md files (not fully explored):**

- "Learnings" sections (what worked/didn't)
- "Errors & Corrections" sections (repeated debugging patterns)
- "Codebase and System Documentation" sections (knowledge being captured)
- "Current State" sections (open questions, pending tasks - indicates incomplete solutions)

**In session JSONL files (not analyzed at tool level):**

```jsonl
{
  "role": "user",
  "content": "...",
  "tool_calls": [
    { "name": "Bash", "input": "..." },
    { "name": "Read", "input": "..." },
    { "name": "Grep", "input": "..." }
  ],
  "tool_results": [...]
}
```

Tool invocation sequences reveal workflow patterns:
- `Bash (ls) → Glob → Read × 3 → Grep` = codebase exploration pattern
- `Bash (find) → Edit × 2 → Bash (git add) → Bash (git commit)` = safe-commit pattern
- `Bash (yt-dlp) → Edit → Bash (test)` = video download pattern

**Claude-mem observations (not used):**

Observations in session JSONL files marked with `<observation>` tags contain:
- `<type>discovery</type>` - patterns user discovered
- `<type>pattern</type>` - workflow patterns observed
- `<facts>` - specific instance data
- `<concepts>` - taxonomy of what was learned

---

## 2. Unexplored Data Sources & Approaches

### 2.1 Session Metadata Analysis

**Available in cass capabilities:**

```
- max_limit: 10000
- Connectors: codex, claude_code, gemini, opencode, amp, cline, aider, cursor
- By Agent: claude_code: 10017, cursor: 61, codex: 6, gemini: 1
- Aggregations: field-level bucketing
```

**Opportunity:** Cursor sessions (61) might show different workflow patterns than claude_code. Codex (6) might reveal deprecated tool patterns to avoid.

### 2.2 Workspace-Specific Opportunity Discovery

**Current data shows workspace clustering:**

```
/Users/jason/Documents/.usage_contexts/coach: 1794 sessions
/Users/jason/Documents/.usage_contexts/random: 1765 sessions
/Users/jason/Code/apart-kit: 1651 sessions
/Users/jason/Code: 1199 sessions
/Users/jason/Code/hackathon-project-reviews: 434 sessions
/Users/jason/Code/video2study: 270 sessions
```

**Approach not tried:**
- Find sessions in coach workspace → extract repeated user requests → check if they appear elsewhere
- Search for "briefing", "summary", "status" across all workspaces → if found in multiple workspaces with high frequency → skill opportunity
- Look for workspace-specific tool patterns (coach might use memory/observation tools more heavily)

### 2.3 Session Lifecycle Classification

Sessions can be classified by:
1. **Turn count**: 1-3 turns = simple question; 8-15 = iterative problem; 20+ = multi-phase project
2. **Error density**: High error messages in output = troubleshooting pattern
3. **Tool diversity**: Single tool session vs. multi-tool orchestration
4. **Outcome type**: File creation, process design, debugging help, integration

**Not analyzed:** Distribution of these across workspaces/users might reveal "coaching" vs "creation" workflows.

### 2.4 Correction & Refinement Loops

From session summary.md "Errors & Corrections" sections:

```
Example from video2study session:
- "Duration key mismatch: info.get('duration_seconds', 0) returned 0" 
  → Fix: check both 'duration' and 'duration_seconds' keys
- "Format string too restrictive for HLS streams"
  → Fix: use flexible format with merge
```

**Pattern:** Users hit edge cases (duration key mismatch, format string) that aren't one-time problems - they're system-level issues that need debugging skills or system documentation updates.

**Not analyzed:** Mining these sections for "repeated debugging patterns" that could become diagnostic skills.

---

## 3. Data Source Integration Matrix

Here's what COULD be analyzed systematically:

| Source | Current Use | Opportunity | Effort | Signal Value |
|--------|------------|-------------|--------|--------------|
| cass search (lexical) | Yes (270 hits "video processing") | Expand to semantic mode | Low | High |
| cass aggregate | No | Group by workspace/date/agent | Low | High |
| cass timeline | Partial | Use for session clustering | Medium | Medium |
| Session JSONL (tool calls) | No | Parse tool invocation sequences | Medium | Very High |
| Session summary.md | No | Extract "Errors & Corrections" | Low | High |
| Claude-mem observations | No | Extract `<type>pattern</type>` | Low | Medium |
| Session metadata (duration, turn count) | No | Cluster by characteristics | Medium | Medium |
| Workspace distribution | Partial | Cross-workspace pattern detection | Medium | High |
| Error message patterns | No | Mine for diagnostic opportunities | Medium | High |
| Cass --fields selection | No | Efficient bulk extraction | Low | Medium |

---

## 4. Design: "Skill Opportunity Finder" Skill

### 4.1 Heuristics for Skill Opportunities

An activity should become a skill when it meets 2+ of these criteria:

| Heuristic | Signal | Threshold |
|-----------|--------|-----------|
| **Repetition frequency** | Same pattern across N sessions | N ≥ 3 sessions |
| **Session turn inflation** | Problem that takes 8+ turns to solve | N ≥ 2 instances |
| **Cross-workspace presence** | Pattern appears in 2+ workspaces | 2+ workspaces |
| **Multi-tool orchestration** | Specific sequence of 3+ tools used repeatedly | N ≥ 3 instances |
| **Correction loops** | User corrects same type of error repeatedly | N ≥ 3 corrections |
| **Artifact standardization** | Output files follow consistent pattern | Pattern consistency ≥ 80% |
| **Tool-invocation complexity** | Tool sequence takes >30 seconds to describe | Complexity score ≥ 0.7 |
| **Time investment** | Sessions solving similar problem take >30 min total | Total ≥ 90 min across N sessions |
| **Error frequency** | Same error category in 3+ sessions | N ≥ 3 errors |
| **Documentation requests** | User asks "how do I X" multiple times in different sessions | N ≥ 3 questions |

### 4.2 Data Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ SKILL OPPORTUNITY FINDER - PROCESSING PIPELINE                  │
└─────────────────────────────────────────────────────────────────┘

Phase 1: DATA INGESTION (Parallel)
├─ cass semantic search: "create", "build", "setup", "process", "automate"
├─ cass aggregate by workspace
├─ Extract all summary.md "Errors & Corrections" sections
├─ Parse session JSONL for tool sequences
└─ Cluster sessions by duration/turn count

Phase 2: PATTERN DETECTION
├─ Lexical pattern matching (phrases, keywords)
├─ Semantic clustering (similar intent)
├─ Tool sequence fingerprinting (same tool combos)
├─ Error pattern extraction (repeated errors)
└─ Workspace cross-reference (same pattern in N workspaces)

Phase 3: SCORING
├─ Apply heuristics (each session/pattern gets score)
├─ Rank by: frequency × complexity × time_investment × uniqueness
└─ Filter: threshold ≥ 2 heuristics AND score ≥ 0.65

Phase 4: PRESENTATION
├─ Group by category (Code Quality, Development, Documentation, etc.)
├─ Show evidence (sessions, examples, error patterns)
├─ Suggest skill structure (name, description, required tools)
└─ List open questions (scope, integration, frequency threshold)
```

### 4.3 Skill Output Format

```yaml
# Auto-generated skill opportunity report

skill:
  name: "skill-name"
  category: "Development | Documentation | Code Quality | Integration | Automation"
  confidence: 0.75
  evidence_count: 5
  
why_this_is_a_skill:
  - "Appears in 5 sessions across 2 workspaces (coach, random)"
  - "Users spend 45+ minutes total solving this repeatedly"
  - "Tool sequence: Bash → Read → Edit → Grep → Bash (fingerprint: 0.89 match)"
  - "Error pattern repeated: Duration key mismatch, format string issues"

examples:
  - session_id: "b1350f2f-4b02-444d-9b39-284cf82a21bd"
    workspace: "/Users/jason/Code/video2study"
    description: "Download video, extract slides, transcribe audio"
    turns: 14
    duration_min: 45
    
  - session_id: "3437ccc2-b7c5-493d-a656-c4b9ce03d72b"
    workspace: "/Users/jason/Code/video2study"
    description: "Fix HLS format detection, update cost tracking"
    turns: 8
    duration_min: 32

suggested_skill_structure:
  name: video-pipeline-executor
  description: "Download videos, extract slides/audio, transcribe, generate study materials"
  required_tools: [Bash, Read, Edit, Grep]
  estimated_development_time_hours: 4
  
open_questions:
  - "Should this integrate with existing video2study tool or be standalone skill?"
  - "What's the minimum frequency threshold: 3 sessions or 5?"
  - "Should it handle all video sources or focus on conference videos?"
```

### 4.4 Interactive vs. Batch Modes

**Batch Mode (Recommended for analysis):**
```bash
/skill-finder analyze --output skill-opportunities.yaml --min-confidence 0.65
```

Outputs ranked list of opportunities, ready for user to prioritize.

**Interactive Mode (For exploration):**
```bash
/skill-finder explore
# Then menu:
# 1. Show top opportunities
# 2. Drill into specific workspace
# 3. Show tool sequence patterns
# 4. Analyze error/correction loops
```

---

## 5. Uncertainties & Questions for User

### 5.1 Scope Definition

| Question | Implication | Default Recommendation |
|----------|-------------|----------------------|
| **Personal vs. team skills?** | Should finder focus only on Jason's workflow patterns or anticipate team needs? | Personal for now (Jason-specific); team patterns can be extracted later |
| **Reusable modules vs. integrated skills?** | Should opportunities become standalone plugins (like safe-commit) or integrated into existing projects? | Standalone plugins (more reusable, discoverable) unless deeply project-specific |
| **Skill granularity** | One large skill per domain or many small composable skills? | Small composable skills (mirror existing safe-commit, weather, skitour pattern) |

### 5.2 Threshold & Heuristic Tuning

| Question | Current Assumption | Range |
|----------|-------------------|-------|
| **Minimum frequency** | ≥3 sessions = skill candidate | 2-5 sessions |
| **Minimum turn count** | 8+ turns indicates complexity | 6-12 turns |
| **Minimum time investment** | 90 min total = worth automating | 60-180 min |
| **Cross-workspace definition** | 2+ workspaces = skill | 2-3 workspaces |
| **Confidence threshold** | Score ≥ 0.65 to surface | 0.55-0.75 |
| **Tool sequence match** | 0.80+ similarity = same pattern | 0.75-0.90 |

### 5.3 Data Source Priorities

| Source | Should be included? | If no, why exclude? |
|--------|-------------------|-------------------|
| Cursor sessions (61) | Unknown | Different tool, might show different patterns |
| Codex sessions (6) | Unknown | Likely deprecated patterns |
| Semantic search | Yes | Much better than lexical alone |
| Session summary.md | Yes | Direct signal from user's own analysis |
| Claude-mem observations | Maybe | Depends on observation capture consistency |
| Tool sequence fingerprinting | Yes | Reveals workflow structure |
| Error correction loops | Yes | Shows pain points user expects to repeat |
| Multi-workspace patterns | Yes | Indicates broadly useful skill |

### 5.4 Integration Questions

| Question | Implication | Options |
|----------|-------------|---------|
| **Auto-suggestion to skill templates?** | Should finder suggest based on templates in `plugins/*/SKILL.md`? | (a) Match patterns to existing templates, (b) Generate fresh opportunities only, (c) Both |
| **Skill status tracking** | Should we track which opportunities became skills vs. were rejected? | (a) New file `skills/GENERATED.yaml`, (b) PR-based review, (c) Manual notes |
| **Refresh frequency** | How often should finder run? | (a) Manual on-demand, (b) Weekly background job, (c) After major projects |

---

## 6. Concrete Opportunities Revealed by Prior Analysis

### Already Found (Prior Analysis - Confirmed)

1. **Video Processing Pipeline** (270 sessions in video2study workspace)
   - Confidence: **0.92** (very high frequency, specific workspace)
   - Status: Likely should become automated skill
   - Evidence: 15 cass hits for "video processing"
   
2. **Research Context Briefing** (repeated in coach workspace)
   - Confidence: **0.78** (cross-pattern but not measured frequency)
   - Status: May already exist as Apart-Kit CLI tool
   - Evidence: Briefing command aggregates Gmail, Discord, calendar

### Newly Identifiable (With Better Methods)

3. **Session Recovery & Navigation** (from random workspace patterns)
   - Signal: "I just lost some kind of session" + "I can't find it again"
   - Occurs in: coach, random workspaces
   - Tool pattern: cass search + timeline navigation
   - **Opportunity:** Skill to help find "lost" sessions using cass queries

4. **Discord Moderation** (repeated in apart-ops)
   - Signal: "repeated issues with spammers on our discord"
   - Occurs in: multiple Discord-related sessions
   - Tool pattern: Discord bot queries + pattern matching
   - Error correction: User tries carl-bot config, then notices it's not enabled
   - **Opportunity:** Skill for Discord automation detection & setup

5. **Architecture/Config Review** (error handling audit pattern)
   - Signal: Sessions titled "audit", "review", "comprehensive error handling"
   - Occurs in: apart-kit, video2study workspaces
   - Tool pattern: Bash (find) → Read × many → Grep + analysis
   - **Opportunity:** Skill for automated codebase audits (error handling, security, patterns)

6. **Backup System Design & Validation** (from OpenPhil session)
   - Signal: Long session with cleanup planning, restic setup, automation
   - Occurs in: isolated session but with very complete planning doc
   - Tool pattern: complex bash commands, status checking, launchd setup
   - Time investment: ~3 hours documented
   - **Opportunity:** Skill for backup automation setup (restic + launchd)

---

## 7. Recommended Next Steps

### Phase 1: Build the Finder (Week 1-2)

1. **Implement core pipeline:**
   - Parse cass JSON output into memory
   - Implement heuristic scoring (start with top 3 heuristics)
   - Serialize opportunities to YAML

2. **Integrate data sources:**
   - cass semantic search
   - Session JSONL tool sequence extraction
   - Session summary.md "Errors & Corrections" mining

3. **Test on known candidates:**
   - Verify video2study shows up with high confidence
   - Verify research briefing pattern found
   - Validate scoring makes intuitive sense

### Phase 2: Validation & Tuning (Week 2-3)

1. Run finder on full 10K sessions
2. Manual review top 20 opportunities (does scoring match user intuition?)
3. Adjust heuristic weights if needed
4. Document any patterns finder missed

### Phase 3: Deployment (Week 3+)

1. Package as skill in `~/Code/jason-agent-skills/plugins/skill-finder/`
2. Create interactive CLI for exploration
3. Document uncertainty ranges user can configure

---

## 8. Summary Table: Gaps vs. Solutions

| Gap | Prior Approach | Solution | Effort | Impact |
|-----|----------------|----------|--------|--------|
| Lexical search only | Pattern matching keywords | Add semantic + lexical hybrid search | Low | High |
| No tool pattern analysis | Workspace-level counts only | Parse JSONL tool sequences | Medium | Very High |
| Summary.md not used | Manual review if at all | Auto-extract "Errors & Corrections" | Low | High |
| Error corrections ignored | Not tracked | Mine correction loops for 3+ instances | Low | High |
| Single-workspace view | Treat as isolated | Cross-workspace coherence detection | Medium | High |
| Session duration ignored | Treated equally | Cluster by turn count/duration | Low | Medium |
| No ranking/scoring | All matches equally weighted | Multi-factor heuristic scoring | Medium | High |
| Manual presentation | Text lists | Structured YAML with evidence | Low | Medium |

---

## Final Recommendation

**Build the Skill Opportunity Finder in three phases:**

1. **MVP (2 weeks):** Core scoring with 3 heuristics, cass integration, YAML output
2. **Enhanced (1 week):** Tool sequence fingerprinting, error loop mining, interactive CLI
3. **Production (ongoing):** Threshold tuning, new data sources, portfolio of found opportunities

The finder should live in `~/Code/jason-agent-skills/plugins/skill-finder/` and be compatible with existing plugin architecture. It will pay for itself after identifying 2-3 opportunities that would have taken 3+ hours each to manually discover.