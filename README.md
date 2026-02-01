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
| [weather](plugins/weather) | Weather forecasts with cloud cover, wind, precipitation. Auto-selects best model (ICON-D2 for Alps, global elsewhere). | [jq](https://jqlang.org/), [curl](https://curl.se/) |
| [skitour](plugins/skitour) | Ski touring conditions for Austrian Alps - avalanche danger, snow depth, and weather combined. | [Bash 4.0+](https://www.gnu.org/software/bash/), [jq](https://jqlang.org/), [curl](https://curl.se/), [uv](https://github.com/astral-sh/uv) |
| [safe-commit](plugins/safe-commit) | Code quality validation with auto-fixes before git commits. | [ruff](https://github.com/astral-sh/ruff), [mypy](https://mypy-lang.org/), [shellcheck](https://www.shellcheck.net/), [markdownlint](https://github.com/DavidAnson/markdownlint) (all optional) |
| [archive-analysis](plugins/archive-analysis) | Archive temporary analysis files to git history while keeping working tree clean. | [uv](https://github.com/astral-sh/uv) |
| [spotlight-search](plugins/spotlight-search) | macOS Spotlight search (mdfind) for fast file discovery across PDFs, Office docs, plain text. | macOS, [pdftotext](https://formulae.brew.sh/formula/poppler) (optional) |
| [publish-code](plugins/publish-code) | Guide a repo from private to public - license, portability audit, GitHub visibility. | [gh](https://cli.github.com/), [gitleaks](https://github.com/gitleaks/gitleaks), [typos](https://github.com/crate-ci/typos), [lychee](https://lychee.cli.rs/), [markdownlint](https://github.com/DavidAnson/markdownlint) |

## License

MIT
