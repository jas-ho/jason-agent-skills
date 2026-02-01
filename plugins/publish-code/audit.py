#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Mechanical audit for publish-code skill.
Catches things that are hard to spot manually: hardcoded paths, potential secrets.
Returns JSON for Claude to review and act on.
"""

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse


def get_tracked_files(repo_path: Path) -> list[str]:
    """Get list of git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "ls-files"], cwd=repo_path, capture_output=True, text=True
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []


def scan_hardcoded_paths(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find hardcoded user paths that break portability."""
    issues = []

    path_patterns = [
        (r"/Users/[a-zA-Z0-9_-]+/", "macOS user path"),
        (r"/home/[a-zA-Z0-9_-]+/", "Linux user path"),
        (r"C:\\Users\\[a-zA-Z0-9_-]+\\", "Windows user path"),
    ]

    skip_extensions = {
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
        if full_path.suffix.lower() in skip_extensions:
            continue
        if full_path.stat().st_size > 200000:  # Skip files > 200KB
            continue

        try:
            content = full_path.read_text(errors="ignore")
            for pattern, desc in path_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    # Get a sample line for context
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
                    break  # One issue per file
        except Exception:
            continue

    return issues


def scan_secrets_gitleaks(repo_path: Path) -> list[dict] | None:
    """Use gitleaks for comprehensive secret detection. Returns None if not available."""
    try:
        result = subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                str(repo_path),
                "--report-format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # gitleaks exits 1 if secrets found, 0 if clean
        if result.returncode not in (0, 1):
            return None

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
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


def scan_secrets_fallback(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Fallback: simple patterns when gitleaks unavailable."""
    issues = []

    secret_patterns = [
        (r"sk-ant-[a-zA-Z0-9-_]{90,}", "Anthropic API key"),
        (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key"),
        (r"sk-proj-[a-zA-Z0-9-_]{80,}", "OpenAI project API key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
        (r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}", "GitHub fine-grained PAT"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
        (r"xoxb-[0-9]{11}-[0-9]{11}-[a-zA-Z0-9]{24}", "Slack bot token"),
        (r"xoxp-[0-9]{11}-[0-9]{11}-[a-zA-Z0-9]{24}", "Slack user token"),
        (r"-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----", "Private key"),
    ]

    skip_extensions = {
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
        ".lock",
    }

    for file_path in tracked_files[:300]:
        full_path = repo_path / file_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.suffix.lower() in skip_extensions:
            continue
        if full_path.stat().st_size > 200000:
            continue

        try:
            content = full_path.read_text(errors="ignore")
            for pattern, desc in secret_patterns:
                if re.search(pattern, content):
                    issues.append({"file": file_path, "type": desc, "severity": "HIGH"})
                    break
        except Exception:
            continue

    return issues


def scan_potential_secrets(
    repo_path: Path, tracked_files: list[str]
) -> tuple[list[dict], str]:
    """Scan for secrets using gitleaks (preferred) or fallback patterns."""
    gitleaks_result = scan_secrets_gitleaks(repo_path)
    if gitleaks_result is not None:
        return gitleaks_result, "gitleaks"
    return scan_secrets_fallback(repo_path, tracked_files), "fallback"


def scan_org_references(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Find Apart Research and other org-specific references."""
    issues = []

    patterns = [
        (r"Apart\s*Research", "Apart Research reference"),
        (r"apartresearch", "apartresearch reference"),
        (r"@apartresearch\.com", "Apart email"),
        (r"notion\.so/[a-f0-9-]{32,}", "Notion page/database ID"),
    ]

    skip_extensions = {
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
        ".lock",
    }
    skip_files = {"CHANGELOG.md", "LICENSE", ".git"}

    for file_path in tracked_files[:200]:
        if any(skip in file_path for skip in skip_files):
            continue
        full_path = repo_path / file_path
        if not full_path.exists() or not full_path.is_file():
            continue
        if full_path.suffix.lower() in skip_extensions:
            continue
        if full_path.stat().st_size > 100000:
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

        # Check if redirected to different domain
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
    """Extract and check links from markdown files in parallel."""
    # Extract URLs from markdown files
    url_pattern = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")
    urls_found: dict[str, str] = {}  # url -> first file found in

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

    # Check URLs in parallel (max 10 concurrent)
    issues = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(check_link, url): url for url in urls_found}
        for future in as_completed(future_to_url):
            result = future.result()
            if result["issue"]:
                result["file"] = urls_found[result["url"]]
                issues.append(result)

    return issues


def scan_typos(repo_path: Path, tracked_files: list[str]) -> list[dict]:
    """Check for common transcription typos in documentation."""
    issues = []

    # Common voice transcription errors: split tool names
    typo_patterns = [
        (r"\bshell\s+check\b", "shellcheck"),
        (r"\bgit\s+hub\b", "GitHub"),
        (r"\bgit\s+lab\b", "GitLab"),
        (r"\bj\s+q\b", "jq"),
        (r"\bp\s+d\s+f\b", "pdf"),
        (r"\bc\s+l\s+i\b", "CLI"),
        (r"\ba\s+p\s+i\b", "API"),
        (r"\bu\s+r\s+l\b", "URL"),
    ]

    for file_path in tracked_files:
        if not file_path.endswith((".md", ".rst", ".txt")):
            continue
        full_path = repo_path / file_path
        if not full_path.exists() or full_path.stat().st_size > 100000:
            continue
        try:
            content = full_path.read_text(errors="ignore")
            for pattern, correct in typo_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append(
                        {
                            "file": file_path,
                            "pattern": pattern,
                            "suggestion": correct,
                        }
                    )
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
        "has_issue_templates": (repo_path / ".github" / "ISSUE_TEMPLATE").exists(),
    }


def main():
    repo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    if not repo_path.exists():
        print(json.dumps({"error": f"Path does not exist: {repo_path}"}))
        sys.exit(1)

    if not (repo_path / ".git").exists():
        print(json.dumps({"error": f"Not a git repository: {repo_path}"}))
        sys.exit(1)

    tracked_files = get_tracked_files(repo_path)

    secrets, scanner_used = scan_potential_secrets(repo_path, tracked_files)

    # Run link checks in parallel with other scans
    link_issues = scan_links(repo_path, tracked_files)

    result = {
        "repo_path": str(repo_path),
        "repo_name": repo_path.name,
        "files_checked": len(tracked_files[:300]),
        "basics": check_basics(repo_path),
        "hardcoded_paths": scan_hardcoded_paths(repo_path, tracked_files),
        "potential_secrets": secrets,
        "secrets_scanner": scanner_used,
        "org_references": scan_org_references(repo_path, tracked_files),
        "broken_links": link_issues,
        "typos": scan_typos(repo_path, tracked_files),
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
