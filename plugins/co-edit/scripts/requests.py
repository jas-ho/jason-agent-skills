"""Exact coedit requests using profiles' carrier grammar, never watcher hashes."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import json
import html
from pathlib import Path
import re

if __package__:
    from .profiles import get_profile
else:
    from profiles import get_profile

TOKEN = "⏵"
SUPPORTED = {".md", ".typ"}
EXCLUDED_DIRS = {"node_modules", "target", "dist", "build", "vendor", "__pycache__"}
ARCHIVE = re.compile(r"^(?:(?:archive|archived|history)(?:\s*[:—–-].*)?|applied\s+\d{4}-\d{2}-\d{2}(?:\s*[—–-]\s*pass\s+\d+)?)$", re.I)
ARCHIVE_ANCHOR = re.compile(r"^\^(coedit-[0-9a-f]+)\r?$", re.MULTILINE)


def fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sidecar(path: str) -> str:
    p = Path(path)
    return str(p) if p.name.endswith(".notes.md") else str(p) + ".notes.md"


def authorized(scope: str, path: str) -> bool:
    root, candidate = Path(scope), Path(path)
    if not root.is_absolute() or not candidate.is_absolute():
        return False
    # Resolving existing symlinks also checks parents of not-yet-created sidecars.
    if str(candidate.resolve()) != str(candidate) or candidate.suffix.lower() not in SUPPORTED:
        return False
    if root.is_dir():
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            return False
        return not any(part.startswith(".") or part in EXCLUDED_DIRS for part in relative.parts)
    return candidate == root or str(candidate) == sidecar(str(root))


@dataclass(frozen=True)
class Request:
    raw: str
    start: int
    end: int
    body_start: int
    body_end: int
    body: str
    kind: str
    author: str
    line: int
    signed: bool

    @property
    def revision(self) -> str:
        return fingerprint(self.raw)

    def submitted_raw(self) -> str:
        if self.signed:
            return self.raw
        at = self.body_end - self.start
        # The profile's text group has carrier-specific whitespace semantics.
        # Insert before its trailing whitespace, never outside the HTML carrier.
        while at and self.raw[at - 1].isspace():
            at -= 1
        return self.raw[:at] + (" " if at and not self.raw[at - 1].isspace() else "") + TOKEN + self.raw[at:]


def _blank(out: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if out[i] != "\n":
            out[i] = " "


def _archive_ranges(view: str, profile) -> Iterator[tuple[int, int]]:
    start = archive_level = None
    pos = 0
    for line in view.splitlines(keepends=True):
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$" if profile.name == "markdown" else r"^\s*(=+)\s+(.+?)\s*$", line.rstrip("\r\n"))
        if heading:
            level, title = len(heading[1]), heading[2].strip()
            archived = bool(ARCHIVE.fullmatch(title))
            if start is not None and (level <= archive_level or archived):
                yield start, pos
                start = None
            if archived:
                start, archive_level = pos, level
        pos += len(line)
    if start is not None:
        yield start, pos


def executable_view(text: str, path: str, *, archives_only: bool = False, lexical_only: bool = False) -> str:
    """Length-preserving lexical exclusion; headings never use title dropping."""
    profile = get_profile(Path(path))
    # BOM replacement (not removal) is essential to exact live-buffer offsets.
    source = (" " + text[1:]) if text.startswith("\ufeff") else text
    out = list(source)
    if profile.name == "markdown":
        lines = source.splitlines(keepends=True)
        pos = 0
        front = bool(lines and lines[0].strip() == "---")
        fence = None
        quote = False
        for index, line in enumerate(lines):
            stripped = line.rstrip("\r\n")
            if front:
                _blank(out, pos, pos + len(line))
                if index and stripped.strip() in {"---", "..."}:
                    front = False
            elif fence:
                _blank(out, pos, pos + len(line))
                if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*$", stripped):
                    fence = None
            else:
                match = re.match(r"^ {0,3}(`{3,}|~{3,})", stripped)
                if match:
                    fence = (match[1][0], len(match[1]))
                    _blank(out, pos, pos + len(line))
                elif re.match(r"^ {0,3}>", stripped):
                    quote = True
                    _blank(out, pos, pos + len(line))
                elif quote and stripped.strip() and not re.match(r"^ {0,3}#{1,6}\s", stripped):
                    # CommonMark lazy blockquote continuation is also quoted.
                    _blank(out, pos, pos + len(line))
                else:
                    quote = False
                if re.match(r"^(?: {4}|\t)", line):
                    _blank(out, pos, pos + len(line))
            pos += len(line)
        # Existing CommonMark delimiter logic + Anchor exclusions, reused.
        out = list(profile.blank_quoted_spans("".join(out)))
    else:
        # Shield strings before the existing raw/nested-comment scanner. Skip
        # real line comments so quotes in request prose do not mask requests.
        i = 0
        while i < len(source):
            if source.startswith("//", i) and (not i or source[i - 1] != ":"):
                i = source.find("\n", i)
                if i < 0:
                    break
            elif source[i] == '"':
                end = i + 1
                while end < len(source):
                    if source[end] == "\\":
                        end += 2
                    elif source[end] == '"':
                        end += 1
                        break
                    else:
                        end += 1
                _blank(out, i, min(end, len(source)))
                i = end
            else:
                i += 1
        out = list(profile.strip_excluded_regions("".join(out)))
    view = "".join(out)
    if lexical_only:
        return view
    archived = list(" " if char != "\n" else "\n" for char in source) if archives_only else None
    for start, end in _archive_ranges(view, profile):
        if archives_only:
            archived[start:end] = source[start:end]
        else:
            _blank(out, start, end)
    return "".join(archived if archives_only else out)


def history_insertion(text: str, path: str) -> tuple[int, int, bool]:
    """Insert within an existing lexical History, before its closing heading."""
    view = executable_view(text, path, lexical_only=True)
    headings = list(re.finditer(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", view, re.MULTILINE))
    histories = [heading for heading in headings if heading[2].strip().lower() == "history"]
    if not histories:
        return len(text), 2, True
    heading = histories[-1]
    level = len(heading[1])
    end = next((other.start() for other in headings if other.start() > heading.start() and len(other[1]) <= level), len(text))
    return end, level, False


def parse(text: str, path: str) -> list[Request]:
    profile = get_profile(Path(path))
    view = executable_view(text, path)
    out = list(view)
    reserved = r"<!--\s*CLAUDE.*?(?:-->|\Z)" if profile.name == "markdown" else r"(?<!:)//\s*CLAUDE[^\n]*"
    for match in re.finditer(reserved, view, re.DOTALL | re.I):
        _blank(out, match.start(), match.end())
    view = "".join(out)
    result = []
    for match in profile.build_pattern(None).finditer(view):
        if match["type"].upper().startswith("CLAUDE") or not profile.accept_match(text, match):
            continue
        # Filtering may have blanked examples *inside* a request. The raw body
        # (not the filtered match group) is authoritative for authorization.
        body = text[match.start("text"):match.end("text")]
        raw = text[match.start():match.end()]
        result.append(Request(raw, match.start(), match.end(), match.start("text"), match.end("text"), body, match["type"], match["author"], text.count("\n", 0, match.start()) + 1, body.rstrip().endswith(TOKEN)))
    return result


def archived_raws(text: str, path: str) -> set[str]:
    """Historical anchors are tombstones, not executable requests."""
    profile = get_profile(Path(path))
    view = executable_view(text, path, archives_only=True)
    return {text[m.start():m.end()] for m in profile.build_pattern(None).finditer(view) if not m["type"].upper().startswith("CLAUDE")}


def archive_sections(text: str, path: str) -> Iterator[str]:
    """Yield separate archive sections using the executable-view boundaries."""
    view = executable_view(text, path, lexical_only=True)
    for start, end in _archive_ranges(view, get_profile(Path(path))):
        yield text[start:end]


def archive_entries(section: str) -> Iterator[tuple[str, str]]:
    """An entry ends at its next anchor or this archive section's end."""
    anchors = list(ARCHIVE_ANCHOR.finditer(section))
    for index, anchor in enumerate(anchors):
        end = anchors[index + 1].start() if index + 1 < len(anchors) else len(section)
        yield anchor[1], section[anchor.end():end]


def archive_evidence(segment: str) -> tuple[str, list[tuple[str, str]]] | None:
    """Validate source and complete protocol fields within one anchor segment."""
    blocks = list(re.finditer(r"<pre data-coedit-([a-z-]+)>(.*?)</pre>", segment, re.DOTALL))
    if len(re.findall(r"<pre\b[^>]*\bdata-coedit-", segment, re.I)) != len(blocks):
        return None
    fields = [(block[1], html.unescape(block[2])) for block in blocks]
    roles = [role for role, _ in fields]
    if roles != ["original", "decision"] + ["path", "cleanup"] * ((len(roles) - 2) // 2):
        return None
    sources = [match for match in re.finditer(r"(?m)^\*\*Coedit source:\*\* ([^\r\n]+)\r?$", segment)
               if not any(block.start() <= match.start() < block.end() for block in blocks)]
    if len(sources) != 1 or sources[0].end() > blocks[0].start():
        return None
    try:
        source = json.loads(sources[0][1])
    except (ValueError, TypeError):
        return None
    return (source, fields) if isinstance(source, str) and Path(source).is_absolute() else None


def archive_records(text: str, path: str) -> list[tuple[str, str]]:
    """Protocol provenance is entry-local; legacy raw markers use their own file."""
    profile = get_profile(Path(path))
    default = path[:-len(".notes.md")] if path.endswith(".notes.md") else path
    result, entries = [], []
    pattern = profile.build_pattern(None)
    for section in archive_sections(text, path):
        legacy = list(section)
        for block in re.finditer(r"<pre\b[^>]*\bdata-coedit-.*?(?:</pre>|\Z)", section, re.DOTALL | re.I):
            _blank(legacy, block.start(), block.end())
        if Path(default).is_absolute():
            result.extend((default, section[match.start():match.end()])
                          for match in pattern.finditer("".join(legacy))
                          if not match["type"].upper().startswith("CLAUDE"))
        entries.extend(archive_entries(section))
    counts = Counter(anchor for anchor, _ in entries)
    for anchor, segment in entries:
        if counts[anchor] != 1:
            continue
        evidence = archive_evidence(segment)
        if evidence:
            source, fields = evidence
            result.append((source, fields[0][1]))
    return result


def token_only_submission(before: str, after: Request, path: str) -> bool:
    """Only exact raw carrier equality after token insertion proves signoff."""
    previous = parse(before, path)
    if len(previous) != 1 or previous[0].signed:
        return False
    token_at = after.body_end - after.start
    while token_at and after.raw[token_at - 1].isspace():
        token_at -= 1
    without_token = after.raw[:token_at - 1] + after.raw[token_at:]
    return before == without_token or previous[0].submitted_raw() == after.raw
