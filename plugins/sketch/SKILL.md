---
name: sketch
description: Watch Jason's hand sketch on the iPad (Obsidian Excalidraw, synced to the Mac) in near real time, give think-aloud feedback while he draws, and on "done" produce a clean separate diagram (d2 + PNG). Use for "watch my sketch", "I'm drawing the theory of change", "look at my drawing", "clean up my sketch", or any .excalidraw.md he is drawing in. Not for diagrams the agent drafts from text alone (write d2 directly).
---

# Sketch with Jason

Jason draws on the iPad in the Obsidian Excalidraw plugin; the drawing is a `<name>.excalidraw.md` in the vault (`~/Projects`), synced to the Mac by Obsidian Sync. `excalidraw-render` (in `~/bin`, `--help` for details) turns it into a PNG you can look at.

## Hard rule

Never write into the `.excalidraw.md` Jason is drawing in, not even to add notes. Obsidian Sync merges `.md` files as text, and a concurrent write can corrupt the compressed drawing or lose his strokes. Everything you produce goes into separate files.

## Start

1. Find the sketch: the file Jason names, otherwise list candidates newest first (`ls -t <project-dir> | grep excalidraw.md`). Ask if several are plausible; if there is none, ask him to create one in the project folder on the iPad.
2. Render PNGs into your scratchpad, never into the vault (they would sync back to the iPad).
   - Claude Code: run the watcher under the Monitor tool (timeout at the maximum, re-arm on expiry):

     ```bash
     excalidraw-render <sketch>.excalidraw.md -o <scratchpad>/<name>.png --watch 2>&1
     ```

   - Other harnesses: no watcher. Each time Jason says he drew something, run `excalidraw-render <sketch>.excalidraw.md -o <scratchpad>/<name>.png` once.
3. Read the PNG after each render. `excalidraw-render <sketch> --json` gives exact typed text labels and element types; handwriting stays stroke data, so ask Jason when a handwritten word is unclear.

Watcher output, one line per event: `rendered N elements (arrived HH:MM:SS, Ns after last stroke)` for a new version; `already there at start` for the version found when it (re)starts, which is not new work; `waiting for <file> to appear` for a wrong or not-yet-synced path; `unreadable, will retry` for a half-synced file, which usually clears on the next sync. If a file stays unreadable for 60 s the watcher exits with `still unreadable ... stopping`: check the file with `--json` instead of re-arming blindly.

## While he draws: think-aloud feedback

Short chat comments, not essays: what you read the diagram as saying, handwriting you are unsure about, and substantive gaps (missing causal links, an outcome without an input, boxes that duplicate each other). Hold back on layout nitpicks until he asks for the clean version. If several events arrive in quick succession, comment once on the latest.

## On "done": clean version

Write a separate `<name>.d2` next to the sketch (if the project already has d2 diagrams, match their style), render it with `d2 <name>.d2 <name>.png`, read the PNG back and check it against the sketch. Name later versions `-v2`, `-v3` instead of overwriting one Jason has already seen. Tell him which file to open on the iPad. Stop the watcher (TaskStop in Claude Code) when the session's sketching is over, and restart it on the new file if he switches to another sketch.

## When nothing arrives

Normal latency stroke-to-Mac is a few seconds (measured 3 s, 2026-10-22). The plugin writes the file when he taps save or leaves the drawing. If he saved and nothing arrives within a minute, the Mac side of Obsidian Sync is usually stuck (seen once: a dropped connection that stalled ~6 min, then recovered on its own): ask him to check the sync log in Obsidian on the Mac (iPad "Upload complete" but no download on the Mac means the Mac is stuck).
