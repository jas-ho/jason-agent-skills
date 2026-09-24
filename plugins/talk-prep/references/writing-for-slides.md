# Writing for slides and talk text

Applies to outline prose, slide text, speaker notes and the talk page. General anti-slop rules live in `~/.claude/context-writing.md`; this file adds what is specific to talks. Jason's audiences are often mostly non-native English speakers and not specialists.

## Plain words

- **Titles and takeaways** must read plainly to an outsider without the speaker. Bullets can stay short cues.
- **Expand every acronym on first use**, in the slide or in the notes.
- **No internal labels, IDs or file names** on slides (team shorthand, citation codes, research file names).
- **No reference back to a term that was never named** ("did both" needs the two things named first).
- **No abstract noun stacks** ("Evaluate the collective"). Say who does what: "Test agents as a group, not one by one."
- **When Jason says he doesn't get a line, reword it.** Don't add an explanation line under it. If the second attempt still isn't clear, ask what he'd say, in his own words.
- **Screen every title, tagline and takeaway before showing it:** count-led titles ("Three X that Y", "Two incidents, one timeline"), antithesis ("not X but Y"), colon punchlines, eyebrow labels, and saying the same thing twice. Offer 2-3 plain options.

## Structure

- **Each section:** claim → evidence → (one controlled study if there is one) → what follows. Every bullet serves the claim.
- **Explaining a failure:** intended design → what actually happened → failure class. Keep one level of abstraction, ordered from mundane to foundational.
- **Takeaways state the general lesson,** not the incident detail. Test: would the audience just answer "obviously, patch X"?
- **Rank by what's most interesting,** not by what fits the frame. The frame can be adapted afterwards.
- **One running example.** If a second one appears, ask before building visuals for both.
- **Structural, not agentive, framing** when describing other people's work, unless accountability is the point.

## Three layers

Keep three kinds of text apart, and decide early which material goes where:

1. **On the slide:** what the audience reads.
2. **Speaker notes:** what to say, timing cues, if-asked facts, guard rails ("say X, not Y").
3. **Planning notes:** sources, confidence, todos. These go in comments or a sidecar file.

Speaker guidance and internal IDs leaking into source lines is the failure to watch for.

## Evidence

- **Every number points to one canonical source.** Reconcile sources that disagree before the deck ships. When a count depends on the method, say which method.
- **Confidence tags for evidence-heavy talks:**
  - 🟢 robust;
  - 🟡 tentative;
  - 🔴 blocked, always with the cheapest action that would close the gap.
- **Research menus from subagents:** tag each item [public], [check] or [conf]. Verify public/private and access claims before tagging anything [public].
- **Quotes on slides come from the raw primary text, never from a summary.** Quote marks only for verbatim text. Mark paraphrase as paraphrase.
- **Legal and regulatory claims:** fetch the primary text. Don't write "from memory, check before quoting".

## Heuristic questions

- What is the audience's first question after this slide?
- Could I cut it and lose nothing?
- What is the one thing to remember from it? If there are two, consider splitting the slide.
- Am I editing prose or judgement? A weak claim needs better evidence, not stronger words.
