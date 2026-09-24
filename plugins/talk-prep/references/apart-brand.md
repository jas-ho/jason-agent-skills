Resolve `<skill-dir>` to the loaded talk-prep skill directory and quote its absolute path in the commands below.

# Apart brand

## In a Typst deck

- Palette: one green (`#45fe98` on dark, `#26C26B` on light backgrounds), a dark background `#101010` or off-white `#FAFAF8`, and neutral greys for hierarchy. In charts, use neutral greys plus green for the highlighted series, never a rainbow.
- Font: Inter.
- The asterisk mark is in `references/assets/` (SVG and PNG). A bold green `*` also works as a footnote marker for Apart credit.

# Apart pandoc reference template

`apart-reference.pptx` is a pandoc-compatible reference doc that carries Apart
branding. Pass it to pandoc so a compiled deck comes out already themed. Use the
absolute path so it resolves when compiling a deck from any project directory:

```bash
pandoc -t pptx --slide-level=2 \
  --reference-doc=<skill-dir>/references/apart-reference.pptx \
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

To change the template itself, see `apart-template-maintenance.md`.
