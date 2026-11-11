# Original editable DOCX fixtures

All text, the 8×8 checker PNG, styles, notes, tables, and headers are synthesized
by `generate.py`. No external documents, images, templates, or copyrighted text
are inputs. These fixtures and their generator use the repository's MIT license.

Run `python tests/fixtures/docx-edit/generate.py` to regenerate, or append
`--check` to compare every committed byte and the manifest. The generator uses
only Python's standard library, fixes ZIP metadata, and stores each part without
ZIP compression. Every DOCX is below the stricter 50,000-byte limit.

| File | Actual bytes | Body paragraphs | All body paragraphs, including cells | Tables | Images | Normal footnotes | Normal endnotes | Sections |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plain.docx | 3,491 | 3 | 3 | 0 | 0 | 0 | 0 | 1 |
| heading.docx | 3,525 | 3 | 3 | 0 | 0 | 0 | 0 | 1 |
| table.docx | 6,092 | 3 | 12 | 1 | 0 | 0 | 0 | 1 |
| image.docx | 4,443 | 3 | 3 | 0 | 1 | 0 | 0 | 1 |
| notes.docx | 5,190 | 3 | 3 | 0 | 0 | 1 | 1 | 1 |
| sections.docx | 4,582 | 3 | 3 | 0 | 0 | 0 | 0 | 2 |

`heading.docx` assigns Heading1 to its first paragraph. `table.docx` has three
rows and three cells in every row. Notes include separator entries, which are
excluded from normal note counts. `sections.docx` has ordered margins
`1440/1440/1440/1440` and `1080/2160/1800/720` twips (top/right/bottom/left),
with a section-linked header containing a real PAGE field.

`manifest.json` pins byte lengths, SHA256 hashes, and initial structural counts.
Regression usage and results are in `../../docx-edit/README.md`.
