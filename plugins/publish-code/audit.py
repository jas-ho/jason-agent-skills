#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Mechanical audit for publish-code skill.
Uses external tools (gitleaks, typos) for quality checks.
Returns JSON for Claude to review and act on.

Required tools: gitleaks, typos (install via brew)
"""

import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_TOOLS = ["gitleaks", "typos"]


def check_tools() -> list[str]:
    """Check for required external tools."""
    missing = [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]
    return missing


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
    # gitleaks exits 1 if secrets found, 0 if clean
    if result.returncode not in (0, 1):
        return [{"error": f"gitleaks failed: {result.stderr}"}]

    if not result.stdout.strip():
        return []

    findings = json.loads(result.stdout)
    return [
        {
            "file": f.get("File", "unknown"),
            "line": f.get("StartLine", 0),
            "type": f.get("Description", f.get("RuleID", "secret")),
            "severity": "HIGH",
        }
        for f in findings
    ]


def scan_typos(repo_path: Path) -> list[dict]:
    """Use typos to find spelling mistakes in code and docs."""
    result = subprocess.run(
        ["typos", "--format", "json", str(repo_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # typos exits 2 if typos found, 0 if clean
    if result.returncode not in (0, 2):
        return [{"error": f"typos failed: {result.stderr}"}]

    if not result.stdout.strip():
        return []

    # typos outputs one JSON object per line
    issues = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            finding = json.loads(line)
            if finding.get("type") == "typo":
                issues.append(
                    {
                        "file": finding.get("path", "unknown"),
                        "line": finding.get("line_num", 0),
                        "typo": finding.get("typo", ""),
                        "corrections": finding.get("corrections", []),
                    }
                )
        except json.JSONDecodeError:
            continue

    return issues


def scan_hardcoded_paths(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find hardcoded user paths that break portability."""
    issues = []
    path_patterns = [
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
            for pattern, desc in path_patterns:
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


def scan_org_references(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find org-specific references (Apart Research, Notion IDs, etc.)."""
    issues = []
    patterns = [
        (r"Apart\s*Research", "Apart Research reference"),
        (r"apartresearch", "apartresearch reference"),
        (r"@apartresearch\.com", "Apart email"),
        (r"notion\.so/[a-f0-9-]{32,}", "Notion page/database ID"),
    ]
    skip_ext = {".png", ".jpg", ".gif", ".pdf", ".zip", ".gz", ".tar", ".lock"}
    skip_files = {"CHANGELOG.md", "LICENSE", ".git"}

    for file_path in tracked_files[:200]:
        if any(skip in file_path for skip in skip_files):
            continue
        full_path = repo_path / file_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.suffix.lower() in skip_ext or full_path.stat().st_size > 100000:
            continue

        try:
            content = full_path.read_text(errors="ignore")
            for pattern, desc in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append({"file": file_path, "type": desc})
                    break
        except Exception:
            continue

    return issues


def check_link(url: str, timeout: int = 10) -> dict:
    """Check a single URL, return status info."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-sI",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code} %{redirect_url}",
                "-L",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        parts = result.stdout.strip().split(" ", 1)
        status = int(parts[0]) if parts[0].isdigit() else 0
        final_url = parts[1] if len(parts) > 1 else ""

        original_domain = urlparse(url).netloc
        final_domain = urlparse(final_url).netloc if final_url else original_domain

        if status >= 400:
            return {"url": url, "status": status, "issue": "error"}
        elif final_domain and final_domain != original_domain:
            return {
                "url": url,
                "status": status,
                "issue": "redirect",
                "final_url": final_url,
            }
        return {"url": url, "status": status, "issue": None}
    except subprocess.TimeoutExpired:
        return {"url": url, "status": 0, "issue": "timeout"}
    except Exception as e:
        return {"url": url, "status": 0, "issue": str(e)}


def scan_links(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Check links from markdown files in parallel."""
    url_pattern = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")
    urls_found: dict[str, str] = {}

    for file_path in tracked_files:
        if not file_path.endswith((".md", ".rst", ".txt")):
            continue
        full_path = repo_path / file_path
        if not full_path.exists() or full_path.stat().st_size > 100000:
            continue
        try:
            content = full_path.read_text(errors="ignore")
            for match in url_pattern.finditer(content):
                url = match.group(2)
                if url not in urls_found:
                    urls_found[url] = file_path
        except Exception:
            continue

    if not urls_found:
        return []

    issues = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(check_link, url): url for url in urls_found}
        for future in as_completed(future_to_url):
            result = future.result()
            if result["issue"]:
                result["file"] = urls_found[result["url"]]
                issues.append(result)

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

    # Check required tools
    missing = check_tools()
    if missing:
        print(
            json.dumps(
                {
                    "error": f"Missing required tools: {', '.join(missing)}",
                    "install": "brew install " + " ".join(missing),
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

    # Run scans
    secrets = scan_secrets(repo_path)
    typos = scan_typos(repo_path)
    link_issues = scan_links(repo_path, tracked_files)

    result = {
        "repo_path": str(repo_path),
        "repo_name": repo_path.name,
        "files_checked": len(tracked_files[:300]),
        "basics": check_basics(repo_path),
        "secrets": secrets,
        "typos": typos,
        "hardcoded_paths": scan_hardcoded_paths(repo_path, tracked_files),
        "org_references": scan_org_references(repo_path, tracked_files),
        "broken_links": link_issues,
    }

    # Summary flags
    result["has_blockers"] = bool(secrets)
    result["needs_review"] = bool(
        result["hardcoded_paths"]
        or result["org_references"]
        or result["broken_links"]
        or result["typos"]
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
