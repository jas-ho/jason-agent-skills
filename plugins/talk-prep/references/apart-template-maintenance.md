# Apart pandoc template: maintenance

Only needed to change the Apart look or adopt a new template, never to compile a deck.

## Updating to a new brand template

You only need this when you want to **change the look or adopt a new Apart
template** — not to compile a deck. To compile, point pandoc at the committed
`apart-reference.pptx` (see the top of this file); it's ready as-is. Run the
commands below from this `references/` directory.

- **Tweak the look** (colors, type scale, spacing): edit the `DS_*` tokens at the
  top of `build-apart-reference.sh`, then run it with no argument — it rebuilds
  from the committed `source-template.pptx`:

  ```bash
  ./build-apart-reference.sh
  ```

- **Adopt a new Apart template**: export it from Google Slides (**File → Download
  → Microsoft PowerPoint**), build from it, and update the committed source:

  ```bash
  ./build-apart-reference.sh /path/to/new-export.pptx
  cp /path/to/new-export.pptx source-template.pptx
  ```

The script builds to a temp file, then validates before publishing: it checks
the zip is valid, asserts the brand edits actually landed, and smoke-compiles
with pandoc — **failing** (leaving the old `apart-reference.pptx` untouched) if
any layout falls back or an edit no-ops. Only on success does it move the new
file into place. Commit the regenerated `apart-reference.pptx`, an updated
`source-template.pptx`, any regenerated `assets/*.png`, and your `DS_*` edits.

**Requires:** Bash 4+ (Homebrew bash on macOS — the system `/bin/bash` is 3.2),
`pandoc`, `zip`/`unzip`, `perl` (all standard). `rsvg-convert` is needed only when
re-rendering the logo PNG from the SVG.

## Brand alignment (Design System tokens)

By default (`ALIGN=1`) the build applies the official **Apart Design System**
tokens, overriding whatever the exported template carries. This matters because
the standalone "Apart Slide Template" export is partly off-brand:

|                 | Slide-template export | Applied by default (live-verified)              |
| --------------- | --------------------- | ----------------------------------------------- |
| Font            | Arial                 | **Inter** (Neuemontreal is web/logo-only, paid) |
| Dark background | `#202729`             | **`#101010`**                                   |
| Primary green   | `#05CE7C` / `#45FE98` | **`#46FF99`** accent, **`#26C26B`** fill        |
| Text on dark    | `#F8F8F8`             | **`#F7F7F5`**                                   |

Alignment also applies Apart's **type scale and layout**: left-aligned bold
titles (big hero title on the cover) with tight display tracking, looser body
line + paragraph spacing, the corner asterisk in the bottom-right (clear of
left-aligned body text) with the muted date bottom-left, a dark-mode **table
style** (light text, green header rule, grey hairline rows, no fills), and a
full-width title + content layout for table/caption slides. Slide structure and
dimensions still come from the export; everything else is forced to brand.

All tunables are `DS_*` variables at the top of `build-apart-reference.sh`:
colors/font, `DS_LOGO_*` (asterisk asset, size, corner margins), `DS_TITLE_SIZE` /
`DS_COVER_TITLE_SIZE` / `DS_TITLE_SPC` (content + cover title size, tracking),
`DS_BODY_SIZE` / `DS_BODY_SIZE_L2` (body + nested-bullet text size),
`DS_BODY_LNSPC` / `DS_BODY_SPCBEF` (body line + paragraph spacing),
`DS_TABLE_RULE` (table hairline grey). Edit there; re-run
to rebuild.

To instead mirror the export verbatim (no alignment, no type scale), run:

```bash
ALIGN=0 ./build-apart-reference.sh
```

## Previewing a compiled deck

The compiled `.pptx` is meant for **Google Slides** (File → Import slides) or
PowerPoint, which render it faithfully. **Keynote refuses to import a pandoc deck
that contains speaker notes (`::: notes`)** ("file format is invalid") — verified
by bisection (one note makes any deck fail; a note-free deck imports fine). This
is a Keynote strictness quirk, not a problem with the deck or the reference. To
eyeball a deck with notes locally, add `--lua-filter=strip-notes.lua` (bundled
here) to drop the notes from that one output, or just import into Google Slides:

```bash
pandoc -t pptx --slide-level=2 \
  --reference-doc=<skill-dir>/references/apart-reference.pptx \
  --lua-filter=<skill-dir>/references/strip-notes.lua \
  outline.md -o preview.pptx
```
