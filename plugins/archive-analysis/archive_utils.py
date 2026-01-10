#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

"""Archive analysis utilities for repository cleanup.

Discovers and analyzes files for archiving, providing rich context for
intelligent agent decisions.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import typer
except ImportError:
    print(
        "Error: typer not available. Running with uv should handle this.",
        file=sys.stderr,
    )
    sys.exit(1)

app = typer.Typer(help="Archive analysis utilities for repository cleanup")


def run_command(cmd: list[str], cwd: str | None = None) -> tuple[str, int]:
    """Run a shell command and return output and return code."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return f"Error: {e}", 1


def discover_untracked_markdown(repo_root: str) -> list[str]:
    """Find all untracked markdown files."""
    output, returncode = run_command(["git", "status", "--porcelain"], cwd=repo_root)

    if returncode != 0:
        return []

    untracked = []
    for line in output.split("\n"):
        if line.startswith("??") and line.endswith(".md"):
            # Extract filename (skip the ?? and whitespace)
            filepath = line[3:].strip()
            untracked.append(filepath)

    return untracked


def discover_all_markdown(repo_root: str) -> list[str]:
    """Find all markdown files in repo (for explore mode)."""
    output, returncode = run_command(["git", "ls-files", "*.md"], cwd=repo_root)

    if returncode != 0:
        return []

    tracked = [f for f in output.split("\n") if f]

    # Also get untracked
    untracked = discover_untracked_markdown(repo_root)

    return tracked + untracked


def get_file_metadata(filepath: str, repo_root: str) -> dict[str, Any]:
    """Extract metadata for a file."""
    full_path = Path(repo_root) / filepath

    if not full_path.exists():
        return {"exists": False, "size_kb": 0, "last_modified": None, "lines": 0}

    stat = full_path.stat()
    size_kb = round(stat.st_size / 1024, 1)
    modified = datetime.fromtimestamp(stat.st_mtime)
    age_days = (datetime.now() - modified).days

    # Count lines
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            lines = len(f.readlines())
    except Exception:
        lines = 0

    return {
        "exists": True,
        "size_kb": size_kb,
        "last_modified": modified.strftime("%Y-%m-%d %H:%M"),
        "age_days": age_days,
        "lines": lines,
    }


def check_git_tracked(filepath: str, repo_root: str) -> bool:
    """Check if file is tracked by git."""
    output, returncode = run_command(["git", "ls-files", filepath], cwd=repo_root)
    return returncode == 0 and output.strip() != ""


def detect_patterns(filepath: str) -> list[str]:
    """Detect patterns in filename that hint at purpose."""
    patterns = []
    filename = Path(filepath).name.upper()

    # Analysis patterns
    if "COMPARISON" in filename:
        patterns.append("contains_COMPARISON_in_name")
    if "ANALYSIS" in filename:
        patterns.append("contains_ANALYSIS_in_name")
    if "SESSION" in filename:
        patterns.append("contains_SESSION_in_name")
    if "NOTES" in filename:
        patterns.append("contains_NOTES_in_name")
    if "PROMPT" in filename:
        patterns.append("contains_PROMPT_in_name")
    if "REPORT" in filename:
        patterns.append("contains_REPORT_in_name")

    # Status patterns
    if any(x in filename for x in ["DRAFT", "WIP", "TEMP", "EXPERIMENTAL"]):
        patterns.append("temporary_or_experimental")

    # Core doc patterns (should probably NOT archive)
    if any(
        x in filename
        for x in ["README", "CONTRIBUTING", "LICENSE", "CHANGELOG", "ARCHITECTURE"]
    ):
        patterns.append("core_documentation")

    if filename == "TODO.MD" or filename == "TASKS.MD":
        patterns.append("task_tracking")

    return patterns


def find_references(filepath: str, repo_root: str) -> dict[str, Any]:
    """Find all references to a file in the repository."""
    filename = Path(filepath).name

    # Use git grep to find references
    # Look for the filename in markdown links and other references
    output, returncode = run_command(["git", "grep", "-l", filename], cwd=repo_root)

    referenced_by = []
    if returncode == 0 and output:
        referenced_by = [f for f in output.split("\n") if f and f != filepath]

    # Also check for markdown link patterns specifically
    link_pattern = f"\\[.*\\]\\(.*{re.escape(filename)}.*\\)"
    output2, returncode2 = run_command(
        ["git", "grep", "-l", "-E", link_pattern], cwd=repo_root
    )

    if returncode2 == 0 and output2:
        for f in output2.split("\n"):
            if f and f != filepath and f not in referenced_by:
                referenced_by.append(f)

    return {"inbound_count": len(referenced_by), "inbound_from": referenced_by}


def analyze_content(filepath: str, repo_root: str) -> dict[str, Any]:
    """Analyze file content for structure and key elements."""
    full_path = Path(repo_root) / filepath

    if not full_path.exists():
        return {}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return {"error": "Could not read file"}

    # Extract top-level headings
    headings = []
    for line in content.split("\n"):
        if line.startswith("## "):
            headings.append(line[3:].strip())
            if len(headings) >= 5:  # Limit to first 5
                break

    # Detect content characteristics
    has_tables = "|" in content and "---" in content
    has_code_blocks = "```" in content
    has_metrics = bool(re.search(r"\d+%|\d+x|\d+/\d+", content))
    has_todos = bool(re.search(r"TODO|FIXME|- \[ \]", content))

    # Extract first 150 chars for preview
    first_line = content.split("\n")[0] if content else ""
    preview = first_line[:150]

    return {
        "has_tables": has_tables,
        "has_code_blocks": has_code_blocks,
        "has_metrics": has_metrics,
        "has_todos": has_todos,
        "top_level_headings": headings,
        "preview": preview,
    }


def find_related_files(filepath: str, all_files: list[str]) -> dict[str, list[str]]:
    """Find files that might be related to this one."""
    filename = Path(filepath).name
    base_name = filename.split(".")[0]

    # Find files with similar names
    similar_names = []
    for f in all_files:
        if f != filepath and base_name.lower() in Path(f).name.lower():
            similar_names.append(f)

    return {
        "similar_names": similar_names[:5]  # Limit to 5
    }


def detect_convention(repo_root: str) -> dict[str, Any]:
    """Detect existing archive conventions in repository."""
    archive_path = Path(repo_root) / "archive"
    index_path = archive_path / "index.md"

    exists = archive_path.exists() and archive_path.is_dir()
    index_exists = index_path.exists()

    existing_archives = []
    if exists:
        try:
            # List archived files
            for item in archive_path.iterdir():
                if item.is_file() and item.name != "index.md":
                    existing_archives.append(item.name)
        except Exception:
            pass

    return {
        "archive_exists": exists,
        "index_exists": index_exists,
        "index_location": "archive/index.md",
        "existing_archives": existing_archives[:10],  # Limit to 10
    }


def analyze_files_impl(
    file_paths: list[str] | None, mode: str, repo_root: str
) -> dict[str, Any]:
    """Main analysis function."""

    # Discover files based on mode
    if file_paths:
        # Explicit files provided
        discovered_files = file_paths
    elif mode == "untracked":
        discovered_files = discover_untracked_markdown(repo_root)
    elif mode == "explore":
        discovered_files = discover_all_markdown(repo_root)
    else:
        discovered_files = []

    # Analyze each file
    file_analyses = []
    for filepath in discovered_files:
        metadata = get_file_metadata(filepath, repo_root)
        if not metadata["exists"]:
            continue

        git_tracked = check_git_tracked(filepath, repo_root)
        patterns = detect_patterns(filepath)
        references = find_references(filepath, repo_root)
        content = analyze_content(filepath, repo_root)
        related = find_related_files(filepath, discovered_files)

        file_analyses.append(
            {
                "path": filepath,
                "metadata": {**metadata, "git_tracked": git_tracked},
                "patterns_detected": patterns,
                "references": references,
                "content_structure": content,
                "related_files": related,
            }
        )

    # Generate summary
    total_size_kb = sum(f["metadata"]["size_kb"] for f in file_analyses)
    untracked_count = sum(1 for f in file_analyses if not f["metadata"]["git_tracked"])

    return {
        "mode": mode,
        "convention": detect_convention(repo_root),
        "summary": {
            "total_candidates": len(file_analyses),
            "total_size_kb": round(total_size_kb, 1),
            "untracked_count": untracked_count,
            "tracked_count": len(file_analyses) - untracked_count,
        },
        "files": file_analyses,
    }


@app.command()
def analyze(
    files: list[str] = typer.Argument(
        None, help="Specific files to analyze (optional)"
    ),
    mode: str = typer.Option(
        "untracked", help="Discovery mode: 'untracked' or 'explore'"
    ),
    repo_root: str = typer.Option(".", help="Repository root directory"),
):
    """
    Analyze files for archiving with automatic discovery.

    Modes:
    - untracked: Discover only untracked markdown files (fast, default)
    - explore: Review all markdown files in repository (comprehensive)
    """
    result = analyze_files_impl(files, mode, repo_root)
    print(json.dumps(result, indent=2))


@app.command()
def discover(
    mode: str = typer.Option(
        "untracked", help="Discovery mode: 'untracked' or 'explore'"
    ),
    repo_root: str = typer.Option(".", help="Repository root directory"),
):
    """Discover candidate files without full analysis."""
    if mode == "untracked":
        files = discover_untracked_markdown(repo_root)
    elif mode == "explore":
        files = discover_all_markdown(repo_root)
    else:
        files = []

    print(json.dumps({"mode": mode, "files": files}, indent=2))


@app.command()
def check_convention(
    repo_root: str = typer.Option(".", help="Repository root directory"),
):
    """Check existing archive convention in repository."""
    result = detect_convention(repo_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
