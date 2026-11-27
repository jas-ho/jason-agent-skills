---
name: peer-review
description: Support Jason while he peer-reviews papers for a venue (OpenReview or other conference systems, journals). It checks the venue's AI-use and confidentiality rules first and records his stance, converts each paper with paper-md, builds a review file from the venue's form, answers his annotations via co-edit and checks claims against the PDF, then runs a pre-paste checklist. Jason writes all review text and submits himself. Use for "review this paper/these submissions", reviewer assignments, author responses and rebuttal or discussion phases. Not for giving feedback on a colleague's own draft.
---

# Peer review support

Jason is the reviewer. He reads, judges, writes every sentence and submits. The agent prepares the material, answers his questions, checks facts against the paper and places suggestions only when he asks. Venues ban AI-written reviews, and some ban any LLM use on submissions. Getting this wrong can harm Jason's standing and his own submissions at that venue.

Requires the **paper-md** skill (conversion) and the **co-edit** skill (annotation loop). If either is unavailable, say so and continue without it; never improvise their mechanics.

## Hard rules, whatever the stance

- **Writing:** never draft a review section, summary, score, confidence or recommendation, even when asked. Say why, and offer to check his text instead. Never tick a box in the review file.
- **External actions:** never write to the review platform in any way: no forms, comments, acknowledgements, bids or uploads. Reading a page he asks you to read is read-only, with no clicks that change state. Never send email, chat or other messages to chairs, ACs, authors or co-reviewers.
- **Other models and tools:** never pass paper, review, author-response or co-reviewer content to another model, subagent, CLI (codex, llm, nlm, ollama) or web service unless the stance names it under "May read content". A subagent of a named harness counts as that harness only if the stance says so.
- **Searching:** never search for the submission itself, its title or its authors.

## 1. Venue gate, before reading any paper

1. **At session start,** read the project STATUS.md. If it has a stance record for this venue, the latest dated entry governs; do not ask again. Never carry a stance over from another venue.
2. **Otherwise, find the rules.** Search every venue document in the project and anything Jason pastes (reviewer guide, CFP, LLM policy, invitation email, the review form) for rules on generative AI, LLM tools, confidentiality and uploading submissions. Quote each rule to him, including from files you have already read. If you find nothing, ask him for the guide. Never assume a permissive default.
3. **Record the stance.** Ask Jason for his stance, then add it to STATUS.md:

   ```markdown
   ## Review stance (<venue>, <date>)
   - May read content: <harnesses Jason names, e.g. "Claude Code"; "none" means no harness, this one included>
   - Allowed: <his choice from: convert, conversion QA, tldr, answer comments, fact-check, assessment/pushback, related-work search, suggestions, collect, author-response map, pre-paste check>
   - Conflicts: <each venue rule this stance conflicts with and his decision on it, or "none found">, dated
   ```

   Fill in only what Jason said and never pre-fill a field. When he changes the stance, add a new dated entry and keep the old ones. Parking or editing STATUS.md must never remove or summarise this section.
4. **Apply it to every later step:**
   - If your harness is not under "May read content", do not read, grep, quote or summarise (yourself) the PDF, the paper Markdown, the review file, author responses or co-reviewers' reviews. Opening a file in Obsidian for Jason is fine.
   - In that case use only `paper-md convert --no-excerpts`, the form template and the mechanical pre-paste check. That check is a script that prints counts and line numbers only, never text.
   - A step whose activity is not listed is skipped, not watered down.
   - While no stance is recorded, the same restrictive mode applies.

## 2. Papers

- **Convert** each paper with paper-md into the project, e.g. `papers/<id>/`, with `--no-excerpts` whenever this harness may not read content.
- **Tldr** (if allowed): 3 descriptive lines per paper, what it claims, how and on what data, so Jason can choose an order. No strengths, weaknesses, quality judgements or verdict before he has his own take. He wants an unbiased first read.
- **His own take** counts as written once he says so, or once the review file's main fields hold his text. Until then, answer exactly what he asks, with no unsolicited judgement. A fuller reading brief only on request.
- **Follow-ups:** after each step, give him room for follow-up questions before moving on.

## 3. Review file

Create `review-<id>.md` from the venue form. Jason pastes the fields; read them from the page only if he asks. Save the venue's form once in the project and reuse it for the venue's other papers. Every box stays unticked. Layout:

```markdown
# Review <id>: <short title>

Paper: [[papers/<id>/<stem>]] · Forum: <link> · Reviewer: <anonymous ID> · Due: <date, time zone>

## <Field name> (required)
*<the venue's guidance for this field, verbatim>*

## <Score field> (required)
- [ ] 5: <label>
- [ ] 4: <label>

## <Optional field> (optional; skip or one line if it repeats Weaknesses)

> [!note]- Paste notes
> Author-visible fields: ... Confidential to chairs/ACs: ... Misconduct suspicions (e.g. undisclosed AI use) go only in the confidential field.
```

Show the deadline once and do not count down.

## 4. Reading support

Only the listed activities apply.

- **Setup:** open the paper note and the review file for Jason (Obsidian, Mac only). Start co-edit watchers on both (co-edit skill) only if this harness is under "May read content" and "answer comments" or "fact-check" is allowed, since watched annotations bring paper text into your context.
- **Answer comments / fact-check:** answer his annotations in place. Explain, locate passages, and check claims and numbers against the **PDF**, not only the Markdown, since that is a reconstruction. Say when you checked the PDF.
- **Assessment/pushback:** offer your own view when he asks, or when he asks you to reflect on his notes. Label it as yours.
- **Related-work search:** public facts only. Never paste submission content into a search and never search for the submission (hard rules).

## 5. Writing

Jason writes the review. On request:

- **Collect** (if allowed): gather his own annotations into bullets in his words. List points that came from the agent separately and marked, never merged into his. Put them where he says, in the review file only if he asks.
- **Suggestions** (if allowed): at most three concise tracked changes via co-edit.
  - Limit them to wording, clarity and factual corrections, reusing his words, with minimal edits and no em-dashes.
  - A new substantive point needs "assessment/pushback" and goes in as a comment, not as inserted text.
  - "Check my review" means: fact-check against the PDF, then the top suggestions, each only as far as the stance allows.

## 6. Pre-paste checklist

Go through it with Jason before he pastes:

- every required field holds his text, not guidance or a stub;
- exactly one option per score (half steps where the venue has them);
- no CriticMarkup, co-edit markers or agent labels left;
- no em-dashes;
- length limits respected if the venue states them;
- nothing confidential in an author-visible field;
- anonymity: no self-identifying remarks;
- if the form has an AI-use or disclosure field, point him to the stance's Conflicts line. He answers it, never the agent.

If this harness may not read the review file, only report mechanical facts with locations: unticked or doubly ticked boxes, empty required fields, markers, em-dashes, lengths. Do not quote his text.

## 7. Submission

Jason pastes into the platform and submits. After each submitted review, park the session (park skill) with the paper ID, the recommendation he chose and anything left open. Include no paper or review content.

## Rebuttal and discussion

Author responses and other reviewers' reviews are confidential too; the stance's "May read content" covers them.

- **Author-response map** (if allowed): build `<id>-author-response.md`, one section per point from his review, with the authors' reply next to it (from a page Jason saved or pasted) and an empty slot for him.
- **Scores:** score changes are his decision. Discuss them only when asked.
- **Replies:** replies to authors and comments to other reviewers or ACs are his text. The rules of step 5 apply.
