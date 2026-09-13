#!/usr/bin/env python3
"""Per-format carrier, quoting, exclusion, and heading parsers for co-edit.

`requests.py` consumes the carrier grammar; `runtime.py` owns authorization,
durable requests, and editor transactions. This module does not authorize
requests or write documents. `get_profile()` dispatches by file extension,
with markdown as the fallback for unknown extensions. The LaTeX parser is
retained and regression-tested even though live LaTeX editing is unsupported.

Profile descriptors such as `default_signoff`, `pause_line`, and
`cursor_probe` are historical parser metadata, not the live runtime protocol.
The parser interface is:

    name                    profile id
    extensions              lowercased, dotted extensions claimed by dispatch
    build_pattern(prefixes, relaxed=False)
                            compiled marker regex with `type`/`author`/`text`;
                            `relaxed=True` is the near-miss variant of the
                            same grammar (any-case type, optional author)
    exclusion_rules         ordered (name, pattern, flags, count) transforms
    strip_excluded_regions  length/newline-preserving blanking of those regions
    blank_quoted_spans      length-preserving opaque fill of QUOTED spans only
    accept_match(raw, m)    profile-specific post-filter on a pattern match
    collect_headings(text)  (line_idx0, level, title) over the FULL cleaned text
    cursor_probe            historical cursor-probe metadata
    default_signoff         historical sign-off metadata; not authorization
    marker_example          illustrative carrier syntax, not a live request
    pause_line              historical control-marker example
    comment_desc            prose name of the carrier ("an HTML comment", ...)

`collect_headings` takes the full cleaned TEXT rather than a list of lines on
purpose: the LaTeX profile has to brace-match a `\\section{...}` title across
line boundaries. Profiles that work line-by-line just split internally.

`strip_excluded_regions` has two possible implementations: the shared regex
table walk (markdown), or a procedural scanner supplied by the profile (typst
raw text needs matching-delimiter semantics that a regex cannot express).
Either way the contract is identical: same length, same newline positions, so
match offsets in the cleaned text still map to the raw file's line numbers.

TWO VIEWS, TWO JOBS
-------------------
Marker consumers use two distinct views of the raw text:

  marker_view  = profile.blank_quoted_spans(raw)   -> the MARKER pass
  heading_view = profile.strip_excluded_regions(raw) -> heading collection

Markers fire wherever marker syntax appears, with exactly two exclusions, both
of which are explicit quoting: (1) the profile's inline literal spans (markdown
and typst single-line backtick runs, LaTeX `\\verb`/`\\lstinline`), and (2) the
sidecar protocol's `**Anchor:**` lines (markdown only — the sidecar is always
`.md`). Everything else — fences, frontmatter, link-reference lines, typst
block comments and raw blocks, LaTeX verbatim environments — is a region a user
may legitimately annotate, and a silently missed marker is worse than a
spurious one.

Heading collection keeps the FULL exclusion machinery, because `# comment` in a
bash fence or `\\section` inside a verbatim body must not become "under heading
X" enrichment. That is why `strip_excluded_regions` and its rule tables survive
unchanged even though the marker pass no longer uses them.

`blank_quoted_spans` fills with an OPAQUE character (`QUOTED_SPAN_FILLER`,
U+0001), not spaces: the marker patterns' lazy text groups are wrapped in
`\\s*`, so whitespace fill would let a leading/trailing quoted span be absorbed
by the surrounding `\\s*` and truncated out of the match. With an opaque filler
the span stays inside `span("text")` and consumers recover the marker
body VERBATIM by slicing `raw` at those offsets. Both views are therefore
strictly length- and offset-preserving against `raw` (including a leading BOM,
which becomes one filler character rather than being removed).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# The markdown marker carrier's comment delimiters.
MARKER_OPEN = "<!--"
MARKER_CLOSE = "-->"

# Historical cursor-probe metadata. Live editor capability checks belong to
# the runtime and editor bridge, not profile dispatch.
NO_CURSOR_PROBE_EXTENSIONS = frozenset({".tex", ".typ"})


# Fill character for the MARKER view's quoted spans. Deliberately NOT a space:
# every marker pattern wraps its lazy `text` group in `\s*`, so a whitespace
# fill would let `\s*` swallow a leading or trailing quoted span and truncate
# it out of `span("text")` — the span consumers slice from `raw` to recover
# verbatim marker text. U+0001 is opaque to `\s`, matches
# `.` under DOTALL, and never occurs in real prose.
QUOTED_SPAN_FILLER = "\x01"


def _blank(m: re.Match) -> str:
    """Same-length whitespace replacement: every char becomes a space,
    newlines are preserved. Keeps offsets/line numbers stable."""
    return re.sub(r"[^\n]", " ", m.group(0))


def _fill_quoted(out: list, start: int, stop: int) -> None:
    """Overwrite out[start:stop] with QUOTED_SPAN_FILLER in place, leaving
    newlines alone so line numbers and offsets are preserved exactly."""
    for k in range(max(start, 0), min(stop, len(out))):
        if out[k] != "\n":
            out[k] = QUOTED_SPAN_FILLER


def _quoted_view_base(text: str) -> list:
    """Mutable char list for a marker view, with a leading BOM replaced by one
    filler character.

    `strip_excluded_regions` REMOVES the BOM (shortening the text by one);
    the marker view must not, because consumers slice `raw` at match offsets
    taken from this view. Replacing it keeps every offset identical to `raw`
    while making sure the BOM itself can never be part of a match."""
    out = list(text)
    if out and out[0] == "﻿":
        out[0] = QUOTED_SPAN_FILLER
    return out


def _apply_exclusion_rules(rules: tuple, text: str) -> str:
    """Run an ordered exclusion table through the shared `_blank`."""
    for _name, pattern, flags, count in rules:
        text = re.sub(pattern, _blank, text, count=count, flags=flags)
    return text


def _drop_single_top_level(headings: list) -> list:
    """A document with exactly one level-1 heading uses it as the document
    title, not as a section: it would prefix every chain with the same ~40
    chars of zero discriminating power. Docs with multiple level-1 sections
    keep them. Shared by every profile so the heading chain in an event means
    the same thing whatever the file format is."""
    if sum(1 for _, level, _ in headings if level == 1) == 1:
        return [h for h in headings if h[1] != 1]
    return headings


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """One file format's marker syntax, exclusion regions, and headings.

    The three behavioral entry points (`build_pattern`,
    `strip_excluded_regions`, `collect_headings`) are methods that delegate to
    plain functions stored on the instance, so a profile is data rather than a
    class hierarchy — there is no shared base behavior worth inheriting, only
    the shared exclusion-table walk, which lives in the default
    `strip_excluded_regions` path.
    """

    name: str
    extensions: tuple[str, ...]
    cursor_probe: bool
    default_signoff: bool
    marker_example: str
    pause_line: str
    comment_desc: str
    _pattern_builder: Callable[[list | None, bool], re.Pattern]
    _heading_collector: Callable[[str], list]
    exclusion_rules: tuple[tuple[str, str, int, int], ...] = ()
    # Optional procedural replacement for the exclusion_rules walk. When set,
    # exclusion_rules is expected to be empty (the scanner IS the rule set).
    _region_scanner: Callable[[str], str] | None = field(default=None)
    # Builds the MARKER view (see the module docstring's "two views" section).
    _quoted_span_blanker: Callable[[str], str] | None = field(default=None)
    # Optional post-filter applied to every pattern match, given the RAW text
    # and the match. Lets a profile reject a match the regex alone cannot
    # (LaTeX backslash parity: `100\% TODO(jason): x ;;` is an escaped percent,
    # not a comment). Returning False drops the match entirely — it is neither
    # content nor control.
    _match_filter: Callable[[str, re.Match], bool] | None = field(default=None)

    def build_pattern(self, prefixes: list | None, relaxed: bool = False) -> re.Pattern:
        """Compiled marker regex exposing `type`, `author` and `text` groups.
        Matches must be non-overlapping and yielded in document order by
        finditer. `author` may be None/empty in closed-list mode, where the
        parenthetical is optional; authorization is the caller's responsibility.

        `relaxed=True` builds a diagnostic variant of the same grammar:
        same carrier, same terminator,
        same `text` group, but the type may be any case and the author
        parenthetical is optional — subject to still requiring a `:`/`.`
        delimiter OR a parenthetical, so an ordinary `<!-- note like this -->`
        comment is not a candidate. When `prefixes` is supplied, the relaxed
        variant's type alternative is constrained to that list too
        (case-insensitively): a type outside a closed list would not fire
        even with the right case and an author, so it is a routing decision,
        not a near-miss, and must not be reported as one. With `prefixes`
        empty/None the type may be any word, same as the real permissive
        pattern's shape without its case/author requirements. Sharing the
        builder is what keeps the carrier checks (the typst `(?<!:)` guard,
        the LaTeX parity `accept_match`, the line-bounded text group)
        identical between the real and the relaxed pass."""
        return self._pattern_builder(prefixes, relaxed)

    def blank_quoted_spans(self, text: str) -> str:
        """The MARKER view: fill this format's inline literal spans (and, for
        markdown, `**Anchor:**` protocol lines) with `QUOTED_SPAN_FILLER`.

        Strictly length- and offset-preserving against `text`, including a
        leading BOM — consumers slice `raw` at offsets taken from this view."""
        if self._quoted_span_blanker is None:
            return text
        return self._quoted_span_blanker(text)

    def accept_match(self, raw: str, match: re.Match) -> bool:
        """True when `match` (found in the marker view) is a real marker for
        this profile. Default: every match is accepted."""
        if self._match_filter is None:
            return True
        return self._match_filter(raw, match)

    def strip_excluded_regions(self, text: str) -> str:
        """Blank regions that heading collection must not read from,
        preserving length and newline positions. The UTF-8 BOM is stripped
        first (one character, no newline, so line numbers are unaffected).
        This differs from the offset-preserving marker view."""
        text = text.removeprefix("﻿")
        if self._region_scanner is not None:
            return self._region_scanner(text)
        return _apply_exclusion_rules(self.exclusion_rules, text)

    def collect_headings(self, cleaned_text: str) -> list:
        """(line_idx0, level, title) for every heading in the exclusion-cleaned
        FULL text."""
        return self._heading_collector(cleaned_text)


# ---------------------------------------------------------------------------
# Markdown profile
# ---------------------------------------------------------------------------

# Ordered exclusion transforms, each a (name, pattern, flags, count) tuple —
# count 0 means "all" (re.sub's own convention), matching re.sub's count kwarg
# directly.
#
# THIS TABLE FEEDS HEADING COLLECTION ONLY. It is not the marker pass's
# exclusion set: a marker inside a fence or frontmatter fires (see "two views"
# in the module docstring); the marker pass's own exclusions (quoted spans,
# `**Anchor:**` lines) come from `_markdown_blank_quoted_spans`, with
# CommonMark run semantics a flat regex cannot implement — of the regions
# below, none doubles as a marker exclusion.
#
# ORDER IS SEMANTIC: rules run sequentially on already-blanked text, not on
# independent copies of the raw text. A marker sitting inside an earlier
# rule's blanked region is invisible to every later rule too. Every rule must
# be length- and newline-preserving (via `_blank`), so reordering or changing
# a rule's count/flags changes behavior — this table is not a set.
MARKDOWN_EXCLUSION_RULES: tuple[tuple[str, str, int, int], ...] = (
    # YAML frontmatter at the top of the file only (count=1: a later `---`
    # in the body is a thematic break, not a second frontmatter fence).
    # Tolerates CRLF, missing trailing newline, and EOF-terminated
    # frontmatter (no body after).
    ("yaml-frontmatter", r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", re.DOTALL, 1),
    # Fenced code blocks (``` and ~~~).
    ("fenced-code-backtick", r"```.*?```", re.DOTALL, 0),
    ("fenced-code-tilde", r"~~~.*?~~~", re.DOTALL, 0),
)

# `**Anchor:** <verbatim marker line>` — the co-edit sidecar's entry format.
# Quoted marker syntax that must never fire as a live marker. This is a
# MARKER-VIEW-ONLY exclusion (filled by `_markdown_blank_quoted_spans`): an
# `**Anchor:**` line can never be an ATX heading, so it has no place in
# MARKDOWN_EXCLUSION_RULES above, which feeds heading collection only.
# The marker view's finditer runs on the ORIGINAL raw text (not the BOM-
# filled copy `_quoted_view_base` builds), so a leading BOM directly before
# an `**Anchor:**` line on the file's first line must be tolerated here: `\s`
# does not match U+FEFF (it has no Unicode Whitespace property), so without
# the explicit `﻿?` the anchor line would fail to match and leak as a live
# marker on a BOM-prefixed file.
_MD_ANCHOR_LINE_RE = re.compile(r"^﻿?\s*\*\*Anchor:\*\*.*$", re.MULTILINE)

_MD_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
_MD_INLINE_COMMENT_RE = re.compile(
    rf"{re.escape(MARKER_OPEN)}.*?(?:{re.escape(MARKER_CLOSE)}|$)"
)


def _fill_backtick_spans_commonmark(out: list, line: str, base: int) -> None:
    """Fill every CommonMark code span on ONE line, in place.

    CommonMark: a backtick string is a MAXIMAL run of backticks; an opening run
    of N closes on the next backtick string of EXACTLY N on the same line, and
    an unmatched run is literal text. That run arithmetic is why this is a
    scanner and not a `` `[^`\\n]+` `` regex — such a regex would match from
    the second backtick of ``` ``x` ``` through the internal single backtick
    and leave the rest of the span (marker syntax included) exposed.

    An opening run whose first backtick is preceded by an ODD run of
    backslashes is ESCAPED — literal text, not an opener — and is skipped
    without opening a span (`\\`` `` never opens a code span). Closing runs are
    unaffected by escaping: CommonMark backslash escapes do not work inside
    code spans, so a `` \\` `` found while searching for the close still closes
    normally.

    Spans are filled INCLUDING their delimiters; scanning resumes after the
    closing run, so nested-looking runs cannot re-open a span inside one that
    was already consumed. `base` is the line's offset in the full text."""
    length = len(line)
    i = 0
    while i < length:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < length and line[j] == "`":
            j += 1
        run = j - i
        bs = 0
        p = i - 1
        while p >= 0 and line[p] == "\\":
            bs += 1
            p -= 1
        if bs % 2 == 1:
            # Escaped opener (odd backslash run immediately before it):
            # literal backticks, not a span. Skip the run (not just one
            # char) so its own backticks cannot re-open.
            i = j
            continue
        k = j
        close = -1
        while k < length:
            if line[k] == "`":
                m = k
                while m < length and line[m] == "`":
                    m += 1
                if m - k == run:
                    close = m
                    break
                k = m
            else:
                k += 1
        if close == -1:
            # Unmatched opener: literal backticks, not a span. Skip the run
            # (not just one char) so its own backticks cannot re-open.
            i = j
            continue
        _fill_quoted(out, base + i, base + close)
        i = close


def _markdown_blank_quoted_spans(text: str) -> str:
    """Markdown MARKER view: single-line code spans plus `**Anchor:**` lines.

    Fences, frontmatter and link-reference definitions are deliberately NOT
    blanked — a marker a user typed inside a fenced example is a marker."""
    out = _quoted_view_base(text)
    pos = 0
    for line in text.split("\n"):
        _fill_backtick_spans_commonmark(out, line, pos)
        pos += len(line) + 1
    for m in _MD_ANCHOR_LINE_RE.finditer(text):
        _fill_quoted(out, m.start(), m.end())
    return "".join(out)


def _markdown_build_pattern(prefixes: list | None, relaxed: bool = False) -> re.Pattern:
    """Compile a regex matching annotation comments.

    Two modes:

    1. **Permissive (default, ``prefixes`` is None or empty)**: matches any
       2+-uppercase-letter prefix AND requires the author parenthetical
       ``(name)``. Case-sensitive on the prefix. This is the safety net
       against false-positives from normal HTML comments and boilerplate.
       Matches espanso-shortcut output (`,a`, `,q`, etc. all produce
       `<!-- PREFIX(jason): text -->`).

    2. **Closed list (``--prefixes A,B,C``)**: matches exactly those
       prefixes, case-insensitive, author parenthetical optional. Use this
       for project-specific filtering or backward compatibility.

    The prefix must be followed by a delimiter — `(`, whitespace, `:`, `.`,
    or the comment terminator `-->` — so we don't accidentally match
    longer words that start with a prefix (`NOTEBOOK`, `TODOING`, etc.).

    Permissive default rationale: the skill treats the prefix as the user's
    organizational tag, not a routing signal — the classifier reads the
    comment content. So the watcher matches any reasonable uppercase token
    rather than gating on a closed palette. The author parenthetical is
    the reliable signal that this is a user-authored co-edit marker rather
    than a stray HTML comment or templated boilerplate.

    Examples (permissive default — all match):
      <!-- TODO(jason): foo -->
      <!-- QUESTION(jason): is X true? -->
      <!-- HUNCH(jason): I think Carlos confirmed this -->
      <!-- DESIGN(jason): variant menu -->
    Examples (permissive default — non-matches):
      <!-- TODO: foo -->                 (no author parenthetical)
      <!-- todo(jason): foo -->          (lowercase prefix)
      <!-- this is just a comment -->    (lowercase, no parenthetical)
      <!--more-->                        (Hugo / Jekyll fold markers)
      <!--#include ... -->               (SSI directives)

    3. **Relaxed (``relaxed=True``, near-miss diagnostics only)**: same
       carrier and terminator, any-case type, optional author, but a `:`/`.`
       delimiter OR a parenthetical is still required — so `<!-- note: x -->`
       and `<!-- TODO: x -->` are candidates while `<!--more-->` and
       `<!-- just a sentence -->` are not. When ``prefixes`` is given, the
       type alternative is constrained to that list (case-insensitively),
       exactly like closed-list mode — under `--prefixes NOTE`,
       `<!-- todo(jason): x -->` and `<!-- TODO: x -->` are not candidates
       either, since no case/author fix would make them fire.
    """
    # The text group refuses to cross a `<!--`: an UNTERMINATED marker being
    # typed above an existing comment must not swallow that comment's `-->`
    # and emit a phantom marker spanning intervening prose.
    open_re = re.escape(MARKER_OPEN)
    close_re = re.escape(MARKER_CLOSE)
    text_group = rf"(?P<text>(?:(?!{open_re}).)*?)"
    if relaxed:
        if prefixes:
            # Closed-list mode: constrain the type alternative to the list
            # (case-insensitively), same boundary lookahead as the real
            # closed-list pattern below, so `NOTEBOOK` can't match a `NOTE`
            # prefix mid-word.
            alt = "|".join(re.escape(p) for p in prefixes)
            return re.compile(
                open_re
                + rf"\s*(?P<type>{alt})(?=\s|\(|:|\.|{close_re})\s*"
                + r"(?:\((?P<author>[^)]*)\)\s*[:.]?|[:.])\s*"
                + text_group
                + rf"\s*{close_re}",
                re.DOTALL | re.IGNORECASE,
            )
        return re.compile(
            open_re
            + r"\s*(?P<type>[A-Za-z][A-Za-z_-]+)\s*"
            + r"(?:\((?P<author>[^)]*)\)\s*[:.]?|[:.])\s*"
            + text_group
            + rf"\s*{close_re}",
            re.DOTALL,
        )
    if not prefixes:
        # Permissive default: uppercase prefix + REQUIRED author parenthetical.
        # Case-sensitive on the type group; the IGNORECASE flag is dropped.
        return re.compile(
            open_re
            + r"\s*(?P<type>[A-Z][A-Z_-]+)\s*\((?P<author>[^)]+)\)\s*[:.]?\s*"
            + text_group
            + rf"\s*{close_re}",
            re.DOTALL,
        )
    # Closed-list mode: case-insensitive, parenthetical optional.
    alt = "|".join(re.escape(p) for p in prefixes)
    return re.compile(
        rf"{open_re}\s*(?P<type>{alt})(?=\s|\(|:|\.|{close_re})"
        rf"(?:\((?P<author>[^)]*)\))?\s*[:.]?\s*{text_group}\s*{close_re}",
        re.IGNORECASE | re.DOTALL,
    )


def _markdown_collect_headings(cleaned_text: str) -> list:
    """Return (line_idx0, level, title) for every ATX heading. Runs on the
    blanked text, so headings inside fenced code blocks or frontmatter don't
    count. Setext (underline) headings are not recognized.

    Splits on "\\n" only — NOT splitlines(), which also splits on \\f, \\v,
    NEL, U+2028 etc. and would desync the indices from the "\\n"-counted line
    numbers used by marker consumers."""
    headings = []
    for idx, line in enumerate(cleaned_text.split("\n")):
        m = _MD_HEADING_RE.match(line)
        if m:
            # HTML comments on a heading line (inline markers included —
            # only fences/frontmatter are blanked in `cleaned`) are not part
            # of the title; tolerate an unterminated one being composed
            title = _MD_INLINE_COMMENT_RE.sub("", m.group(2))
            # strip optional closing hashes: "## Title ##" -> "Title"
            title = re.sub(r"\s+#+$", "", title.rstrip()).strip()
            if title:
                headings.append((idx, len(m.group(1)), title))
    return _drop_single_top_level(headings)


MARKDOWN = Profile(
    name="markdown",
    extensions=(".md", ".markdown"),
    cursor_probe=True,
    # Markdown gets the Obsidian cursor guard, which already covers
    # half-composed markers; requiring `;;` on top of it would be friction
    # for the primary workflow.
    default_signoff=False,
    marker_example=f"{MARKER_OPEN} TODO(jason): text {MARKER_CLOSE}",
    pause_line=f"{MARKER_OPEN} PAUSE(jason): ... {MARKER_CLOSE}",
    comment_desc="an HTML comment",
    _pattern_builder=_markdown_build_pattern,
    _heading_collector=_markdown_collect_headings,
    exclusion_rules=MARKDOWN_EXCLUSION_RULES,
    _quoted_span_blanker=_markdown_blank_quoted_spans,
)


# ---------------------------------------------------------------------------
# Typst profile
# ---------------------------------------------------------------------------
#
# Marker placement
# ----------------
# A typst marker is any `// TYPE(author):` on any line: trailing comments
# (`= Heading // NOTE(jason): x ;;`), doc comments (`/// TODO(jason): x ;;`),
# markers inside `/* */` blocks and inside raw blocks all fire. The former
# `^[ \t]*` standalone anchor was a false-positive defence that cost silent
# false negatives; the sign-off symbol is the composition guard, and the ONE
# exclusion is a single-line raw span (see `_typst_blank_quoted_spans`).
# A marker inside a string literal (`#let x = "// TODO(jason): x ;;"`) fires
# too — the scanner has no string-literal awareness and deliberately does not
# need one. The `(?<!:)` guard in the pattern is what keeps `https://...` from
# opening a marker, mirroring typst's own rule.
#
# Cleaning order (heading view only)
# ----------------------------------
# Markers ARE line comments, so the cleaning pass must leave line comments
# intact or there would be nothing left for heading collection to strip. The
# order is therefore:
#
#   1. `strip_excluded_regions` blanks block comments and raw regions, and
#      SKIPS OVER (but does not blank) `//` line comments — skipping matters,
#      because a backtick or `/*` inside a comment must not open a region.
#   2. `collect_headings` runs the same scanner again over the already-cleaned
#      text with line-comment blanking ON, so `== Other // NOTE(...)` yields
#      the title `Other` and a marker line can never be read as a heading.
#
# Markers are NOT extracted from this text — they come from the marker view
# (`blank_quoted_spans`), which blanks only single-line raw spans.
#
# Known limitation of step 3: the scanner has no string-literal awareness, so
# a `//` inside a quoted string on a heading line would be blanked too. The
# one realistic case — a URL — is handled by not treating `//` preceded by
# `:` as a comment start, which is also what typst does for `https://x`
# (verified on typst 0.15: `= see http://x.com/y` keeps the whole URL, while
# `= a//b` keeps only `a`).

_TYPST_HEADING_RE = re.compile(r"^(=+)[ \t]+([^\n]+?)[ \t\r]*$", re.MULTILINE)
_TYPST_LABEL_RE = re.compile(r"\s*<[\w:.-]+>\s*$")


def _typst_scan(text: str, blank_line_comments: bool) -> str:
    """Left-to-right scanner producing a blanked copy of `text`.

    Blanks, in one pass (whichever construct starts first wins, exactly as a
    lexer would):

      - `/* ... */` block comments, NESTED. Verified on typst 0.15:
        `/* a /* b */` leaves the comment open and swallows what follows, so a
        depth counter — not a non-greedy regex — is the faithful model. An
        unterminated block comment blanks to EOF.
      - raw text with typst's matching-delimiter semantics. A run of N
        backticks opens a raw region; N==1 closes on the next backtick, N==2
        is an empty raw (both consumed), N>=3 closes on the first later run of
        >=N backticks and consumes exactly N of it — the surplus backticks
        stay in the text and may open a fresh region, which is precisely what
        typst does (verified: "```\\nalpha\\n````\\nbeta`" parses as raw
        "alpha" followed by raw "\\nbeta"). An unterminated raw blanks to EOF.

    `//` line comments are always SKIPPED (so their contents cannot open a raw
    or block comment) but only blanked when `blank_line_comments` is true —
    markers are line comments and must survive the marker pass. A `//`
    immediately preceded by `:` is not a comment start (URL scheme).

    Length and newline positions are preserved exactly.
    """
    out = list(text)
    n = len(text)

    def blank(start: int, stop: int) -> None:
        for k in range(start, min(stop, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            depth = 1
            j = i + 2
            while j < n and depth:
                if text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    depth += 1
                    j += 2
                elif text[j] == "*" and j + 1 < n and text[j + 1] == "/":
                    depth -= 1
                    j += 2
                else:
                    j += 1
            blank(i, j)
            i = j
            continue
        if (
            ch == "/"
            and i + 1 < n
            and text[i + 1] == "/"
            and not (i > 0 and text[i - 1] == ":")
        ):
            j = text.find("\n", i)
            if j == -1:
                j = n
            if blank_line_comments:
                blank(i, j)
            i = j
            continue
        if ch == "`":
            k = i
            while k < n and text[k] == "`":
                k += 1
            run = k - i
            if run == 2:
                end = k
            elif run == 1:
                close = text.find("`", k)
                end = n if close == -1 else close + 1
            else:
                end = n
                j = k
                while j < n:
                    if text[j] == "`":
                        m = j
                        while m < n and text[m] == "`":
                            m += 1
                        if m - j >= run:
                            end = j + run
                            break
                        j = m
                    else:
                        j += 1
            blank(i, end)
            i = end
            continue
        i += 1
    return "".join(out)


def _typst_strip_excluded_regions(text: str) -> str:
    """Blank block comments and raw regions; leave `//` line comments intact
    (markers live in them)."""
    return _typst_scan(text, blank_line_comments=False)


def _fill_typst_raw_spans(out: list, line: str, base: int) -> None:
    """Fill every SINGLE-LINE typst raw span on one line, in place.

    Uses typst's own delimiter-run semantics, the ones `_typst_scan` documents:
    a run of 1 closes on the next backtick, a run of 2 is an empty raw (both
    consumed), a run of N>=3 closes on the first later run of >=N and consumes
    exactly N of it.

    A run that does not close ON THIS LINE opens a MULTI-LINE raw block, which
    is not "quoting" for the marker pass — a marker inside a multi-line raw
    block fires. So the opener is skipped, not filled."""
    length = len(line)
    i = 0
    while i < length:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < length and line[j] == "`":
            j += 1
        run = j - i
        if run == 2:
            end = j
        elif run == 1:
            close = line.find("`", j)
            end = -1 if close == -1 else close + 1
        else:
            end = -1
            k = j
            while k < length:
                if line[k] == "`":
                    m = k
                    while m < length and line[m] == "`":
                        m += 1
                    if m - k >= run:
                        end = k + run
                        break
                    k = m
                else:
                    k += 1
        if end == -1:
            i = j
            continue
        _fill_quoted(out, base + i, base + end)
        i = end


def _typst_blank_quoted_spans(text: str) -> str:
    """Typst MARKER view: single-line raw spans only.

    Block comments, multi-line raw blocks and string literals are NOT blanked
    — markers inside them fire."""
    out = _quoted_view_base(text)
    pos = 0
    for line in text.split("\n"):
        _fill_typst_raw_spans(out, line, pos)
        pos += len(line) + 1
    return "".join(out)


def _typst_build_pattern(prefixes: list | None, relaxed: bool = False) -> re.Pattern:
    """Compile a regex matching typst marker comments, anywhere on a line.

    Mirrors the markdown grammar with `//` as the carrier and end-of-line as
    the terminator:

      permissive (default)  `// TYPE(author): text`, uppercase TYPE, author
                            parenthetical REQUIRED, case-sensitive prefix
      closed list           exactly the listed prefixes, case-insensitive,
                            parenthetical optional; callers enforce any
                            additional author or authorization requirements

    There is no `^[ \\t]*` anchor: a marker fires wherever its syntax appears
    (trailing comments, `///` doc comments, string literals, raw blocks). The
    `(?<!:)` lookbehind is the one carrier check — it stops `https://x` and
    `#link("http://y")` from opening a marker, exactly as typst itself does.

    There is no terminator to defuse: the text group is `[^\\n]*`, so it can
    never swallow a following line. Any trailing sign-off symbol stays inside
    the text group; authorization and submission rules belong to callers.

    Closed-list mode does NOT accept `.` as a prefix delimiter (markdown does,
    for the legacy `<!-- TODO. text -->` convention). No such convention exists
    for typst, and accepting `.` would misread a protocol-relative URL such as
    `//pause.example.com` as a listed `PAUSE` marker.

    Examples (permissive default — all match):
      // TODO(jason): foo ;;
      /// TODO(jason): doc-comment carrier ;;
      = Heading // NOTE(jason): trailing comment ;;
      #let x = "// TODO(jason): in a string ;;"
    Examples (permissive default — non-matches):
      // TODO: foo                          (no author parenthetical)
      // todo(jason): foo                   (lowercase prefix)
      `// TODO(jason): quoted ;;`           (single-line raw span)
      https://TODO(jason): x                (`//` preceded by `:`)

    With ``relaxed=True`` this builds the near-miss variant instead: any-case
    type, optional author, `:`/`.` delimiter or parenthetical still required,
    same `(?<!:)` guard and same `[^\\n]*` line-bounded text group. When
    ``prefixes`` is given, the type alternative is constrained to that list
    (case-insensitively), same as closed-list mode above — under
    `--prefixes NOTE`, `// todo(jason): x ;;` and `// TODO: x ;;` are not
    candidates either, since no case/author fix would make them fire.
    """
    if relaxed:
        if prefixes:
            alt = "|".join(re.escape(p) for p in prefixes)
            return re.compile(
                rf"(?<!:)//[ \t]*(?P<type>{alt})(?=[ \t]|\(|:|\.|$)[ \t]*"
                r"(?:\((?P<author>[^)\n]*)\)[ \t]*[:.]?|[:.])[ \t]*"
                r"(?P<text>[^\n]*)",
                re.IGNORECASE | re.MULTILINE,
            )
        return re.compile(
            r"(?<!:)//[ \t]*(?P<type>[A-Za-z][A-Za-z_-]+)[ \t]*"
            r"(?:\((?P<author>[^)\n]*)\)[ \t]*[:.]?|[:.])[ \t]*"
            r"(?P<text>[^\n]*)",
            re.MULTILINE,
        )
    if not prefixes:
        return re.compile(
            r"(?<!:)//[ \t]*(?P<type>[A-Z][A-Z_-]+)[ \t]*\((?P<author>[^)\n]+)\)"
            r"[ \t]*[:.]?[ \t]*(?P<text>[^\n]*)",
            re.MULTILINE,
        )
    alt = "|".join(re.escape(p) for p in prefixes)
    return re.compile(
        rf"(?<!:)//[ \t]*(?P<type>{alt})(?=[ \t]|\(|:|$)"
        r"(?:\((?P<author>[^)\n]*)\))?[ \t]*[:.]?[ \t]*(?P<text>[^\n]*)",
        re.IGNORECASE | re.MULTILINE,
    )


def _typst_collect_headings(cleaned_text: str) -> list:
    """(line_idx0, level, title) for every typst heading in the cleaned text.

    Level is the length of the `=` run. Typst requires whitespace after the
    run, so `=nospace` is not a heading. A trailing `<label>` is stripped from
    the title, and `//` line comments are blanked first so a trailing comment
    never leaks into a title."""
    text = _typst_scan(cleaned_text, blank_line_comments=True)
    headings = []
    for m in _TYPST_HEADING_RE.finditer(text):
        title = _TYPST_LABEL_RE.sub("", m.group(2)).strip()
        if title:
            headings.append((text.count("\n", 0, m.start()), len(m.group(1)), title))
    return _drop_single_top_level(headings)


TYPST = Profile(
    name="typst",
    extensions=(".typ",),
    # The cursor guard is an Obsidian + HTML-comment mechanism; typst files
    # are edited elsewhere, so sign-off is the only composition guard left.
    cursor_probe=False,
    default_signoff=True,
    marker_example="// TODO(jason): text ;;",
    pause_line="// PAUSE(jason): ...",
    comment_desc="a // line comment",
    _pattern_builder=_typst_build_pattern,
    _heading_collector=_typst_collect_headings,
    _region_scanner=_typst_strip_excluded_regions,
    _quoted_span_blanker=_typst_blank_quoted_spans,
)


# ---------------------------------------------------------------------------
# LaTeX profile
# ---------------------------------------------------------------------------
#
# Scope of the LaTeX "parser"
# ---------------------------
# `_latex_scan` is a LEXER-SHAPED APPROXIMATION, not a TeX parser. It knows
# exactly four things:
#
#   1. `%` starts a comment that runs to end of line — unless it is escaped.
#      Escaping is decided by BACKSLASH PARITY, which falls out of the scanner
#      consuming `\<char>` as one atom: `\%` is a literal percent (the `%` is
#      eaten as the escape's payload), `\\%` is a linebreak macro followed by a
#      REAL comment, `\\\%` is a linebreak plus a literal percent. The same
#      atom-consumption makes `\{` / `\}` not count toward brace balance.
#   2. Verbatim-family ENVIRONMENTS, from a fixed allowlist (below): opened by
#      `\begin{X}`, closed only by a LINE-ANCHORED `\end{X}`.
#   3. Inline verbatim COMMANDS: `\verb<d>...<d>`, `\verb*<d>...<d>`,
#      `\lstinline<d>...<d>` and `\lstinline[opts]<d>...<d>`.
#   4. Nothing else.
#
# Explicitly OUT of scope, and deliberately so: catcode redefinitions
# (`\catcode`\%=12`), user-defined verbatim commands
# (`\DefineShortVerb`, `\newminted`, `\lstnewenvironment`), macro expansion,
# `\input`/`\include` following, math mode, and every other part of TeX. A
# document that redefines what `%` means is outside what this watcher claims to
# handle; the failure mode is a marker that does or does not fire, never a
# corrupted file, because the scanner only ever blanks characters in a COPY.
#
# Marker placement
# ----------------
# A latex marker is any `% TYPE(author):` on any line: trailing comments
# (`\section{X} % NOTE(jason): y ;;`), `%%` dividers, markers inside verbatim
# environments — all fire. The former `^[ \t]*` standalone anchor was a
# false-positive defence that cost silent false negatives.
#
# Two carrier checks survive, both real lexical facts rather than heuristics:
#   - BACKSLASH PARITY (`_latex_backslash_run_even`, wired up as the profile's
#     `_match_filter`): an odd run of `\` before the `%` means an escaped
#     percent, so `Sales rose 100\% TODO(jason): x ;;` is not a comment at all,
#     while `\\% TODO(jason): x ;;` is.
#   - the ONE exclusion, inline verbatim COMMANDS (`_latex_blank_quoted_spans`):
#     `\verb<d>...<d>`, `\verb*<d>...<d>`, `\lstinline[opts]{...}`. Backticks
#     are NOT special in LaTeX (they are opening quotes).
#
# Cleaning order — identical to typst, and for HEADINGS only
# ----------------------------------------------------------
#   1. `strip_excluded_regions` blanks verbatim environments and inline verbatim
#      commands, and SKIPS OVER (does not blank) `%` comments — skipping matters
#      because a `\begin{verbatim}` inside a comment must not open a region.
#   2. `collect_headings` re-runs the scanner over the already-cleaned text with
#      comment blanking ON, purely to locate `\section`-family commands that are
#      not themselves commented out. Title text is then read from the
#      NON-comment-blanked text so that LaTeX's "a comment eats the newline and
#      the next line's leading whitespace" rule can be honored when a title
#      spans lines.

# Environments whose bodies are typeset verbatim (plus `comment`, whose body is
# dropped entirely). An ALLOWLIST, not a heuristic: `\begin{X}` for any other X
# is ordinary markup and must stay visible, or a marker inside a `figure` or
# `itemize` would silently stop firing.
LATEX_VERBATIM_ENVIRONMENTS: frozenset[str] = frozenset(
    {
        "verbatim",
        "verbatim*",
        "Verbatim",
        "Verbatim*",
        "BVerbatim",
        "LVerbatim",
        "SaveVerbatim",
        "lstlisting",
        "minted",
        "comment",
    }
)

# `\begin{...}` with the environment name captured. `*` is part of the name
# (`verbatim*`), `@` shows up in internal environment names.
_LATEX_BEGIN_RE = re.compile(r"\\begin\{([A-Za-z@]+\*?)\}")
# `\verb` / `\verb*` / `\lstinline`, but not `\verbatim`, `\verbose`: the
# negative lookahead stops the command name from being a prefix of a longer one.
_LATEX_INLINE_VERB_RE = re.compile(r"\\(verb|lstinline)(\*?)(?![A-Za-z])")

# Sectioning commands, longest-first so alternation cannot match `\section`
# inside `\subsection`. `(?![A-Za-z])` keeps `\sectionmark` / `\partname` out.
_LATEX_HEADING_RE = re.compile(
    r"\\(subparagraph|subsubsection|subsection|paragraph|section|chapter|part)"
    r"\*?(?![A-Za-z])"
)

# LEVEL NORMALIZATION (judgment call, Phase 3):
#
# These are LaTeX's own sectioning numbers, used unshifted: `\section` is 1
# and `\subsection` is 2, matching markdown's H1/H2 hierarchy. `\part` (-1)
# and `\chapter` (0) remain ordered before sections. The parser regressions
# assert these levels through collected headings rather than this table.
LATEX_HEADING_LEVELS: dict[str, int] = {
    "part": -1,
    "chapter": 0,
    "section": 1,
    "subsection": 2,
    "subsubsection": 3,
    "paragraph": 4,
    "subparagraph": 5,
}


def _latex_option_block_end(text: str, start: int, line_stop: int) -> int | None:
    """Index just past the `]` closing the `\\lstinline[...]` option block that
    opens at `start`, or None if it does not close on this line.

    BRACE-AWARE: `\\lstinline[language={[LaTeX]TeX}]{...}` must not end at the
    `]` inside `{[LaTeX]TeX}`, or the delimiter is misidentified and the
    payload leaks. `\\<char>` is consumed as one atom so an escaped bracket
    never moves the depth. Shared by both `_latex_scan` (heading view) and
    `_latex_blank_quoted_spans` (marker view) — one parser for this construct,
    not two that could drift apart. Both callers apply the same rule for a
    None result: an option block that does not close on this line is
    unparseable, so the region is blanked through end of line rather than
    guessing a delimiter and leaking the payload."""
    bracket = 0
    brace = 0
    k = start
    while k < line_stop:
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            brace += 1
        elif c == "}":
            brace -= 1
        elif brace == 0 and c == "[":
            bracket += 1
        elif brace == 0 and c == "]":
            bracket -= 1
            if bracket == 0:
                return k + 1
        k += 1
    return None


def _latex_scan(text: str, blank_comments: bool) -> str:
    """Left-to-right scanner producing a blanked copy of `text`.

    Blanks, leftmost-construct-wins in a single pass:

      - verbatim-family environments from `LATEX_VERBATIM_ENVIRONMENTS`, from
        the start of the `\\begin{X}` line through the end of the matching
        LINE-ANCHORED `\\end{X}` line. Line-anchored on purpose: a listing whose
        BODY contains the text `\\end{minted}` mid-line must not terminate the
        region early. Unterminated environments blank to EOF.
      - `\\verb<d>...<d>`, `\\verb*<d>...<d>`, `\\lstinline[opts]<d>...<d>`.
        The delimiter is the next non-space character; the region ends at its
        next occurrence on the SAME line (unterminated -> end of line).
        `\\lstinline{...}` is brace-matched instead, since that form is common.
        `[opts]` itself is closed by `_latex_option_block_end` (brace-aware,
        shared with the marker view's `_latex_blank_quoted_spans`); an
        unparseable option block blanks through end of line rather than
        guessing a delimiter and leaking the payload — same rule both callers
        apply.

    `%` comments are always SKIPPED — so a `\\begin{verbatim}` or a `\\verb`
    inside a comment cannot open a region — but only BLANKED when
    `blank_comments` is true. Markers are comments, so they must survive the
    marker pass; heading collection blanks them.

    Backslash parity is structural, not counted: `\\<char>` is consumed as one
    atom unless it starts a construct above, so `\\%` never opens a comment and
    `\\\\%` (two atoms' worth: `\\\\` then `%`) does.

    Length and newline positions are preserved exactly.
    """
    out = list(text)
    n = len(text)

    def blank(start: int, stop: int) -> None:
        for k in range(max(start, 0), min(stop, n)):
            if out[k] != "\n":
                out[k] = " "

    def line_end(pos: int) -> int:
        j = text.find("\n", pos)
        return n if j == -1 else j

    i = 0
    while i < n:
        ch = text[i]
        if ch == "%":
            j = line_end(i)
            if blank_comments:
                blank(i, j)
            i = j
            continue
        if ch != "\\":
            i += 1
            continue

        env_match = _LATEX_BEGIN_RE.match(text, i)
        if env_match and env_match.group(1) in LATEX_VERBATIM_ENVIRONMENTS:
            env = env_match.group(1)
            end_re = re.compile(
                r"^[ \t]*\\end\{" + re.escape(env) + r"\}", re.MULTILINE
            )
            end_match = end_re.search(text, env_match.end())
            stop = n if end_match is None else line_end(end_match.end())
            # Whole lines, \begin/\end included. This scanner builds the
            # HEADING view only, so the question is never "could a marker
            # live here" (it could, and it fires) but "could a sectioning
            # command on the delimiter line be a real heading" — inside a
            # verbatim body it cannot.
            blank(text.rfind("\n", 0, i) + 1, stop)
            i = stop
            continue

        verb_match = _LATEX_INLINE_VERB_RE.match(text, i)
        if verb_match:
            p = verb_match.end()
            if verb_match.group(1) == "lstinline" and p < n and text[p] == "[":
                nl = line_end(p)
                opt_end = _latex_option_block_end(text, p, nl)
                if opt_end is None:
                    # Unparseable option block: blank through end of line
                    # rather than guess a delimiter and leak the payload —
                    # same rule the MARKER view's _latex_blank_quoted_spans
                    # uses for this case.
                    blank(i, nl)
                    i = nl
                    continue
                p = opt_end
            if p >= n or text[p] in " \t\r\n":
                # `\verb` with no delimiter — not a verbatim region, just a
                # command token. Consume the token and move on.
                i = verb_match.end()
                continue
            delim = text[p]
            if delim == "{" and verb_match.group(1) == "lstinline":
                # Brace-matching is only valid for `\lstinline{code}` — a
                # documented form. Plain `\verb`/`\verb*` treat `{` as an
                # ORDINARY delimiter char per the `\verb<d>...<d>` grammar:
                # `\verb{payload{` closes at the SECOND `{`, same as any
                # other delimiter, so it falls through to the `else` branch.
                depth = 0
                k = p
                stop = line_end(p)
                while k < stop:
                    c = text[k]
                    if c == "\\":
                        k += 2
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            stop = k + 1
                            break
                    k += 1
                end = stop
            else:
                close = text.find(delim, p + 1)
                nl = line_end(p + 1)
                end = close + 1 if close != -1 and close < nl else nl
            blank(i, end)
            i = end
            continue

        # ordinary escape / control sequence: consume `\` + one char so the
        # payload can never be re-read as a comment or delimiter.
        i += 2
    return "".join(out)


def _latex_strip_excluded_regions(text: str) -> str:
    """Blank verbatim environments and inline verbatim commands; leave `%`
    comments intact (markers live in them)."""
    return _latex_scan(text, blank_comments=False)


def _latex_blank_quoted_spans(text: str) -> str:
    """LaTeX MARKER view: inline verbatim COMMANDS only.

    `\\verb<d>...<d>`, `\\verb*<d>...<d>`, `\\lstinline<d>...<d>` and
    `\\lstinline[opts]{...}`, each on ONE line. Deliberately none of
    `_latex_scan`'s other machinery: verbatim ENVIRONMENTS are not quoting (a
    marker inside a listing fires), and `%` comments must obviously survive.
    Backticks are not special in LaTeX.

    `\\<char>` is consumed as one atom, which is what makes `\\\\verb|x|`
    (a linebreak macro followed by the literal text `verb|x|`) not a verbatim
    command — the same parity rule the `%` filter uses."""
    out = _quoted_view_base(text)
    n = len(text)

    def line_end(pos: int) -> int:
        j = text.find("\n", pos)
        return n if j == -1 else j

    i = 0
    while i < n:
        if text[i] != "\\":
            i += 1
            continue
        verb_match = _LATEX_INLINE_VERB_RE.match(text, i)
        if not verb_match:
            # ordinary escape / control sequence: consume `\` + one char.
            i += 2
            continue
        p = verb_match.end()
        nl = line_end(i)
        if verb_match.group(1) == "lstinline" and p < nl and text[p] == "[":
            opt_end = _latex_option_block_end(text, p, nl)
            if opt_end is None:
                # Unparseable option block: blank through end of line rather
                # than guess a delimiter and leak the payload.
                _fill_quoted(out, i, nl)
                i = nl
                continue
            p = opt_end
        if p >= nl or text[p] in " \t\r":
            # `\verb` with no delimiter — just a command token.
            i = verb_match.end()
            continue
        delim = text[p]
        if delim == "{" and verb_match.group(1) == "lstinline":
            depth = 0
            k = p
            end = nl
            while k < nl:
                c = text[k]
                if c == "\\":
                    k += 2
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = k + 1
                        break
                k += 1
        else:
            close = text.find(delim, p + 1)
            end = close + 1 if close != -1 and close < nl else nl
        _fill_quoted(out, i, end)
        i = max(end, i + 1)
    return "".join(out)


def _latex_build_pattern(prefixes: list | None, relaxed: bool = False) -> re.Pattern:
    """Compile a regex matching LaTeX marker comments, anywhere on a line.

    Mirrors the typst grammar with `%` as the carrier and end-of-line as the
    terminator:

      permissive (default)  `% TYPE(author): text`, uppercase TYPE, author
                            parenthetical REQUIRED, case-sensitive prefix
      closed list           exactly the listed prefixes, case-insensitive,
                            parenthetical optional; callers enforce any
                            additional author or authorization requirements

    There is no `^[ \\t]*` anchor, so this pattern DOES match at an escaped
    percent. Backslash parity is therefore checked after the fact, by the
    profile's `_match_filter` (`_latex_backslash_run_even` against the RAW
    text at `match.start()`): an odd run means `\\%`, a literal percent, and
    the match is dropped. The regex alone cannot do this — a lookbehind cannot
    count an unbounded backslash run.

    Closed-list mode does NOT accept `.` as a prefix delimiter, for the same
    reason typst does not: there is no `% TODO. text` convention here, and
    accepting `.` widens the control-prefix surface for nothing.

    Examples (permissive default — all match, subject to the parity filter):
      % TODO(jason): foo ;;
      %% TODO(jason): after a divider ;;
      \\section{X} % NOTE(jason): trailing comment ;;
      \\\\% TODO(jason): even backslash run, a real comment ;;
    Examples (permissive default — non-matches):
      Sales rose 100\\% TODO(jason): nope ;;   (odd run: escaped percent)
      \\verb|% TODO(jason): nope ;;|           (inline verbatim command)
      % TODO: foo ;;                          (no author parenthetical)
      % todo(jason): foo ;;                   (lowercase prefix)

    With ``relaxed=True`` this builds the near-miss variant instead: any-case
    type, optional author, `:`/`.` delimiter or parenthetical still required.
    The parity filter is a profile `_match_filter`, so it applies to the
    relaxed pass unchanged — `100\\% TODO: x` is not a near-miss either. When
    ``prefixes`` is given, the type alternative is constrained to that list
    (case-insensitively), same as closed-list mode above — under
    `--prefixes NOTE`, `% todo(jason): x ;;` and `% TODO: x ;;` are not
    candidates either, since no case/author fix would make them fire.
    """
    if relaxed:
        if prefixes:
            alt = "|".join(re.escape(p) for p in prefixes)
            return re.compile(
                rf"%[ \t]*(?P<type>{alt})(?=[ \t]|\(|:|\.|$)[ \t]*"
                r"(?:\((?P<author>[^)\n]*)\)[ \t]*[:.]?|[:.])[ \t]*"
                r"(?P<text>[^\n]*)",
                re.IGNORECASE | re.MULTILINE,
            )
        return re.compile(
            r"%[ \t]*(?P<type>[A-Za-z][A-Za-z_-]+)[ \t]*"
            r"(?:\((?P<author>[^)\n]*)\)[ \t]*[:.]?|[:.])[ \t]*"
            r"(?P<text>[^\n]*)",
            re.MULTILINE,
        )
    if not prefixes:
        return re.compile(
            r"%[ \t]*(?P<type>[A-Z][A-Z_-]+)[ \t]*\((?P<author>[^)\n]+)\)"
            r"[ \t]*[:.]?[ \t]*(?P<text>[^\n]*)",
            re.MULTILINE,
        )
    alt = "|".join(re.escape(p) for p in prefixes)
    return re.compile(
        rf"%[ \t]*(?P<type>{alt})(?=[ \t]|\(|:|$)"
        r"(?:\((?P<author>[^)\n]*)\))?[ \t]*[:.]?[ \t]*(?P<text>[^\n]*)",
        re.IGNORECASE | re.MULTILINE,
    )


def _latex_match_is_real_comment(raw: str, match: re.Match) -> bool:
    """Profile `_match_filter`: the matched `%` is a real comment start only
    when the backslash run immediately before it is EVEN. See
    `_latex_backslash_run_even`."""
    return _latex_backslash_run_even(raw, match.start())


def _latex_skip_gap(text: str, i: int) -> int:
    """Advance past whitespace and whole `%` comments (a comment also eats its
    newline and the next line's leading whitespace, exactly as TeX does)."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "%":
            j = text.find("\n", i)
            if j == -1:
                return n
            i = j + 1
            while i < n and text[i] in " \t":
                i += 1
        elif c in " \t\r\n":
            i += 1
        else:
            break
    return i


def _latex_read_title(text: str, pos: int) -> str:
    """Read a sectioning command's braced title starting at `pos` (just after
    the command name and its optional `*`).

    Skips an optional balanced `[short title]` argument — the short title is
    NOT the heading title — then brace-matches the `{...}` group. Nested braces
    and macros are kept as LITERAL TEXT: `\\section{The \\textbf{X} case}` gives
    the title `The \\textbf{X} case`. Rendering LaTeX markup into plain text is
    a rabbit hole (`\\cite`, `\\ref`, `$math$`, custom macros) with no correct
    answer; the chain is a locator, and the source form is what the user will
    recognize and can grep for.

    `%` comments inside the title are skipped along with the newline and the
    following line's indentation, so a title broken across lines with a
    trailing comment rejoins the way LaTeX would set it. Escaped `\\{` / `\\}`
    are kept verbatim and do not move the brace depth. Returns "" when there is
    no braced argument (e.g. `\\part` used bare)."""
    n = len(text)
    i = _latex_skip_gap(text, pos)
    if i < n and text[i] == "[":
        depth = 0
        while i < n:
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c == "%":
                j = text.find("\n", i)
                i = n if j == -1 else j + 1
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        i = _latex_skip_gap(text, i)
    if i >= n or text[i] != "{":
        return ""
    depth = 0
    buf: list[str] = []
    closed = False
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            buf.append(text[i : i + 2])
            i += 2
            continue
        if c == "%":
            j = text.find("\n", i)
            if j == -1:
                break
            i = j + 1
            while i < n and text[i] in " \t":
                i += 1
            continue
        if c == "{":
            depth += 1
            if depth > 1:
                buf.append(c)
            i += 1
            continue
        if c == "}":
            depth -= 1
            i += 1
            if depth == 0:
                closed = True
                break
            buf.append(c)
            continue
        buf.append(c)
        i += 1
    if not closed:
        # The outer `{` never closed (EOF, or a comment that ate to EOF with
        # no trailing newline) — there is no title, not "whatever we
        # accumulated". Otherwise `\section{Broken` with no closing brace
        # would return the rest of the file as its title.
        return ""
    return re.sub(r"\s+", " ", "".join(buf)).strip()


def _latex_backslash_run_even(text: str, pos: int) -> bool:
    """True when the run of consecutive `\\` characters immediately
    preceding `text[pos]` has EVEN length (zero included).

    `_latex_scan` consumes `\\<char>` as one atom but never rewrites the
    source, so `_LATEX_HEADING_RE.finditer` can land a match on the SECOND
    backslash of `\\\\section{Fake}` — a linebreak macro followed by literal
    text, not a sectioning command — as readily as on a real `\\section`.
    Backslash-run parity recovers the atom boundary after the fact: an EVEN
    run before the match means the matched `\\` starts its own atom (`\\section`,
    or `\\\\\\section` — a linebreak then a genuine command); an ODD run means
    the matched `\\` is itself the payload of the PRECEDING escape
    (`\\\\section`, `\\\\\\\\section` — not a command)."""
    count = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        count += 1
        i -= 1
    return count % 2 == 0


def _latex_collect_headings(cleaned_text: str) -> list:
    """(line_idx0, level, title) for every sectioning command in the cleaned
    text.

    Commands are located in a comment-blanked copy (so a commented-out
    `% \\section{Draft}` is not a heading), but titles are read from the
    cleaned text itself, where comments are still present — see
    `_latex_read_title` for why that matters.

    NO single-top-level drop (judgment call, Phase 3). Markdown and typst drop
    a lone level-1 heading because a lone `# Title` / `= Title` IS the document
    title. LaTeX documents put their title in `\\title{...}`, which is not a
    heading at all, so a lone `\\section` is a real section — dropping it would
    delete the only chain a single-section paper has. The heuristic also fires
    on the wrong thing here: after normalization `\\section` is level 1, so a
    book with one `\\chapter` (level 0) would keep it while a paper with one
    `\\section` would lose it, which is backwards."""
    located = _latex_scan(cleaned_text, blank_comments=True)
    headings = []
    for m in _LATEX_HEADING_RE.finditer(located):
        if not _latex_backslash_run_even(located, m.start()):
            # Odd run: the matched `\` is escaped by the backslash before it
            # (`\\section`), so this is a linebreak macro followed by literal
            # text — not a real sectioning command.
            continue
        title = _latex_read_title(cleaned_text, m.end())
        if title:
            headings.append(
                (
                    cleaned_text.count("\n", 0, m.start()),
                    LATEX_HEADING_LEVELS[m.group(1)],
                    title,
                )
            )
    return headings


LATEX = Profile(
    name="latex",
    extensions=(".tex",),
    # No Obsidian probe for LaTeX: the guard is an Obsidian + HTML-comment
    # mechanism and .tex files are edited in Overleaf / TeXShop / an IDE.
    # Sign-off is the composition guard.
    cursor_probe=False,
    default_signoff=True,
    marker_example="% TODO(jason): text ;;",
    # PAUSE is sign-off-exempt (matching typst), so no pre-typed `;;`.
    pause_line="% PAUSE(jason): ...",
    comment_desc="a % line comment",
    _pattern_builder=_latex_build_pattern,
    _heading_collector=_latex_collect_headings,
    _region_scanner=_latex_strip_excluded_regions,
    _quoted_span_blanker=_latex_blank_quoted_spans,
    _match_filter=_latex_match_is_real_comment,
)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

PROFILES: dict[str, Profile] = {p.name: p for p in (MARKDOWN, TYPST, LATEX)}

_BY_EXTENSION: dict[str, Profile] = {
    ext: p for p in PROFILES.values() for ext in p.extensions
}


def get_profile(path: Path, override: str | None = None) -> Profile:
    """Profile for a watched file: `--profile NAME` wins, else the file's
    lowercased extension, else markdown.

    Markdown is the default for UNKNOWN extensions on purpose — the skill's
    sidecar is always `.md`, extensionless vault notes are markdown, and a
    format we haven't taught the watcher yet degrades to "HTML-comment
    markers, markdown exclusions" rather than to nothing at all."""
    if override:
        return PROFILES[override]
    return _BY_EXTENSION.get(path.suffix.lower(), MARKDOWN)
