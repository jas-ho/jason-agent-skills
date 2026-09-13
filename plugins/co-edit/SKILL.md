---
name: co-edit
description: Live collaborative writing in Obsidian for Markdown and Typst, with explicit revision-bound submissions, safe concurrent edits, inline answers and sidecar proposals. Use when the user asks to coedit, watch a writing document or folder, or work from inline annotation requests while they keep writing. Shared workflow for OMP, Claude Code and supported Codex clients; requires a ready native delivery adapter. Not for source code or one-shot copyediting.
compatibility: macOS, Python 3, running Obsidian with its CLI; Typst requires an editable Obsidian Markdown view. Native harness delivery must pass readiness. Bundled scripts resolve relative to this skill directory.
---

# Co-edit

The user owns the prose. A **clear request deliberately submitted with `⏵` authorizes the requested edit**, including substantive changes. Do not ask for a second apply confirmation. Broad requests such as “make this introduction stronger” get alternatives first. No separate live/sidecar modes: choose the appropriate surface for each response.

One shared runtime owns submissions, timestamps, exact revisions, pending work and write receipts. Harness adapters only deliver events and expose native UI. Do not implement another watcher in a prompt or treat a delivered notification as completed work.

## Start an explicit scope

1. Use the file or folder the user named. If absent, ask for the scope; do not infer authorization from recent files. A recursive folder admits existing and new supported documents automatically, without per-file enrollment. A file includes its adjacent `<file>.notes.md` sidecar.
2. Start the **owning conversation's** native adapter below. Wait for the runtime's `ready` event, then read status. A spawned process, installed skill or old “watching” message is not readiness.
3. Read current requests and existing sidecar history. Explicit attachment authorizes a one-time import of newly discovered signed requests at that snapshot; this is not proof of a past keystroke. A signed carrier or document appearing afterward is **not** another import window: it needs an observed unsigned carrier followed by fresh token insertion. Existing unresolved valid submissions resume. Legacy unsigned/`;;` requests remain untouched and need fresh submission.
4. Announce effective scope, supported formats, pending/blocked counts and any hold/pause or recovery requirement once. Do not open/rearrange the user's panes. Navigation is through document links, nearby sidecar links and the native pending view.

Only Markdown and `.typ` through verified Obsidian editor buffers are supported by this runtime. Do not claim live safety for LaTeX, Overleaf, other editors, remote coedit or unknown extensions. Preserve existing documents and sidecars; no bulk rewrite. Code, journals and databases stay outside the vault.

### Native delivery

**OMP:** use the native `coedit` tool or `/coedit`. Start the explicit scope, then use its status/pending, read, submit, hold/pause, write, state, resolve and stop operations. Notifications are compact `aside` wake hints; query durable pending state when one arrives. OMP plan mode has delivery restrictions: obey the adapter's readiness warning rather than promising autonomous editing there. Do not extend or replace generic `monitor` with a second coedit owner.

**Claude Code:** discover the native `Monitor` tool and run one thin adapter, not raw runtime stdout:

```text
python3 -u <skill-directory>/adapters/claude.py watch --scope <absolute-path> --owner <owning-Claude-session-UUID>
```

Use the current session ID, never a newly invented owner. Native local/plugin Skill loading substitutes `${CLAUDE_SESSION_ID}`; when reading this file manually, the installed Bash transport supplies `CLAUDE_CODE_SESSION_ID`. Resolve the value before launching; literal placeholders are not identities.

Use Monitor's actual `command` and `persistent: true` schema with correctly quoted arguments. Its permission check delegates to Bash; approve only the exact scoped command. The adapter holds the runtime's stdin pipe open and filters non-waking status locally, emitting compact readiness/work hints and bounded failure signals. Raw Monitor wakes on every stdout line and supplies `/dev/null` stdin, so running the shared watcher directly there is incorrect. If Monitor is unavailable or readiness fails, report unsupported delivery rather than starting a background substitute.

Use `scripts/runtime.py call` with one structured JSON object on stdin for editorial operations; an explicitly approved exact command can read a private JSON input file outside the vault. Read durable status on work hints; neither hints nor model summaries prove a write. Stop the runtime owner and Monitor on explicit stop/session shutdown; reattach and reconcile on resume. Closing headless CLI stdin alone is not verified session termination while a persistent Monitor is active. Native busy/idle delivery, reviewed archive, explicit stop and owning-process SIGTERM cleanup were exercised; no Claude-native review picker is claimed.

**Codex CLI:** launch `python3 <skill-directory>/adapters/codex.py watch --scope <absolute-path>` directly through the owning CLI's native `exec_command`, with `tty: true` and a short yield interval. Obsidian GUI/IPC startup is blocked by ordinary workspace sandboxing on this Mac: request the user's native approval for this one scoped foreground process. Do not change global sandbox policy, background it, or create another model owner. Retain its command-session ID and use native `write_stdin` for newline-terminated JSON such as `{"id":"check-status","op":"status"}`. Each operation has a distinct correlation `id`; omit `owner` and `scope`, which are fixed from the inherited `CODEX_THREAD_ID` and startup scope. Responses carry `type: response` and the same ID; ready/pending/status/diagnostic events may interleave. One operation may be outstanding; stop can interrupt it, but uncertainty still requires reconciliation rather than replay. Do not launch separate per-operation GUI commands under the sandbox. Require actual `ready` before announcing watching. JSON stop ends the scope explicitly; EOF/CLI exit ends the process without erasing pending work. Native user interruption still pauses queue delivery until user continuation. Desktop support is not implied.

On the tested Codex 0.154.0 installation, the requested scoped escalation ran without presenting approval under both configured and stricter user/on-request policies, and Obsidian aborted before readiness. **That native route remains blocked here**, despite the adapter's passing process/channel checks. Do not represent it as operational or substitute a global sandbox bypass.

Ordinary research/drafting delegation uses the current harness's native workers. Give them explicit context and read-only ownership of the relevant material; the parent alone performs coedit writes. Purposeful cross-model reviews are allowed when useful or requested. Use the actual host tool schema, not hardcoded foreign tool names.

## Submitting and revising

Request creation snippets leave requests **unsigned**. Examples of deliberately finished requests:

```text
<!-- TODO(jason): Add a citation for the stated date. ⏵ -->
// TODO(jason): Replace “established” with “suggested” in this sentence. ⏵
```

- Finish with the terminal `⏵`, typed directly or inserted by **`,sign`**. To submit a revised request, **remove its old `⏵`, then insert a fresh one**. That renewed insertion records the current exact revision. Do not stack signatures or infer fresh consent from a glyph that remained while wording changed. There is no second Espanso submission shortcut.
- Each submission records a distinct ID/generation, UTC time and exact request fingerprint outside the document. A timestamp alone does not authorize text edited afterward. Do not add status flags or machine IDs to the user's request.
- `generation`, submission identity and timings describe the last signed submission; `submitted_revision` identifies that exact text. Edited current `raw`/`revision` can differ while `needs-resubmission`. Those historical fields are not fresh consent, and the pending view labels their timings as previous-submission evidence.
- Editing the request invalidates its accepted revision. An old visible token, a pause in typing, or moving the cursor away is **not** renewed consent. Submit again.
- Accepted signatures receive a request-local Obsidian confirmation identifying the exact revision; invalidation gets a separate notice. An absent confirmation is not a reason for the agent to re-sign on the user's behalf. Inspect current status and safe next action.
- After an event-coverage gap, unchanged pending revisions recover automatically. Previously tracked changed requests require fresh submission unless an exact-revision submission record matches. Explain `needs-resubmission` directly.
- Surrounding prose changes do not invalidate an otherwise unchanged request. Reread and adapt when the same intent still clearly applies; stage alternatives/clarification if it no longer does.
- Deleting a request cancels pending work after a cut/paste grace period; it is not approval. Moving an unchanged request must not create duplicate work. A continuously present signed original is temporarily blocked while identical copies are ambiguous; uniqueness can restore its prior state only with complete continuity evidence. A copied request whose wording diverges still needs a fresh sign. Never reconstruct old consent from a legacy blocked-state explanation.
- After observed duplication, an entirely new already-signed carrier with the same kind/author may have unprovable ancestry, especially across a restart. It conservatively needs a fresh sign; unrelated wording alone is not provenance. Creating the carrier unsigned and then inserting `⏵` avoids this ambiguity.
- `CLAUDE(...)` and its reserved prefix family identify assistant comments regardless of the actual model. Never place a user request inside an assistant comment; HTML comments cannot nest.
- Literal examples, quoted anchors, frontmatter, fenced/raw code, blockquotes and recognized archive sections are not executable requests. Active sidecar user requests remain eligible. Legacy `Applied YYYY-MM-DD` sections remain history.

Interpret the complete comment and its surrounding context, not its type label or a verb keyword. `QUESTION`, `TODO`, `IDEA` and other reasonable uppercase types are organizational labels. Preserve self-notes as self-notes; do not turn an explicitly deferred thought into unsolicited research.

## Choose the response surface

| User intent | Response |
| --- | --- |
| Clear bounded edit, addition, cut or structural instruction | Make that authorized edit directly; no second approval |
| Broad or materially ambiguous improvement | Offer alternatives, explain the meaningful tradeoff |
| Short factual/background question | Put a concise sourced answer in a comment near the question |
| Small wording alternatives | Keep them inline near the relevant span |
| Lengthy alternatives, research, sources or decision discussion | Use a stable entry in `<file>.notes.md` with a nearby pointer |
| Missing intent that blocks one request | Ask near that request and mark it awaiting-user; continue independent work |

Use a reserved `<!-- CLAUDE(<request-id>): ... -->` comment in Markdown, or `// CLAUDE(<request-id>): ...` lines in Typst. Escape/split content that would prematurely close its comment carrier. Long answers belong in the sidecar, not a giant hidden main-document comment.

Sidecar entries have a stable heading/link, a brief label, the original request quoted as a non-executable anchor, and only useful proposal/source/discussion sections. Preserve existing `## Active` and archive conventions when adopting a sidecar. Use Obsidian links for navigation; do not automatically rearrange panes. For a Typst main document, navigation can live in its comment plus the Markdown sidecar/chat.

The user can review by writing a signed directive, directly editing a proposal, giving unambiguous chat shorthand, or choosing through the harness pending/review UI. **Their edited proposal text is authoritative.** “Apply B” means the current B, not a cached version. When chat supplies the decision, bind it to the exact current pending request/proposal; clarify only if that reference is genuinely ambiguous.

Clarification is document-first. Use a structured choice picker when the user requests it, not for every edit. Silence is not a choice. Quiet direct edits and compact batched summaries are the default; avoid per-keystroke chatter.

## Work from durable pending state

For each submitted request:

1. Read its current `id`, `generation`, exact raw request, context and sidecar through the runtime. A wake message may be stale or truncated.
2. Interpret the authorized outcome and mark `working` before processing, including trivial answers; this records pickup time. Retain useful research if the request changes, but do not apply it to an unsubmitted revision.
3. Research or draft as needed. Cite actual sources; do not invent missing service capabilities. One blocked request does not stall independent ones.
4. Reread immediately before editing. Pass exact expected affected text and, if using a proposal, its exact current source span to the guarded write operation.
5. A committed `purpose: answer` becomes **answered**, not resolved. Leave the request and adjacent answer visible until the user asks to close/archive that reviewed answer or explicitly chooses **Archive reviewed answer**. Do not reprocess answered work or move it to working. For alternatives/clarifications requiring a decision, write with `purpose: proposal` and record `awaiting-user`. A completed direct edit whose delivered prose remains visible may resolve immediately.

Use the runtime's `next_action`, receipt summaries and timing stages rather than dumping UUIDs, fingerprints, payloads or full documents into chat. Submission, hint emission, native handoff, pickup and commit are distinct times; handoff is not proof of consumption. Current diagnostics block or qualify readiness; recovered/history entries are evidence, not current failures. A non-waking status/empty/recovered event updates the view without creating new work.

### Shared operation interface

`python3 <skill-directory>/scripts/runtime.py call` accepts **one JSON object on stdin** and returns JSON. Pass prose as structured stdin, never interpolate it into shell code. OMP exposes these operations through its native tool. Codex sends the same operation fields through the approved adapter's stdin channel, adding correlation `id` and omitting fixed `owner`/`scope`. Obtain request IDs/generations from current status/read; never invent them.

- `status`: scopes, readiness and pending/blocked/answered work, safe next actions, timing and receipt summaries, and separate current/history diagnostics; optional owner filter outside the fixed-owner Codex channel.
- `read`: owner + request_id, current request/document/sidecar context.
- `submit`: owner + equivalent native deliberate signing at the active request, only when explicitly requested by the user; never use it to repair missing consent automatically. Native adapters supply their fixed owner; the CLI requires `--owner` and does not scan unrelated scopes. The normal writing workflow is removing/reinserting `⏵`.
- `state`: owner + request_id + generation, state `working` or `awaiting-user`, optional reason.
- `hold`: owner + boolean value; stops applies while collection continues.
- `pause`: owner + boolean value; batches wake delivery while collection continues.
- `write`: owner + request_id + generation + unique operation_id; `target` has path, expected, replacement; optional `proposal` has path and expected. `purpose` distinguishes apply/answer/proposal. Empty expected means append only with the exact current full `base` guard.
- `resolve`: owner + request_id + generation + unique operation_id + editorial record. Any generation with committed-answer evidence requires literal `reviewed: true`, representing explicit human review/closure, before new archive/cleanup mutations—even through legacy or repair paths. Silence, another question, or an agent's completed answer is not review. Optional `cleanup: [{path, expected}]` selects proven generated scaffolding. Archive exact content before guarded removals; preserve changed/unproven spans and report `cleanup-needed`. If even the sole generated answer is missing, refuse closure rather than silently omit it from history. Reuse an existing partial resolution's operation ID and record, never a fresh ID to bypass uncertainty.
- `reconcile`: owner + request_id, optional generation; inspect live snapshots and receipt/recovery evidence without document mutations, opening/creating editors, consuming submission events, advancing the owner's cursor, or restoring write authority. It can recognize committed work while current cleanup authorization is blocked. A later normal synchronization must independently revalidate any remaining authority.
- `stop`: that owner only; explicit stop must not silently rearm on resume.

Write example shape, with values obtained from a fresh runtime read:

```json
{
  "op": "write",
  "owner": "<returned-owner>",
  "request_id": "<returned-request-id>",
  "generation": 1,
  "operation_id": "<fresh-operation-UUID>",
  "purpose": "apply",
  "target": {
    "path": "<authorized-document>",
    "expected": "<exact unique current affected text>",
    "replacement": "<authorized replacement>"
  },
  "proposal": {
    "path": "<current-proposal-document>",
    "expected": "<exact selected current proposal span>"
  }
}
```

Omit `proposal` or use `null` for direct edits that do not select proposed wording. Never invent an empty proposal. Do not treat the example generation as a default. Use the actual runtime schema/help for adapter-specific fields.

## Write and recovery invariants

- **All coedit main, sidecar and archive mutations use the shared guarded runtime.** Never bypass it with Edit/Write, a filesystem replacement, or the old writer when Obsidian refuses a buffer.
- The final synchronous editor operation validates owner/coverage, submitted request, selected proposal when present, and expected edit target together. Cleanup additionally requires the exact current archive buffer and uninterrupted archive evidence at that same boundary. Each archive entry must contain its own source metadata and complete protocol fields within the same recognized archive section; another entry or History/Applied section cannot supply proof. A historical committed archive receipt is insufficient after its content was removed or changed. Opening an inactive editor first does not waive the final check.
- Archive ingestion uses the same entry-local evidence. Legacy raw history maps only to its own document or adjacent main document, never to source metadata from another entry.
- Conflicting open views, missing/ambiguous anchors, unsupported surfaces and uncertain ownership block the affected operation. Do not silently fuzzy-match.
- Typst editor access does not imply Sync coverage. The observed Mac vault's Sync filter excludes `.typ`; do not relocate real Typst documents or promise backup merely because a local write succeeded.
- Preserve unrelated live edits and ordinary editor undo. No whole-file replacement from an old snapshot, unsolicited footnote renumbering, formatting sweep or save-and-pause fallback disguised as live editing.
- Operations are prepared before mutation and receipted afterward. A transport error can occur after commit: use read-only `reconcile` and inspect current receipt/state, never blindly retry or change an operation ID to bypass a refusal.
- Main edits and archival are separate transactions. If an edit landed and archival failed, reconcile its proof first, then resume the **same saved resolution**; repair authorizes only its unfinished internal stages, not another public edit or a reset to working. Human review remains required for answered work. Preserve original requests, variants, decision and change summary in dated history before deleting active scaffolding. Restored scaffolding is preserved and reported, never silently replay-cleaned.
- User undo does not authorize replay of resolved work. User deletion cancels; it does not mean “accept and reapply.”
- Runtime state belongs under the private local coedit state directory, never in skill source or the vault. State is shared across harnesses, not copied during switching.

## Hold, stop and resume

`hold apply` stops applies, not request collection. An inline `PAUSE(author): ...` comment batches that file's notifications without requiring a sign-off; removing it releases pending notifications. Scope pause is separate. Report the actual persisted hold/pause state on resume.

There is one live owner per overlapping file/folder scope. To change harnesses, stop the old owner, then start/reconcile in the new harness. Do not invent an automatic handoff system or steal a live lease.

Work can continue while the owning harness remains running and the user is elsewhere. Closing that owner stops model work and its watcher; recovery is explicit and revision-aware. Do not confuse viewing a child agent with closing the parent. On actual conversation switches follow the adapter's lifecycle and never claim a stopped watcher is still active.

On explicit stop, report which scope is no longer watched. Preserve documents, unresolved state and editorial history. On resume, verify current readiness and reconcile before acting. Operational acceptance requires the user's real writing/review session; file discovery and a passing schema check alone do not prove coediting works.
