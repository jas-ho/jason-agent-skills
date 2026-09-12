Resolve `<skill-dir>` to the loaded slide-creation directory and quote its absolute path in the commands below.

# Apart pandoc reference template

`apart-reference.pptx` is a pandoc-compatible reference doc that carries Apart
branding. Pass it to pandoc so a compiled deck comes out already themed. Use the
absolute path so it resolves when compiling a deck from any project directory:

```bash
pandoc -t pptx --slide-level=2 \
  --reference-doc=<skill-dir>/reference/apart-reference.pptx \
  slides-outline.md -o slides.pptx
```

No Google-Slides import-and-restyle step needed for the basics — theme colors,
fonts, dark background, slide size, and the corner logo come through directly.
Brand values (verified against the live apartresearch.com site): background
`#101010`, off-white text `#F7F7F5`, accent green `#46FF99`, fill `#26C26B`,
font Inter.

## Why this isn't just the raw Google Slides export

Pandoc matches template slide layouts by exact PowerPoint names ("Title and
Content", "Section Header", "Two Content", ...) and expects specific placeholder
types. A raw Google-Slides export names its layouts differently (`TITLE_AND_BODY`,
`SECTION_HEADER`, ...) with incompatible placeholders, so pandoc silently falls
back to its own default layouts and the branding is lost.

`build-apart-reference.sh` solves this by using pandoc's _own_ default reference
(correct structure, guaranteed) as the skeleton and grafting Apart's look onto it:
theme (colors + fonts), master background, master logo(s), and slide dimensions —
all extracted dynamically from the source export.

## Assets

`assets/` holds the corner asterisk monogram:

- `apart_asterisk_green.svg` — working source, recolored to the brand green
  `#46ff99` (matches the live favicon `#44ff98` and CSS accent `#46ff99`).
- `apart_asterisk_green.kit-original.svg` — the pristine Design System kit
  export, kept for provenance. It ships as `#23ef89`, a darker green than the
  live brand mark.
- `apart_asterisk_green.png` — 1024px transparent render of the working SVG; the
  build embeds this as the corner logo (`DS_LOGO` in the script), replacing the
  low-res raster the export carries, so there's no mismatched backing square on
  the dark slide.

Re-render the PNG after editing the working SVG:

```bash
rsvg-convert -w 1024 -h 1024 assets/apart_asterisk_green.svg -o assets/apart_asterisk_green.png
```

Logo size and position are set by `DS_LOGO_SIZE` / `DS_LOGO_MARGIN_*` in the
build script (currently 0.6 in, bottom-right corner).

## Updating to a new brand template

You only need this when you want to **change the look or adopt a new Apart
template** — not to compile a deck. To compile, point pandoc at the committed
`apart-reference.pptx` (see the top of this file); it's ready as-is. Run the
commands below from this `reference/` directory.

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
  --reference-doc=<skill-dir>/reference/apart-reference.pptx \
  --lua-filter=<skill-dir>/reference/strip-notes.lua \
  outline.md -o preview.pptx
```
