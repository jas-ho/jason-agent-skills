---
name: slide-creation
description: Author or substantially restructure a talk's slide deck; compiles a markdown outline to .pptx via pandoc for Google Slides import. Use for drafting a new deck, restructuring an outline, or a substantive revision pass. Not for one-shot edits (typo, translate, single phrase) or simple format conversions; handle those directly.
---

Resolve `<skill-dir>` to the absolute directory containing this loaded SKILL.md; all bundled `reference/` paths are relative to it. Quote the resulting absolute path when passing it to pandoc or a script. Shared personal writing-context references are separate from installation paths.

# Slide creation

You're helping author a talk deck. The deliverable depends on what the user is authoring in: a markdown outline you compile to `.pptx` with `pandoc` (default for Google Slides import workflows), or, if they already work in Keynote, Beamer, Pitch, a corporate template, or their own raw `.pptx`, direct edits there. Always check first.

The principles below are tool-agnostic. Pandoc is one compilation path.

## First move: clarify scope, then audience

For any non-trivial drafting ask, gather what you need before drafting. If the user said "make slides for X" with little context, ask 2-3 sharp questions instead of fabricating an audience. Useful early prompts:

- Who is in the room, and what do they already know?
- What's the time slot, and what fraction is Q&A?
- What is the **one thing** they should leave with?
- What substrate are we authoring in (markdown + pandoc, existing .pptx, Keynote, Beamer, …)?
- Anything off-limits (info hazards, NDAs, unfinished work, speaker-only material)?

Re-read every claim and every word against the audience contract as you draft. If a slide doesn't earn its place against it, cut it.

For mixed-sensitivity decks (main slides + speaker-only backup + appendix), name which parts go where in planning notes so material doesn't leak across.

## Principles

### Three layers in the outline: on-slide, speaker, planning

Pandoc distinguishes three contexts. Use the right one for each piece of material.

**On-slide content**: between H2 headings. Standard markdown:

```markdown
## Slide title

Body text. Stays compact; the slide doesn't read itself out loud.

- Bullet one
- Bullet two

**Bold** for emphasis, _italic_ for term-introductions, `code spans`
for monospace, and [hyperlinks like this](https://example.com) become
clickable in Google Slides after import.

Images: ![alt text](path/to/img.png){width=2.5in height=2.5in}
```

**Speaker notes**: `::: notes` fenced div. Pandoc attaches these to the slide as PowerPoint speaker notes (visible in presenter mode, not on the projected slide). Use for talk-track, transitions, things to remember to say.

```markdown
::: notes
Mention here that the cluster numbers reflect overlap; one project can sit
in more than one threat cluster. If asked: yes, the LABEL_MAP is reproducible.
:::
```

**Planning context**: drafting-only material (sources, confidence tags, todos, alternatives, "would have been a slide" background). Three places to put it, depending on volume:

1. **Inline HTML comments** for small per-slide bits. Pandoc strips these from pptx output entirely.

   ```markdown
   <!-- Planning:
   🟢 cluster sizes from cluster_summary.md, run 2026-05-16
   🟡 C3 description: defensible; sharper version pending Krishnan re-read
   🔴 Defense-side clustering not yet schema'd; flag for schema_v2.md
   -->
   ```

2. **Appendix slides** for richer content: bigger reference tables, detailed methodology, full project lists, screenshot evidence, anything you want nicely-formatted during drafting. Pandoc renders them like any other slide, but after Google Slides import you hide them, move them to a backup deck, or delete them. They also double as Q&A backup if you want to keep them. Markdown tables, longer prose, embedded images all preserved.

3. **Sibling `slides-outline.notes.md`** (co-edit pattern) for voluminous planning that doesn't fit comfortably inline: multi-page brainstorms, large source dumps, decision logs.

Mixing the three is fine. Common pattern: appendix slides for "rich background I want to reference during drafting"; inline HTML comments for "small per-slide source/confidence/todo notes"; sibling file only when planning grows large enough to feel cramped in-file.

### Use markdown faithfully

Pandoc renders standard markdown. The author makes structure explicit:

- `**bold**` for emphasis. Don't expect the renderer to guess.
- `*italic*` for introduced terms or titles of works.
- `- item` for unordered lists; `1. item` for ordered lists. Don't use indentation tricks.
- `**Sub-header**: explanation` is a common one-line "name + description" pattern that survives template apply.
- `![alt](path){width=Xin height=Yin}` for images. Width/height attributes are optional; default sizing is usually fine. Position is determined by the slide layout; for precise placement, do it after template apply in Google Slides.
- `[text](url)` for hyperlinks. Prefer hyperlinked existing text over bare URLs.

### Tag confidence when claims need traceability

For evidence-heavy decks (research talks, post-mortems, audits) tag load-bearing claims in planning notes:

- 🟢 robust: source verified, numbers reproducible
- 🟡 tentative: defensible now, sharper after one more pass
- 🔴 blocked: on the slide, evidence isn't there yet

**For every 🔴 claim, name the cheapest action that closes the gap.** The action might be analytical (re-run a query), empirical (look up a source, run a test), or social (ask a colleague, send an email). A 🔴 without an action is a hidden problem.

Skip this system for decks where claim-traceability isn't the bottleneck (status updates, sales pitches, keynote-style vision talks, tutorials).

### Make quantitative claims traceable

Every number on a slide should point to a source file, query, or computed artifact. When numbers disagree across sources, reconcile before the deck ships; don't pick the convenient number.

### Frame carefully when describing other people's work

When the talk characterizes a group, a past situation, or someone else's prior decisions, default to framings that name structural factors (constraints, incentives, design of the situation) over framings that assign blame to specific people. Structural framings tend to point at the actual lever for change; agentive ones can read as ungenerous when the people described are in the room. Flip when accountability is genuinely the point (post-mortems, sales differentiation, leadership commitments).

### Write plainly

Follow the content-generation guidance in `~/.claude/CLAUDE.md` (no em-dashes, no contrastive elevation, no rhetorical self-answers, no hedging that avoids commitment). Do one focused plainness sweep before declaring a slide done.

## Compiling with pandoc

Default workflow:

```bash
pandoc -t pptx --slide-level=2 slides-outline.md -o slides-outline.pptx
```

That's the whole tool. Then File → Import slides in Google Slides → apply template → final tweaks.

Useful options:

- `--reference-doc=ref.pptx`: supply a template `.pptx` that pandoc uses for theme, fonts, and slide dimensions. If the user has a corporate or conference template they want pandoc to start from, point at it. Without this flag, pandoc uses its default style (which the user replaces on import anyway). **Caveat:** a raw Google-Slides export usually does NOT work here — pandoc matches layouts by exact PowerPoint names and placeholder types, which GSlides exports don't satisfy, so it silently falls back to defaults. To turn a GSlides export into a usable reference, convert it with the pattern in `reference/` (build a branded reference doc on pandoc's own skeleton). For the Apart template this is already done — see the next bullet; don't rebuild it just to compile a deck.
- **Apart decks**: there is one committed, ready-to-use reference doc at the absolute path
  `<skill-dir>/reference/apart-reference.pptx`
  (Inter, `#101010` bg, `#F7F7F5` text, `#46FF99`/`#26C26B` green, corner asterisk, 16:9, left-aligned editorial layout). **To compile any Apart deck, just point pandoc at that path — there is nothing to build or rebuild:** `--reference-doc=<skill-dir>/reference/apart-reference.pptx`. Rebuild the reference _only_ when the Apart Google Slides template or brand itself changes (not to compile a deck): re-export the template to `.pptx`, then run `<skill-dir>/reference/build-apart-reference.sh <path-to-your-export>` and replace `reference/source-template.pptx` with that export. With no argument the script rebuilds from the committed `source-template.pptx` (use that after editing the `DS_*` tokens). See `reference/README.md`.
- `--metadata title="..."`: set the deck title (used by the auto-generated title slide if you've included a YAML frontmatter block).
- `-V slideLevel=2`: same as `--slide-level=2`; either works.

Slide structure pandoc expects with `--slide-level=2`:

- H1 (`#`): bigger structural break. Useful for "Part 1 / Part 2" decks; otherwise omit.
- H2 (`##`): each starts a new slide. The H2 text becomes the slide title.
- Below H2: everything until the next H2 is that slide's body.

For a title slide, use YAML frontmatter:

```markdown
---
title: AIxBio Hackathon Findings
subtitle: Cross-Track Findings on DNA Screening, Early Warning, and Biosecurity Tools
author: Jason Hoelscher-Obermaier
date: May 21, 2026
---
```

Or just write your own H2 as the first slide for full control over layout.

When the deck needs more than pandoc gives you (precise image positioning, layered shapes, exact colors), don't fight pandoc. Apply the template in Google Slides and adjust there.

## Heuristic questions

Pull these out when stuck or when reviewing a draft.

- _"What's the imagined audience's first question after this slide?"_ If you can't answer it, the slide doesn't stand alone.
- _"Could I cut this and lose nothing?"_ If yes, cut.
- _"Where does this number come from?"_ If you don't know, treat as 🔴 (or push back to the user).
- _"Is this framing agentive when it should be structural, given who's in the room?"_
- _"What's the one thing I want them to remember from this slide?"_ If there are two, consider splitting.
- _"Am I editing prose or judgment?"_ Don't dress up a weak claim with stronger words. Find better evidence or weaken the claim.

## Iteration and pushback

- Defer to the user on style preferences and audience reads; they know the room.
- Push back on substantive errors (wrong number, unsupported claim, framing that misrepresents). Briefly say what's wrong and propose the fix, then let them decide.
- After 2-3 rounds of small edits on the same slide, suggest stepping back: "do we want to restructure this, or is this just a phrasing pass?"

## Common roadblocks

- **Content density too high** → split. Rule-of-thumb: ~45-60s per slide for a typical talk. Varies by format (tutorial slides can sit longer; keynote slides shorter).
- **Title wraps and crowds the body** → shorten, or move the subtitle into the body as an opening line.
- **Image fills the slide** → treat body text as caption-only.
- **Numbers disagree across sources** → reconcile before slides ship; document the canonical source in planning notes.
- **Tone keeps drifting back to LLM-speak** → dedicated plainness sweep.

## Anti-patterns

- **Saying the same thing twice in different words.** Common LLM pattern: a sentence followed by a near-paraphrase that adds no information. After each draft, ask "is the second sentence saying something the first didn't?" If not, cut it.
- **Mixing planning notes into on-slide content.** Defeats paste-readiness. Use HTML comments or `::: notes`.
- **Naming a 🔴 claim without naming the closing action.** Leaves the next step undefined.
- **Auto-styling the .pptx past what survives the template apply.** Wasted effort.
- **Reinventing pandoc.** If you find yourself building a custom MD→pptx parser, stop. Pandoc handles 90%+ of slide-deck needs natively; the missing 10% (precise positioning, custom shapes) belongs after template apply, in Google Slides, not in the compile step.
- **Asking the user to confirm trivial decisions repeatedly.** Make the reasonable call; let them redirect.
- **Drafting from an empty audience contract.** Ask 2-3 questions before fabricating one.
