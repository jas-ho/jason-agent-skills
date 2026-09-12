# Native lifecycle mappings

These mappings were inspected on the Mac on 2026-09-12. They describe current capabilities, not a universal API. Read the actual runtime tool definitions before calling them. A missing interface is a visible capability gap, not permission to invoke a vendor runtime inside a different harness.

## Codex collaboration

- Launch: `collaboration.spawn_agent` returns the canonical agent ID/task path. Use a concrete task and the available model-selection rules. The launch is nonblocking; record its returned identity. Forked context is native inheritance, not conversion from a CC transcript.
- Status: `collaboration.list_agents`; select the exact returned identity. A path prefix is only an inventory filter, not a substitute for the full cancellation/follow-up target.
- Running steering: `collaboration.send_message` to that exact worker. Idle continuation: `collaboration.followup_task`, which starts a turn if idle. Never send a user operation to a similarly named sibling.
- Waiting: `collaboration.wait_agent` reports mailbox activity, not necessarily the final payload itself. Results arrive in the conversation. Keep the output associated with its sender/ID; `result` returns that delivered output. There is no generic `get_result` or durable job database in this interface. If output is no longer available, report that rather than inventing it.
- Cancel: `collaboration.interrupt_agent` stops the current turn; the worker remains addressable. Inspect the exact worker afterward and describe it as interrupted if that is the native outcome. Do not claim deletion or permanent cancellation.
- The currently advertised launcher has no per-worker sandbox/tool allowlist argument. Review's no-mutation contract must be in the task and respected by the worker. Do not pass imaginary `read_only`, `allowed_tools`, or `sandbox` fields or claim that a prompt enforces them. When the user requires enforced isolation, this interface alone does not establish it.

## OMP task and hub

Installed source root: `~/.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent/` (18.1.18 in the inspected installation).

- Launch through `task` using the advertised flat or batch schema. `src/task/types.ts` selects schema by runtime settings; batch form has `context` and `tasks`, flat form has `agent` and `task`. Do not assume a `background`, `resume`, or `model` field exists. Use a suitable available agent definition and its configured model/effort routing. Explicit unavailable model choices are reported, not silently remapped.
- `src/task/index.ts` returns both agent ID and registered job ID for background jobs. The native job ID is the canonical status/result/cancel identity; retain its native agent-ID mapping for messaging. They can differ on collision. `hub jobs` exposes `agentUrlId` for that native mapping (`src/tools/hub/types.ts`). This is native metadata, not a second application job registry.
- Status: `hub` with `op: "jobs"`; select the exact native job ID from returned rows. `op: "list"` lists addressable agents and their running/idle/parked states. Visibility is session-scoped; not-found does not prove termination elsewhere.
- Result/wait: `hub` with `op: "wait", ids: [exactJobId], timeoutMs: 30000`, or the existing delivered result. Completion can auto-deliver on yield; a settled jobs/wait snapshot can consume that delivery. Preserve `resultText`, `errorText`, `structured`, and referenced artifacts from the same job. Do not duplicate work because one delivery channel was already consumed.
- Follow-up: `hub` with `op: "send", to: exactAgentId, message: ...`. Peer messaging wakes idle/parked workers when enabled. Resolve the native mapping before sending. If peer messaging is unavailable, disclose that specific limit; do not guess a resume flag on `task`.
- Cancel: `hub` with `op: "cancel", ids: [exactJobId]`; inspect the returned cancelled/not_found/already_completed outcome. Do not use process `stop`, `name`, or `signal` to cancel an agent job.
- Read-only classification is based on the agent definition's tool list (`src/task/read-only-policy.ts`). The bundled `reviewer` has bash/lsp and is not classified read-only by that policy; the bundled `scout` has read/grep/glob/web_search and uses a smaller model. Choose judgment and permissions deliberately. Task's optional `tools` field is for eval-defined tools, not a general replacement allowlist. Do not claim it strips a reviewer's mutation tools. Prompt-bound review remains no-write, and enforced isolation requires a separately verified suitable native definition.
- `hub` may report async or peer messaging disabled. Report the affected lifecycle operations as unavailable in that runtime. Do not construct a detached process or custom polling store to mimic native support.

## CC vendor boundary

CC's selected `openai-codex/codex` plugin owns `/codex:*` commands and its job state. The inspected source is `~/.claude/plugins/cache/openai-codex/codex/1.0.6/commands/`. Resolve the enabled source via current plugin metadata rather than assuming this cache path forever. Retain its native commands in CC. The native adapter above applies to Codex/OMP; it does not rename vendor job IDs, import the vendor job store, or reimplement stop-review-gate hooks.

## Verification boundary

Source inspection establishes schemas and intended lifecycle behavior. This adapter still needs an operational review → status → result → exact follow-up test and a separate exact-job interruption test in each enabled host. No live worker was launched as part of authoring this file. Do not mark native continuity verified from file discovery alone.
