# Talk page and day-of

## Talk page (build at T-2 days)

- **One QR code on the closing slide** pointing to a simple page, instead of many links on slides. Links on slides distract during the talk; the page serves people afterwards.
- **Contents, top to bottom:**
  - title and date;
  - slides PDF, public version: no speaker notes, no drafting or private backup slides;
  - contact;
  - primary sources;
  - background;
  - any checklist as copyable text;
  - how to get involved.
- **Verify every link with curl** before publishing. Bot-blocked sites (openai.com returns 403) can be checked through a text proxy.
- **Local preview first,** then deploy. On cairn: `/srv/<name>/`, a Caddyfile block, validate, reload (see `~/.claude/context-coding/html.md`). Check Tailscale or the network before deploying.
- **The QR target must be live before the slide with the QR code is final.** Never leave a QR pointing at a dead URL.
- **After deploying, only re-upload the PDF** when the deck changes.
- **Final check:** open the actual public PDF, page through it for drafting or private content, and scan the QR code with a phone.

## Q&A prep

- **Prepare the 3-4 most likely skeptical questions,** in general form:
  - Is it real?
  - What's missing from the story?
  - Can anything be done?
  - What does it cost, or whom does it hurt?
- **Keep expensive but good answers here** rather than in the talk body.
- **Appendix slides do triple duty:** Q&A backup, drafting space, and a fallback for content that almost made the main deck.

## Day-of checklist

- [ ] Confirm mic and sound check (requested at T-7).
- [ ] Test the projector with your own laptop and adapter, then re-test just before the start.
- [ ] Prepare a plan for a dead projector: a 2-minute opener that works without slides (a story or an audience question).
- [ ] Put the PDF with and without notes on a USB stick and the phone.
- [ ] Record the talk (lapel mic to phone) for the debrief.
- [ ] Engagement beats ready (planned in the budget phase), e.g. an audience question ("imagine you're the agent waking up to this task: what do you do?").
- [ ] Rebuild the final PDFs from source and re-upload the public PDF if it changed.
