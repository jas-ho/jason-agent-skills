---
name: paper-md
description: Turn a paper, report or policy brief into clean, quotable Markdown, converted locally with Marker plus deterministic cleanup (margin line numbers, running headers/footers, page-break splits, dropped maths symbols, heading levels) and a triage report of what still needs checking against the PDF. Input is a local PDF, an arXiv ID/URL, a DOI or a direct PDF URL. Use when Jason wants to read, annotate, review or quote a PDF document in Markdown or Obsidian, including confidential submissions under review; peer-review uses it. Not for Office files (markitdown) or for redacting PII (redact-pdf).
---

# Paper PDF to quotable Markdown

The script `scripts/paper_md.py` next to this SKILL.md does the mechanical work. The agent settles confidentiality first and judges the leftovers afterwards. Run it as `python3 "<skill-dir>/scripts/paper_md.py" ...`, where `<skill-dir>` is the directory of the loaded SKILL.md. It needs only the standard library plus three tools on PATH: `marker_single` (marker-pdf, a Mac pipx install), and `pdftotext` and `pdfinfo` (poppler).

## 1. Confidentiality first

Marker runs locally, but you are a cloud model: whatever you read from the Markdown, the page images or the report's excerpts leaves the machine.

- **Public document:** go ahead.
- **Confidential document** (a submission under review, an NDA draft): look for the stance record in the project STATUS.md. It lists the class, which harnesses may read the content and the allowed activities.
  - A stance record without "convert" means no conversion at all.
  - Pass `--no-excerpts` whenever this harness may not read the content: no record yet, a record that does not list this harness, or one without "conversion QA". The report then carries kinds, page numbers and counts only. Marker's stderr carries progress and file paths only; the file names are the one piece of identifying text you will see.
  - No record: ask Jason before reading anything.
  - "Conversion QA" not allowed: hand Jason the `unresolved` list and do not open the Markdown or images yourself.
  - Never fetch a confidential document from the web and never upload it anywhere.

## 2. Get the PDF

For a public remote source, run:

```bash
python3 "<skill-dir>/scripts/paper_md.py" fetch SOURCE --out DIR
```

SOURCE can be an arXiv ID or URL, a DOI (the script finds the open-access PDF via OpenAlex) or a direct PDF URL.

| Exit | Status | What to do |
| --- | --- | --- |
| 0 | `outputs.pdf` holds the file | An existing file is never replaced; a re-fetch writes `.v2.pdf` |
| 6 | `no_open_access_pdf` | Ask Jason for the file |
| 6 | `not_pdf` | Publisher page or login wall: ask Jason for the file |
| 6 | `download_failed` / `lookup_failed` | Network problem: retry once, then ask |

## 3. Convert

```bash
python3 "<skill-dir>/scripts/paper_md.py" convert PDF [--out DIR] [--name STEM] [--fast] [--no-excerpts]
```

- **Outputs:** `<stem>.md` next to the PDF (or in `--out`), plus `<stem>_figures/` with the images. An existing note is never overwritten; a rerun writes `<stem>.v2.md`. Replacing an annotated note is Jason's call, done through co-edit.
- **Run time:** about 8 s per page with OCR (the default). OCR is what gives proper inline LaTeX; `--disable_ocr` mangled inline maths on maths-heavy papers.
- **`--fast`:** skips OCR, about 3-5× faster. Offer it only for a prose document when speed matters, and say it may lose maths. It is refused automatically for scans.
- **One run at a time:** a second call exits 5 (busy) at once, before doing any work. Run convert in the foreground, or as one background job you wait on; never start a second while one runs. Ctrl-C or SIGTERM stops Marker too: SIGTERM first, then SIGKILL after 5 s.
- **First run:** Marker downloads about 1 GB of models, and a note says so.
- **Exit 3:** a tool is missing (`dependency_missing`) or not accessible (`dependency_denied`, e.g. a sandbox that cannot read the pipx venv). Report which and stop.

stdout is always one JSON object, failures included: `status`, `outputs`, `counts` (what each pass changed), `unresolved` (what it could not decide, with 1-based PDF pages), `notes`, and `error` on failure. Code fences, tables and display maths are not rewritten. Two exceptions: page links in table cells become plain text, and a fence holding five or more of its page's margin line numbers, each 1-3 above the previous, loses those number lines (Marker puts boxed prompts into fences). Shorter or irregular runs are kept and reported as `line_number_leftover`.

## 4. Check the leftovers against the PDF

Do this only where the stance allows conversion QA; otherwise give Jason the list. Go through `unresolved` by kind:

| Kind | Meaning and fix |
| --- | --- |
| `symbol_gap`, `check_maths_symbols` | Maths symbols dropped or not matched uniquely. Look at the PDF page and fix the formula text. |
| `numbers_not_in_pdf_text` | A number in the md that the PDF text of that page lacks. Often a converter error or a leftover line number, sometimes harmless (LaTeX, a footnote marker). |
| `caption_without_figure_or_table`, `several_images_on_page` | A figure was probably flattened into text or split into pieces. |
| `probable_line_number_strip` | A narrow tall image, usually a margin line-number strip. Confirm on the page, then delete the embed and the file. |
| `possible_page_break_split` | A paragraph may be split at a page break. Join it if the PDF shows one paragraph. |
| `page_text_short`, `page_without_text` | Text missing for that page, often a table rendered as an image, or a scan. |
| `pages_without_reference_text` | Pages with no PDF text layer (scans). Their OCR text could not be cross-checked at all. |
| `line_number_leftover`, `header_footer_text_kept`, `glued_number_kept` | Leftover margin numbers or header text. A single number next to text is kept because it may be data. Remove it if the PDF shows it is a margin number. |

To fix a flattened or split figure:
1. Re-render the figure from the PDF: `pdftoppm -f N -l N -r 200 -png -x X -y Y -W W -H H -singlefile PDF <stem>_figures/<name>`. N is the 1-based page; the pixel coordinates are measured at 200 dpi on a rendered page image, so render the whole page first (`pdftoppm -f N -l N -r 200 -png PDF page`) and read the box off it.
2. Replace the pieces with the one image.
3. Delete the superseded fragments, including loose bar values or axis labels left as text.

The flags are triage only. When conversion QA is allowed, also compare every figure and table with its PDF page once, flagged or not.

Finish all fixes before Jason starts annotating. After that, every change goes through co-edit and competes with his cursor.

## 5. Report

Tell Jason in two or three lines:
- where the note is;
- what the cleanup changed;
- what is still unverified, e.g. "maths on pp. 6 and 12 not checked; Fig. 3 re-rendered".

The note's first line already says it is a machine reconstruction to check against the PDF before quoting.
