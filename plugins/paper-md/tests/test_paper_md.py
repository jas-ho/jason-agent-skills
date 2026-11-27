"""Tests for paper_md.py on synthetic fixtures (invented text, no real documents).

Run: uv run --with pytest pytest plugins/paper-md/tests -q
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "paper_md.py"
sys.path.insert(0, str(SCRIPT.parent))
import paper_md as pm  # noqa: E402

FILLER = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor " * 2
)


def ref_page(
    i: int, lines_from: int | None = None, footer: str | None = None, extra: str = ""
) -> str:
    """pdftotext-like page text: optional margin line numbers, body, optional footer."""
    rows = (
        [str(n) for n in range(lines_from, lines_from + 40)]
        if lines_from is not None
        else []
    )
    rows += [FILLER, extra]
    if footer:
        rows += [footer, str(i + 1)]
    return "\n".join(rows)


def md_doc(pages: list[str]) -> str:
    out = []
    for i, body in enumerate(pages):
        out += [f"{{{i}}}" + "-" * 48, "", body, ""]
    return "\n".join(out)


def clean(
    md: str, ref: list[str], tmp_path: Path, private: bool = False
) -> tuple[str, pm.Report]:
    rep = pm.Report(private=private)
    return pm.clean_markdown(md, ref, len(ref), tmp_path, rep), rep


def kinds(rep: pm.Report) -> set[str]:
    return {u["kind"] for u in rep.unresolved}


# ----------------------------------------------------------------- line numbers


def lined_ref(n: int = 6) -> list[str]:
    return [ref_page(i, lines_from=1 + 40 * i) for i in range(n)]


def test_line_numbers_removed_plain_bold_heading_and_glued(tmp_path):
    pages = [f"Intro text {FILLER}." for _ in range(6)]
    pages[0] += "\n\n3 4\n\n**5**\n\n# 6 7"
    pages[1] += "\n\n**52 53** Some heading text\n\nA reference line, 2020. 61 62"
    out, rep = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "3 4" not in out and "**5**" not in out and "# 6 7" not in out
    assert "Some heading text" in out and "**52 53**" not in out
    assert "A reference line, 2020." in out and "61 62" not in out
    assert rep.counts["line_number_lines_removed"] == 3
    assert rep.counts["glued_line_numbers_removed"] == 2


def test_single_glued_number_is_data_and_kept(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[0] += "\n\n20 participants completed the study.\n\nWe enrolled 20"
    out, rep = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "20 participants completed the study." in out and "We enrolled 20" in out
    assert "glued_number_kept" in kinds(rep)


def test_list_items_keep_their_numbers(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[0] += "\n\n1. Observed values: 20 21\n- Participants: **22**"
    out, _ = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "Observed values: 20 21" in out and "Participants: **22**" in out


def test_line_number_preservation_in_enabled_document(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[0] += "\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 2 | 3 |"
    pages[0] += "\n\n1. first item\n2. second item"
    pages[0] += "\n\n$$x = y$$\n\n(3)"
    pages[0] += "\n\n```\nx = 12\n9100\n```"
    pages[2] += "\n\n9000\n\n9001\n\n9002"  # outside the page's line-number range
    out, _ = clean(md_doc(pages), lined_ref(), tmp_path)
    for kept in (
        "| 1 | 2 |",
        "1. first item",
        "(3)",
        "```\nx = 12\n9100\n```",
        "9000",
        "9001",
        "9002",
    ):
        assert kept in out


def test_line_numbers_inside_code_fences_removed(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    # true positive: a boxed prompt with margin numbers 52-58 (steps 1-3) inside
    pages[1] += (
        "\n\n```\n52\n53\n    prompt text here\n54\n56\n    more prompt\n57\n58\n```"
    )
    out, _ = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "```\n    prompt text here\n    more prompt\n```" in out


def test_anonymous_placeholder_glued_to_title_is_stripped(tmp_path):
    out, _ = clean(
        md_doc(["# A Long Paper Title Here ANONYMOUS AUTHOR(S)\n\nText."]),
        [ref_page(0)],
        tmp_path,
    )
    assert out.splitlines()[0] == "# A Long Paper Title Here"


def test_in_range_numbers_in_maths_and_small_fences_are_kept(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[0] += "\n\n$$\n20\n$$\n\n```\nanswer:\n21\n```"
    out, _ = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "$$\n20\n$$" in out and "```\nanswer:\n21\n```" in out


def test_fenced_numbers_kept_unless_they_ascend_like_line_numbers(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    blocks = [
        "```\n10\n20\n30\n35\n40\n```",  # genuine output, steps of 5-10
        "```\n3\n1\n2\n5\n4\n```",  # genuine output, not ascending
        "```\nx\n11\n12\n13\n```",  # only 3 in-range numbers: kept, reported
        "```\n5\n```\n```\n6\n```\n```\n7\n```",  # adjacent fences count separately
    ]
    pages[0] += "\n\n" + "\n\n".join(blocks)
    out, rep = clean(md_doc(pages), lined_ref(), tmp_path)
    for block in blocks:
        assert block in out
    assert "line_number_leftover" in kinds(rep)


def test_no_line_numbers_in_pdf_keeps_number_lines(tmp_path):
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[1] += "\n\n12\n\n13 14"
    out, rep = clean(md_doc(pages), [ref_page(i) for i in range(6)], tmp_path)
    assert "12" in out and "13 14" in out
    assert "line_number_lines_removed" not in rep.counts


def test_descending_or_scattered_numbers_do_not_count_as_line_numbers():
    scattered = "\n".join(
        str(v) for v in [90, 70, 50, 30, 10, 80, 60, 40, 20, 5, 95, 15]
    )
    descending = "\n".join(str(v) for v in range(40, 0, -1))
    assert pm.line_number_ranges([scattered, descending]) == [None, None]
    assert pm.line_number_ranges(["\n".join(map(str, range(417, 469)))]) == [(417, 468)]


def test_narrow_image_is_flagged_not_removed(tmp_path):
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 30, 200)
        + b"\x00" * 20
    )
    (tmp_path / "_page_1_Figure_1.png").write_bytes(png)
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[1] += "\n\n![](_page_1_Figure_1.png)"
    out, rep = clean(md_doc(pages), lined_ref(), tmp_path)
    assert "![](_page_1_Figure_1.png)" in out
    assert "probable_line_number_strip" in kinds(rep)


# ----------------------------------------------------------------- headers and footers

FOOT = "Manuscript submitted to ACM"


def test_surviving_footers_removed_nine_of_fortyone(tmp_path):
    ref = [ref_page(i, footer=FOOT) for i in range(41)]
    pages = [f"Body text number {i} {FILLER}." for i in range(41)]
    for i in range(0, 36, 4):  # nine survivors, as observed
        pages[i] += f"\n\n{FOOT}"
    pages[37] = f"Sentence that ends {FOOT} 38 and goes on {FILLER}."
    out, rep = clean(md_doc(pages), ref, tmp_path)
    assert FOOT not in out
    assert rep.counts["header_footer_lines_removed"] == 9
    assert rep.counts["header_footer_fragments_removed"] == 1


def test_footer_removal_keeps_an_adjacent_decimal(tmp_path):
    ref = [ref_page(i, footer=FOOT) for i in range(6)]
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[2] = f"Result was {FOOT} 0.84 when measured, then {FOOT} 1e-3 later"
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert "0.84 when measured" in out and "1e-3 later" in out and FOOT not in out


def test_footer_removal_keeps_a_number_written_before_it(tmp_path):
    ref = [ref_page(i, footer=FOOT) for i in range(6)]
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[2] = f"Result 1e-3 {FOOT} measured, and 42 {FOOT} more"
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert "Result 1e-3" in out and "and 42" in out and FOOT not in out


def test_short_header_text_in_body_survives(tmp_path):
    ref = [ref_page(i, footer="Results") for i in range(10)]
    pages = [f"Body {FILLER}." for _ in range(10)]
    pages[4] = f"Body {FILLER}.\n\nResults\n\nMore body {FILLER}."
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert "\nResults\n" in out


def test_header_text_with_data_is_not_a_header_line(tmp_path):
    ref = [ref_page(i, footer="Evaluation results overview") for i in range(10)]
    pages = [f"Body {FILLER}." for _ in range(10)]
    pages[4] = (
        f"Body {FILLER}.\n\nEvaluation results overview: 0.84\n\nMore body {FILLER}."
    )
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert "Evaluation results overview: 0.84" in out


def test_repeated_real_headings_kept_even_when_at_pdf_page_tops(tmp_path):
    ref = [
        "Prompt\n" + FILLER for _ in range(10)
    ]  # the heading is a top row on every page
    pages = [f"### **Prompt**\n\nAnswer {i} {FILLER}." for i in range(10)]
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert out.count("Prompt") == 10


def test_composite_running_header_line_removed(tmp_path):
    ref = ["Ada Author, Bob Author\nMai 2018\n" + FILLER for _ in range(8)]
    pages = [
        f"### **Ada Author, Bob Author Mai 2018**\n\nText {i} {FILLER}."
        for i in range(8)
    ]
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert "Ada Author" not in out


def test_footer_text_inside_code_or_table_untouched(tmp_path):
    ref = [ref_page(i, footer=FOOT) for i in range(6)]
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[2] += f"\n\n```\n{FOOT}\n```\n\n| {FOOT} | x |"
    out, _ = clean(md_doc(pages), ref, tmp_path)
    assert f"```\n{FOOT}\n```" in out and f"| {FOOT} | x |" in out


# ----------------------------------------------------------------- page breaks


def test_page_break_join_rules(tmp_path):
    pages = [
        "The sentence continues across",
        "the page break here. Done.",
        "# Heading\n\nfine text",
        "| t | u |\n|---|---|\n| 1 | 2 |",
        "a hyphenated word con-",
        "tinues here.",
    ]
    out, rep = clean(md_doc(pages), [ref_page(i) for i in range(6)], tmp_path)
    assert "The sentence continues across the page break here." in out
    assert "Done.\n\n# Heading" in out
    assert "con-\n\ntinues" in out
    assert "possible_page_break_split" in kinds(rep)


def test_joined_text_keeps_its_page_for_the_audit(tmp_path):
    ref = ["start text " + FILLER, "continued 12.5 text " + FILLER]
    md = md_doc(["start text " + FILLER, "continued 12.5 text " + FILLER])
    _, rep = clean(md.replace(FILLER + "\n", FILLER.rstrip() + "\n"), ref, tmp_path)
    assert "numbers_not_in_pdf_text" not in kinds(rep)
    assert "page_text_short" not in kinds(rep)


# ----------------------------------------------------------------- symbols


def test_symbol_gap_filled_from_unique_same_page_candidate(tmp_path):
    ref = [
        "The correlation was strong across all models (\U0001d45f = 0.84) in the main study "
        + FILLER
    ]
    md = md_doc(
        ["The correlation was strong across all models ( = 0.84) in the main study."]
    )
    out, rep = clean(md, ref, tmp_path)
    assert "(r = 0.84)" in out
    assert rep.counts["symbol_gaps_filled"] == 1


def test_symbol_gap_not_filled_from_longer_number_or_other_page(tmp_path):
    md = md_doc(
        ["The correlation was strong across all models ( = 0.84) here.", FILLER]
    )
    longer = [
        "The correlation was strong across all models (\U0001d45f = 0.8407) " + FILLER,
        FILLER,
    ]
    decimal = [
        "The correlation was strong across all models (\U0001d45f = 0.84e-3) " + FILLER,
        FILLER,
    ]
    other_page = [
        FILLER,
        "The correlation was strong across all models (\U0001d45f = 0.84) " + FILLER,
    ]
    for ref in (longer, decimal, other_page):
        out, rep = clean(md, ref, tmp_path)
        assert "( = 0.84)" in out
        assert "symbol_gap" in kinds(rep)


def test_symbol_gap_with_exponent_in_markdown_not_filled_from_mantissa(tmp_path):
    ref = ["The correlation was strong across all models (\U0001d45f = 0.84) " + FILLER]
    md = md_doc(["The correlation was strong across all models ( = 0.84e-3) here."])
    out, _ = clean(md, ref, tmp_path)
    assert "( = 0.84e-3)" in out


def test_symbol_gap_not_filled_from_unicode_minus_exponent(tmp_path):
    ref = [
        "The correlation was strong across all models (\U0001d45f = 0.84e\u22123) "
        + FILLER
    ]
    md = md_doc(["The correlation was strong across all models ( = 0.84) here."])
    out, _ = clean(md, ref, tmp_path)
    assert "( = 0.84)" in out


def test_symbol_gap_with_two_candidates_is_listed(tmp_path):
    ref = [
        "across all models (\U0001d45f = 0.84) and across all models (\U0001d70f = 0.84) "
        + FILLER
    ]
    out, rep = clean(
        md_doc(["Values differed across all models ( = 0.84) in the study."]),
        ref,
        tmp_path,
    )
    assert "( = 0.84)" in out
    assert "symbol_gap" in kinds(rep)


def test_short_gap_without_context_is_still_reported(tmp_path):
    _, rep = clean(md_doc(["( = 0.84)"]), [FILLER], tmp_path)
    assert "symbol_gap" in kinds(rep)


def test_missing_symbols_and_superscripts_are_reported(tmp_path):
    ref = ["We set α = 0.05 and report R² for all tests " + FILLER]
    _, rep = clean(md_doc(["We set = 0.05 and report R for all tests."]), ref, tmp_path)
    item = next(u for u in rep.unresolved if u["kind"] == "check_maths_symbols")
    assert "α" in item["excerpt"] and "²" in item["excerpt"]


def test_latex_symbols_count_as_present(tmp_path):
    _, rep = clean(
        md_doc(["We set $\\alpha = 0.05$ here."]),
        ["We set α = 0.05 " + FILLER],
        tmp_path,
    )
    assert "check_maths_symbols" not in kinds(rep)


# ----------------------------------------------------------------- headings, anchors


def test_headings_follow_numbering_and_single_title(tmp_path):
    md = md_doc(
        [
            (
                "### **A Title**\n\n# ANONYMOUS SUBMISSION\n\n### 1 Introduction\n\n# 2 Methods\n\n"
                "## 2.1 Data\n\n# Unnumbered\n\n# References\n\n### A Extra results\n\n#### A.1 More\n\n"
                "## Experiments with Anonymous Authors\n\n```\n# not a heading\n```"
            )
        ]
    )
    out, _ = clean(md, [ref_page(0)], tmp_path)
    heads = [ln for ln in out.splitlines() if ln.startswith("#")]
    assert heads == [
        "# A Title",
        "## 1 Introduction",
        "## 2 Methods",
        "### 2.1 Data",
        "## Unnumbered",
        "## References",
        "## A Extra results",
        "### A.1 More",
        "## Experiments with Anonymous Authors",
        "# not a heading",
    ]


def test_marker_anchors_and_page_links_removed(tmp_path):
    md = md_doc(
        [
            '<span id="page-3-0"></span>See [\\[53\\]](#page-11-3) and [Section 2](#page-2-1).'
        ]
    )
    out, _ = clean(md, [ref_page(0)], tmp_path)
    assert "See [53] and Section 2." in out


def test_page_links_in_table_cells_become_text(tmp_path):
    md = md_doc(["| See [Section 2](#page-2-1) | x |\n|---|---|"])
    out, _ = clean(md, [ref_page(0)], tmp_path)
    assert "| See Section 2 | x |" in out


def test_missing_short_page_is_flagged(tmp_path):
    ref = [ref_page(0), "twenty words " * 10]
    _, rep = clean(md_doc([f"Body {FILLER}.", ""]), ref, tmp_path)
    assert any(
        u["kind"] == "page_text_missing" and u["page"] == 2 for u in rep.unresolved
    )


def test_scan_pages_are_listed_by_page(tmp_path):
    _, rep = clean(
        md_doc([f"OCR text {FILLER}", f"OCR text {FILLER}"]), ["", ""], tmp_path
    )
    item = next(
        u for u in rep.unresolved if u["kind"] == "pages_without_reference_text"
    )
    assert item["pages"] == [1, 2]


def test_private_report_has_no_document_text(tmp_path):
    secret = "Confidential Benchmark Header"
    ref = [
        ref_page(i, footer=secret, extra="We set α = 0.05 with value 77.7")
        for i in range(6)
    ]
    pages = [f"Body {FILLER}." for _ in range(6)]
    pages[1] += "\n\nWe set ( = 0.05) with value 99.9\n\nFigure 1: secret caption words"
    _, rep = clean(md_doc(pages), ref, tmp_path, private=True)
    dumped = json.dumps({"u": rep.unresolved, "n": rep.notes})
    for leak in ("Confidential", "secret", "99.9", "α", "lorem"):
        assert leak not in dumped
    assert rep.unresolved


# ----------------------------------------------------------------- convert wrapper


def fake_marker(md_text: str, image: bool = False):
    def run(_marker, pdf, work, fast, _fd, quiet=False):
        d = work / pdf.stem
        d.mkdir(parents=True)
        (d / f"{pdf.stem}.md").write_text(md_text)
        if image:
            (d / "_page_0_Figure_1.jpeg").write_bytes(b"\xff\xd8\xff\xd9")

    return run


@pytest.fixture
def fake_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "require", lambda tools: {t: t for t in tools})
    monkeypatch.setattr(pm, "marker_version", lambda _p: "0.0-test")
    monkeypatch.setattr(pm, "model_cache_present", lambda: True)
    monkeypatch.setattr(pm, "pdf_page_count", lambda _p: 1)
    monkeypatch.setattr(pm, "pdf_text_pages", lambda _p: [ref_page(0)])
    monkeypatch.setattr(pm, "LOCK_PATH", tmp_path / "lock")


def run_main(capsys, argv) -> tuple[int, dict]:
    code = pm.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_convert_never_overwrites_and_rewrites_image_links(
    tmp_path, monkeypatch, fake_tools, capsys
):
    pdf = tmp_path / 'My "Paper".pdf'
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        pm,
        "run_marker",
        fake_marker(md_doc(["Text.\n\n![](_page_0_Figure_1.jpeg)"]), image=True),
    )
    _, first = run_main(capsys, ["convert", str(pdf)])
    _, second = run_main(capsys, ["convert", str(pdf)])
    assert Path(first["outputs"]["md"]).name == "My-Paper.md"
    assert Path(second["outputs"]["md"]).name == "My-Paper.v2.md"
    body = Path(second["outputs"]["md"]).read_text()
    assert "![](My-Paper.v2_figures/_page_0_Figure_1.jpeg)" in body
    assert body.startswith('---\nsource: "My \\"Paper\\".pdf"\n')
    assert (tmp_path / "My-Paper_figures" / "_page_0_Figure_1.jpeg").exists()


def test_image_links_in_code_are_not_rewritten(
    tmp_path, monkeypatch, fake_tools, capsys
):
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc = md_doc(["![](_page_0_Figure_1.jpeg)\n\n```\n![](example.png)\n```"])
    monkeypatch.setattr(pm, "run_marker", fake_marker(doc, image=True))
    _, out = run_main(capsys, ["convert", str(pdf)])
    body = Path(out["outputs"]["md"]).read_text()
    assert (
        "![](c_figures/_page_0_Figure_1.jpeg)" in body
        and "```\n![](example.png)\n```" in body
    )


def test_image_links_in_tables_are_relinked(tmp_path, monkeypatch, fake_tools, capsys):
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc = md_doc(["| Diagram | ![](_page_0_Figure_1.jpeg) |\n|---|---|"])
    monkeypatch.setattr(pm, "run_marker", fake_marker(doc, image=True))
    _, out = run_main(capsys, ["convert", str(pdf)])
    assert (
        "![](t_figures/_page_0_Figure_1.jpeg)" in Path(out["outputs"]["md"]).read_text()
    )


def test_table_looking_lines_in_code_are_not_relinked(
    tmp_path, monkeypatch, fake_tools, capsys
):
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc = md_doc(["![](_page_0_Figure_1.jpeg)\n\n```\n| ![](example.png) |\n```"])
    monkeypatch.setattr(pm, "run_marker", fake_marker(doc, image=True))
    _, out = run_main(capsys, ["convert", str(pdf)])
    assert "```\n| ![](example.png) |\n```" in Path(out["outputs"]["md"]).read_text()


def test_reserved_name_skips_existing_figures_dir(tmp_path):
    (tmp_path / "x_figures").mkdir()
    md, assets = pm.reserve_md(tmp_path / "x")
    assert md.name == "x.v2.md" and assets.name == "x.v2_figures" and md.exists()


def test_convert_no_excerpts_has_no_document_text(
    tmp_path, monkeypatch, fake_tools, capsys
):
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(pm, "pdf_text_pages", lambda _p: ["We set α = 0.05 " + FILLER])
    doc = md_doc(["Secret sentence one ( = 0.05) value.\n\nFigure 1: secret caption"])
    monkeypatch.setattr(pm, "run_marker", fake_marker(doc))
    code, out = run_main(capsys, ["convert", str(pdf), "--no-excerpts"])
    assert code == 0 and out["unresolved"]
    assert "ecret" not in json.dumps(out)


def test_fast_refused_for_scans(tmp_path, monkeypatch, fake_tools, capsys):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(pm, "pdf_text_pages", lambda _p: [""])
    seen = {}

    def run(marker, p, work, fast, fd, quiet=False):
        seen["fast"] = fast
        fake_marker(md_doc(["Scanned text."]))(marker, p, work, fast, fd)

    monkeypatch.setattr(pm, "run_marker", run)
    _, out = run_main(capsys, ["convert", str(pdf), "--fast"])
    assert seen["fast"] is False and out["mode"]["ocr"] is True


def test_busy_lock_returns_exit_5_before_any_work(
    tmp_path, monkeypatch, fake_tools, capsys
):
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        pm, "pdf_page_count", lambda _p: pytest.fail("work started while busy")
    )
    fd = os.open(tmp_path / "lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        code, out = run_main(capsys, ["convert", str(pdf)])
    finally:
        os.close(fd)
    assert code == pm.EXIT_BUSY and out["status"] == "busy"
    assert set(out) >= {"outputs", "counts", "unresolved", "notes"}


def write_fake_marker(path: Path, body: str) -> str:
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def fake_tool_env(tmp_path: Path, marker_body: str) -> tuple[dict, Path]:
    """PATH with fake marker_single/pdftotext/pdfinfo; returns (env, pdf)."""
    write_fake_marker(tmp_path / "marker_single", marker_body)
    for tool in ("pdftotext", "pdfinfo"):
        out = "Pages: 1" if tool == "pdfinfo" else "text " * 20
        write_fake_marker(tmp_path / tool, f"print({out!r})\n")
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "HOME": str(tmp_path),  # the lock lives under ~/.cache/paper-md
    }
    return env, pdf


def wait_for(path: Path, timeout: float = 10) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        time.sleep(0.05)
    raise AssertionError(f"{path.name} never written")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def lock_is_held(lock: Path) -> bool:
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def test_lock_outlives_a_killed_wrapper_while_marker_runs(tmp_path):
    pidfile = tmp_path / "child.pid"
    body = f"import os, time\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n"
    env, pdf = fake_tool_env(tmp_path, body)
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "convert", str(pdf)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child = int(wait_for(pidfile))
    proc.kill()  # no cleanup in the wrapper
    proc.wait()
    lock = tmp_path / ".cache" / "paper-md" / "marker.lock"
    try:
        assert lock_is_held(lock)
        assert lock.read_text().strip() == str(child)
    finally:
        os.kill(child, signal.SIGKILL)
    for _ in range(100):
        if not alive(child):
            break
        time.sleep(0.05)
    assert not lock_is_held(lock)


def test_sigterm_stops_stubborn_marker_and_its_descendants(tmp_path):
    pidfile, gpidfile = tmp_path / "child.pid", tmp_path / "grandchild.pid"
    stubborn = tmp_path / "stubborn.py"
    stubborn.write_text(
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    body = (
        "import os, signal, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(stubborn)!r}, {str(gpidfile)!r}])\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    env, pdf = fake_tool_env(tmp_path, body)
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "convert", str(pdf)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    child, grandchild = int(wait_for(pidfile)), int(wait_for(gpidfile))
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=40)
    assert proc.returncode == pm.EXIT_CONVERT
    assert json.loads(out)["status"] == "interrupted"
    assert not alive(child) and not alive(grandchild)


def test_sigterm_during_preprocessing_returns_json(tmp_path):
    env, pdf = fake_tool_env(tmp_path, "print('unused')\n")
    started = tmp_path / "pdftotext.started"
    write_fake_marker(
        tmp_path / "pdftotext",
        f"import time\nopen({str(started)!r}, 'w').write('1')\ntime.sleep(30)\n",
    )
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "convert", str(pdf)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    wait_for(started)
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=30)
    assert proc.returncode == pm.EXIT_CONVERT
    assert json.loads(out)["status"] == "interrupted"


def test_private_mode_suppresses_marker_output(tmp_path):
    body = "import sys\nprint('SENTINEL-OUT')\nprint('SENTINEL-ERR', file=sys.stderr)\nsys.exit(1)\n"
    env, pdf = fake_tool_env(tmp_path, body)
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "convert", str(pdf), "--no-excerpts"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert run.returncode == pm.EXIT_CONVERT
    assert "SENTINEL" not in run.stdout + run.stderr
    loud = subprocess.run(
        [sys.executable, str(SCRIPT), "convert", str(pdf)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "SENTINEL-ERR" in loud.stderr


def test_missing_dependency_exit_3(monkeypatch, tmp_path, capsys):
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(pm.shutil, "which", lambda _t, mode=None: None)
    code, out = run_main(capsys, ["convert", str(pdf)])
    assert code == pm.EXIT_DEP and out["status"] == "dependency_missing"


def test_usage_error_is_json_exit_2(capsys):
    code, out = run_main(capsys, ["convert"])
    assert code == pm.EXIT_USAGE and out["status"] == "usage_error"


# ----------------------------------------------------------------- fetch


@pytest.fixture
def fetch_env(monkeypatch):
    monkeypatch.setattr(pm, "require", lambda tools: {t: t for t in tools})
    monkeypatch.setattr(pm, "pdf_page_count", lambda _p: 3)


def test_fetch_arxiv_versions_existing_file(tmp_path, monkeypatch, fetch_env, capsys):
    monkeypatch.setattr(
        pm, "http_get", lambda url: (b"%PDF-1.5 fake", "application/pdf")
    )
    _, first = run_main(
        capsys, ["fetch", "https://arxiv.org/abs/2106.09685v2", "--out", str(tmp_path)]
    )
    _, second = run_main(capsys, ["fetch", "2106.09685v2", "--out", str(tmp_path)])
    assert first["source"]["url"] == "https://arxiv.org/pdf/2106.09685v2"
    assert Path(second["outputs"]["pdf"]).name == "arxiv-2106.09685v2.v2.pdf"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "arxiv-2106.09685v2.pdf",
        "arxiv-2106.09685v2.v2.pdf",
    ]


def test_fetch_with_denied_pdfinfo_is_exit_3(tmp_path, monkeypatch, fetch_env, capsys):
    monkeypatch.setattr(
        pm, "http_get", lambda url: (b"%PDF-1.5 fake", "application/pdf")
    )

    def denied(_p):
        raise pm.Fail(
            pm.EXIT_DEP,
            "dependency_denied",
            "pdfinfo could not be executed",
            tool="pdfinfo",
        )

    monkeypatch.setattr(pm, "pdf_page_count", denied)
    code, out = run_main(capsys, ["fetch", "2106.09685", "--out", str(tmp_path)])
    assert code == pm.EXIT_DEP and out["tool"] == "pdfinfo"
    assert not list(tmp_path.iterdir())


def test_fetch_doi_without_open_access_is_exit_6(
    tmp_path, monkeypatch, fetch_env, capsys
):
    empty = json.dumps({"best_oa_location": None, "locations": []}).encode()
    monkeypatch.setattr(pm, "http_get", lambda url: (empty, "application/json"))
    code, out = run_main(
        capsys, ["fetch", "10.1145/1234567.7654321", "--out", str(tmp_path)]
    )
    assert code == pm.EXIT_FETCH and out["status"] == "no_open_access_pdf"


def test_fetch_html_or_invalid_pdf_leaves_nothing(
    tmp_path, monkeypatch, fetch_env, capsys
):
    def get(url):
        if "openalex" in url:
            return json.dumps(
                {"best_oa_location": {"pdf_url": "https://example.org/x.pdf"}}
            ).encode(), "application/json"
        return b"<html>login</html>", "text/html"

    monkeypatch.setattr(pm, "http_get", get)
    code, out = run_main(capsys, ["fetch", "doi:10.1000/xyz", "--out", str(tmp_path)])
    assert code == pm.EXIT_FETCH and out["status"] == "not_pdf"

    def bad_pdf(_p):
        raise subprocess.CalledProcessError(1, ["pdfinfo"])

    monkeypatch.setattr(pm, "http_get", lambda url: (b"%PDF-broken", "application/pdf"))
    monkeypatch.setattr(pm, "pdf_page_count", bad_pdf)
    code, out = run_main(
        capsys, ["fetch", "https://example.org/y.pdf", "--out", str(tmp_path)]
    )
    assert code == pm.EXIT_FETCH and out["status"] == "not_pdf"
    assert not list(tmp_path.iterdir())
