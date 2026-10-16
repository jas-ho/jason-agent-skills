# Accelerate Europe and Transformative KI Österreich brands

Templates, logos, fonts and colour tokens for both initiatives live in `~/Code/ae/slide-templates` (private: github.com/accelerate-europe/slide-templates). Read its `AGENTS.md` before building a deck; it maps markdown to layouts and gives the check loop.

- Pandoc decks: `--reference-doc="$HOME/Code/ae/slide-templates/dist/ae-reference.pptx"` (or `tki-reference.pptx`); a `~` after `=` is not expanded. These replace the Typst default when the talk is for AE or TKI. After every pandoc build, run `"$HOME/Code/ae/slide-templates/polish.py" talk.pptx`: it fixes the cover date size, splits subtitle and author, moves table captions under the table and renumbers shape ids.
- Google Slides: the repo README has make-a-copy links to both masters (an @accelerate-europe.org account is needed); otherwise import the same `.pptx` as a theme, or start from `dist/<brand>-starter.pptx`.
- Figures: `dist/<brand>.mplstyle` and `dist/<brand>-tokens.css`; logos in `assets/<brand>/` (SVG with outlined text, PNG renders).
- Matthias Samwald owns both brands. Brand values marked `proposed` in `brands/*.json` are not confirmed by him yet; don't add new brand decisions without flagging them.
