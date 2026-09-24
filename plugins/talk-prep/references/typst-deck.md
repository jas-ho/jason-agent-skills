# Typst deck

The default path: a Typst deck in the project folder, next to the outline (not in `~/Code`, where Jason can't see it). Build with `typst compile`; check with deck-lint.

## Structure from the start

- **Design tokens at the top of the deck:** a few body sizes (for example `body`, `dense`, `small`), list spacing, and colours for each role. Slides use the tokens. Sizes set by hand per slide (18/20/21/22pt) caused most of the fit and consistency fixes in the 09/2026 deck.
- **Helpers:** add one when a content type appears a second time, not up front. Useful ones so far: a takeaway bar, a reasoning (chain of thought) card, a post card (board or wiki), a source line, a footnote. Cards label themselves in their credit line ("— reasoning · agent, via METR"; "— name, board post"), so no legend is needed and a wrong choice is visible.
- **Metadata:** every slide emits `#metadata((title: ...)) <deck-slide>` so deck-lint can check slide boundaries and you can refer to slides by title.
- **Notes build:** an input flag (`--input notes=true`) adds exactly one notes page after every slide, empty if the slide has no notes, section openers included. Slides then sit on odd pages and notes on even pages in two-page view ("Two Pages", not "Book").
- **Theme:** default to all-light for unknown projectors. Leave decorative section colouring out unless there is an on-screen reason.

## Checking

Load the `deck-lint` skill; it owns the commands, flags and config. talk-prep only sets the cadence:

- **After each batch of edits:** `check --typ`, with the same `--input` flags as the real build.
- **Once per major revision:** a design review from the contact sheet, before Jason finds problems piecemeal:
  - one body size;
  - one list spacing;
  - quote style matching the source type;
  - date format;
  - footer and source lines distinguishable;
  - no one-word overrun lines.
- **From the first build:** a `deck-lint.toml` next to the deck, with a `forbidden` list (internal IDs, speaker-guidance phrases like "Do not quote", known misspellings of names). The check then catches leaks on every run, not only before delivery.
- **Refer to slides by title,** not page number. Page numbers shift with every edit.

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
