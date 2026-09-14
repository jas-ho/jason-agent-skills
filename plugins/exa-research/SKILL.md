---
name: exa-research
description: Research using the selected Exa search and fetch integration, including multi-angle literature, company, people, and competitive research. Use when Exa research is requested or selected; preserve Exa-only retrieval and report missing access.
---

# Exa research

This is a shared orchestration adapter. The installed Exa vendor package supplies its query, extraction, filtering, synthesis, and source-quality documentation; its MCP connection can be disabled when the host uses a direct Exa connection. Resolve its actual installed source via the host's plugin/workflow inventory; the audited Mac source is `~/.claude/plugins/cache/exa/exa/3.3.8/skills/search/`. Read its `references/searching.md` and only the other references needed for the task. Do not copy vendor internals or treat that cache version as a permanent portable install location. If vendor documentation is unavailable, report the dependency rather than silently choosing a different research workflow.

Use only the advertised Exa search and fetch operations corresponding to `web_search_exa` and `web_fetch_exa`, with the actual native tool names and schema. Do not call advanced search, an autonomous research endpoint, generic web search, browser scraping, curl, or another fetch service to bypass this workflow. Vendor suggestions to use another fetch tool do not apply to this adapter. Native filesystem tools may read instructions or write the requested report; they are not alternative web retrieval tools.

Discover the tools before launching workers. Missing tools, auth failures and rate limits are distinct blockers: report which occurred and use the supported existing setup path. Do not copy keys/tokens or invent a query-string credential. New account/login consent belongs to the user. Do not substitute generic web search when Exa access fails. A tool appearing in the catalog is not proof that authentication succeeded.

Use the requested depth. A single page or narrow query can stay in the parent. For independent substantial search territories, use the host's native workers (Codex collaboration, OMP task/hub, CC native agent tool) when delegation is available and authorized. Select the actual available model using the host's model-routing guidance: inexpensive workers for mechanical extraction; stronger reasoning for relevance judgments, technical evidence, and synthesis. Do not require Claude's `haiku` alias in another harness, invent a background flag, or launch workers that lack Exa access.

Give each worker its subquestion, qualification criteria, needed fields, absolute paths to the relevant vendor references, date bounds, allowed Exa tools, and compact return format with source URLs. Keep exact native job IDs for follow-ups. If native workers are unavailable, do a bounded serial Exa pass and disclose the limitation; do not launch a second CLI merely for isolation.

Calculate relative date bounds using the host's date tools. Define qualification criteria and output fields before broad searches. Search across distinct angles, fetch promising sources when snippets cannot establish a claim, verify dates and hard constraints, merge duplicate URLs/entities, and distinguish unverified candidates from qualifying results. Do not claim completeness when Exa access, coverage or the requested number remains short. Return sources beside factual claims and explain material coverage gaps.
