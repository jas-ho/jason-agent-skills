#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Mechanical audit for publish-code skill.
Uses external tools for quality checks - no DIY patterns.
Returns JSON for Claude to review and act on.

Required: gitleaks, typos, lychee, markdownlint, gh
Install: brew install gitleaks typos-cli lychee markdownlint-cli gh

Config: .markdownlint.json in skill dir provides sensible defaults.
Uses project's config if present, otherwise falls back to skill config.

Limits: Scans first 300 tracked files, skips files >200KB.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_TOOLS = ["gitleaks", "typos", "lychee", "markdownlint", "gh"]


def check_tools() -> list[str]:
    """Check for required external tools."""
    return [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]


def get_tracked_files(repo_path: Path) -> list[str]:
    """Get list of git-tracked files."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=repo_path, capture_output=True, text=True
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def scan_secrets(repo_path: Path) -> list[dict]:
    """Use gitleaks to scan for secrets in git history."""
    result = subprocess.run(
        ["gitleaks", "detect", "--source", str(repo_path), "--report-format", "json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode not in (0, 1):
        return [{"error": f"gitleaks failed: {result.stderr}"}]
    if not result.stdout.strip():
        return []

    return [
        {
            "file": f.get("File", "unknown"),
            "line": f.get("StartLine", 0),
            "type": f.get("Description", f.get("RuleID", "secret")),
        }
        for f in json.loads(result.stdout)
    ]


def scan_typos(repo_path: Path) -> list[dict]:
    """Use typos to find spelling mistakes."""
    result = subprocess.run(
        ["typos", "--format", "json", str(repo_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode not in (0, 2):
        return [{"error": f"typos failed: {result.stderr}"}]
    if not result.stdout.strip():
        return []

    issues = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            f = json.loads(line)
            if f.get("type") == "typo":
                issues.append(
                    {
                        "file": f.get("path", "unknown"),
                        "line": f.get("line_num", 0),
                        "typo": f.get("typo", ""),
                        "corrections": f.get("corrections", []),
                    }
                )
        except json.JSONDecodeError:
            continue
    return issues


def scan_links(repo_path: Path) -> list[dict]:
    """Use lychee to check links in markdown files."""
    result = subprocess.run(
        ["lychee", "--format", "json", "--no-progress", str(repo_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    # lychee exits 0 if all ok, 1 if issues, 2 if errors
    if result.returncode not in (0, 1, 2):
        return [{"error": f"lychee failed: {result.stderr}"}]
    if not result.stdout.strip():
        return []

    try:
        data = json.loads(result.stdout)
        issues = []
        for file, errors in data.get("error_map", {}).items():
            for err in errors:
                issues.append(
                    {
                        "file": file,
                        "url": err.get("url", ""),
                        "status": err.get("status", {}).get("code", 0),
                        "error": err.get("status", {}).get("text", "unknown"),
                    }
                )
        return issues
    except json.JSONDecodeError:
        return [{"error": "Failed to parse lychee output"}]


def fix_markdown(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Run markdownlint --fix and return unfixable issues."""
    md_files = [str(repo_path / f) for f in tracked_files if f.endswith(".md")]
    if not md_files:
        return []

    # Use project config if exists, otherwise use skill's relaxed defaults
    cmd = ["markdownlint", "--fix"]
    project_configs = [".markdownlint.json", ".markdownlintrc", ".markdownlint.yaml"]
    if not any((repo_path / c).exists() for c in project_configs):
        # Use skill's default config (disables noisy style rules)
        skill_config = Path(__file__).parent / ".markdownlint.json"
        if skill_config.exists():
            cmd.extend(["--config", str(skill_config)])

    result = subprocess.run(
        cmd + md_files,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Exit 0 = all fixed, Exit 1 = unfixable issues remain
    if result.returncode == 0:
        return []

    # Parse stderr for remaining issues (format: "file:line rule description")
    issues = []
    for line in result.stderr.strip().split("\n"):
        if not line or "error" not in line.lower():
            continue
        # Example: "README.md:15:9 error MD060/table-column-style ..."
        match = re.match(r"(.+?):(\d+):\d+ error (\S+)", line)
        if match:
            issues.append(
                {
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "rule": match.group(3),
                    "message": line,
                }
            )
    return issues


def scan_hardcoded_paths(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find hardcoded user paths that break portability."""
    issues = []
    patterns = [
        (r"/Users/[a-zA-Z0-9_-]+/", "macOS user path"),
        (r"/home/[a-zA-Z0-9_-]+/", "Linux user path"),
        (r"C:\\Users\\[a-zA-Z0-9_-]+\\", "Windows user path"),
    ]
    skip_ext = {
        ".png",
        ".jpg",
        ".gif",
        ".ico",
        ".woff",
        ".ttf",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
    }

    for file_path in tracked_files[:300]:
        full_path = repo_path / file_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.suffix.lower() in skip_ext or full_path.stat().st_size > 200000:
            continue

        try:
            content = full_path.read_text(errors="ignore")
            for pattern, desc in patterns:
                for line_num, line in enumerate(content.split("\n"), 1):
                    if re.search(pattern, line):
                        issues.append(
                            {
                                "file": file_path,
                                "line": line_num,
                                "type": desc,
                                "sample": line.strip()[:100],
                            }
                        )
                        break
                else:
                    continue
                break
        except Exception:
            continue
    return issues


def get_git_identity(repo_path: Path) -> list[str]:
    """Get user's git identity patterns to search for."""
    patterns = []
    for key in ["user.name", "user.email"]:
        result = subprocess.run(
            ["git", "config", key], cwd=repo_path, capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            value = result.stdout.strip()
            patterns.append(value)
            # Extract username from email (before @)
            if "@" in value:
                patterns.append(value.split("@")[0])
    return [p for p in patterns if len(p) > 2]  # Skip very short patterns


def scan_personal_refs(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find references to user's git identity (name, email, username)."""
    patterns = get_git_identity(repo_path)
    if not patterns:
        return []

    issues = []
    skip_ext = {".png", ".jpg", ".gif", ".pdf", ".zip", ".gz", ".tar", ".lock"}
    skip_files = {"LICENSE", "LICENCE", "CHANGELOG.md", ".git"}

    for file_path in tracked_files[:300]:
        if any(skip in file_path for skip in skip_files):
            continue
        full_path = repo_path / file_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.suffix.lower() in skip_ext or full_path.stat().st_size > 200000:
            continue

        try:
            content = full_path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.lower() in content.lower():
                    issues.append({"file": file_path, "pattern": pattern})
                    break  # One issue per file
        except Exception:
            continue

    return issues


def check_basics(repo_path: Path) -> dict:
    """Check for basic required files."""
    return {
        "has_license": bool(
            list(repo_path.glob("LICENSE*")) + list(repo_path.glob("LICENCE*"))
        ),
        "has_readme": bool(list(repo_path.glob("README*"))),
        "has_contributing": bool(list(repo_path.glob("CONTRIBUTING*"))),
        "has_gitignore": (repo_path / ".gitignore").exists(),
    }


def main():
    repo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    missing = check_tools()
    if missing:
        print(
            json.dumps(
                {
                    "error": f"Missing required tools: {', '.join(missing)}",
                    "install": "brew install gitleaks typos-cli lychee markdownlint-cli",
                }
            )
        )
        sys.exit(1)

    if not repo_path.exists():
        print(json.dumps({"error": f"Path does not exist: {repo_path}"}))
        sys.exit(1)

    if not (repo_path / ".git").exists():
        print(json.dumps({"error": f"Not a git repository: {repo_path}"}))
        sys.exit(1)

    tracked_files = get_tracked_files(repo_path)

    result = {
        "repo_path": str(repo_path),
        "repo_name": repo_path.name,
        "files_checked": len(tracked_files[:300]),
        "basics": check_basics(repo_path),
        "secrets": scan_secrets(repo_path),
        "typos": scan_typos(repo_path),
        "broken_links": scan_links(repo_path),
        "markdown_unfixable": fix_markdown(repo_path, tracked_files),
        "hardcoded_paths": scan_hardcoded_paths(repo_path, tracked_files),
        "personal_refs": scan_personal_refs(repo_path, tracked_files),
    }

    result["has_blockers"] = bool(result["secrets"])
    result["needs_review"] = bool(
        result["hardcoded_paths"]
        or result["broken_links"]
        or result["typos"]
        or result["markdown_unfixable"]
        or result["personal_refs"]
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
