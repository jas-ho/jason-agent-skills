"""Pure Markdown exclusion regressions for marker and heading views.

Checks behavioral exclusions and source-position invariants, not rule-table layout.
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


_marker_pattern = P.MARKDOWN.build_pattern(None)

adversarial_inputs = {
    "constructed: BOM + frontmatter": "﻿---\ntitle: x\n---\n# H\n<!-- TODO(jason): x -->\n",
    "constructed: CRLF frontmatter": "---\r\ntitle: x\r\n---\r\n# H\r\n<!-- TODO(jason): x -->\r\n",
    "constructed: form feed inside fence": "```\nline one\fline two\n<!-- TODO(jason): in fence -->\n```\n",
    "constructed: nested code+anchor+linkref": (
        '[ref]: http://example.com "title"\n'
        "**Anchor:** <!-- TODO(jason): quoted -->\n"
        "`<!-- TODO(jason): span -->`\n"
        "~~~\n<!-- TODO(jason): tilde fence -->\n~~~\n"
    ),
    "constructed: empty string": "",
    "constructed: no exclusions at all": "just prose, no markers, no fences\nsecond line\n",
}

for label, raw in adversarial_inputs.items():
    normalized = raw.removeprefix("﻿")
    cleaned = P.MARKDOWN.strip_excluded_regions(raw)
    check(
        f"heading view preserves source offsets after BOM removal — {label}",
        len(cleaned) == len(normalized)
        and [i for i, char in enumerate(cleaned) if char == "\n"]
        == [i for i, char in enumerate(normalized) if char == "\n"],
    )

composed = (
    "```\n"
    "fence body with `<!-- TODO(jason): span in fence -->` inline code inside it\n"
    "```\n"
    "\n"
    "A real marker outside everything. <!-- TODO(jason): real one -->\n"
)
composed_cleaned = P.MARKDOWN.strip_excluded_regions(composed)
check(
    "fenced block containing an inline-code span containing marker-looking "
    "text: nothing leaks",
    "TODO(jason): span in fence" not in composed_cleaned,
    repr(composed_cleaned),
)
check(
    "the real marker outside the fence survives",
    "TODO(jason): real one" in composed_cleaned,
    repr(composed_cleaned),
)

per_rule_heading_fixtures = {
    # Level 2 ("##"), not "#": a lone level-1 heading is dropped by
    # `_drop_single_top_level` (it reads as the document title), which would
    # make the BEFORE-stripping assertion meaningless for these single-heading
    # fixtures.
    "yaml-frontmatter": "---\ntitle: x\n## fake heading\n---\n",
    "fenced-code-backtick": "```\n## fake heading\n```\n",
    # The tilde-fence rule was previously completely unexercised by any test.
    "fenced-code-tilde": "~~~\n## fake heading\n~~~\n",
}

def _has_fake_heading(headings: list) -> bool:
    return any(title == "fake heading" for _, _, title in headings)


for rule_name, raw in per_rule_heading_fixtures.items():
    before_headings = P.MARKDOWN.collect_headings(raw)
    cleaned = P.MARKDOWN.strip_excluded_regions(raw)
    after_headings = P.MARKDOWN.collect_headings(cleaned)
    check(
        f"EXCLUSION_RULES['{rule_name}']: fake heading visible BEFORE stripping",
        _has_fake_heading(before_headings),
        repr(before_headings),
    )
    check(
        f"EXCLUSION_RULES['{rule_name}']: fake heading suppressed AFTER stripping",
        not _has_fake_heading(after_headings),
        repr(after_headings),
    )

_mixed_title_cleaned = P.MARKDOWN.strip_excluded_regions("## Use `foo` here\n")
check(
    "a heading title's code span is no longer stripped out",
    P.MARKDOWN.collect_headings(_mixed_title_cleaned) == [(0, 2, "Use `foo` here")],
    f"{P.MARKDOWN.collect_headings(_mixed_title_cleaned)}",
)

_code_only_cleaned = P.MARKDOWN.strip_excluded_regions("## `foo`\n")
check(
    "a code-only heading title now survives as a real heading (previously "
    "blanked to empty and dropped)",
    P.MARKDOWN.collect_headings(_code_only_cleaned) == [(0, 2, "`foo`")],
    f"{P.MARKDOWN.collect_headings(_code_only_cleaned)}",
)

# None of the three remaining heading-view rules doubles as a marker
# exclusion: a marker inside frontmatter or a fence still fires in the
# marker view exactly as it does in raw text.
per_rule_marker_fixtures = {
    "yaml-frontmatter": "---\ntitle: x\n<!-- TODO(jason): fm rule marker -->\n---\n",
    "fenced-code-backtick": "```\n<!-- TODO(jason): backtick fence rule marker -->\n```\n",
    "fenced-code-tilde": "~~~\n<!-- TODO(jason): tilde fence rule marker -->\n~~~\n",
}

for rule_name, raw in per_rule_marker_fixtures.items():
    view = P.MARKDOWN.blank_quoted_spans(raw)
    check(
        f"marker view: '{rule_name}' region is NOT a marker exclusion — marker fires",
        bool(_marker_pattern.search(view)),
        repr(view),
    )
    check(
        f"marker view: '{rule_name}' fixture — length and newlines preserved",
        len(view) == len(raw)
        and [i for i, c in enumerate(raw) if c == "\n"]
        == [i for i, c in enumerate(view) if c == "\n"],
    )

# Explicit marker-view tests for the two ACTUAL marker exclusions — a code
# span and an Anchor line — kept here rather than table-driven, since neither
# is (or needs to be) a member of EXCLUSION_RULES any more.
_explicit_marker_view_fixtures = {
    "inline-code-span": (
        "prose `<!-- TODO(jason): inline span rule marker -->` more prose\n"
    ),
    "anchor-protocol": "**Anchor:** <!-- TODO(jason): anchor rule marker -->\n",
}
for label, raw in _explicit_marker_view_fixtures.items():
    view = P.MARKDOWN.blank_quoted_spans(raw)
    check(
        f"marker view: '{label}' region IS a marker exclusion — marker is hidden",
        not _marker_pattern.search(view),
        repr(view),
    )
    check(
        f"marker view: '{label}' fixture — length and newlines preserved",
        len(view) == len(raw)
        and [i for i, c in enumerate(raw) if c == "\n"]
        == [i for i, c in enumerate(view) if c == "\n"],
    )

for label, raw in adversarial_inputs.items():
    view = P.MARKDOWN.blank_quoted_spans(raw)
    check(
        f"marker view preserves length (BOM included) — {label}",
        len(view) == len(raw),
        f"{len(raw)} -> {len(view)}",
    )
    check(
        f"marker view preserves newline positions — {label}",
        [i for i, c in enumerate(raw) if c == "\n"]
        == [i for i, c in enumerate(view) if c == "\n"],
    )
    check(
        f"marker view fills with the OPAQUE filler, never whitespace — {label}",
        all(
            v == r or v == P.QUOTED_SPAN_FILLER for r, v in zip(raw, view, strict=True)
        ),
    )

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("all profile invariant checks passed")
