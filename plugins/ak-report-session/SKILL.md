---
name: ak-report-session
description: Analyze an explicitly identified CC, Codex, or OMP JSONL session for tool counts, recorded timings, and performance problems using the external Apart Kit reporting workflow. Produces a local report and never sends it.
---

# Apart Kit session report adapter

Apart Kit owns the reporting workflow. Read its external command at the configured apart-kit root, currently `~/Code/apart-kit/commands/report-session.md`. Keep it external and unchanged. Apply the schema and delivery corrections below instead of its CC-only path/layout and duration assumptions.

Identify the exact requested session from the owning runtime's session ID/transcript path, or an explicit user selection. Never select the latest file automatically. Current layouts include CC `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`, Codex `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, and OMP `~/.omp/agent/sessions/<encoded-cwd>/*.jsonl`; layouts are discovery hints, not proof of ownership. Confirm the file's header/session metadata where present. Do not infer a session ID from a model nickname.

Run the bundled metadata-only parser with the actual loaded skill directory:

```bash
python3 "<skill-dir>/scripts/session_metrics.py" /absolute/selected-session.jsonl --harness auto
```

It reads the selected file and prints JSON metrics; it does not export prompt/tool output text, run tools, traverse child transcripts, or send anything. Read [references/transcript-formats.md](references/transcript-formats.md) to interpret its fields, limitations and supported structures. Preserve malformed-line counts, missing timings and failure signals honestly. File-span elapsed time includes idle time and copied history; call-to-result elapsed time includes scheduling and batching. Neither is actual tool execution time. Do not rank bottlenecks by fabricated durations.

Summarize the observed tool counts, explicit timed completion records when present, unmatched calls/results, malformed records and recorded error flags. Codex shell/MCP completion events are reported separately from top-level tool call counts to avoid counting an event mirror twice or pretending nested functions.exec operations are all individually visible. Subagent launch counts are launch operations, not verified child-session counts or durations. Analyze an explicitly selected child transcript separately when needed.

Use context already provided about what the user was trying to do; ask only for material missing context after producing the local analysis. To diagnose a specific failure, inspect the minimum relevant transcript excerpt locally; do not paste raw transcripts or credentials into a report. Explain when a active/growing transcript snapshot is partial.

Produce the report in the current authorized workspace or conversation. This adapter never sends mail, uploads a transcript, or attaches the file. The vendor's send step is outside this adapter. If the user later explicitly requests delivery, use the appropriate separately authorized communication workflow and its current recipient/content scope.
