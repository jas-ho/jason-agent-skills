---
name: talk-prep
description: Prepare a talk or presentation end to end - content, outline, slides, timing, run-throughs, talk page, day-of logistics, debrief. Use at the start of any talk or presentation project and whenever work on one resumes (outline, slides, rehearsal, logistics). Not for a one-off edit to an existing slide.
---

# Talk prep

Resolve `<skill-dir>` to the directory containing this SKILL.md. The files under `references/` load at the phase that needs them; don't read them all up front.

The failure this skill exists to prevent: lessons from past talks were logged and never loaded, so the same late run-through happened twice. The timeline below goes into the project, not only into this skill.

## First action: put the timeline in the project

If the project README has no `## Timeline`, write one, counted back from `deadline:` (ask for the date if it's missing). Tick items there as they happen; every later session reads it.

```markdown
## Timeline
- [ ] Content: audience, the one sentence, the change they should make (T-3 weeks)
- [ ] Outline locked, section by section (T-10 days)
- [ ] Plain slides built from the locked outline; ask organisers for mic, sound check, projector test, recording (T-7 days)
- [ ] First timed run-through, recorded (T-5 days)
- [ ] Cuts applied; styling pass (T-4 days)
- [ ] Second timed run; talk page and QR target live (T-2 days)
- [ ] Day-of checklist (T-0)
- [ ] Debrief, lessons folded into talk-prep (T+1)
```

Shift the dates for a short lead time, but keep the order. These are checkpoints, not gates: a quick visual prototype is fine, decorative polish waits.

## Phases

1. **Content.** Ask 2-3 sharp questions if the audience is unclear: who's in the room, the slot and Q&A share, the one thing they leave with, what's off-limits. Then the outline. The abstract comes after the outline, and the title last (the speaker usually writes it).
2. **Outline.** Section by section; Jason ticks a section done, then its slides get built. Answers to his questions go to Q&A prep, not the talk body, unless he says otherwise. Writing rules: `references/writing-for-slides.md`.
3. **Budget.** Jason speaks at about **115 wpm** (measured 05/2026 and 09/2026; the first timed run replaces it). Budget every section at that pace from the start. Fix the time for the section that carries the main outcome, often the ask or policy part, and build its examples early. Plan one or two engagement beats (an audience question, a quick poll, a short clip) and budget them, plus 3-5 minutes of buffer for tech trouble. After the first run, every addition comes with a proposed cut.
4. **Slides.** If the deck already exists in Keynote, Beamer, PowerPoint or Google Slides, edit it there; don't convert. For a new deck, the default is Typst plus deck-lint: `references/typst-deck.md`. For decks that must end up in Google Slides: `references/pandoc-google-slides.md`. Apart-branded talks: `references/apart-brand.md`.
5. **Verify.** One fact pass after the slide build, by agents reading primary sources; check their key claims yourself before applying anything. Later, re-check only the claims a factual edit touched. Say "document X doesn't say Y" only after reading X in full. Then run a report-only consistency audit of the deck.
6. **Run-through.** Recorded and transcribed, with a timing analysis and a revision plan: `references/run-through.md`.
7. **Talk page and day-of.** `references/day-of.md`.
8. **Debrief.** Capture how it went, then fold lessons into this skill the same day, or open a Linear issue. No "log now, triage later".

## Working with Jason

- Draft first and let him react; give options with a recommendation.
- Apply clear instructions directly.
- Batch pending decisions into one structured question round with a recommended default.
- After 2-3 rounds of small edits on one slide, ask whether it needs restructuring rather than more phrasing.
- In co-edit mode, never rewrite a region he is typing in; wait for the marker's sign-off.
