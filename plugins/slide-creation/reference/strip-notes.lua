-- Drop pandoc speaker-note blocks (::: notes ... :::) from the output.
-- Use only for a local Keynote preview: Keynote rejects pandoc decks that
-- contain speaker notes ("file format is invalid"). Google Slides and
-- PowerPoint import notes fine, so don't use this for the real deck.
--
--   pandoc -t pptx --slide-level=2 \
--     --reference-doc=apart-reference.pptx --lua-filter=strip-notes.lua \
--     outline.md -o preview.pptx
function Div(el)
  if el.classes:includes('notes') then return {} end
end
