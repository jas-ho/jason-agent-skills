---
name: reading-list
description: Build, edit or deploy a reading list on reader.jasho.fyi (instances in ~/Code/reader-lists, engine ~/Code/reader, hosting via ~/Code/vps-setup). Use when creating a list, adding or rewriting readings, writing descriptions, adding deep links (jumps), changing the reader engine, or deploying a list. Not for reading the lists or for unrelated static sites.
---

# Reading lists on reader.jasho.fyi

This skill routes; it does not repeat the details. Each topic has one owner:

| Topic | Source of truth |
| --- | --- |
| Fields, rendering, jumps syntax | `~/Code/reader/docs/model.md` (read the version the instance pins) |
| How to write the fields well | `~/Code/reader/docs/writing.md` |
| Workflow, tools, prompts, jump checks | `~/Code/reader-lists/tools/README.md` |
| Hosting conventions, `lists.json` index | `~/Code/reader-lists/README.md` |
| One list's standing rules, ids, limitations, releases | that instance's `README.md` |
| What was verified and how | that instance's `source-checks.md` |
| Deploys and release records | this skill |

Read the instance README and `tools/README.md` before changing content. If two sources disagree, stop and tell Jason rather than picking one.

## Guardrails

- Deploys, kvd, Caddy or DNS changes, and anything shared with list readers need Jason's explicit OK in the current session. Show the change first (screenshots for anything visible).
- `~/Code/reader` is public: no hosts, private lists, people or credentials there.
- Never print or transmit sync secrets. Never `rm`; use `trash`.
- Research behind a list may belong to another project (the instance's `source-checks.md` names it). Read it and corroborate read-only; send corrections to that project instead of editing its files. If facts for a reading cannot be verified, leave that reading out and say so.

## New list

1. New folder in `~/Code/reader-lists`: `list.json` with a new list `id`; `config.json` with a new `sync.site`, no `importFrom`, no copied `storageKey` or compatibility file, `"homeLink": {"label": "All lists", "url": "/"}` (shape in the repository README).
2. Pin a committed reader that supports every field used: `git -C ~/Code/reader rev-parse HEAD > <instance>/reader-version`.
3. Add the list to `lists.json`; write the instance README (purpose, standing rules, id table) and `source-checks.md`.
4. Content per `tools/README.md`.

## Engine changes

Follow `~/Code/reader/AGENTS.md` (reviews, checks, docs and examples in the same commit). Push only with Jason's OK; instances then pin the new commit.

## Deploy and record (after Jason's OK)

1. Commit the instance, and push the reader commit it pins if that is new. All three trees must be clean.
2. `cd ~/Code/vps-setup && uv run services/static-sites/reader/deploy.py --reader ../reader --instance ../reader-lists/<instance> --slug <slug> --deploy` (frontier-ai: `--instance services/static-sites/reader/instance --slug frontier-ai`, then push vps-setup). After a new list's first deploy, or when its `lists.json` entry changes, redeploy the index from the same directory: `uv run services/static-sites/reader/deploy.py --index ../reader-lists/lists.json --deploy`, and add its release line under "Index releases" in `~/Code/reader-lists/README.md`.
3. Live check at phone size, light and dark: no page errors, no horizontal overflow, contents sheet opens; `uv run tools/check_jumps.py <instance>/list.json` if links changed.
4. Add a release line to the instance README: date, reader commit, what changed, the release ID printed by deploy.py, and "Roll back with `--rollback <that release ID>`" (rollback takes the release that is live and restores the one before it). Commit.
5. Rollback: `uv run services/static-sites/reader/deploy.py --slug <slug> --rollback <live release ID>` (index: `--rollback index-…` without `--slug`); it restores the release before the live one. Then add a line saying which release was rolled back and which one is live again, so the last line always names the live release. Checks, server-side records and the live test: `~/Code/vps-setup/services/static-sites/reader/README.md`.
