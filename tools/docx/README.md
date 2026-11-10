# W3 DOCX verification

`verify_docx.py` uses only Python's standard library. It never imports or calls
EXReader. It audits ZIP CRC/XML syntax, package entry points, nonempty sections,
every body paragraph's properties (including table cells), effective double
spacing, Times New Roman/12pt text runs, Letter paper, one-inch margins, and a
section-linked header containing a PAGE field. Missing/unused headers warn;
absence of a used PAGE field fails. Formatting inherited through document
defaults and paragraph/character styles is resolved; unknown fonts fail.

This is the requested formatting profile, not full OOXML schema validation or
proof that the Microsoft Word desktop application opened a file.

```powershell
python -m unittest discover -s tests/docx -v
python tools/docx/verify_docx.py input.docx --json build/verification.json
python tools/docx/roundtrip.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/w3-roundtrip
```

The verifier exits 1 if any check fails and prints **all** failing XML elements.
The self-test first runs a valid DOCX through the CLI (exit 0), then removes its
`pgSz` and requires exit 1 and XML context. Additional mutations cover each
formatting requirement, malformed input, inheritance, later sections and
same-length text substitutions.

By default `roundtrip.py` calls the read-only SDK exporter. `--editable` instead
uses `exr_edit_docx_open` -> `exr_edit_docx_write` -> SDK reread. Both paths use
the same independent six-metric comparison for each of the three real inputs.
Editable mode compares the formatting verifier's results against the source:
arbitrary inputs retain their fonts, margins and styles. Text/image hashes and
all six metrics must match.

```powershell
python tools/docx/roundtrip.py --editable --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/x1-roundtrip
python tests/docx/check_edit_bridge.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/x1-edits
ctest --test-dir build/native -R native-docx-edit-io --output-on-failure
```

The editable API is declared in `exr/formats.h`; its model remains in
`exr/edit.h`. It calls the existing DOCX reader for semantic validation and the
existing XML DOM for direct pPr/rPr/sectPr mapping. A second Expat pass records
source byte spans. All OPC members are deep copied, including media, note and
relationship parts. Tables expose rows, cells and paragraph blocks; unknown
blocks and complex inline XML retain their original bytes.
Plain direct text runs remain editable; fields, hyperlinks and mixed-content
runs are preserved as whole opaque runs. Property edits retain unmodelled
property children and unknown attributes. Splits/deletions place section breaks
at the remaining section boundary. Source styles, headers and footers stay in
their original parts. New documents receive Letter sections, one-inch margins
and a header with dirty PAGE and DATE fields and 12pt Times New Roman defaults.

## Table and image editing (X6)

`exr/edit.h` exposes `exr_edit_table`, `exr_edit_row`, `exr_edit_cell` and the
`exr_edit_table_insert_row`, `delete_row`, `set_cell_text`, `set_width` and
`set_borders` commands. Indices are zero-based physical cells; `SIZE_MAX` inserts
before the first row. `set_cell_text` replaces the cell's paragraphs with one
paragraph containing the supplied text runs. New runs receive fresh IDs.
Borders accept `EXR_EDIT_BORDER_NONE`, `SINGLE` and `DOUBLE`; widths use twips.
Rows/cells/paragraphs/runs retain their IDs across edits and undo/redo.

Merged, nested, shaded and other opaque cell contents are protected from text
replacement (`EXR_UNSUPPORTED`). Other cells/rows in that table remain editable.
Insertion/deletion cannot split a vertical merge chain. Unsupported cells,
unmodified rows, grid properties and unmodelled XML keep their original bytes.
Caller-created rows leave `source_index` zero; empty cells receive an empty
paragraph on export. Tables can also be seeded through `exr_edit_doc_create`.

`exr_edit_insert_image` accepts PNG/JPEG bytes with a byte count and positive
finite point dimensions, and returns a new block ID. Export creates media,
relationships, MIME declarations and an inline drawing with 12700 EMU per point.
Payload bytes are copied without re-encoding. `exr_edit_delete_image` accepts a
new image block ID or an imported opaque drawing run ID; a paragraph ID removes
its image drawings while retaining text and non-image drawings. Imported runs
inside table cells are supported. `exr_edit_delete_table` removes a table.
All commands use the existing transaction/undo/redo history. Export removes
deleted-image relationships and media no longer targeted by any remaining OPC
relationship, while preserving shared media and unrelated original parts.

```powershell
ctest --test-dir build/native -R native-docx-edit-x6 --output-on-failure
python tests/test_docx_edit_table_image.py --library build/native/libexreader.dll --output build/x6-evidence all
python tests/docx/check_table_image.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/x6-real
```

The real-input check compares the original, unedited bridge output and edited
output with #117's unchanged six-metric auditor (three files, 18 comparisons).
Protected or empty original cells are exercised through a temporary new row
and a persistent table-width edit. Other inputs persist an original-cell text
edit of equal character length. The six synthetic fixtures separately require
original-cell text edits, correct row/column counts and byte-preserved parts.
See `docs/DOCX-X6.md` for measured results and the preserved merged-cell XML.

XML in the main part and package relationships must be UTF-8 (US-ASCII is also
accepted). Other XML encodings return `EXR_UNSUPPORTED` with a null output.
Packed input and the total extracted parts are limited to 128 MiB, with at most
10,000 OPC entries and the existing XML DOM depth/node limits. `write` returns
memory; callers save it only after success.
Caller-seeded paragraph/text templates must match their retained original main
part. Unresolvable templates return `EXR_UNSUPPORTED` instead of being omitted.
The source and exported ZIP/XML are independently
measured. It compares six metrics and exits 1 on **any** drift, including increases:

| Metric | Definition |
| --- | --- |
| Paragraphs | All `w:p` descendants of the main body, including table cells |
| Characters | Unicode code points of `w:t` in body + normal footnotes/endnotes; no added separators |
| Tables | All `w:tbl` descendants of the main body |
| Images | DrawingML `a:blip` and VML `v:imagedata` XML occurrences in body + notes; alternate representations count separately |
| Footnotes | Normal footnote elements in the relationship-linked footnotes part, excluding separator types |
| Section margins | Ordered top/right/bottom/left attributes per `sectPr`; absent values are null, never silently defaulted |

Text SHA256 and media-payload SHA256 comparisons additionally detect equal-count
content substitutions. SDK text equality is reported separately: it cannot prove
that the independent original DOCX structure survived. Exact source SHA256 is
required before processing. A read/export/re-read error is an ERROR, never a PASS.

Real inputs are not redistributed. Place unmodified local copies at the paths
in `tests/docx/corpus.json` (relative to that manifest). Their hashes identify the
tested revisions. The corpus covers a real Minitab course manual chapter (tables
and images), a course syllabus (five sections), and the published UN report
[A/HRC/40/69](https://www.ohchr.org/sites/default/files/HRBodies/HRC/RegularSessions/Session40/Documents/A_HRC_40_69.docx)
(five actual footnotes). Sources were not augmented to manufacture coverage.

If `soffice` and `pdftotext` are on PATH, the runner converts both files with an
isolated LibreOffice profile and compares page counts and every page's text.
Paths may also be passed with `--soffice` and `--pdftotext`. It normalizes trailing
line whitespace and page-edge whitespace only. Every changed page is listed
with text hashes; complete unified text diffs stay in the output folder.
Unavailable tools produce SKIP; conversion errors produce ERROR.

Full local reports (including failing XML and source text contexts) stay under
ignored `build/`. Committed evidence removes those XML contexts and contains only
counts, hashes and statuses. `tests/docx/evidence/profile.txt` retains full XML for
a controlled, nonprivate EXReader export. Original verifier assertions and the
read-only export path remain available.
