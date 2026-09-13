"""Pure Markdown/Typst profile parser regressions.

Carrier parsing is independent of live runtime authorization and writer behavior.
The fixture payloads may contain literal semicolons; no sign-off is inferred here.
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


CONTRACT_DIR = Path(__file__).resolve().parent / "fixtures" / "contract"
SAMPLE_MD = CONTRACT_DIR / "sample.md"
SAMPLE_TYP = CONTRACT_DIR / "sample.typ"
SAMPLE_TEX = CONTRACT_DIR / "sample.tex"


def extract(raw, profile):
    """Expose carrier text and line positions, not runtime request semantics."""
    view = profile.blank_quoted_spans(raw)
    return [
        (
            raw.count("\n", 0, match.start()) + 1,
            match.group("type"),
            raw[match.start("text"):match.end("text")],
        )
        for match in profile.build_pattern(None).finditer(view)
        if profile.accept_match(raw, match)
    ]


md_raw = SAMPLE_MD.read_text(encoding="utf-8")
md_rows = extract(md_raw, P.MARKDOWN)

dispatch_cases = [
    ("note.md", None, "markdown"),
    ("note.markdown", None, "markdown"),
    ("NOTE.MD", None, "markdown"),
    ("paper.typ", None, "typst"),
    ("PAPER.TYP", None, "typst"),
    # `.tex` is claimed by the latex profile since Phase 3 (its own suite,
    # tests/test_latex.py, owns the behavior; this is the dispatch check)
    ("paper.tex", None, "latex"),
    ("paper.TeX", None, "latex"),
    # unknown extensions still fall back to markdown
    ("notes.rst", None, "markdown"),
    ("extensionless", None, "markdown"),
    # explicit override beats the extension in both directions
    ("note.md", "typst", "typst"),
    ("paper.typ", "markdown", "markdown"),
    ("paper.tex", "typst", "typst"),
]
for filename, override, expected in dispatch_cases:
    got = P.get_profile(Path("/tmp") / filename, override)
    check(
        f"dispatch: {filename} (override={override!r}) -> {expected}",
        got.name == expected,
        f"got {got.name}",
    )

check(
    "contract md: the three expected markers, at the expected lines — the one "
    "inside the fence now FIRES (fences are not quoting)",
    md_rows
    == [
        (7, "TODO", "first contract marker"),
        (12, "TODO", "fenced, matches"),
        (17, "QUESTION", "second contract marker?"),
    ],
    f"{md_rows}",
)
md_cleaned = P.MARKDOWN.strip_excluded_regions(SAMPLE_MD.read_text(encoding="utf-8"))
check(
    "contract md: headings, with the single H1 title dropped",
    P.MARKDOWN.collect_headings(md_cleaned)
    == [(4, 2, "Section One"), (14, 3, "Nested Two")],
    f"{P.MARKDOWN.collect_headings(md_cleaned)}",
)

typ_raw = SAMPLE_TYP.read_text(encoding="utf-8")
typ_cleaned = P.TYPST.strip_excluded_regions(typ_raw)
typ_pat = P.TYPST.build_pattern(None)

check(
    "contract typ: the 3-backtick run inside the 4-backtick block does not "
    "close it (line 24 stays blanked)",
    typ_cleaned.split("\n")[23].strip() == "",
    repr(typ_cleaned.split("\n")[23]),
)
check(
    "contract typ: headings, label stripped, trailing comment stripped, "
    "single top-level dropped",
    P.TYPST.collect_headings(typ_cleaned) == [(4, 2, "Sub"), (30, 2, "Other")],
    f"{P.TYPST.collect_headings(typ_cleaned)}",
)
check(
    "contract typ: '=nospace' is not a heading (typst needs the space)",
    all(title != "nospace" for _, _, title in P.TYPST.collect_headings(typ_cleaned)),
)

typst_pattern_cases = [
    ("// TODO(jason): plain ;;\n", True, "standalone marker"),
    ("    // TODO(jason): indented ;;\n", True, "indented standalone marker"),
    ("\t// TODO(jason): tabbed ;;\n", True, "tab-indented standalone marker"),
    # The standalone-line anchor is GONE: markers fire wherever the syntax is.
    ('#let x = "// TODO(jason): nope ;;"\n', True, "inside a string literal"),
    ("= Heading // NOTE(jason): trailing ;;\n", True, "trailing comment"),
    # `///` is typst's doc-comment convention; the marker starts at the SECOND
    # slash of the run, so a doc comment carries a marker just fine.
    ("/// TODO(jason): triple slash ;;\n", True, "/// doc comment"),
    ("// TODO: no author ;;\n", False, "no author parenthetical"),
    ("// todo(jason): lowercase ;;\n", False, "lowercase prefix"),
    ("// just a normal comment\n", False, "plain comment"),
    # `(?<!:)`: a URL's `//` is not a comment start, which is also typst's rule.
    ('#link("https://TODO(jason): x ;;")\n', False, "// preceded by ':' (URL)"),
    ("x `// TODO(jason): quoted ;;` y\n", False, "single-line raw span"),
]
for raw, should_match, why in typst_pattern_cases:
    got = bool(typ_pat.search(P.TYPST.blank_quoted_spans(raw)))
    check(
        f"typst pattern: {'matches' if should_match else 'rejects'} — {why}",
        got == should_match,
        repr(raw),
    )

two_markers = "// TODO(jason): one ;;\n// NOTE(jason): two ;;\n"
found = [(m.group("type"), m.group("text")) for m in typ_pat.finditer(two_markers)]
check(
    "typst pattern: consecutive markers match in document order, non-overlapping",
    found == [("TODO", "one ;;"), ("NOTE", "two ;;")],
    f"{found}",
)
check(
    "typst pattern: text group cannot cross a newline",
    all("\n" not in t for _, t in found),
)

typ_closed = P.TYPST.build_pattern(["TODO", "PAUSE"])
check(
    "typst pattern (closed list): case-insensitive, parenthetical optional",
    bool(typ_closed.search("// todo: lowercase closed-list\n"))
    and bool(typ_closed.search("// TODO(jason): with author\n")),
)
check(
    "typst pattern (closed list): a prefix not on the list is rejected",
    not typ_closed.search("// NOTE(jason): not listed\n"),
)
check(
    "typst pattern (closed list): no longer standalone-anchored either",
    bool(typ_closed.search('x = "// TODO(jason): fires now"\n')),
)

typ_note = P.TYPST.build_pattern(["note", "PAUSE"])
check(
    "typst pattern (closed list): a protocol-relative URL is not a listed marker",
    not typ_note.search('#let cdn = "//pause.example.com/assets"\n'),
    repr(typ_note.pattern),
)
check(
    "typst pattern (closed list): '//note.example.com' is not a 'note' marker",
    not typ_note.search('#let u = "//note.example.com/x"\n'),
)
check(
    "typst pattern (closed list): a real listed marker still matches",
    bool(typ_note.search("// note(jason): still works\n")),
)


# =====================================================================
# (h) typst scanner invariants on adversarial inputs
# =====================================================================

scanner_inputs = {
    "empty": "",
    "no constructs": "just prose\nsecond line\n",
    "unterminated block comment": "/* nope\nstill inside\n",
    "unterminated 3-backtick raw": "```\nabc\ndef\n",
    "unterminated single-backtick raw": "`abc\ndef\n",
    "nested block comments": "/* a /* b */ c */\n= After\n",
    "empty raw (two backticks)": "x ``y`` z\n",
    "4-backtick wrapping a 3-run": "````\na\n```\nb\n````\n",
    "CRLF marker": "= H\r\n// TODO(jason): crlf ;;\r\n",
    "CRLF block comment": "/* a\r\nb */\r\n= H\r\n",
    "backtick inside a line comment": "// see ``` detail\n= After\n",
    "block-comment opener inside a line comment": "// /* not a block\n= After\n",
    "url is not a comment": "= see http://x.com/y\n",
    "lone backtick at EOF": "prose `\n",
    "contract fixture": typ_raw,
}
for label, raw in scanner_inputs.items():
    for blank_comments in (False, True):
        out = P._typst_scan(raw, blank_comments)
        tag = "blank-comments" if blank_comments else "keep-comments"
        check(
            f"typst scanner ({tag}) preserves length — {label}",
            len(out) == len(raw),
            f"{len(raw)} -> {len(out)}",
        )
        check(
            f"typst scanner ({tag}) preserves newline positions — {label}",
            [i for i, c in enumerate(raw) if c == "\n"]
            == [i for i, c in enumerate(out) if c == "\n"],
        )
    cleaned = P.TYPST.strip_excluded_regions(raw)
    check(
        f"typst strip_excluded_regions preserves length — {label}",
        len(cleaned) == len(raw.removeprefix("﻿")),
    )

# Behavioral scanner checks
check(
    "typst scanner: an unterminated block comment blanks to EOF",
    P.TYPST.strip_excluded_regions("/* nope\n// TODO(jason): swallowed ;;\n").strip()
    == "",
)
check(
    "typst scanner: an unterminated raw block blanks to EOF",
    P.TYPST.strip_excluded_regions("```\n// TODO(jason): swallowed ;;\n").strip() == "",
)
nested = "/* outer\n/* inner */\n// TODO(jason): nested comment ;;\n*/\n"
check(
    "typst scanner: block comments NEST — an inner */ does not reopen the file "
    "(verified against typst 0.15)",
    not typ_pat.search(P.TYPST.strip_excluded_regions(nested)),
    repr(P.TYPST.strip_excluded_regions(nested)),
)

# --- Behavioral assertions for adversarial scanner inputs (expected cleaned
# output / downstream extraction results), not just length/newline
# preservation ---

# (a) `/*` inside a raw block is not a block comment: the raw closes at its
# own backtick delimiter, and text after that close is untouched.
raw_with_slashstar = "`/* x`AFTER\n"
check(
    "typst scanner: '/*' inside a raw block does not open a block comment; "
    "text after the raw's closing backtick survives",
    P.TYPST.strip_excluded_regions(raw_with_slashstar) == "      AFTER\n",
    repr(P.TYPST.strip_excluded_regions(raw_with_slashstar)),
)

# (b) run == 2 is an empty raw region: it consumes exactly the two
# backticks, and a marker line right after it still extracts.
empty_raw_then_marker = "``\n// TODO(jason): after empty raw ;;\n"
empty_raw_cleaned = P.TYPST.strip_excluded_regions(empty_raw_then_marker)
check(
    "typst scanner: run==2 empty raw consumes exactly the two backticks",
    empty_raw_cleaned == "  \n// TODO(jason): after empty raw ;;\n",
    repr(empty_raw_cleaned),
)
check(
    "typst scanner: marker line after an empty raw region still extracts",
    bool(typ_pat.search(empty_raw_cleaned))
    and typ_pat.search(empty_raw_cleaned).group("text").strip() == "after empty raw ;;",
)

# (c) surplus closing backticks: a 3-backtick raw closed by a later 4-run
# consumes exactly 3 of it; the surplus backtick survives and opens a fresh
# (here unterminated) raw region of its own — the exact docstring example.
surplus_input = "```\nalpha\n````\nbeta`"
surplus_cleaned = P.TYPST.strip_excluded_regions(surplus_input)
check(
    "typst scanner: 3-backtick raw closed by a 4-run consumes exactly 3; "
    "the surplus backtick opens a new (unterminated) raw region",
    surplus_cleaned == "   \n     \n    \n     ",
    repr(surplus_cleaned),
)

# (d) a backtick appearing after `//` on a marker line does not open a raw
# region: the line comment is skipped wholesale, so the marker still
# extracts and the following line is not blanked.
backtick_after_comment = "// TODO(jason): a ` backtick ;;\n// NOTE(jason): next ;;\n"
backtick_after_comment_cleaned = P.TYPST.strip_excluded_regions(backtick_after_comment)
check(
    "typst scanner: a backtick after '//' on a marker line does not open a "
    "raw region — nothing is blanked",
    backtick_after_comment_cleaned == backtick_after_comment,
    repr(backtick_after_comment_cleaned),
)
backtick_after_comment_matches = [
    (m.group("type"), m.group("text"))
    for m in typ_pat.finditer(backtick_after_comment_cleaned)
]
check(
    "typst scanner: both the backtick-bearing marker and the following marker extract",
    backtick_after_comment_matches
    == [("TODO", "a ` backtick ;;"), ("NOTE", "next ;;")],
    f"{backtick_after_comment_matches}",
)

def typ_headings(raw: str) -> list:
    return P.TYPST.collect_headings(P.TYPST.strip_excluded_regions(raw))


# Two top-level headings on purpose: the single-top-level title-drop heuristic
# would otherwise eat the one heading these checks are looking for.
_after_two = "= After\n= Two\n"
check(
    "typst scanner: the outer block comment DOES close on its own */",
    typ_headings(nested + _after_two) == [(4, 1, "After"), (5, 1, "Two")],
    f"{typ_headings(nested + _after_two)}",
)
check(
    "typst scanner: a backtick inside a line comment cannot open a raw region",
    typ_headings("// see ``` detail\n" + _after_two)
    == [(1, 1, "After"), (2, 1, "Two")],
    f"{typ_headings('// see ``` detail\\n' + _after_two)}",
)
check(
    "typst headings: a URL's // is not a line comment",
    typ_headings("= see http://x.com/y\n= Two\n")
    == [(0, 1, "see http://x.com/y"), (1, 1, "Two")],
    f"{typ_headings('= see http://x.com/y\\n= Two\\n')}",
)
check(
    "typst headings: a bare // IS stripped from a title",
    typ_headings("= a // b\n= Two\n") == [(0, 1, "a"), (1, 1, "Two")],
    f"{typ_headings('= a // b\\n= Two\\n')}",
)
check(
    "typst headings: the single-top-level title is dropped, like markdown's H1",
    typ_headings("= Only Title\n\n== Sec\n") == [(2, 2, "Sec")],
    f"{typ_headings('= Only Title\\n\\n== Sec\\n')}",
)

marker_view_shape_inputs = {
    "empty": "",
    "no quoting": "just prose\nsecond line\n",
    "BOM": "﻿# H\n<!-- TODO(jason): x -->\n",
    "unmatched opener": "prose ``x and nothing else\n",
    "CRLF span": "a `b` c\r\nd\r\n",
    "contract md": SAMPLE_MD.read_text(encoding="utf-8"),
    "contract typ": typ_raw,
    "contract tex": SAMPLE_TEX.read_text(encoding="utf-8"),

}
for label, raw in marker_view_shape_inputs.items():
    for prof in (P.MARKDOWN, P.TYPST, P.LATEX):
        view = prof.blank_quoted_spans(raw)
        check(
            f"marker view ({prof.name}) preserves length — {label}",
            len(view) == len(raw),
            f"{len(raw)} -> {len(view)}",
        )
        check(
            f"marker view ({prof.name}) preserves newline positions — {label}",
            [i for i, c in enumerate(raw) if c == "\n"]
            == [i for i, c in enumerate(view) if c == "\n"],
        )
check(
    "marker view: a leading BOM becomes ONE filler char (offsets unchanged), "
    "unlike strip_excluded_regions which removes it",
    P.MARKDOWN.blank_quoted_spans("﻿abc")[0] == P.QUOTED_SPAN_FILLER
    and len(P.MARKDOWN.blank_quoted_spans("﻿abc")) == 4
    and len(P.MARKDOWN.strip_excluded_regions("﻿abc")) == 3,
)

# --- CommonMark code-span run semantics (markdown) -------------------------
F = P.QUOTED_SPAN_FILLER
code_span_cases = [
    ("a `x` b", "a " + F * 3 + " b", "single backtick pair"),
    (
        "``x` <!-- TODO(jason): q -->``",
        F * 30,
        "double delimiter containing a shorter internal run — the WHOLE span",
    ),
    (
        "```a`b``c``` tail",
        F * 12 + " tail",
        "triple delimiter containing 1- and 2-runs",
    ),
    (
        "````a```b```` t",
        F * 13 + " t",
        "quadruple delimiter containing a 3-run",
    ),
    ("x `` y", "x `` y", "empty span: a bare 2-run with no closing 2-run is literal"),
    ("x ```` y", "x ```` y", "unmatched 4-run is literal, not a span"),
    ("a `unclosed b", "a `unclosed b", "unmatched opener is literal"),
    ("`a` and `b`", F * 3 + " and " + F * 3, "two spans on one line"),
    ("`a\nb`", "`a\nb`", "a run that does not close on its own line is literal"),
]
for src, expected, why in code_span_cases:
    got = P.MARKDOWN.blank_quoted_spans(src)
    check(f"md code-span scanner: {why}", got == expected, f"{got!r} != {expected!r}")

# --- verbatim marker text through the opaque filler ------------------------
verbatim_text_cases = [
    ("<!-- TODO(jason): `foo` -->\n", "`foo`", "quoted content is the WHOLE body"),
    ("<!-- TODO(jason): `foo` bar -->\n", "`foo` bar", "quoted content leads"),
    ("<!-- TODO(jason): bar `foo` -->\n", "bar `foo`", "quoted content trails"),
    (
        "<!-- TODO(jason): rename `foo` to `bar` -->\n",
        "rename `foo` to `bar`",
        "two quoted spans inside one marker",
    ),
    (
        "<!-- TODO(jason): compare `x --> y` and stop -->\n",
        "compare `x --> y` and stop",
        "a '-->' inside a quoted span is not the terminator",
    ),
]
for src, expected, why in verbatim_text_cases:
    rows = extract(src, P.MARKDOWN)
    check(
        f"md marker text is verbatim: {why}",
        rows == [(1, "TODO", expected)],
        f"{rows}",
    )

check(
    "md: a marker wholly inside a code span does not fire",
    extract("prose `<!-- TODO(jason): quoted -->` more\n", P.MARKDOWN) == [],
)
check(
    "md: a marker inside a DOUBLE-backtick span containing a stray backtick "
    "does not fire (the pairwise regex this replaced leaked it)",
    extract("``x` <!-- TODO(jason): quoted -->``\n", P.MARKDOWN) == [],
)
check(
    "md: markers inside fences, frontmatter and link-ref lines all FIRE",
    extract(
        "---\nx: <!-- TODO(jason): fm -->\n---\n"
        "```\n<!-- TODO(jason): fence -->\n```\n"
        "[ref]: http://x.com <!-- TODO(jason): linkref -->\n",
        P.MARKDOWN,
    )
    == [(2, "TODO", "fm"), (5, "TODO", "fence"), (7, "TODO", "linkref")],
    f"{extract('---', P.MARKDOWN)}",
)
check(
    "md: an **Anchor:** line still does NOT fire (sidecar protocol quoting)",
    extract("**Anchor:** <!-- TODO(jason): nope -->\n", P.MARKDOWN) == [],
)
check(
    "md: the **Anchor:** line is filled in the MARKER view too, not just the "
    "heading view",
    "TODO(jason)"
    not in P.MARKDOWN.blank_quoted_spans("**Anchor:** <!-- TODO(jason): nope -->\n"),
)

# --- typst raw-span run semantics ------------------------------------------
typ_span_cases = [
    ("x `// TODO(jason): q ;;` y", True, "single-line 1-run span"),
    ("x ``` // TODO(jason): q ;; ``` y", True, "single-line 3-run span"),
    ("x ```` a ``` // TODO(jason): q ;; ```` y", True, "4-run containing a 3-run"),
    ("x `` y // TODO(jason): fires ;;", False, "empty raw (2-run) does not quote"),
    ("```\n// TODO(jason): fires ;;\n```", False, "multi-line raw is not quoting"),
    ("`a\n// TODO(jason): fires ;;\nb`", False, "multi-line 1-run raw is not quoting"),
]
for src, quoted, why in typ_span_cases:
    got = "TODO(jason)" not in P.TYPST.blank_quoted_spans(src)
    check(
        f"typst raw-span scanner: {'quotes' if quoted else 'does not quote'} — {why}",
        got == quoted,
        repr(P.TYPST.blank_quoted_spans(src)),
    )

check(
    "BOM + Anchor line: no content markers, no control markers surface",
    extract(
        "﻿**Anchor:** <!-- PAUSE(jason): legacy -->\n",
        P.MARKDOWN,
    )
    == [],
)
check(
    "BOM + Anchor line: the anchor line is blanked in the MARKER view itself "
    "(not just filtered downstream)",
    "PAUSE(jason)"
    not in P.MARKDOWN.blank_quoted_spans("﻿**Anchor:** <!-- PAUSE(jason): legacy -->\n"),
)

check(
    "escaped opener: one backslash (odd) before the backtick — literal, "
    "marker inside survives and fires",
    extract(
        "\\`<!-- TODO(jason): live -->\\`\n",
        P.MARKDOWN,
    )
    == [(1, "TODO", "live")],
)
check(
    "escaped opener: two backslashes (even) before the backtick — a REAL "
    "opener, marker inside is quoted and does not fire",
    extract(
        "\\\\`<!-- TODO(jason): quoted -->`\n",
        P.MARKDOWN,
    )
    == [],
)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("all profile checks passed")
