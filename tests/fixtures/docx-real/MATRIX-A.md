# MATRIX-A: Bridge Round-Trip Fidelity (Read → Model → Write, No Edits)

Each of the 30 original synthetic real-world `.docx` fixtures in `tests/fixtures/docx-real/` is read via `exr_edit_docx_read`, held in `exr_edit_doc` without edits, written back via `exr_edit_docx_write`, and evaluated against the 18-metric verification suite (`M01`–`M18`, combining all 14 `tools/docx/verify_docx.py` checks, all 6 `tools/docx/roundtrip.py` metrics, SDK reread text hash parity, and structural XML fidelity).

## Before vs. After Fixes Summary

| Stage | Fixtures 18/18 PASS | Total Metric Cells PASS | Failing Fixtures & Root Causes |
| --- | --- | --- | --- |
| **Before Fixes (`c04560b7`)** | 25/30 | 450/540 | `02-table-merged-hmerge-vmerge` (0/18 EXR_FORMAT), `10-numbering-restart-override` (0/18 EXR_FORMAT), `11-numbering-style-bound` (0/18 EXR_FORMAT), `12-numbering-chinese-counting` (0/18 EXR_FORMAT), `30-other-header-table-chinese-fields` (0/18 EXR_FORMAT) |
| **After Fixes** | **30/30** | **540/540** | None (0 failures) |

## 18 Metric Definitions (`M01`–`M18`)

| Metric ID | Description |
| --- | --- |
| `M01_package_xml` | ZIP CRC, XML syntax, w:document/w:body integrity (verify_docx #1) |
| `M02_content_types` | [Content_Types].xml main & part content types (verify_docx #2) |
| `M03_relationships` | Root & document relationships integrity (verify_docx #3) |
| `M04_opc_parts` | Non-main OPC parts byte-for-byte retention (styles/numbering/notes/headers/theme/media/comments) |
| `M05_sdk_reread` | Core reader exr_document_open_memory reread & extracted text hash parity |
| `M06_paragraphs` | Paragraph count fidelity (roundtrip.py #1: exact in A, +1 inserted in B) |
| `M07_characters` | Character count & UTF-8 text SHA-256 fidelity (roundtrip.py #2) |
| `M08_para_and_run_props` | Paragraph pPr presence, 480/auto line spacing, TNR 12pt (verify_docx #6-#9) |
| `M09_styles_and_theme` | Style inheritance chain, direct overrides (b=0/i=0, inherited line/indent), theme fonts |
| `M10_tables_and_merges` | Table count (roundtrip.py #3), gridSpan/hMerge/vMerge, nested w:tbl, w:tblHeader, multipara cell guard |
| `M11_fields` | Simple (w:fldSimple) & complex (w:fldChar/w:instrText) PAGE/NUMPAGES/DATE/REF/TOC/Chinese fields |
| `M12_numbering` | Multi-level ilvl, lvlRestart, lvlOverride/startOverride, numStyleLink, Chinese/enclosed numbering |
| `M13_sections_and_margins` | Section count & 4-side margins (roundtrip.py #6) + verify_docx #4/#5/#10/#11 parity |
| `M14_section_cols_and_orient` | Landscape page orientation (w:orient) and multi-column w:cols/w:col definitions |
| `M15_headers_and_footers` | Header/footer parts, references, PAGE field, and header tables (verify_docx #12-#14) |
| `M16_footnotes_and_endnotes` | Footnote count (roundtrip.py #5), footnotePr/numRestart, footnote tables, endnotes |
| `M17_graphics_and_shapes` | Image count & SHA-256 (roundtrip.py #4), wp:inline, wp:anchor wrap, wpg:wgp, v:group |
| `M18_annotations_and_txbx` | Textbox w:txbxContent, comment anchors + comments.xml, bookmarks, vanish hidden text |

## Per-Fixture Bridge Round-Trip Table (30 Fixtures × 18 Metrics = 540 Cells)

| Fixture | Category | Score | `M01` | `M02` | `M03` | `M04` | `M05` | `M06` | `M07` | `M08` | `M09` | `M10` | `M11` | `M12` | `M13` | `M14` | `M15` | `M16` | `M17` | `M18` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `01-table-merged-grid-vmerge` | `tables` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `02-table-merged-hmerge-vmerge` | `tables` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `03-table-nested-subtable` | `tables` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `04-table-repeating-header-multipar-list` | `tables` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `05-field-page-numpages` | `fields` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `06-field-date-formatted` | `fields` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `07-field-ref-crossref` | `fields` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `08-field-toc-complex` | `fields` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `09-numbering-multilevel-nested` | `numbering` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `10-numbering-restart-override` | `numbering` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `11-numbering-style-bound` | `numbering` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `12-numbering-chinese-counting` | `numbering` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `13-style-inheritance-chain` | `styles` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `14-style-direct-override-unbold` | `styles` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `15-style-direct-indent-override` | `styles` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `16-style-theme-fonts` | `styles` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `17-section-multi-margins` | `sections` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `18-section-portrait-landscape-mix` | `sections` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `19-section-columns-1-2-3` | `sections` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `20-section-headers-first-even` | `sections` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `21-footnote-restart-each-page` | `footnotes` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `22-footnote-containing-table` | `footnotes` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `23-footnote-endnote-mixed-formatted` | `footnotes` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `24-graphic-inline-drawing` | `graphics` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `25-graphic-floating-anchor-wrap` | `graphics` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `26-graphic-group-shapes` | `graphics` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `27-other-textbox-txbxcontent` | `other` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `28-other-comment-anchors` | `other` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `29-other-bookmarks-and-vanish` | `other` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| `30-other-header-table-chinese-fields` | `other` | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
