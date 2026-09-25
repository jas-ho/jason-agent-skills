---
name: workspace
description: Prepare and manage named macOS desktops through the workspace CLI. Use for workspace requests or when a substantial, clearly separate task would benefit from its own desktop and app windows. Not for ordinary subtasks or background reviews.
---

# Task workspaces

Use the installed `workspace` CLI on Jason's Mac; it owns desktop creation, app windows, layout and return behavior. Requires the logged-in macOS GUI worker. If unavailable, report the limitation and continue the task without desktop setup. Use `workspace check --json` to diagnose readiness; it does not establish every app permission.

## Decide placement

- Create automatically when a substantial task clearly deserves its own working context. Ask only when separation is ambiguous; ordinary subtasks stay together. Creating a desktop does not authorize launching another agent. Background workers should leave desktop setup to the originating conversation unless explicitly delegated.
- Read `workspace list --json` first. Reuse a desktop whose task association is established in the conversation, such as one created here or identified by the user; do not infer ownership from a matching name. Reuse means reporting its ID without switching or creating more windows.
- Prepare and return by default. Announce setup briefly because it visits the new desktop. Use `--stay` or `switch` only when the user wants to move there. Run mutations sequentially and respect manual desktop changes; do not switch back to repair a skipped return.
- Name alone works. Add an existing project directory, relevant URLs or an existing vault-relative note when known; do not create folders or notes just to populate a desktop. App choices and layout belong in the CLI recipe, not this skill.

## Execute

```sh
workspace create "Task name" --json
workspace create "Task name" --directory /absolute/project --json
```

Name alone links the terminal to an exact existing tmux session or a configured project folder, otherwise creating a fresh home session. Explicit `--directory` or `--tmux-session` overrides linking; use `--directory ~` for a fresh home session. Supply `--tmux-session` only for an existing session chosen for this task; `--directory` does not reset that session's working state. Attachment leaves other clients connected and does not select a particular tmux window.

Use `workspace COMMAND --help` for options, including repeated `--url`, `--note` and `--config`. Use fresh desktop IDs from `list` or the create result; desktop numbers are positional and IDs must be refreshed after reboot/removal.

Read the JSON outcome: only `status: complete` is completion (exit 0); close previews use `confirmation_required` and exit 1. Keep the returned `operation_id` and `data.space_id` in the conversation. For running, partial or uncertain outcomes, inspect `workspace result OPERATION_ID --json` and fresh desktop inventory before deciding what remains. Never blindly repeat creation: every call makes another desktop, and a missing result does not prove nothing happened. Preserve successful windows and tmux sessions on failure; report blocked steps for attention rather than retrying them.

Close only when requested. Preview with `workspace close --id ID --json`; an explicit close request authorizes adding `--yes` after reviewing that inventory, without another confirmation. A preview does not reserve the contents. Let save prompts remain for the user. Desktop closure does not manage tmux lifetime; never kill sessions as part of closure.

Report the desktop name/ID, terminal session when present, and any incomplete setup. Do not claim an agent launched merely because its desktop exists.
