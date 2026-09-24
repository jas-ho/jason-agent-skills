# Typst deck

The default path: a Typst deck in the project folder, next to the outline (not in `~/Code`, where Jason can't see it). Build with `typst compile`; check with deck-lint (load the `deck-lint` skill for its contract).

## Structure from the start

- **Design tokens at the top of the deck:** a few body sizes (for example `body`, `dense`, `small`), list spacing, and colours for each role. Slides use the tokens. Sizes set by hand per slide (18/20/21/22pt) caused most of the fit and consistency fixes in the 09/2026 deck.
- **Helpers:** add one when a content type appears a second time, not up front. Useful ones so far: a takeaway bar, a reasoning (chain of thought) card, a post card (board or wiki), a source line, a footnote. Cards label themselves in their credit line ("— reasoning · agent, via METR"; "— name, board post"), so no legend is needed and a wrong choice is visible.
- **Metadata:** every slide emits `#metadata((title: ...)) <deck-slide>` so deck-lint can check slide boundaries and you can refer to slides by title.
- **Notes build:** an input flag (`--input notes=true`) adds exactly one notes page after every slide, empty if the slide has no notes, section openers included. Slides then sit on odd pages and notes on even pages in two-page view ("Two Pages", not "Book").
- **Theme:** default to all-light for unknown projectors. Leave decorative section colouring out unless there is an on-screen reason.

## Checking

- **After each batch of edits:** `deck-lint check --typ deck.typ --json`, with the same `--input` flags as the build. Fix spillover and collisions; judge wrap and runt warnings in context.
- **Visual review:** `deck-lint sheet deck.pdf --output <new-name>.png --columns 4 --width 420`, then look at the sheet. Render single pages at 120 ppi or more before trusting a "missing" element; at 60 ppi bullets can vanish.
- **Refer to slides by title,** not page number. Page numbers shift with every edit.
- **Systematic design review from the sheet, once per major revision,** before Jason finds problems piecemeal:
  - one body size;
  - one list spacing;
  - quote style matching the source type;
  - date format;
  - footer and source lines distinguishable;
  - no one-word overrun lines.
- **Pre-delivery grep** on the built PDF for leaks and typos:

  ```bash
  pdftotext deck.pdf - | grep -nE 'Do not|TODO|OAI-[0-9]+|<internal ids>|<name misspellings>'
  ```

## Workflow

- **Check first that the editor picks up changes made on disk,** using a scratch copy. A stale preview buffer (Tinymist in Obsidian) once overwrote agent writes for about 50 minutes.
- **Take a backup before each pass** (scratchpad), and edit with exact-match anchors. Curly quotes in text the user typed break anchors, so re-grep when an anchor misses.
- **Theme pass comes last,** after the first timed run. If the visual direction is still open, compare 3-5 themes on about 10 probe slides in one image; with a given design (organiser template, Apart brand), skip that. Apply structural style changes one at a time.

## Typst gotchas

- Short lists are "tight" and ignore `spacing`; set `tight: false`.
- Don't name helpers or locals `left`/`right`; they shadow the alignment keywords.
- `move()` inside an alignment creates a block; wrap it in `box(move(...))` to keep it inline.
- `#v()` between inline texts inside a block matters: without it, or a `\`, title and subtitle merge onto one line.
- Markup-mode `else` needs care; build logic in code mode when it branches.
