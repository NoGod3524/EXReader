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

`roundtrip.py` calls the public SDK: open source DOCX -> `exr_document_export`
to DOCX -> open the exported DOCX and read its text. This is the currently
documented text-profile writer; this revision has no DOCX preserve-profile writer.
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
a controlled, nonprivate EXReader export. Existing product failures are reported
as failures; this task changes no product implementation or existing assertions.
