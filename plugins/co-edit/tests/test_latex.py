"""Pure LaTeX profile regressions; live LaTeX editing is not supported.

Covers parity, inline/verbatim scanners, carrier grammar, and heading parsing.
No watcher processes, protocol authorization, or file writes.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import profiles as P

FAILURES = []

def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


LATEX = P.LATEX
PAT = LATEX.build_pattern(None)
SAMPLE_TEX = Path(__file__).resolve().parent / "fixtures" / "contract" / "sample.tex"


def markers_in(raw, pattern=PAT):
    """Read carrier matches verbatim, without runtime authorization or IDs."""
    view = LATEX.blank_quoted_spans(raw)
    return [
        (match.group("type"), raw[match.start("text"):match.end("text")])
        for match in pattern.finditer(view)
        if LATEX.accept_match(raw, match)
    ]


def shape_ok(raw, cleaned):
    """The exclusion contract: same length, same newline positions."""
    return len(raw) == len(cleaned) and [i for i, c in enumerate(raw) if c == "\n"] == [
        i for i, c in enumerate(cleaned) if c == "\n"
    ]

for filename, override, expected in [
    ("paper.tex", None, "latex"),
    ("PAPER.TEX", None, "latex"),
    ("paper.TeX", None, "latex"),
    ("paper.tex", "markdown", "markdown"),
    ("paper.md", "latex", "latex"),
]:
    got = P.get_profile(Path("/tmp") / filename, override)
    check(
        f"dispatch: {filename} (override={override!r}) -> {expected}",
        got.name == expected,
        f"got {got.name}",
    )

# =====================================================================
# (b) scanner: backslash parity
# =====================================================================
#
# Parity is asserted through the COMMENT-BLANKING mode of the scanner, which is
# the mode heading collection uses: whatever it blanks, it considered a comment.

parity_cases = [
    # (source, is_a_comment, why)
    ("100% off\n", True, "bare % starts a comment"),
    ("100\\% off\n", False, "\\% — odd backslash run, escaped literal percent"),
    ("100\\\\% off\n", True, "\\\\% — even run, linebreak then a real comment"),
    ("100\\\\\\% off\n", False, "\\\\\\% — odd run, linebreak then literal percent"),
    ("100\\\\\\\\% off\n", True, "\\\\\\\\% — even run, real comment"),
]
for src, is_comment, why in parity_cases:
    blanked = P._latex_scan(src, blank_comments=True)
    got = "off" not in blanked
    check(f"parity: {why}", got == is_comment, f"{src!r} -> {blanked!r}")
    check(
        f"parity: length/newline preserved for {src!r}",
        shape_ok(src, blanked),
    )

check(
    "parity: an escaped % cannot carry a marker — the pattern matches, the "
    "profile's accept_match post-filter drops it",
    markers_in("Sales rose 100\\% TODO(jason): nope\n") == [],
)

check(
    "parity: a REAL mid-line comment after an EVEN backslash run IS a marker",
    markers_in("Sales rose\\\\% TODO(jason): yes\n") == [("TODO", "yes")],
    f"{markers_in('Sales rose\\\\% TODO(jason): yes')}",
)
for src, fires, why in [
    ("100\\% TODO(jason): x\n", False, "1 backslash — escaped percent"),
    ("100\\\\% TODO(jason): x\n", True, "2 backslashes — real comment"),
    ("100\\\\\\% TODO(jason): x\n", False, "3 backslashes — escaped percent"),
    ("100\\\\\\\\% TODO(jason): x\n", True, "4 backslashes — real comment"),
]:
    check(
        f"parity post-filter: {'fires' if fires else 'does not fire'} — {why}",
        bool(markers_in(src)) == fires,
        f"{markers_in(src)}",
    )

# Escaped braces do not move brace depth: without that, the title's `{` would
# stay open and swallow the rest of the document.
esc_braces = "\\section{A \\{ literal \\} brace}\n\nBody.\n"
check(
    "escaped braces: \\{ and \\} do not count toward brace balance",
    LATEX.collect_headings(LATEX.strip_excluded_regions(esc_braces))
    == [(0, 1, "A \\{ literal \\} brace")],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(esc_braces))}",
)


# =====================================================================
# (c) scanner: verbatim environments
#
# Verbatim environments are a HEADING-view exclusion only. A `\section` in a
# listing must not become "under heading X" enrichment — but a marker a user
# typed inside a listing is a marker, so it fires. Each case below therefore
# asserts BOTH: what the marker pass yields, and that the heading view still
# blanks the region.
# =====================================================================


def heading_view_blanks(raw, needle):
    """The heading view (strip_excluded_regions) hides `needle`."""
    return needle not in LATEX.strip_excluded_regions(raw)


verbatim_env = (
    "Before.\n"
    "\\begin{verbatim}\n"
    "% TODO(jason): inside verbatim\n"
    "\\end{verbatim}\n"
    "% TODO(jason): after verbatim\n"
)
check(
    "verbatim env: a marker inside the body FIRES (verbatim is not quoting)",
    markers_in(verbatim_env)
    == [("TODO", "inside verbatim"), ("TODO", "after verbatim")],
    f"{markers_in(verbatim_env)}",
)
check(
    "verbatim env: the HEADING view still blanks the body",
    heading_view_blanks(verbatim_env, "inside verbatim"),
)

# The `\end{X}` search is LINE-ANCHORED: delimiter-looking text in the body
# must not terminate the region early, or a `\section` below it would leak
# into the heading chain.
minted_lookalike = (
    "\\begin{minted}{python}\n"
    "print('\\\\end{minted} is just a string here')\n"
    "\\section{Fake heading inside the listing}\n"
    "\\end{minted}\n"
    "\\section{Genuinely after}\n"
)
check(
    "verbatim env: a mid-line \\end{minted} lookalike does NOT close the region "
    "(heading view)",
    LATEX.collect_headings(LATEX.strip_excluded_regions(minted_lookalike))
    == [(4, 1, "Genuinely after")],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(minted_lookalike))}",
)

commented_begin = (
    "% \\begin{verbatim} this is only talked about, not opened\n"
    "% TODO(jason): must still fire\n"
)
check(
    "verbatim env: \\begin{verbatim} inside a % comment does not open a region",
    markers_in(commented_begin) == [("TODO", "must still fire")],
    f"{markers_in(commented_begin)}",
)

unterminated = (
    "Before.\n"
    "% TODO(jason): before the env\n"
    "\\begin{lstlisting}\n"
    "% TODO(jason): inside an unterminated listing\n"
    "more listing text, no \\end ever\n"
)
check(
    "verbatim env: markers inside an unterminated environment fire too",
    markers_in(unterminated)
    == [
        ("TODO", "before the env"),
        ("TODO", "inside an unterminated listing"),
    ],
    f"{markers_in(unterminated)}",
)
check(
    "verbatim env: an unterminated environment still blanks to EOF in the HEADING view",
    heading_view_blanks(unterminated, "inside an unterminated listing"),
)

allowlist_only = (
    "\\begin{itemize}\n"
    "% TODO(jason): inside itemize, still a marker\n"
    "\\end{itemize}\n"
    "\\begin{figure}\n"
    "% NOTE(jason): inside figure, still a marker\n"
    "\\end{figure}\n"
)
check(
    "verbatim env: the allowlist is an allowlist — itemize/figure are NOT excluded",
    markers_in(allowlist_only)
    == [
        ("TODO", "inside itemize, still a marker"),
        ("NOTE", "inside figure, still a marker"),
    ],
    f"{markers_in(allowlist_only)}",
)

for env in sorted(P.LATEX_VERBATIM_ENVIRONMENTS):
    src = f"\\begin{{{env}}}\n% TODO(jason): x\n\\end{{{env}}}\n"
    check(
        f"verbatim env: a marker inside '{env}' FIRES",
        markers_in(src) == [("TODO", "x")],
        f"{markers_in(src)}",
    )
    check(
        f"verbatim env: '{env}' is on the allowlist and blanks its body in the "
        "heading view",
        heading_view_blanks(src, "TODO(jason)"),
    )

check(
    "verbatim env: blanking is length- and newline-preserving",
    shape_ok(minted_lookalike, LATEX.strip_excluded_regions(minted_lookalike))
    and shape_ok(unterminated, LATEX.strip_excluded_regions(unterminated)),
)


# =====================================================================
# (d) scanner: inline verbatim commands
# =====================================================================

inline_cases = [
    ("\\verb|% TODO(jason): x| trailing\n", [], "\\verb| ... |"),
    ("\\verb*+% TODO(jason): x+ trailing\n", [], "\\verb*+ ... +"),
    ("\\lstinline!% TODO(jason): x! trailing\n", [], "\\lstinline! ... !"),
    (
        "\\lstinline[language=Python]{% TODO(jason): x}\n",
        [],
        "\\lstinline[opts]{ ... }",
    ),
    (
        "\\verb|literal|\n% TODO(jason): after the verb\n",
        [("TODO", "after the verb")],
        "text after a closed \\verb still fires",
    ),
    (
        "\\verbatim is not a verb command\n% TODO(jason): fires\n",
        [("TODO", "fires")],
        "\\verbatim is not matched as \\verb + 'atim'",
    ),
    (
        "\\verbose{x}\n% TODO(jason): fires\n",
        [("TODO", "fires")],
        "\\verbose is not matched as \\verb + 'ose'",
    ),
]
for src, expected, why in inline_cases:
    check(f"inline verbatim: {why}", markers_in(src) == expected, f"{markers_in(src)}")

unterminated_verb = (
    "\\verb|% TODO(jason): unterminated\n% TODO(jason): next line\n"
)
check(
    "inline verbatim: an unterminated \\verb blanks only to end of line",
    markers_in(unterminated_verb) == [("TODO", "next line")],
    f"{markers_in(unterminated_verb)}",
)
check(
    "inline verbatim: blanking is length- and newline-preserving",
    all(shape_ok(src, LATEX.strip_excluded_regions(src)) for src, _, _ in inline_cases)
    and all(shape_ok(src, LATEX.blank_quoted_spans(src)) for src, _, _ in inline_cases),
)

# The MARKER view's \lstinline option block is BRACE-AWARE: a `]` nested inside
# braces must not end the option group, or the delimiter is misidentified and
# the payload leaks as a live marker.
lstinline_nested = [
    (
        "\\lstinline[language={[LaTeX]TeX}]{% TODO(jason): quoted}\n",
        [],
        "a `]` inside braces does not close the option block",
    ),
    (
        "\\lstinline[a={x[1]},b=2]{% TODO(jason): quoted} after\n",
        [],
        "several options, one with nested brackets inside braces",
    ),
    (
        "\\lstinline[escape=\\]]{% TODO(jason): quoted}\n",
        [],
        "an escaped `]` inside the option block",
    ),
    (
        "\\lstinline[unclosed option block {% TODO(jason): leak\n"
        "% TODO(jason): next line\n",
        [("TODO", "next line")],
        "an unparseable option block blanks through end of line",
    ),
]
for src, expected, why in lstinline_nested:
    check(
        f"lstinline options: {why}", markers_in(src) == expected, f"{markers_in(src)}"
    )
check(
    "lstinline options: brace-aware blanking is length/newline preserving",
    all(shape_ok(src, LATEX.blank_quoted_spans(src)) for src, _, _ in lstinline_nested),
)
check(
    "latex: backticks are NOT special — a backtick does not open a quoted span",
    markers_in("A ` backtick then % TODO(jason): fires\n") == [("TODO", "fires")],
    f"{markers_in('A ` backtick then % TODO(jason): fires')}",
)
check(
    "latex: a marker WRAPPED in backticks fires too (they are opening quotes "
    "in LaTeX, not a code-span delimiter)",
    markers_in("``% TODO(jason): fires anyway''\n")
    == [("TODO", "fires anyway''")],
    f"{markers_in(chr(96) * 2 + '% TODO(jason): x' + chr(39) * 2)}",
)


# =====================================================================
# (e) marker grammar
# =====================================================================

pattern_cases = [
    ("% TODO(jason): plain\n", True, "standalone marker"),
    ("    % TODO(jason): indented\n", True, "indented standalone marker"),
    ("\t% TODO(jason): tabbed\n", True, "tab-indented standalone marker"),
    # The standalone-line anchor is GONE.
    ("\\section{X} % NOTE(jason): trailing\n", True, "trailing comment"),
    ("%% TODO(jason): double percent\n", True, "%% divider comment"),
    ("\\\\% TODO(jason): even backslash run\n", True, "\\\\% is a real comment"),
    ("Prose 50\\% TODO(jason): escaped\n", False, "escaped % (parity filter)"),
    ("% TODO: no author\n", False, "no author parenthetical"),
    ("% todo(jason): lowercase\n", False, "lowercase prefix"),
    ("% just a normal latex comment\n", False, "plain comment"),
    ("\\verb|% TODO(jason): quoted|\n", False, "inside \\verb (the ONE exclusion)"),
]
for src, should_match, why in pattern_cases:
    view = LATEX.blank_quoted_spans(src)
    got = any(LATEX.accept_match(src, m) for m in PAT.finditer(view))
    check(
        f"latex pattern: {'matches' if should_match else 'rejects'} — {why}",
        got == should_match,
        repr(src),
    )

two = "% TODO(jason): one\n% NOTE(jason): two\n"
found = [(m.group("type"), m.group("text")) for m in PAT.finditer(two)]
check(
    "latex pattern: consecutive markers match in document order, non-overlapping",
    found == [("TODO", "one"), ("NOTE", "two")],
    f"{found}",
)
check(
    "latex pattern: the text group cannot cross a newline",
    all("\n" not in t for _, t in found),
)

closed = LATEX.build_pattern(["TODO", "PAUSE"])
check(
    "latex pattern (closed list): case-insensitive, parenthetical optional",
    bool(closed.search("% todo: lowercase closed-list\n"))
    and bool(closed.search("% TODO(jason): with author\n")),
)
check(
    "latex pattern (closed list): a prefix not on the list is rejected",
    not closed.search("% QUESTION(jason): off the list\n"),
)
check(
    "latex pattern (closed list): no longer standalone-anchored",
    bool(closed.search("\\section{X} % TODO(jason): trailing\n")),
)
# `.` is not a closed-list prefix delimiter for latex either.
_tex_note = LATEX.build_pattern(["note", "PAUSE"])
check(
    "latex pattern (closed list): '%pause.example' is not a PAUSE control marker",
    not _tex_note.search("URL-ish %pause.example.com/assets\n"),
)
check(
    "latex pattern (closed list): a real listed marker still matches",
    bool(_tex_note.search("% note(jason): still works\n")),
)

tex_raw = SAMPLE_TEX.read_text(encoding="utf-8")
tex_cleaned = LATEX.strip_excluded_regions(tex_raw)
check(
    "contract tex: exclusion cleaning preserves length and newline positions",
    shape_ok(tex_raw, tex_cleaned),
)
check(
    "contract tex: % comments SURVIVE exclusion cleaning (markers live in them)",
    "% TODO(jason): first latex marker" in tex_cleaned,
)

check(
    "contract tex: line 18's \\verb span is filled in the MARKER view",
    "TODO(jason)" not in LATEX.blank_quoted_spans(tex_raw).split("\n")[17],
    repr(LATEX.blank_quoted_spans(tex_raw).split("\n")[17]),
)

tex_headings = LATEX.collect_headings(tex_cleaned)
check(
    "contract tex: headings preserve nested titles and physical line numbers",
    tex_headings
    == [
        (10, 1, "Long \\textbf{nested} title continued"),
        (19, 2, "Starred sub"),
    ],
    f"{tex_headings}",
)

ladder = (
    "\\part{P}\n"
    "\\chapter{C}\n"
    "\\section{S}\n"
    "\\subsection{SS}\n"
    "\\subsubsection{SSS}\n"
    "\\paragraph{Pa}\n"
    "\\subparagraph{SPa}\n"
    "% TODO(jason): deepest\n"
)
ladder_headings = LATEX.collect_headings(LATEX.strip_excluded_regions(ladder))
check(
    "headings: the full 7-command ladder is strictly increasing in level",
    [lvl for _, lvl, _ in ladder_headings] == [-1, 0, 1, 2, 3, 4, 5],
    f"{ladder_headings}",
)

siblings = (
    "\\section{One}\n"
    "\\subsection{A}\n"
    "\\subsection{B}\n"
    "\\section{Two}\n"
    "\\subsection{C}\n"
)
sib_headings = LATEX.collect_headings(LATEX.strip_excluded_regions(siblings))

check(
    "headings: \\section -> level 1 nests exactly like markdown H1 > H2",
    [lvl for _, lvl, _ in sib_headings]
    == [
        lvl
        for _, lvl, _ in P.MARKDOWN.collect_headings("# One\n## A\n## B\n# Two\n## C\n")
    ],
    f"{sib_headings}",
)

# JUDGMENT CALL: no single-top-level drop for latex. A lone \section is a real
# section (LaTeX titles live in \title{}), unlike a lone markdown H1.
lone = "\\title{The Paper}\n\\section{Only Section}\n% TODO(jason): x\n"
lone_headings = LATEX.collect_headings(LATEX.strip_excluded_regions(lone))
check(
    "headings: a LONE \\section is KEPT (no single-top-level drop for latex)",
    lone_headings == [(1, 1, "Only Section")],
    f"{lone_headings}",
)
check(
    "headings: markdown still DOES drop its lone H1 (behavior unchanged)",
    P.MARKDOWN.collect_headings("# Only\n\ntext\n") == [],
)
check(
    "headings: \\title{...} is not a heading",
    all(t != "The Paper" for _, _, t in lone_headings),
)

heading_cases = [
    ("\\section*{Starred}\n", [(0, 1, "Starred")], "starred variant, same level"),
    (
        "\\section[Short]{Long title}\n",
        [(0, 1, "Long title")],
        "optional short title is skipped, braced title wins",
    ),
    (
        "\\section[Short {with} braces]{Long}\n",
        [(0, 1, "Long")],
        "short title with braces inside balanced brackets",
    ),
    (
        "\\section{The \\textbf{X} case}\n",
        [(0, 1, "The \\textbf{X} case")],
        "nested braces/macros kept as literal source text",
    ),
    (
        "\\section{Split\nacross lines}\n",
        [(0, 1, "Split across lines")],
        "multiline title joins on whitespace",
    ),
    (
        "% \\section{Commented out}\n\\section{Real}\n",
        [(1, 1, "Real")],
        "a commented-out sectioning command is not a heading",
    ),
    ("\\sectionmark{Running head}\n", [], "\\sectionmark is not \\section"),
    ("\\partname\n", [], "\\partname is not \\part"),
    ("\\section\n", [], "a bare sectioning command with no braced title"),
]
for src, expected, why in heading_cases:
    got = LATEX.collect_headings(LATEX.strip_excluded_regions(src))
    check(f"headings: {why}", got == expected, f"{got}")

check(
    "headings: a sectioning command inside a verbatim body is not a heading",
    LATEX.collect_headings(
        LATEX.strip_excluded_regions(
            "\\begin{verbatim}\n\\section{Fake}\n\\end{verbatim}\n\\section{Real}\n"
        )
    )
    == [(3, 1, "Real")],
)

# The HEADING view's \lstinline option block now shares the same brace-aware
# `_latex_option_block_end` the MARKER view uses (see `lstinline_nested`
# above) instead of a flat first-`]` search — a `\section` inside the
# option's payload must not become a heading, and a `\section` after the
# construct on the same line must still be one either way.
heading_lstinline_cases = [
    (
        "\\lstinline[language={[LaTeX]TeX}]{\\section{Inside}}\\section{After}\n",
        [(0, 1, "After")],
        "a `]` inside braces does not close the option block early, so the "
        "payload's \\section stays hidden while the same-line \\section "
        "after the construct still fires",
    ),
    (
        "\\lstinline[unclosed {\\section{Fake}\n\\section{Next line}\n",
        [(1, 1, "Next line")],
        "an unparseable option block blanks through end of line, same as "
        "the marker view",
    ),
]
for src, expected, why in heading_lstinline_cases:
    got = LATEX.collect_headings(LATEX.strip_excluded_regions(src))
    check(f"headings: {why}", got == expected, f"{got}")

# =====================================================================
# (i) bug-fix regressions: backslash-parity headings, unterminated titles,
#     \verb{...} delimiter gating, plus untested adversarial cases
# =====================================================================

# --- Bug 1: escaped section commands must not become false headings -------
#
# `_latex_scan` consumes `\<char>` as one atom without rewriting the source,
# so the heading regex can land on the SECOND backslash of `\\section{Fake}`.
# Backslash-run parity at the match site is the fix: an EVEN run of `\`
# immediately before the match means it's a real command; an ODD run means
# it's the payload of the preceding escape.
escaped_headings = (
    "\\\\section{Fake}\n"  # 2 literal backslashes -> odd run before match -> NOT a heading
    "\\section{Real}\n"  # 1 literal backslash -> even (0) run -> a real heading
    "\\\\\\section{Real2}\n"  # 3 literal backslashes -> even (2) run -> linebreak + real heading
    "\\\\\\\\section{Fake2}\n"  # 4 literal backslashes -> odd (3) run -> NOT a heading
)
escaped_result = LATEX.collect_headings(LATEX.strip_excluded_regions(escaped_headings))
check(
    "bug1: \\\\section{Fake} beside \\section{Real} — only Real is a heading",
    escaped_result == [(1, 1, "Real"), (2, 1, "Real2")],
    f"{escaped_result}",
)

# --- Bug 2: unterminated titles must not swallow the rest of the file ------
unterminated_title = "\\section{Broken\nrest of file with no closing brace...\n"
check(
    "bug2: \\section{Broken with no closing brace yields no heading",
    LATEX.collect_headings(LATEX.strip_excluded_regions(unterminated_title)) == [],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(unterminated_title))}",
)
# Properly closed titles must be unaffected by the closed-tracking fix.
still_closes = "\\section{Fine}\n\\section{Also fine}\n"
check(
    "bug2: properly closed titles are unaffected",
    LATEX.collect_headings(LATEX.strip_excluded_regions(still_closes))
    == [(0, 1, "Fine"), (1, 1, "Also fine")],
)

# --- Bug 3: \verb{...} is NOT brace-matched (only \lstinline{...} is) ------
verb_brace = "\\verb{payload{ \\section{Real}\n"
check(
    "bug3: \\verb{payload{ closes at the SECOND { — an ordinary delimiter, not a brace match",
    LATEX.collect_headings(LATEX.strip_excluded_regions(verb_brace))
    == [(0, 1, "Real")],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(verb_brace))}",
)
check(
    "bug3: \\lstinline{...} still brace-matches (unaffected by the \\verb gate)",
    LATEX.collect_headings(
        LATEX.strip_excluded_regions(
            "\\lstinline{a { nested } brace}\n\\section{Real}\n"
        )
    )
    == [(1, 1, "Real")],
)

# --- adversarial: \verb with {, %, and \ as delimiters ---------------------
verb_percent = "\\verb%payload%tail\n"
scanned_verb_percent = P._latex_scan(verb_percent, blank_comments=False)
check(
    "adversarial: \\verb%...% treats % as an ORDINARY delimiter, not a comment start "
    "(blanked even with blank_comments=False, which real comments never are)",
    "payload" not in scanned_verb_percent and "tail" in scanned_verb_percent,
    f"{scanned_verb_percent!r}",
)

verb_backslash_delim = "\\verb\\payload\\tail\n"
scanned_verb_backslash = P._latex_scan(verb_backslash_delim, blank_comments=True)
check(
    "adversarial: \\verb\\...\\ — a backslash can itself be the delimiter, no crash",
    "payload" not in scanned_verb_backslash and "tail" in scanned_verb_backslash,
    f"{scanned_verb_backslash!r}",
)
check(
    "adversarial: \\verb with {, %, \\ delimiters is length/newline preserving",
    shape_ok(verb_brace, LATEX.strip_excluded_regions(verb_brace))
    and shape_ok(verb_percent, LATEX.strip_excluded_regions(verb_percent))
    and shape_ok(
        verb_backslash_delim, LATEX.strip_excluded_regions(verb_backslash_delim)
    ),
)

# --- adversarial: \verb at end of line / with no delimiter -----------------
verb_eol = "\\verb\n% TODO(jason): after verb eol\n"
check(
    "adversarial: \\verb at end of line with no delimiter is just a command token",
    markers_in(verb_eol) == [("TODO", "after verb eol")],
    f"{markers_in(verb_eol)}",
)
verb_eof = "\\verb"
scanned_verb_eof = P._latex_scan(verb_eof, blank_comments=True)
check(
    "adversarial: \\verb at EOF (no delimiter at all) does not crash",
    scanned_verb_eof == verb_eof,
    f"{scanned_verb_eof!r}",
)

# --- adversarial: a lone backslash as the last character of the file -------
lone_backslash = "text ends with a lone backslash \\"
scanned_lone_backslash = P._latex_scan(lone_backslash, blank_comments=True)
check(
    "adversarial: a lone trailing backslash does not crash and preserves length",
    scanned_lone_backslash == lone_backslash
    and len(scanned_lone_backslash) == len(lone_backslash),
    f"{scanned_lone_backslash!r}",
)

# --- adversarial: nested square brackets in the optional short-title arg ---
nested_brackets = "\\section[short [inner] bracket]{Title}\n"
check(
    "adversarial: nested square brackets in \\section[short [inner]]{Title} are balanced",
    LATEX.collect_headings(LATEX.strip_excluded_regions(nested_brackets))
    == [(0, 1, "Title")],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(nested_brackets))}",
)

# --- adversarial: two different verbatim environments nested --------------
# `\begin{verbatim}` opens first, so it wins; the whole `\begin{minted}` line
# inside its body is just body text and never opens a second region. Close is
# line-anchored on the OUTER environment's `\end{verbatim}`. Marker-wise this
# is now moot (both markers fire), so the HEADING view is what asserts it.
nested_envs = (
    "\\begin{verbatim}\n"
    "\\begin{minted}\n"
    "\\section{Inside both}\n"
    "\\end{verbatim}\n"
    "\\section{After outer verbatim}\n"
)
check(
    "adversarial: nested verbatim environments — outer wins, line-anchored close",
    LATEX.collect_headings(LATEX.strip_excluded_regions(nested_envs))
    == [(4, 1, "After outer verbatim")],
    f"{LATEX.collect_headings(LATEX.strip_excluded_regions(nested_envs))}",
)
check(
    "adversarial: markers inside those nested environments all FIRE",
    markers_in(
        "\\begin{verbatim}\n"
        "\\begin{minted}\n"
        "% TODO(jason): inside both\n"
        "\\end{verbatim}\n"
        "% TODO(jason): after outer verbatim\n"
    )
    == [("TODO", "inside both"), ("TODO", "after outer verbatim")],
)

# Physical line endings must not leak into heading titles.
crlf = "\\section{Doc}\r\n\\subsection{Sec}\r\n% TODO(jason): crlf marker\r\n"
check(
    "latex CRLF heading positions",
    LATEX.collect_headings(LATEX.strip_excluded_regions(crlf))
    == [(0, 1, "Doc"), (1, 2, "Sec")],
)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("all latex profile checks passed")
