#!/usr/bin/env python3
"""paper-md: turn a paper or report PDF into clean, quotable Markdown, locally.

Commands:
  fetch SOURCE --out DIR    arXiv ID/URL, DOI or direct PDF URL -> local PDF (public only)
  convert PDF [--out DIR]   Marker (local, never --use_llm) -> cleanup -> audit -> .md

stdout: one JSON object with status, outputs, counts, unresolved and notes (plus error
on failure); only --help prints plain usage text instead. stderr: diagnostics and Marker progress (file paths and timings, no
document text). Exit codes: 0 done (unresolved items may remain), 2 usage, 3 dependency
missing or denied, 4 conversion or I/O failure, 5 busy (another conversion holds the
lock), 6 fetch failed.

Each cleanup rule fires only in a context the evidence showed and lists what it cannot
decide. Code fences, tables and display maths are not rewritten (exceptions: page links
in table cells, and margin line numbers inside a fence that holds 5 or more of them,
stepping +1 to +3). Nothing existing is
overwritten: new outputs get a .v2, .v3, ... suffix. With --no-excerpts the report
carries kinds, page numbers and counts only, never document text.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import http.client
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_DEP, EXIT_CONVERT, EXIT_BUSY, EXIT_FETCH = 0, 2, 3, 4, 5, 6
EXCERPT_LEN = 80
KILL_GRACE_S = 5
# A fixed per-user path, not the temp dir: sandboxed harnesses get private temp dirs,
# which would let two conversions run side by side.
LOCK_PATH = Path.home() / ".cache" / "paper-md" / "marker.lock"


class Fail(Exception):
    def __init__(self, code: int, status: str, detail: str, **extra):
        super().__init__(detail)
        self.code, self.status, self.detail, self.extra = code, status, detail, extra


def log(msg: str) -> None:
    print(f"paper-md: {msg}", file=sys.stderr, flush=True)


# ------------------------------------------------------------------------ helpers


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return s[:80] or "document"


def candidates(base: Path, suffix: str):
    """base.suffix, base.v2.suffix, base.v3.suffix, ..."""
    n = 1
    while True:
        yield base.with_name((base.name if n == 1 else f"{base.name}.v{n}") + suffix)
        n += 1


def run_text(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except PermissionError as e:
        raise Fail(
            EXIT_DEP,
            "dependency_denied",
            f"{cmd[0]} could not be executed",
            tool=cmd[0],
        ) from e


def require(tools: list[str]) -> dict[str, str]:
    found = {}
    for tool in tools:
        path = shutil.which(tool)
        if not path:
            visible = shutil.which(tool, mode=os.F_OK)
            status = "dependency_denied" if visible else "dependency_missing"
            detail = "not executable here" if visible else "not found on PATH"
            raise Fail(EXIT_DEP, status, f"{tool} {detail}", tool=tool)
        found[tool] = path
    return found


def marker_version(marker_path: str) -> str:
    """Version from the interpreter in marker_single's shebang (pipx/uv venv)."""
    try:
        real = Path(os.path.realpath(marker_path))
        first = real.read_text(errors="replace").splitlines()[0]
        py = first[2:].strip().split()[0] if first.startswith("#!") else ""
        code = "import importlib.metadata as m; print(m.version('marker-pdf'))"
        return run_text([py, "-c", code]).strip() or "unknown"
    except (OSError, IndexError, subprocess.CalledProcessError):
        return "unknown"


def model_cache_present() -> bool:
    for base in (
        Path.home() / "Library/Caches/datalab/models",
        Path.home() / ".cache/datalab/models",
    ):
        with contextlib.suppress(OSError):
            if base.is_dir() and any(base.iterdir()):
                return True
    return False


def pdf_page_count(pdf: Path) -> int:
    out = run_text(["pdfinfo", str(pdf)])
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    if not m:
        raise Fail(
            EXIT_CONVERT, "not_a_pdf", f"pdfinfo found no page count in {pdf.name}"
        )
    return int(m.group(1))


def pdf_text_pages(pdf: Path) -> list[str]:
    pages = run_text(["pdftotext", "-enc", "UTF-8", str(pdf), "-"]).split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) from a JPEG or PNG header, stdlib only."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            if data[i + 1] in SOF_MARKERS:
                height = int.from_bytes(data[i + 5 : i + 7], "big")
                return int.from_bytes(data[i + 7 : i + 9], "big"), height
            i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


# -------------------------------------------------------------------------- fetch

ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?"
    r"((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)(?:\.pdf)?$",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"(?:doi\.org/|doi:)?(10\.\d{4,9}/\S+)$", re.IGNORECASE)


def http_get(url: str, timeout: int = 60) -> tuple[bytes, str]:
    headers = {"User-Agent": "paper-md/1 (local paper conversion)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def resolve_source(source: str) -> tuple[str, str, str]:
    """-> (kind, pdf_url, slug)."""
    s = source.strip()
    is_url = s.lower().startswith(("http://", "https://"))
    looks_arxiv = "arxiv" in s.lower() or not (is_url or DOI_RE.search(s))
    if looks_arxiv and (m := ARXIV_RE.search(s)):
        ident = m.group(1)
        name = "arxiv-" + slug(ident.replace("/", "-"))
        return "arxiv", f"https://arxiv.org/pdf/{ident}", name
    if m := DOI_RE.search(s):
        doi = m.group(1).rstrip(".")
        api = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="/")
        try:
            data = json.loads(http_get(api)[0])
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise Fail(
                EXIT_FETCH, "lookup_failed", f"OpenAlex lookup failed: {e}", doi=doi
            ) from e
        best = (data.get("best_oa_location") or {}).get("pdf_url")
        others = [
            loc.get("pdf_url")
            for loc in data.get("locations") or []
            if loc.get("pdf_url")
        ]
        url = best or (others[0] if others else None)
        if not url:
            detail = "OpenAlex lists no open-access PDF; ask for the file"
            raise Fail(EXIT_FETCH, "no_open_access_pdf", detail, doi=doi)
        return "doi", url, "doi-" + slug(doi.replace("/", "-"))
    if is_url:
        return "url", s, slug(Path(urllib.parse.urlparse(s).path).stem)
    detail = "expected an arXiv ID/URL, a DOI or an http(s) PDF URL"
    raise Fail(EXIT_USAGE, "unrecognised_source", detail)


def publish_new(tmp: Path, base: Path, suffix: str) -> Path:
    """Hard-link tmp to the first free versioned name; never replaces a file."""
    for dest in candidates(base, suffix):
        try:
            os.link(tmp, dest)
            return dest
        except FileExistsError:
            continue
    raise AssertionError("unreachable")


def cmd_fetch(args: argparse.Namespace) -> dict:
    require(["pdfinfo"])
    kind, url, name = resolve_source(args.source)
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"downloading {url}")
    try:
        body, ctype = http_get(url)
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise Fail(EXIT_FETCH, "download_failed", str(e), url=url) from e
    if not body.startswith(b"%PDF"):
        detail = f"response is not a PDF (Content-Type {ctype or 'unknown'})"
        raise Fail(EXIT_FETCH, "not_pdf", detail, url=url)
    with tempfile.NamedTemporaryFile(
        dir=out_dir, prefix=".paper-md-", suffix=".pdf"
    ) as tmp:
        tmp.write(body)
        tmp.flush()
        try:
            pages = pdf_page_count(Path(tmp.name))
        except Fail as e:
            if e.code == EXIT_DEP:
                raise
            raise Fail(
                EXIT_FETCH, "not_pdf", "pdfinfo rejected the download", url=url
            ) from e
        except subprocess.CalledProcessError as e:
            raise Fail(
                EXIT_FETCH, "not_pdf", "pdfinfo rejected the download", url=url
            ) from e
        dest = publish_new(Path(tmp.name), out_dir / name, ".pdf")
    source = {"kind": kind, "input": args.source, "url": url}
    return {
        "status": "fetched",
        "outputs": {"pdf": str(dest)},
        "source": source,
        "counts": {"pages": pages},
    }


# ----------------------------------------------------------------- Markdown model

MARK_RE = re.compile(r"^\{(\d+)\}-{6,}\s*$")
SPAN_RE = re.compile(r'<span id="page-\d+-\d+"></span>')
PLINK_RE = re.compile(r"\[((?:\\.|[^\]\\])*)\]\(#page-[\d-]+\)")
NUMLINE_RE = re.compile(r"^(?:#{1,6} )?(?:\*\*)?(\d{1,5}(?: \d{1,5})*)(?:\*\*)?$")
GLUED_PRE_RE = re.compile(r"^(\*\*)?(\d{1,5}(?: \d{1,5})*)(\*\*)? (?=\S)")
GLUED_POST_RE = re.compile(r"(?<=\S) (\*\*)?(\d{1,5}(?: \d{1,5})*)(\*\*)?$")
CAPTION_RE = re.compile(
    r"^(?:\*\*|_)?(?:Figure|Fig\.|Table|Abbildung|Tabelle)\s*\d+", re.IGNORECASE
)
TERMINAL_RE = re.compile(r"[.!?:;][\"”’)\]*_]*$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
NUMHEAD_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
LETTERHEAD_RE = re.compile(r"^([A-Z])((?:\.\d+)*)\.?\s+\S")
APPENDIX_RE = re.compile(r"^(?:appendix|appendices|anhang)\b", re.IGNORECASE)
BACKMATTER_RE = re.compile(r"^(?:references|bibliography|literatur)", re.IGNORECASE)
ANON_RE = re.compile(
    r"anonymous\s+(?:submission|paper|authors?(?:\(s\))?)(?:\s*(?:id\s*)?\d+)?",
    re.IGNORECASE,
)
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
GAP_RE = re.compile(
    r"(\S[^\n]{16,}?[(,:;] )([<>=≤≥] )([−\-+]?[0-9][0-9.]*(?:[eE][-+−]?[0-9]+)?)(?![0-9])"
)
GAP_ANY_RE = re.compile(r"(?:^|[(\[,;:]\s?)[<>=≤≥]\s?[−\-+]?\d")
HEADER_REST_RE = re.compile(r"^[\s|∙·•–—-]*(?:\d{1,4}[\s|∙·•–—-]*)*$")
SYM_CHARS = r"A-Za-z\u0370-\u03FF\U0001D400-\U0001D7FF"
SYM_RE = f"([{SYM_CHARS}][{SYM_CHARS}0-9²³\u0302]{{0,3}})"
MATHSYM = set("αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ²³√∑∏∫≤≥≈±×∞∂∇")
GREEK_SMALL = [
    "ALPHA",
    "BETA",
    "GAMMA",
    "DELTA",
    "EPSILON",
    "ZETA",
    "ETA",
    "THETA",
    "IOTA",
    "KAPPA",
    "MU",
    "NU",
    "XI",
    "PI",
    "RHO",
    "SIGMA",
    "TAU",
    "UPSILON",
    "PHI",
    "CHI",
    "PSI",
    "OMEGA",
]
GREEK_CAPITAL = ["Gamma", "Delta", "Theta", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega"]
LATEX_SYM = {
    **{
        "\\" + n.lower(): unicodedata.lookup(f"GREEK SMALL LETTER {n}")
        for n in GREEK_SMALL
    },
    **{
        "\\" + n: unicodedata.lookup(f"GREEK CAPITAL LETTER {n.upper()}")
        for n in GREEK_CAPITAL
    },
    "\\lambda": "λ",
    "\\Lambda": "Λ",
    "\\varepsilon": "ε",
    "\\varphi": "φ",
    "\\sum": "∑",
    "\\prod": "∏",
    "\\int": "∫",
    "\\leq": "≤",
    "\\le": "≤",
    "\\geq": "≥",
    "\\ge": "≥",
    "\\approx": "≈",
    "\\pm": "±",
    "\\times": "×",
    "\\infty": "∞",
    "\\partial": "∂",
    "\\nabla": "∇",
    "\\sqrt": "√",
    "^{2}": "²",
    "^2": "²",
    "^{3}": "³",
    "^3": "³",
}


@dataclass
class Report:
    counts: dict[str, int] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    private: bool = False  # --no-excerpts: no document text anywhere in the report

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def flag(self, kind: str, page: int | None, text: str = "", **extra) -> None:
        item: dict = {"kind": kind, "page": None if page is None else page + 1}
        for key, value in extra.items():
            numeric = isinstance(value, int) or (
                isinstance(value, list) and all(isinstance(v, int) for v in value)
            )
            if numeric or not self.private:
                item[key] = value
        if text and not self.private:
            item["excerpt"] = text.strip()[:EXCERPT_LEN]
        self.unresolved.append(item)

    def note(self, text: str, private_text: str | None = None) -> None:
        self.notes.append(private_text if self.private and private_text else text)


Lines = list  # list[str | None]; None marks a deleted line, so indices stay stable


def pages_of(lines: Lines) -> list[int]:
    page, out = 0, []
    for line in lines:
        if line is not None and (m := MARK_RE.match(line)):
            page = int(m.group(1))
        out.append(page)
    return out


def structure_kinds(lines: Lines) -> list[str | None]:
    """Per line: "fence" (code fence, delimiters included), "math" (display maths),
    "table" (a | row outside fences) or None."""
    kinds: list[str | None] = []
    fence = dmath = False
    for line in lines:
        s = (line or "").strip()
        if s.startswith("```") and not dmath:
            fence = not fence
            kinds.append("fence")
        elif fence:
            kinds.append("fence")
        elif s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            dmath = not dmath
            kinds.append("math")
        elif dmath or s.startswith("$$"):
            kinds.append("math")
        else:
            kinds.append("table" if s.startswith("|") else None)
    return kinds


def structure_mask(lines: Lines) -> list[bool]:
    """True for lines inside code fences, tables or display maths: never rewritten."""
    return [k is not None for k in structure_kinds(lines)]


def is_paragraph(line: str | None) -> bool:
    if not line:
        return False
    s = line.strip()
    if not s or MARK_RE.match(s) or CAPTION_RE.match(s):
        return False
    if s.startswith(("#", "|", "```", "![", "<", "$$", ">", "- ", "* ", "+ ")):
        return False
    return not re.match(r"^\d+[.)] ", s)


def nonblank(lines: Lines, i: int, step: int) -> int | None:
    j = i + step
    while 0 <= j < len(lines):
        if lines[j] is not None and lines[j].strip():
            return j
        j += step
    return None


def norm_line(s: str) -> str:
    s = re.sub(r"^#{1,6}\s+", "", s.strip()).replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", s).strip()


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------- cleanup passes


def strip_anchors(lines: Lines, mask: list[bool], rep: Report) -> None:
    def unescape(m: re.Match) -> str:
        return re.sub(r"\\([\[\]])", r"\1", m.group(1))

    kinds = structure_kinds(lines)
    for i, line in enumerate(lines):
        if line is None or kinds[i] in ("fence", "math"):  # table cells: cleaned too
            continue
        new = PLINK_RE.sub(unescape, SPAN_RE.sub("", line))
        if new != line:
            rep.add("anchors_removed")
            lines[i] = new


def _steps_ok(vals: list[int]) -> bool:
    return all(1 <= b - a <= 3 for a, b in itertools.pairwise(vals))


def line_number_ranges(ref_pages: list[str]) -> list[tuple[int, int] | None]:
    """Per PDF page, the span of margin line numbers pdftotext shows, or None.

    pdftotext emits margin numbers as their own rows, roughly in order. A page has line
    numbers when its number-only rows, in reading order, form a chain of at least 10
    values each 1-3 above an earlier one."""
    out: list[tuple[int, int] | None] = []
    for text in ref_pages:
        chain: dict[int, tuple[int, int]] = {}  # value -> (chain length, chain start)
        for row in (r.strip() for r in text.splitlines()):
            if not (row.isdigit() and len(row) <= 5):
                continue
            v = int(row)
            prev = [chain[v - d] for d in (1, 2, 3) if v - d in chain]
            length, start = max(prev) if prev else (0, v)
            if length + 1 > chain.get(v, (0, v))[0]:
                chain[v] = (length + 1, start)
        best = max(((n, s, v) for v, (n, s) in chain.items()), default=(0, 0, 0))
        out.append((best[1], best[2]) if best[0] >= 10 else None)
    return out


def remove_line_numbers(
    lines: Lines, mask: list[bool], ref_pages: list[str], rep: Report
):
    """Remove margin line numbers, decided per page from the PDF text.

    Returns the per-page ranges when the document has line numbers, else None."""
    ranges = line_number_ranges(ref_pages)
    texted = [
        r for r, t in zip(ranges, ref_pages, strict=False) if len(t.split()) >= 10
    ]
    if not texted or sum(r is not None for r in texted) < max(1, len(texted) / 2):
        return None
    pages = pages_of(lines)
    kinds = structure_kinds(lines)

    def in_range(vals: list[int], p: int) -> bool:
        r = ranges[p] if p < len(ranges) else None
        return bool(r) and all(r[0] <= v <= r[1] for v in vals)

    def number_line(i: int) -> bool:
        m = NUMLINE_RE.match((lines[i] or "").strip())
        vals = [int(v) for v in m.group(1).split()] if m else []
        return bool(m) and _steps_ok(vals) and in_range(vals, pages[i])

    # Marker puts boxed prompts into code fences and the margin numbers land inside them.
    # A fence counts as holding margin numbers when it has at least 5 in-range number
    # lines that, read top to bottom, each step +1 to +3 (as margin numbers do: in 1626's
    # boxed prompts all 341 steps were 1-3). Anything else is kept and reported.
    fence_of: list[int] = []
    fence_vals: dict[int, list[list[int]]] = {}
    fid, inside = 0, False
    for i, k in enumerate(kinds):
        s = (lines[i] or "").strip()
        if k == "fence" and s.startswith("```"):
            if not inside:
                fid += 1
            inside = not inside
        fence_of.append(fid if k == "fence" else -1)
        if k == "fence" and lines[i] is not None and number_line(i):
            fence_vals.setdefault(fid, []).append(
                [int(v) for v in NUMLINE_RE.match(s).group(1).split()]
            )
    margin_fences = {
        f
        for f, vals in fence_vals.items()
        if len(vals) >= 5 and _steps_ok([v for group in vals for v in group])
    }

    for i, line in enumerate(lines):
        if line is None or MARK_RE.match(line) or kinds[i] in ("table", "math"):
            continue
        if NUMLINE_RE.match(line.strip()):
            if kinds[i] == "fence" and fence_of[i] not in margin_fences:
                continue
            if number_line(i):
                lines[i] = None
                rep.add("line_number_lines_removed")
            continue
        if mask[i] or LIST_RE.match(lines[i]):  # list items may end in data values
            continue
        for rx in (GLUED_PRE_RE, GLUED_POST_RE):
            if not (m := rx.search(lines[i])):
                continue
            vals = [int(v) for v in m.group(2).split()]
            if not (_steps_ok(vals) and in_range(vals, pages[i])):
                continue
            # A single plain number next to text may be data ("we enrolled 450"): keep it.
            if len(vals) >= 2 or (m.group(1) and m.group(3)):
                lines[i] = (lines[i][: m.start()] + lines[i][m.end() :]).strip()
                rep.add("glued_line_numbers_removed")
            else:
                rep.flag("glued_number_kept", pages[i], lines[i])
    return ranges


def header_footer_patterns(ref_pages: list[str]) -> list[tuple[re.Pattern, str]]:
    """Running headers/footers: strings among each PDF page's first or last two rows
    (digits normalised) that recur on at least 3 pages and 40% of pages."""
    pages_by_key: dict[str, set[int]] = {}
    samples: dict[str, str] = {}
    for p, text in enumerate(ref_pages):
        rows = [r.strip() for r in text.splitlines() if r.strip()]
        for row in rows[:2] + rows[-2:]:
            row = re.sub(r"^\d+\s+|\s+\d+$", "", row).strip()
            if len(row) > 80 or sum(c.isalpha() for c in row) < 3:
                continue
            key = re.sub(r"\d+", "\0", collapse(row))
            pages_by_key.setdefault(key, set()).add(p)
            samples.setdefault(key, row)
    n = max(1, len(ref_pages))
    out = []
    for key, pages in pages_by_key.items():
        if len(pages) >= 3 and len(pages) >= 0.4 * n:
            parts = [
                r"\d+" if t == "\0" else re.escape(t)
                for t in re.split("(\0)", key)
                if t
            ]
            body = "".join(parts).replace(r"\ ", r"\s+")
            rx = re.compile(r"(?:\*\*)?" + body + r"(?:\s+\d+(?![\w.,]))?(?:\*\*)?")
            out.append((rx, samples[key]))
    return out


def remove_headers_footers(
    lines: Lines, mask: list[bool], ref_pages: list[str], rep: Report
):
    pats = header_footer_patterns(ref_pages)
    if not pats:
        return pats
    rep.note(
        "running headers/footers detected: " + "; ".join(s for _, s in pats),
        f"{len(pats)} running header/footer pattern(s) detected",
    )
    near: set[int] = set()  # the block right before and after each page break
    for i, line in enumerate(lines):
        if line is not None and MARK_RE.match(line):
            for step in (-1, 1):
                if (j := nonblank(lines, i, step)) is not None:
                    near.add(j)
    for edge in (nonblank(lines, -1, 1), nonblank(lines, len(lines), -1)):
        if edge is not None:
            near.add(edge)
    for i, line in enumerate(lines):
        if line is None or mask[i] or MARK_RE.match(line):
            continue
        normed = norm_line(line)
        hits = [(rx, s) for rx, s in pats if rx.search(normed)]
        if not hits:
            continue
        rest = normed
        for rx, _ in hits:
            rest = rx.sub(" ", rest)
        longest = max(len(s) for _, s in hits)
        if HEADER_REST_RE.match(
            rest
        ):  # nothing but header text, page numbers, separators
            if (i in near and not line.lstrip().startswith("#")) or longest >= 15:
                lines[i] = None
                rep.add("header_footer_lines_removed")
            continue
        if i in near and longest >= 15:
            new = line
            for rx, s in hits:
                if len(s) >= 15:
                    new = rx.sub(" ", new)
            if new != line:
                lines[i] = re.sub(r"\s{2,}", " ", new).strip()
                rep.add("header_footer_fragments_removed")
    pages = pages_of(lines)
    for i, line in enumerate(lines):
        if line is None or MARK_RE.match(line):
            continue
        for rx, sample in pats:
            if rx.search(norm_line(line)):
                rep.flag("header_footer_text_kept", pages[i], line, pattern=sample)
                break
    return pats


def drop_anonymous_headings(lines: Lines, mask: list[bool], rep: Report) -> None:
    for i, line in enumerate(lines):
        if line is None or mask[i] or not HEAD_RE.match(line.strip()):
            continue
        text = norm_line(line)
        if ANON_RE.fullmatch(text):
            lines[i] = None
            rep.add("anonymous_headings_removed")
        elif (
            (m := re.search(r"\s+(" + ANON_RE.pattern + r")$", text, re.IGNORECASE))
            and m.group(1).isupper()
            and len(text[: m.start()]) >= 10
        ):
            # Marker glued the template placeholder to the title: "# Title ANONYMOUS AUTHOR(S)"
            level = HEAD_RE.match(line.strip()).group(1)
            lines[i] = f"{level} {text[: m.start()]}"
            rep.add("anonymous_headings_removed")


def fill_symbol_gaps(
    lines: Lines, mask: list[bool], ref_pages: list[str], rep: Report
) -> None:
    """Fill `( = 0.84)`-style gaps from the same PDF page, only when unique."""
    pages = pages_of(lines)
    refs = [collapse(t) for t in ref_pages]
    for i, line in enumerate(lines):
        if line is None or mask[i] or MARK_RE.match(line) or pages[i] >= len(refs):
            continue
        ref = refs[pages[i]]

        def repl(m: re.Match, ref: str = ref) -> str:
            pre, sep, num = m.groups()
            ctx = re.escape(collapse(pre.rstrip())[-14:])
            tail = (
                re.escape(sep.strip())
                + r"\s?"
                + re.escape(num)
                + r"(?![0-9]|[.,][0-9]|[eE][-+−]?[0-9])"
            )
            pat = ctx + r"\s?" + SYM_RE + r"\s?" + tail
            found = {unicodedata.normalize("NFKC", c) for c in re.findall(pat, ref)}
            if len(found) != 1:
                return m.group(0)
            rep.add("symbol_gaps_filled")
            lead = pre[:-1] if pre.endswith("( ") else pre
            return lead + found.pop() + " " + sep + num

        lines[i] = GAP_RE.sub(repl, line)


def fix_headings(lines: Lines, mask: list[bool], rep: Report) -> None:
    """Levels from section numbering; one level-1 title; other level-1 headings become 2."""
    seen_first, in_back = False, False
    for i, line in enumerate(lines):
        if line is None or mask[i] or not (m := HEAD_RE.match(line)):
            continue
        hashes, text = m.groups()
        text = text.strip()
        if text.startswith("**") and text.endswith("**") and len(text) > 4:
            text = text[2:-2].strip()
        if APPENDIX_RE.match(text) or BACKMATTER_RE.match(text):
            in_back = True
        level = len(hashes)
        if not seen_first:
            level, seen_first = 1, True
        elif nm := NUMHEAD_RE.match(text):
            level = min(6, nm.group(1).count(".") + 2)
        elif in_back and (lm := LETTERHEAD_RE.match(text)):
            level = min(6, lm.group(2).count(".") + 2)
        elif APPENDIX_RE.match(text) or level == 1:
            level = 2
        new = "#" * level + " " + text
        if new != line:
            rep.add("headings_changed")
            lines[i] = new


def join_page_breaks(lines: Lines, mask: list[bool], rep: Report) -> None:
    pages = pages_of(lines)
    for i, line in enumerate(lines):
        if line is None or not MARK_RE.match(line):
            continue
        p, n = nonblank(lines, i, -1), nonblank(lines, i, 1)
        if p is None or n is None or mask[p] or mask[n] or MARK_RE.match(lines[n]):
            continue
        prev, nxt = lines[p], lines[n]
        if TERMINAL_RE.search(prev.rstrip()) or not (
            is_paragraph(prev) and is_paragraph(nxt)
        ):
            continue
        if nxt.lstrip()[:1].islower() and not prev.rstrip().endswith("-"):
            lines[p] = prev.rstrip() + " " + nxt.lstrip()
            lines[n] = None
            rep.add("page_break_joins")
        else:
            excerpt = f"{prev.strip()[-40:]} | {nxt.strip()[:40]}"
            rep.flag("possible_page_break_split", pages[n], excerpt)


# -------------------------------------------------------------------------- audit

NUM_TOKEN_RE = re.compile(r"(?<![\w.])[−\-]?\d+(?:[.,]\d+)*%?")
DIGIT_GROUP_RE = re.compile(r"(?<=\d)[\u2009\u202f\u00a0](?=\d{3})")


def numbers_in(text: str) -> list[str]:
    text = DIGIT_GROUP_RE.sub("", text)
    return NUM_TOKEN_RE.findall(text)


def norm_num(tok: str) -> str:
    return tok.replace("−", "-").replace(",", "").rstrip("%")


def page_symbols(text: str) -> set[str]:
    for cmd, ch in sorted(LATEX_SYM.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(cmd, ch)
    return {c for c in text + unicodedata.normalize("NFKC", text) if c in MATHSYM}


def audit(
    lines: Lines, mask, ref_pages, npages, assets: Path, ranges, rep: Report
) -> None:
    """Triage while page markers (and so page attribution) are still exact."""
    pages = pages_of(lines)
    live = [
        (i, ln)
        for i, ln in enumerate(lines)
        if ln is not None and not MARK_RE.match(ln)
    ]
    md_pages: dict[int, list[str]] = {}
    for i, ln in live:
        md_pages.setdefault(pages[i], []).append(ln)
    if ranges:
        left: dict[int, int] = {}
        for i, ln in live:
            m = NUMLINE_RE.match(ln.strip())
            r = ranges[pages[i]] if pages[i] < len(ranges) else None
            if m and r and all(r[0] <= int(v) <= r[1] for v in m.group(1).split()):
                left[pages[i]] = left.get(pages[i], 0) + 1
        for p, n in sorted(left.items()):
            rep.flag("line_number_leftover", p, lines=n)
    for i, ln in live:
        if GAP_ANY_RE.search(ln):
            rep.flag("symbol_gap", pages[i], ln)
    for k, (i, ln) in enumerate(live):
        if not CAPTION_RE.match(ln.strip()):
            continue
        same_page = [x for j, x in live[max(0, k - 2) : k + 3] if pages[j] == pages[i]]
        if not any("![" in x or x.lstrip().startswith("|") for x in same_page):
            rep.flag("caption_without_figure_or_table", pages[i], ln)
    imgs_by_page: dict[int, list[str]] = {}
    for i, ln in live:
        for name in IMG_RE.findall(ln):
            imgs_by_page.setdefault(pages[i], []).append(name)
            size = image_size(assets / Path(name).name)
            if ranges and size and size[0] < 50 and size[1] > 3 * size[0]:
                rep.flag("probable_line_number_strip", pages[i], name, size=list(size))
    for p, names in sorted(imgs_by_page.items()):
        if len(names) >= 2:
            rep.flag("several_images_on_page", p, ", ".join(names), images=len(names))
    no_ref: list[int] = []
    for p in range(npages):
        ref = ref_pages[p] if p < len(ref_pages) else ""
        md_text = "\n".join(md_pages.get(p, []))
        ref_words, md_words = len(ref.split()), len(md_text.split())
        if md_words == 0 and ref_words >= 10:
            rep.flag("page_text_missing", p, pdf_words=ref_words)
            continue
        if ref_words < 10:
            no_ref.append(p + 1)
            if md_words < 10:
                rep.flag("page_without_text", p)
            continue
        if md_words < 0.5 * ref_words and ref_words >= 50:
            rep.flag("page_text_short", p, md_words=md_words, pdf_words=ref_words)
        ref_nums = {norm_num(t) for t in numbers_in(ref)}
        missing = sorted(
            {
                t
                for t in numbers_in(md_text)
                if (len(t) > 1 or "." in t) and norm_num(t) not in ref_nums
            }
        )
        if missing:
            rep.flag(
                "numbers_not_in_pdf_text",
                p,
                " ".join(missing[:20]),
                numbers=len(missing),
            )
        lost = page_symbols(ref) - page_symbols(md_text)
        if lost:
            rep.flag(
                "check_maths_symbols", p, " ".join(sorted(lost)), symbols=len(lost)
            )
    if no_ref:
        rep.flag("pages_without_reference_text", None, pages=no_ref)


# ------------------------------------------------------------------------ convert


@contextlib.contextmanager
def conversion_lock():
    """Machine-wide lock: one conversion at a time. Held for the whole conversion and
    inherited by Marker, so it lives as long as Marker does even if the wrapper dies."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            holder = os.pread(fd, 32, 0).decode(errors="replace").strip()
            detail = f"another conversion is running (pid {holder or '?'})"
            raise Fail(EXIT_BUSY, "busy", detail, lock=str(LOCK_PATH)) from e
        os.ftruncate(fd, 0)
        os.pwrite(fd, str(os.getpid()).encode(), 0)
        yield fd
    finally:
        os.close(fd)


def run_marker(
    marker: str, pdf: Path, work: Path, fast: bool, lock_fd: int, quiet: bool = False
) -> None:
    cmd = [
        marker,
        str(pdf),
        "--output_dir",
        str(work),
        "--paginate_output",
        "--disable_tqdm",
    ]
    if fast:
        cmd.append("--disable_ocr")
    env = {**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    child: subprocess.Popen | None = None

    def stop(signum, _frame):
        raise Fail(EXIT_CONVERT, "interrupted", f"stopped by signal {signum}")

    old = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        log(f"running marker_single on {pdf.name} ({'OCR off' if fast else 'OCR on'})")
        child = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL if quiet else sys.stderr,
            stderr=subprocess.DEVNULL if quiet else sys.stderr,
            env=env,
            start_new_session=True,
            pass_fds=(lock_fd,),
        )
        os.ftruncate(lock_fd, 0)
        os.pwrite(lock_fd, str(child.pid).encode(), 0)
        rc = child.wait()
    except PermissionError as e:
        raise Fail(
            EXIT_DEP,
            "dependency_denied",
            "marker_single could not be executed",
            tool="marker_single",
        ) from e
    finally:
        if child is not None:
            terminate_group(child)  # also stops leftover workers after a normal exit
        for s, h in old.items():
            signal.signal(s, h)
    if rc != 0:
        raise Fail(EXIT_CONVERT, "marker_failed", f"marker_single exited {rc}")


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def terminate_group(child: subprocess.Popen) -> None:
    """Stop the child's whole process group (leader and descendants): SIGTERM, wait up
    to KILL_GRACE_S, then SIGKILL; reap the leader. Signals are blocked meanwhile."""
    pgid = child.pid
    old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if child.poll() is not None and not group_alive(pgid):
                break
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pgid, sig)
            deadline = time.monotonic() + KILL_GRACE_S
            while time.monotonic() < deadline:
                child.poll()
                if child.returncode is not None and not group_alive(pgid):
                    break
                time.sleep(0.05)
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=KILL_GRACE_S)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old)


def render(lines: Lines, mask: list[bool], assets_name: str | None = None) -> str:
    """Drop deleted lines and page markers, point image links into the figures folder,
    collapse blank runs; protected blocks are left as they are."""

    def relink(m: re.Match) -> str:
        return m.group(0).replace(m.group(1), f"{assets_name}/{Path(m.group(1)).name}")

    kinds = structure_kinds(lines)
    out: list[str] = []
    for i, ln in enumerate(lines):
        if ln is None or MARK_RE.match(ln):  # Marker's own page separators
            continue
        if assets_name and kinds[i] not in ("fence", "math"):
            ln = IMG_RE.sub(relink, ln)
        if not ln.strip() and not mask[i] and out and not out[-1].strip():
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def clean_markdown(
    md: str,
    ref_pages: list[str],
    npages: int,
    assets: Path,
    rep: Report,
    relink: bool = False,
) -> str:
    lines: Lines = md.splitlines()
    mask = structure_mask(lines)
    strip_anchors(lines, mask, rep)
    ranges = remove_line_numbers(lines, mask, ref_pages, rep)
    pats = remove_headers_footers(lines, mask, ref_pages, rep)
    if pats:
        rep.add("header_footer_patterns", len(pats))
    drop_anonymous_headings(lines, mask, rep)
    fill_symbol_gaps(lines, mask, ref_pages, rep)
    fix_headings(lines, mask, rep)
    audit(lines, mask, ref_pages, npages, assets, ranges, rep)
    join_page_breaks(lines, mask, rep)
    return render(lines, mask, assets.name if relink else None)


def reserve_md(base: Path) -> tuple[Path, Path]:
    """Create the first free <stem>.md (exclusively) whose _figures dir is also free."""
    for md in candidates(base, ".md"):
        assets = md.with_name(md.stem + "_figures")
        if assets.exists():
            continue
        try:
            md.open("x").close()
            return md, assets
        except FileExistsError:
            continue
    raise AssertionError("unreachable")


def cmd_convert(args: argparse.Namespace) -> dict:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.is_file():
        raise Fail(EXIT_USAGE, "no_such_file", f"{pdf} not found")
    tools = require(["marker_single", "pdftotext", "pdfinfo"])
    rep = Report(private=args.no_excerpts)
    if args.no_excerpts:
        rep.note(
            "Marker output suppressed (--no-excerpts); rerun without it to see Marker diagnostics"
        )
    with conversion_lock() as lock_fd:
        if not model_cache_present():
            rep.note("no Marker model cache found: the first run downloads about 1 GB")
        npages = pdf_page_count(pdf)
        ref_pages = pdf_text_pages(pdf)
        fast = args.fast
        textless = sum(1 for t in ref_pages if len(t.split()) < 10) + max(
            0, npages - len(ref_pages)
        )
        if fast and textless > npages / 2:
            fast = False
            rep.note("--fast refused: most pages have no text layer, so OCR is needed")
        out_dir = Path(args.out).expanduser().resolve() if args.out else pdf.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        version = marker_version(tools["marker_single"])
        with tempfile.TemporaryDirectory(prefix="paper-md-") as tmp:
            work = Path(tmp)
            run_marker(
                tools["marker_single"], pdf, work, fast, lock_fd, quiet=args.no_excerpts
            )
            mds = sorted(work.rglob("*.md"))
            if not mds:
                raise Fail(EXIT_CONVERT, "no_output", "Marker produced no Markdown")
            raw = mds[0].read_text()
            md_path, assets = reserve_md(out_dir / slug(args.name or pdf.stem))
            images = [
                p
                for p in mds[0].parent.iterdir()
                if p.suffix.lower() in (".jpeg", ".jpg", ".png")
            ]
            if images:
                assets.mkdir()
                for img in images:
                    shutil.move(str(img), assets / img.name)
            body = clean_markdown(
                raw, ref_pages, npages, assets, rep, relink=bool(images)
            )
        mode = "OCR off (--fast)" if fast else "OCR on"
        converter = f"marker-pdf {version}, local, {mode}; paper-md cleanup"
        front = (
            "---\n"
            f"source: {json.dumps(pdf.name, ensure_ascii=False)}\n"
            f"converted: {dt.date.today().isoformat()}\n"
            f"converter: {json.dumps(converter)}\n"
            "---\n\n"
            "*Machine reconstruction of the source PDF. Check the PDF before quoting "
            "numbers, maths or figures.*\n\n"
        )
        md_path.write_text(front + body)
    rep.counts.update(
        {"pages": npages, "images": len(images), "unresolved": len(rep.unresolved)}
    )
    return {
        "status": "converted",
        "outputs": {"md": str(md_path), "figures": str(assets) if images else None},
        "mode": {"ocr": not fast, "marker": version},
        "counts": rep.counts,
        "unresolved": rep.unresolved,
        "notes": rep.notes,
    }


# ---------------------------------------------------------------------------- CLI


class Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise Fail(EXIT_USAGE, "usage_error", message)


def envelope(result: dict) -> dict:
    base = {"status": "", "outputs": {}, "counts": {}, "unresolved": [], "notes": []}
    return {**base, **result}


def main(argv: list[str] | None = None) -> int:
    ap = Parser(
        prog="paper_md.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    f = sub.add_parser("fetch", help="download a public arXiv/DOI/URL source as PDF")
    f.add_argument("source")
    f.add_argument("--out", required=True, help="directory for the PDF")
    c = sub.add_parser("convert", help="convert a local PDF to cleaned Markdown")
    c.add_argument("pdf")
    c.add_argument("--out", help="output directory (default: next to the PDF)")
    c.add_argument("--name", help="output file stem (default: slug of the PDF name)")
    c.add_argument(
        "--fast", action="store_true", help="--disable_ocr: faster, loses inline maths"
    )
    c.add_argument(
        "--no-excerpts", action="store_true", help="no document text in the report"
    )
    code = EXIT_OK

    def interrupted(_signum, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        args = ap.parse_args(argv)
        result = cmd_fetch(args) if args.cmd == "fetch" else cmd_convert(args)
    except Fail as e:
        result, code = {"status": e.status, "error": e.detail, **e.extra}, e.code
    except subprocess.CalledProcessError as e:
        result = {
            "status": "tool_failed",
            "error": f"{Path(str(e.cmd[0])).name} exited {e.returncode}",
        }
        code = EXIT_CONVERT
    except KeyboardInterrupt:
        result, code = (
            {"status": "interrupted", "error": "stopped by a signal"},
            EXIT_CONVERT,
        )
    except OSError as e:
        result, code = (
            {"status": "io_error", "error": f"{type(e).__name__}: {e.strerror or e}"},
            EXIT_CONVERT,
        )
    finally:
        signal.signal(signal.SIGTERM, previous)
    if code:
        log(result["error"])
    print(json.dumps(envelope(result), ensure_ascii=False, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
