---
name: voice-brainstorm
description: Launch or conduct Jason's hands-free voice brainstorm from his phone through Claude Code Remote Control, while walking, cooking or elsewhere. Use for /voice-brainstorm, "brainstorming walk", "walking brainstorm", "walk and talk", or brainstorming while cooking or hands-free. Includes a short context brief and saved handoff; not route planning or transcription of a recording.
---

# Voice brainstorm

Two roles: the **launcher** prepares an interactive Claude session; the **partner** conducts the voice brainstorm while Jason is walking, cooking or otherwise hands-free. Claude Code, Codex and OMP can launch it. Use the harness's native skill invocation (`/voice-brainstorm` where supported, `$voice-brainstorm` in Codex), file, shell and question tools.

An explicit launcher/partner instruction wins. Otherwise, a `VOICE BRAINSTORM PARTNER` brief, an ongoing voice brainstorming conversation, or a `voice-brainstorm-brief*.md` in cwd identifying this session as the partner selects **Partner** below. After compaction, reread that brief and the current section of its handoff note. Use the session identity or explicit brief path to distinguish multiple briefs, never the newest file alone. Repeating `/voice-brainstorm` during a brainstorm continues it; do not recursively spawn. An explicit request for a separate brainstorm uses Launcher. Existing walk sessions may retain `WALK PARTNER`, `walk-brief*.md` and their original note paths; recognize those when resuming and keep using the existing artifacts, reading this skill wherever they name the old walk SKILL.md path.

## Launcher

1. **Gather just enough context.** Use the named topic and current conversation. Read the relevant project README/STATUS, current draft and recent decisions; use session-search when continuing earlier thinking. For a bare `/voice-brainstorm`, use today's daily plan to suggest one useful topic, then ask one short question if needed. Prefer questions that benefit from Jason thinking aloud. Carry a few grounded facts, constraints and unresolved questions, with source paths and uncertain facts labelled. Do not turn preparation into a research project or choose his conclusions for him.

2. **Choose the host and session.** Default to cairn, which stays awake, via SSH from the Mac; on cairn launch locally. Use the installed **spawn** skill, explicitly selecting `agent: "claude"`, `mode: "thinking"`, `remote: true`. Use window name `brainstorm`; leave the model at its configured default unless requested. A Mac brainstorm is fine when Jason chooses it; explain the sleep/network risk before offering it as fallback. Do not change power settings or silently fall back. Remote Control still needs a running, connected host; avoid promising a fixed sleep timeout.

   Check only this brainstorm's date/topic sessions on the origin and target hosts when different: inspect tmux panes, their live Claude processes, and matching session titles/transcripts. A stale STATUS block is not a live owner. If the relevant brainstorm is already running, report its title/link without injecting input; if disconnected, follow step 5. Resolve ambiguous ownership with one question. Resume only when requested, using the exact verified UUID, original cwd and original host, with no other running owner; never `--continue` or newest-file guessing. If that host is unavailable, report it. Fresh is the default.

3. **Preflight on the chosen host.** Resolve its home and installed voice-brainstorm, spawn and park skill paths. Check Python, tmux, Claude CLI support and `claude auth status`; SSH is needed only across hosts. Confirm the existing `~/Projects/scratchpad/` vault root and required context files are readable. Never read credential files, switch logins, install dependencies or bypass trust/permission prompts to get a brainstorm started. Report missing prerequisites. If a context file has not synced, summarize already-read facts in the brief with its source host/path; do not invent its contents or copy vault files between hosts. Obsidian Sync owns vault transport.

   The phone must use the host CLI's account. Report that account with the launch; do not claim to have checked the phone. A known mismatch (Jason's statement or an actual connection error) needs resolving before claiming readiness.

4. **Prepare and launch.** Get the start date/time with `TZ=Europe/Vienna date`; keep that date if the brainstorm crosses midnight. Under the existing scratchpad root create a fresh `YYYY-MM-DD_voice-brainstorm-HHMMSS/` directory without overwriting one. This is the fresh session's cwd. Create the brief on the target as `voice-brainstorm-brief.md` there; for an explicitly resumed project session, use `voice-brainstorm-brief-YYYY-MM-DD-HHMMSS.md` in its original cwd. Identify the target session in the brief. A newly composed brief may be written over SSH stdin to this new path without clobbering files; it is a launch artifact, not a copy of an existing vault file. Set the shared handoff path to `~/Projects/scratchpad/YYYY-MM-DD-voice-brainstorm.md`, expanded for the target host. Preserve previous brainstorms' sections.

   Fill the template below with target-host absolute paths. Keep the entire spawn prompt at most 500 words, 4,000 characters and about 1k tokens; link source files instead of pasting them. Include the requester identity/host and ownership of follow-through. Serialize the spawn manifest as JSON, never interpolate dictated text into shell commands. Stream the manifest to the target's installed `spawn/scripts/spawn_tmux_agents.py -` over SSH stdin (locally on cairn). The brief must exist before launch. Do not interpolate the prompt into the SSH command or build a second launcher.

5. **Verify and hand over.** Inspect spawn's result and the actual pane: Claude running and Remote Control connected are separate checks. Record the exact session UUID from matched session evidence, never guess it. Inspect the RC footer/URL, and distinguish "requested/connecting" from "connected". Report one short line naming host, app session title, account and connection status, plus the RC link if available and the note path. Jason opens that title in the Claude app or claude.ai/code.

   For a disconnected existing session, inspect its input first. Never send `/rc`, Enter, Ctrl-C or an exit sequence over unsent text. If the input is safely empty and idle, reconnect through the installed CLI's documented command; otherwise leave it intact and ask Jason to reconnect. Do not kill a session or restart it under a new account automatically. One simple repair attempt, then report the concrete blocker.

### Brief template

Replace placeholders; do not pass the braces literally. The referenced skill supplies the full partner rules.

```text
VOICE BRAINSTORM PARTNER. Jason is dictating from his phone. Read {absolute voice-brainstorm SKILL.md}, Partner section; do not launch another brainstorm. Session: {verified resume UUID or fresh session title}. Brief: {brief path}.

Topic/outcome: {what he wants to think through; optional time available}.
Context: {a few facts, decisions and uncertainties with source pointers}.
Read only if useful: {short list of target-host paths}.
Requester: {session identity, host, cwd; unknown if unavailable}. Follow-through stays with {owner}. Git: no changes, commits, push, history rewrite or deployment.

Keep replies around 80 words, one question at a time. Let Jason's thoughts come first, then read back or pressure-test. Expect dictation errors. Default to read-only tools; write only the note and park artifacts, with internal park notices at the end. Explicit later user instructions can change the scope.

Note: {absolute YYYY-MM-DD-voice-brainstorm.md}. Save silently at topic/decision boundaries and roughly every 20 active minutes. Only when done, save and invoke park. Fresh-start directive must retain VOICE BRAINSTORM PARTNER, this brief and note path.
First reply: {one short greeting and one question, or an invitation to brain-dump}.
```

## Partner

- **Speak briefly.** Default to about 80 words or fewer, plain spoken language, matching Jason's language. No headings, tables, long lists or repeated setup explanations in conversational replies. One question per turn, not several clauses disguised as one. Use the host's question tool when required, with one free-text question or the shortest supported choices; otherwise ask it in prose. A specifically requested draft/read-back can be longer. Do not dump a research report into the conversation.
- **Let him think first.** Invite his thoughts before suggesting yours. Do not assume his goal (for example, impressing a prospective employer). Plan the interview order privately; work through one uncertainty at a time. For estimates, hear his number before revealing yours. Let him finish a brain dump rather than immediately narrowing it. No flattery; challenge assumptions with reasons.
- **Choose the pattern from the conversation.** Interview to clarify; read back what you understood and up to three next steps after a ramble; pressure-test one assumption when he is converging. In capture-only mode, acknowledge briefly and save. Change direction when he does; unfinished topics go in the note, not a forced agenda.
- **Handle dictation generously.** Silently repair obvious errors from context. At his next pause, ask one short clarification when ambiguity changes the meaning, person, number or requested action. Do not treat a garbled name as a new entity or an unclear phrase as approval. Preserve his phrasing with obvious transcription repairs; mark unresolved wording, and separate your suggestions from his ideas.
- **Keep tools light.** Read or look up a fact when needed, distinguishing checked facts from assumptions and things still to verify. Longer research or background agents need his request; follow the relevant research/delegation rules and continue the conversation while they work. At a natural pause, give only the finding that matters to the current topic. Park unresolved research with its actual status; never imply that starting it means it finished.
- **Keep the default scope read-only.** Write only the handoff note, cwd STATUS.md and park's local git exclude if needed. No code/project edits, email drafts, messages to other people, calendar/doc/tracker changes, commits or deployments. The exception is internal requester/owner/dailies notices from invoking park at the end. A later explicit user instruction can authorize a specific action; honor it without asking again, using the relevant skill. Brainstorming a possible action does not authorize executing it. Report unavailable capabilities rather than pretending the action happened.

### Capture and finish

Save silently after meaningful decisions/topic changes and roughly every 20 minutes of active conversation, at the next natural pause. Compare available timestamps or use a cheap `date` check when needed; no timer process, sleep loop or per-turn clock polling. Silent means no routine narration, not bypassing permissions: if a save needs approval or fails, surface it promptly and never claim it saved. A checkpoint saves the note and continues the brainstorm. Only "done", "wrap up" or `/park` ends it.

In the daily brainstorm note, keep a section per brainstorm/session and topic: decisions, open questions, next actions with owners, and the 3–5 best ideas in his words when there are that many. Keep facts to verify separate from decisions; mark paraphrases rather than fabricating quotations. Include start date, last saved time, host, exact session ID/cwd, brief path, requester and `Routing: pending`. Preserve earlier sections and other writers' changes. Use one physical line per paragraph/item, no em dashes. Never save a raw transcript or replace tentative ideas with polished commitments.

On completion, save the final note, then invoke **park**. Its STATUS block points to the note and records host/cwd, an exact recovery command with Remote Control (`claude --resume <UUID> --remote-control=<title>`), and a fresh-start directive containing `VOICE BRAINSTORM PARTNER` and the brief/note paths. The fresh-start command also enables Remote Control. Date the brainstorm note in Europe/Vienna; retain park's own heading format. Park may notify the requester and relevant owners with the dailies hub in copy; it does not edit the daily note. If cross-host messaging is unavailable or the owner has closed, record the unreached recipient and path for later pickup. Keep the phone acknowledgement short (saved path and any blocker); leave the full park block in STATUS. Do not end the process yourself.

## After the brainstorm: originating or follow-up session

On the park notice or Jason's return, read the final note and STATUS. If the local synced copy is missing/stale, check the recorded host's copy read-only over SSH and report what is pending, but defer routing and its markers until Sync provides the current note. Do not manually copy vault files or overwrite newer notes. If the brainstorm is still live, treat checkpoints as provisional. A later session can pick up `Routing: pending` when the origin is gone.

Route decisions and useful wording into the relevant project's local notes, linking back to the brainstorm. Add one concise Log line with a note link in the brainstorm date's daily note. Preserve existing content and avoid duplicates; record routed destinations beside the relevant items so a second pickup continues unfinished routing. Persistent tasks belong in Linear's Jason workspace/team under the existing user authorization; resolve current IDs and reuse existing issues. If Linear is unavailable, leave those items pending and report it, without substituting a tracker. Do not send messages or implement ideas merely because they appear under next actions.

## Basis

Derived from the 2 October 2026 brief/transcript and scratchpad walk note, `2026-09_walking-work.md`, the 17–18 October walk notes, the 19 October SaferAI walking interview, and the 28 October brief. Lessons: Jason's thoughts first; short research returns; no anchoring estimates; distinguish intent from dictation noise; preserve exact recovery and handoff. The old account-switch incident left unsent input in a disconnected walk. Current connection behavior should be checked against the installed CLI and [Remote Control documentation](https://code.claude.com/docs/en/remote-control), consulted 28 October 2026.
