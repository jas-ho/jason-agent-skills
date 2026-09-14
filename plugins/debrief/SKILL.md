---
name: debrief
description: "Debrief. Capture what happened, reflections, and (when target is today) set next-day mode. Writes to ~/Projects/ops/dailies/. Use when the user says /debrief (optionally with 'for yesterday' / 'for YYYY-MM-DD' / 'for all missing days') or at end of day."
---

# Debrief

## Linear routing

All persistent tasks and follow-ups go to the **Jason workspace and Jason team** in Linear (routing updated 2026-09-14), including career, job search, admin, personal/life and side projects. Discover current project, issue and status IDs; do not assume an RD key or authorize another workspace. Broader Apart organization tracking stays in Notion.

The daily note's `## Plan` remains the working surface; link tracked tasks to their Linear issues. `backlog.md` and GoalsWon retain legacy items, not new persistent tracking. GoalsWon daily accountability reconciliation remains supported below. Before creating an issue, check for an existing match; never maintain a duplicate task in the legacy backlog. No automatic bulk migration: move an individual legacy item only with Jason's agreement, verify the Linear issue exists, then remove its backlog entry. If Linear is unavailable, report the task as untracked; do not substitute another tracker or discard its source note.

Capture activity, reflections, and (when target date = today) set next-day mode. Writes `## Debrief` to the daily note. **Keep it fast, under 3 minutes when signals are clean.**

## Flow

### 1. Setup

**Temporal anchor:** Run `date` through the host shell; do not rely on Claude inline shell expansion. Use `date '+%Y-%m-%d %H:%M %Z'` for now and `date '+%Y-%m-%d'` for today. On macOS compute offsets with `date -v-1d` / `date -v+1d`; on Linux use `date -d yesterday` / `date -d tomorrow`. Obtain names and ISO dates from the command output, not mental arithmetic.

Resolve the target date from the user's invocation arguments or following request text:

- empty → current
- `for yesterday` → yesterday
- `for YYYY-MM-DD` → that date
- `for all missing days` → batch mode (see below)

**Host interfaces:** Use the available native question interface when it supports the needed interaction; otherwise ask concise conversational questions. Discover service tools by provider and operation, then inspect their actual parameter schemas. Names below identify operations, not mandatory CC MCP prefixes. Granola, DoneThat, Linear and Beeper connections are independent dependencies; never assume a copied skill provides them. Keep optional signals best-effort and mention an incomplete picture in the resulting summary without blocking other signals. Use `ak` for Google/Discord/Notion workflows under the existing service skills.

State the anchor in your first response ("Debriefing Apr 15 (Tue). Current is Apr 16 (Wed)."). The `### Tomorrow` section in the daily note template is note-relative.

**Retroactive adjustments** (target ≠ today):

- Skip prompt 3 (next-day mode) and omit `### Tomorrow` from the written debrief.
- Write meeting outcomes and reflections only. Skip the step 4 task-capture sweep, calibration writes and GoalsWon reconciliation, and skip step 5 task reconciliation. Batch mode performs its single combined step 5 only after all retrospective notes are written.
- For meeting-outcome sweep, scan only the target note's outcomes.

**Batch mode (`for all missing days`)**: Find dailies in the last 7 days without `## Debrief`. For each missing day, run steps 1-4 as a retroactive single-day debrief (target = that day). Ask the user ONCE at the start for a blanket reflection spanning the gap, and reuse it per day. After the last day, do one combined task reconciliation (step 5) against current Linear issues and legacy backlog entries.

Read or create the daily note at `~/Projects/ops/dailies/<target>.md` (no H1 header; Obsidian uses filename). If `## Debrief` already exists, warn and ask before overwriting.

### 2. Gather Signals — run independent reads in parallel (best-effort; report missing signals briefly)

All signal-gathering uses the resolved **target date**, not "today."

| Signal             | How                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Notes                                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **DoneThat**       | `DoneThat generate_report` with `startDate`/`endDate` = target, `aggregationLevel="task"`. If rowCount:0, retry with `"day"`.                                                                                                                                                                                                                                                                                                                                                                                                                                               | For retroactive, `get_message` at level=day also works; for today, only after midnight.                         |
| **ak briefing**    | `ak briefing --for <target>`; skip if CLI rejects the flag.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                                                                                                                 |
| **Git commits**    | Loop `~/Code/*/`: `git log --oneline --since="<target> 00:00" --until="<target+1d> 00:00" --author="jason"`                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                                                                                                                 |
| **Plan**           | Read `## Plan` from target's daily note. Compare planned vs actual.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                                                                                                                 |
| **GoalsWon goals** | `goalswon goals list --date <target> --limit 50`. Skip `recurring_*`. Keep for Step 4 reconciliation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |                                                                                                                 |
| **GoalsWon chat**  | `goalswon chat list -f <target> -t <target+1d> --json`. Extract the `Results of <date>` submission text + any free-form Jason messages around it. Feed `### Reflections` verbatim where it adds signal.                                                                                                                                                                                                                                                                                                                                                                     | Jason-authored end-of-day reflection — preferred source for Reflections voice.                                  |
| **Granola**        | `list_meetings` with `time_range=custom`, `custom_start=<target>`, `custom_end=<target+1d>`. Then `get_meetings` for participant meetings. Skip meetings with existing `#### *outcomes` sections.                                                                                                                                                                                                                                                                                                                                                                           |                                                                                                                 |
| **Linear**         | Read Jason's issues in the Jason workspace/team, including assigned-to-me and confirmed personal unassigned items. Match completed Plan items to existing issues across states, including Backlog, before step 5.                                                                                                                                                                                                                                                                                                                                                           | All task categories; never modify someone else's issue without explicit instruction. Report unavailable access. |
| **Beeper**         | Two parallel `Beeper search_messages` calls scoped to target day (`dateAfter`/`dateBefore` in ISO 8601 with timezone), `excludeLowPriority=true`, `includeMuted=false`, `limit=20`: (1) `sender="me"` — what was sent, captures concrete contributions; (2) `sender="others"` — keep only items implying a commitment, ask, or notable update; drop generic chatter. Synthesize into themed `### Activity` bullets referencing chat names in plain text (Beeper deeplinks don't resolve in Obsidian). Asks/commitments from this signal feed the Step 4 task capture sweep. |                                                                                                                 |

### 3. Interactive Prompts (3 max, keep conversational, batch in one message)

1. Present synthesized summary. "Anything to add or correct?"
2. "How did the day feel? Wins, frustrations, surprises?" (don't push if terse)
3. (Skipped in retroactive mode.) "Next day — workday, off-work, or day-off?"

Skip any prompt whose answer is already obvious (mode set by calendar, reflection already implied by signals).

**Scan for FEEDBACK markers**: Before writing the debrief, scan the daily note for `<!-- FEEDBACK(jason): ... -->` (canonical) and `#prep-feedback` (legacy). Each match is a calibration entry to migrate in step 4.

### 4. Write `## Debrief`

Place after `## Prep`, before `## Details`. Never overwrite other sections.

```markdown
## Debrief

### Activity

- [Bullets grouped by theme, not chronological. Links everywhere.]
- [Planned vs actual if Plan existed]

### Reflections

[User's words, preserve their voice.]

### Tomorrow

workday | off-work | day-off
[Specific intentions if mentioned]
```

**Post-process Granola meetings**: For unprocessed meetings, write to `## Details`:

```markdown
#### <Meeting title> outcomes

**Key decisions**: [bullet list, or "none"]
**Action items**:

- [ ] [Owner]: [task] [deadline if mentioned]
      **Context**: [1-2 sentences if relevant to other work]

[Granola](https://notes.granola.ai/d/<meeting-id>)
```

**Task capture sweep** (one batched prompt UX, three sources preprocessed separately):

- _Open meeting actions_: scan all `#### *outcomes` for unchecked `- [ ]` items. (These are yours by convention; others' items use `- **Name**:` per the prep agent rule and are skipped here.)
- _Deferred Plan items_: already have category emoji and rough effort.
- _Beeper-derived asks/commitments_: single-message asks from chat; needs stakeholder context.

Present as one batch: "[N] items to track. Track in Linear, carry to tomorrow's Plan, or drop?" On confirmation, route persistent follow-ups in every category to Linear: reuse a matching issue or create one with the resolved Jason team/project, priority, due date and source context. Put the issue link in the source note so a later sweep recognizes it as already tracked. If moving a legacy backlog item, confirm that specific move and verify the issue before removing its backlog entry. If Linear is unavailable or creation fails, report the item as untracked and preserve its source; do not add it to another tracker. Carry-to-tomorrow keeps a today-only intention in Plan; it does not create a second task record or remove an existing Linear issue. Keep unchecked outcome items when carrying them; later sweeps should reuse any linked issue.

**Calibration log**: For each `<!-- FEEDBACK(jason): ... -->` and legacy `#prep-feedback` marker found in step 3, append one bullet to `## Active Feedback` in `~/Projects/ops/dailies/calibration.md`. Format: `- YYYY-MM-DD [emoji from marker, default 🔧] description`. **Idempotency**: If any line in `## Active Feedback` already starts with `- <today>`, assume calibration was already written for today and skip. Don't modify the source markers (user's record).

**Reconcile GoalsWon**: Match daily accountability goals to Plan items by judgment; Linear remains the persistent task owner. Show reconciliation preview (done/partial/pending). On confirm: `goalswon goals complete <id> --status done|pending|partial`. Log one-liner to Activity.

**Simon ping**: Flag standout items (real win, honest struggle, scope change) as "Worth pinging Simon about: [thing]." Don't draft.

### 5. Task reconciliation (Linear and legacy entries)

Match completed `[x]` Plan items to their owning surface (by intent, not exact text):

- **Items with a Linear issue → Linear**: if a completed Plan item maps to Jason's open issue in any category, preview the match and transition to Done only after confirmation (`save_issue` with the resolved Done state for team Jason). Batch with legacy reconciliation confirmation. Log to Activity (`Closed <actual issue identifier> in Linear`). Do not infer completion merely from a meeting or related activity.
- **Legacy backlog-only items → legacy archive**: for an existing entry with no Linear issue, preview and confirm completion, then remove it from `backlog.md` and append to `backlog-done.md` as `- [x] ~~item~~ done DATE`. Skip day-specific items (meetings, one-off replies). Do not create-and-close a new Linear issue just to migrate history; offer that only if Jason wants the individual record. If an issue already exists, reconcile it in Linear and remove any duplicate backlog entry with confirmation.

**Approaching deadlines**: Scan `### Backburner` for `[by DATE]` within 7 days. Flag for promotion to Active.

**Chronic carries**: Check `### Active` for `(DATE)` creation date >3 weeks. Flag up to 3: "Active for [N weeks]. Do it, scope down, demote, or drop?"

### 5b. System maintenance: entity inconsistencies

Part of the debrief is keeping the system in shape. One way it breaks: a wrong entity name (org, fund, person) propagates across files because the prep agent treats previous dailies as authoritative for entity references.

If the user signals an entity-confusion during debrief (explicit `<!-- FIX(jason): wrong → right -->` marker found in note, natural-language correction in conversation, or frustration with a recurring wrong reference): assess and act.

- Assess blast radius via `rg 'wrong-name' ~/Projects/ops/dailies/ ~/Projects/ops/dailies/backlog.md`. Bounded → fix it. Wide → propose targeted scope before acting.
- Edits can land anywhere; user-authored content (`## Debrief`, ticked Plan items, FEEDBACK markers) is more sensitive than prep-authored content. When uncertain, ask.
- Auto-apply when bounded + single-string-sub + clear context. Ask when ambiguous, wide-scope, or in clearly user-authored prose.
- Always emit a concise TLDR of changes (count + files + sample). Audit without friction.

### 6. Confirm

Use absolute dates. Examples:

- Target = today, workday next: "Debrief saved. Friday Apr 17 is a workday. Morning prep at 05:00. Use `/coach` when ready."
- Target = today, day off next: "Debrief saved. Enjoy Saturday."
- Target = past date: "Debrief for Apr 15 saved. Carrying on with today."
