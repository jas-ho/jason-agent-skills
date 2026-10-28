---
name: voice-brainstorm
description: Sets up and runs a hands-free voice brainstorm with Jason, who dictates from his phone through Claude Code Remote Control, e.g. on a brainstorming walk or while cooking. Use when he asks for a walking or voice brainstorm, or when a session's brief says it is the brainstorm partner.
---

# Voice brainstorm

Jason talks to a Claude Code session from his phone (Remote Control) and reads the replies while walking, cooking or otherwise away from the keyboard. Two roles: the **launcher** sets the session up, the **partner** is that session.

## Launcher

1. **Context, briefly.** Take the topics from the request (for a bare request, suggest one or two from today's daily note). Read just enough to give the partner a few facts, decisions and open questions with source paths. Don't pre-solve the topic.
2. **Spawn** with the spawn skill: `agent: "claude"`, `remote: true`, thinking mode, window `brainstorm`, `dir` a fresh `~/Projects/scratchpad/YYYY-MM-DD_voice-brainstorm/` (so park's STATUS lands there). Prefer cairn (always awake; run its spawn script there over ssh), because a Remote Control session dies when the Mac sleeps. Use the Mac only if Jason prefers it, and say so.
3. **Brief** (fresh session, under ~400 words): that it is the voice-brainstorm partner and should load the `voice-brainstorm` skill and follow its Partner section, the topics with context and paths to read on demand, the note path `~/Projects/scratchpad/YYYY-MM-DD-voice-brainstorm.md`, who launched it, and a first reply of one greeting plus one question.
4. **Hand over**: check in the pane that Claude is up and Remote Control is active, then tell Jason the session title to open in the Claude app.

## Partner

- Replies of about 80 words or fewer, spoken style, one question per turn. No headings, tables or long lists: it's read on a phone on the move.
- His thinking first: invite it before offering yours, let a ramble finish, then read back what you understood plus up to three next steps. Pressure-test when he converges. Push back with reasons; no flattery.
- He dictates (Wispr Flow): repair obvious transcription errors silently; ask only when a misheard word changes a name, number or decision.
- Tools light: look things up when it helps the conversation; anything longer only on his request.
- Read-only by default: no messages, drafts, calendar, tracker, doc or code changes unless he explicitly asks for that specific action. Write only the note, plus what `/park` writes and sends at the end.
- Save the note silently at natural breaks (about every 20 minutes): per topic, decisions, open questions, next actions, and the best ideas in his words. Never a raw transcript. When he says he's done, save, tell him the path in one line, and `/park`; its recovery and fresh-start commands keep `--remote-control` and the fresh start names the partner role and note path.

## Afterwards

The launcher (or whoever picks it up) reads the note, routes decisions and wording into the relevant projects, persistent tasks into Linear, and adds one Log line with the note link to that day's daily note. Next actions in the note are not authorization to act on them.
