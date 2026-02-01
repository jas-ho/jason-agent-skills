# jason-agent-skills

Miscellaneous LLM agent skills.

## Installation

```bash
/plugin marketplace add jas-ho/jason-agent-skills
/plugin install <skill-name>@jason-agent-skills
```

## Available Skills

| Skill | Description | Requirements |
|-------|-------------|--------------|
| [weather](plugins/weather) | Weather forecasts with cloud cover, wind, precipitation. Auto-selects best model (ICON-D2 for Alps, global elsewhere). | [jq](https://jqlang.github.io/jq/), curl |
| [skitour](plugins/skitour) | Ski touring conditions for Austrian Alps - avalanche danger, snow depth, and weather combined. | [Bash 4.0+](https://www.gnu.org/software/bash/), [jq](https://jqlang.github.io/jq/), curl, [uv](https://github.com/astral-sh/uv) |
| [safe-commit](plugins/safe-commit) | Code quality validation with auto-fixes before git commits. | [ruff](https://github.com/astral-sh/ruff), [mypy](https://mypy-lang.org/), [shellcheck](https://www.shellcheck.net/), [markdownlint](https://github.com/DavidAnson/markdownlint) (all optional) |
| [archive-analysis](plugins/archive-analysis) | Archive temporary analysis files to git history while keeping working tree clean. | [uv](https://github.com/astral-sh/uv) |
| [spotlight-search](plugins/spotlight-search) | macOS Spotlight search (mdfind) for fast file discovery across PDFs, Office docs, plain text. | macOS, [pdftotext](https://poppler.freedesktop.org/) (optional) |
| [publish-code](plugins/publish-code) | Guide a repo from private to public - license, portability audit, GitHub visibility. | [gh](https://cli.github.com/), [gitleaks](https://github.com/gitleaks/gitleaks) (optional) |

## License

MIT
