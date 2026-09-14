---
name: obsidian-cli
description: Command reference for the `obsidian` CLI (link-updating moves/renames, base queries, properties, backlinks, search, tasks). Load before composing any obsidian command.
---

# Obsidian CLI Reference

For reading/writing file contents, prefer the active harness's native file tools (faster, no Obsidian dependency). Use `obsidian` for Obsidian-aware operations. If the CLI or running Obsidian app is unavailable on this host, report the missing dependency; ordinary file reads and writes can still use native tools.

## Key commands

```bash
# Move/rename (updates all wiki-links vault-wide)
obsidian move path="old/path/file.md" to="new/path/"
obsidian rename path="old/name.md" name="new-name"

# Bases (structured queries over vault databases)
obsidian bases                                          # list available .base files
obsidian base:query file="Projects.base" format=tsv     # tabular results
obsidian base:query file="Projects.base" format=paths   # just file paths

# Properties (frontmatter)
obsidian property:read name="status" path="work/foo/README.md"
obsidian property:set name="status" value="completed" path="work/foo/README.md"

# Links
obsidian backlinks path="work/foo/README.md"            # incoming links
obsidian links path="work/foo/README.md"                # outgoing links

# Search (uses Obsidian search syntax, NOT plain text grep)
obsidian search query="keyword" limit=10
obsidian search:context query="keyword" limit=5         # with line context

# Tasks
obsidian tasks todo                                     # incomplete tasks vault-wide
```

## Conventions

- **`file=` vs `path=`**: `file=` resolves by name like wiki-links (any matching file). `path=` is exact vault-relative path. Prefer `path=` for precision.
- **Quoting**: values with spaces must be quoted: `query="my search term"`
- **Search syntax**: `obsidian search` uses Obsidian's search operators, not plain text. For simple text search, use the active harness's text search tool instead.
- **Output formats**: most list commands support `format=json|tsv|csv`. Bases also support `format=md|paths`.
- **Full reference**: `obsidian help` for all commands, `obsidian help <command>` for details.
