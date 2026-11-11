# MATRIX-B: Edit Side-Effect Matrix (`Matrix B - Matrix A`)

Each of the 30 fixtures in `tests/fixtures/docx-real/` is read via `exr_edit_docx_read`, edited in a transaction (modifying target body paragraph properties via `exr_edit_set_paragraph_props`, inserting a new body paragraph via `exr_edit_insert_paragraph`, verifying table multi-paragraph cell protection and row-insertion `<w:pPr>` preservation, and testing `undo`/`redo`), written via `exr_edit_docx_write`, and compared against `MATRIX-A` to measure extra edit side-effect losses (`Matrix B - Matrix A`).

## Before vs. After Fixes Summary

| Stage | Fixtures 18/18 PASS | Total Metric Cells PASS | Extra Edit Losses (`Matrix B - Matrix A`) | Root Causes of Extra Losses |
| --- | --- | --- | --- | --- |
| **Before Fixes (`c04560b7`)** | 21/30 | 442/540 | 8 cells across 4 fixtures | `04-table-repeating-header-multipar-list (M08,M10)`; `13-style-inheritance-chain (M08,M09)`; `14-style-direct-override-unbold (M08,M09)`; `15-style-direct-indent-override (M08,M09)` |
| **After Fixes** | **30/30** | **540/540** | **0 cells across 0 fixtures** | None (0 edit side-effect losses) |

## Per-Fixture Edit Side-Effect Table (30 Fixtures × 18 Metrics = 540 Cells)

| Fixture | Category | Matrix A | Matrix B | Extra Loss (`B - A`) | `M01` | `M02` | `M03` | `M04` | `M05` | `M06` | `M07` | `M08` | `M09` | `M10` | `M11` | `M12` | `M13` | `M14` | `M15` | `M16` | `M17` | `M18` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `01-table-merged-grid-vmerge` | `tables` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `02-table-merged-hmerge-vmerge` | `tables` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `03-table-nested-subtable` | `tables` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `04-table-repeating-header-multipar-list` | `tables` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `05-field-page-numpages` | `fields` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `06-field-date-formatted` | `fields` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `07-field-ref-crossref` | `fields` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `08-field-toc-complex` | `fields` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `09-numbering-multilevel-nested` | `numbering` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `10-numbering-restart-override` | `numbering` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `11-numbering-style-bound` | `numbering` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `12-numbering-chinese-counting` | `numbering` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `13-style-inheritance-chain` | `styles` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `14-style-direct-override-unbold` | `styles` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `15-style-direct-indent-override` | `styles` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `16-style-theme-fonts` | `styles` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `17-section-multi-margins` | `sections` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `18-section-portrait-landscape-mix` | `sections` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `19-section-columns-1-2-3` | `sections` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `20-section-headers-first-even` | `sections` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `21-footnote-restart-each-page` | `footnotes` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `22-footnote-containing-table` | `footnotes` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `23-footnote-endnote-mixed-formatted` | `footnotes` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `24-graphic-inline-drawing` | `graphics` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `25-graphic-floating-anchor-wrap` | `graphics` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `26-graphic-group-shapes` | `graphics` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `27-other-textbox-txbxcontent` | `other` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `28-other-comment-anchors` | `other` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `29-other-bookmarks-and-vanish` | `other` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `30-other-header-table-chinese-fields` | `other` | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
