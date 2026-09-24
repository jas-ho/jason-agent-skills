# Pandoc → .pptx → Google Slides

Use this path when the deck has to end up in Google Slides (co-authored with others, or an organiser's template). For decks Jason controls, the default is Typst (`typst-deck.md`).

## Compile

```bash
pandoc -t pptx --slide-level=2 slides-outline.md -o slides-outline.pptx
```

Then in Google Slides: File → Import slides → apply the template → final tweaks.

- `--reference-doc=ref.pptx` sets the theme, fonts and slide size. A raw Google Slides export usually does NOT work as a reference: pandoc matches layouts by exact PowerPoint names and placeholder types and silently falls back to defaults. For Apart decks a ready reference exists (`apart-brand.md`).
- `--metadata title="..."` sets the deck title for a YAML title slide.
- `--lua-filter=<skill-dir>/references/strip-notes.lua` drops speaker notes for a public version.

## Outline structure

- `##` (H2) starts a new slide; its text is the title. `#` (H1) only for "Part 1 / Part 2" breaks.
- Speaker notes go in a `::: notes` fenced div. They survive Google Slides import.
- HTML comments `<!-- ... -->` are stripped from the output: use them for planning notes (sources, confidence tags, todos).
- Title slide: YAML frontmatter (`title`, `subtitle`, `author`, `date`), or write your own first H2 for full control. Where body text lands depends on the reference doc's layouts; check the first compiled slide.
- Use plain markdown affordances: `**bold**`, `*italic*`, `` `code` ``, `[text](url)`, `- item`, `1. item`, `**Sub-header**: explanation`. Don't expect the renderer to infer emphasis from indentation.
- Images: `![alt](file.png){width=2.5in}`. For both Obsidian and pandoc, images must be real files (no symlinks) next to the markdown, without spaces in the name; no `![[wikilinks]]`.
- Pandoc does not split overflowing slides; overflow just runs off the slide. Split dense slides yourself and check the compiled deck.

## Limits

- Positioning is automatic; precise placement, layered shapes and exact colours belong in Google Slides after the template apply. Don't build a custom markdown→pptx generator; pandoc covers 90%.
- Google Slides has no theme-level hyperlink style; links stay blue and underlined per run. Apps Script can restyle them. `TextStyle.getForegroundColor()` returns only explicitly set colours, not inherited ones.
