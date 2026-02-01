# jason-agent-skills

Miscellaneous LLM agent skills.

## Installation

```bash
/plugin marketplace add jas-ho/jason-agent-skills
/plugin install <skill-name>@jason-agent-skills
```

## Available Skills

| Skill | Description |
|-------|-------------|
| weather | Weather forecasts with cloud cover, wind, precipitation. Auto-selects best model (ICON-D2 for Alps, global elsewhere). |
| skitour | Ski touring conditions for Austrian Alps - avalanche danger, snow depth, and weather combined. |
| safe-commit | Code quality validation (ruff, mypy, shellcheck, markdownlint) with auto-fixes before git commits. |
| archive-analysis | Archive temporary analysis files to git history while keeping working tree clean. |
| spotlight-search | macOS Spotlight search (mdfind) for fast file discovery across PDFs, Office docs, plain text. |
| publish-code | Guide a repo from private to public - license, portability audit, GitHub visibility. |

## Requirements

- **macOS** (required for spotlight-search; other skills work cross-platform)
- **Bash 4.0+** for skitour (`brew install bash` on macOS)
- **jq**, **curl** for weather and skitour
- Various linters for safe-commit (ruff, mypy, shellcheck, markdownlint - optional, validates what's available)

## License

MIT
