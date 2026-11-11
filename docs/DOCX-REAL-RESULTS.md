# DOCX Real-World Round-Trip & Edit Fidelity Results (Union of PR #126 and PR #132)

Base commit: `c04560b784bda182b350b9f6faac33a10ed60509` (`origin/codex/dx-integration-20261110`).
This report documents the **union merge of PR #126 (`codex/dx-realworld-20261110`) into PR #132 (`codex/dx-realworld-argon-20261110`)**, combining both complementary sets of fixes and evaluating **all four 30×18 matrices (`Matrix A-argon`, `Matrix B-argon`, `Matrix A-codex`, `Matrix B-codex`)** across all 60 committed `.docx` fixtures (`tests/fixtures/docx-real/argon/` and `tests/fixtures/docx-real/codex/`).

## Executive Summary

| Matrix | Suite | Operation | Pre-Fix Score (`c04560b7`) | Post-Union Score | Extra Edit Losses (`B - A`) |
| --- | --- | --- | ---: | ---: | ---: |
| **`Matrix A-argon`** | Argon (30 fixtures in `tests/fixtures/docx-real/argon/`) | Read → Model → Write (no-op) | 450/540 (25/30 fixtures) | **540/540 (30/30 fixtures, 100%)** | — |
| **`Matrix B-argon`** | Argon (30 fixtures in `tests/fixtures/docx-real/argon/`) | Read → Paragraph Props + Insert Para + Table Row/Cell Guards + Undo/Redo → Write | 442/540 (21/30 fixtures) | **540/540 (30/30 fixtures, 100%)** | **0 cells (0 fixtures)** |
| **`Matrix A-codex`** | Codex (30 fixtures in `tests/fixtures/docx-real/codex/`) | Read → Model → Write (`noop`, exact OPC payload check) | 531/540 (21/30 exact) | **540/540 (30/30 exact, 100%)** | — |
| **`Matrix B-codex`** | Codex (30 fixtures in `tests/fixtures/docx-real/codex/`) | Read → `exr_edit_set_run_text` single-run replacement → Write (`edited`, exact oracle check) | 531/540 (21/30 exact) | **540/540 (30/30 exact, 100%)** | **0 cells (0 fixtures)** |
| **Total** | **60 fixtures (2 suites × 30)** | **4 Matrices × 540 cells** | **1,954 / 2,160** | **2,160 / 2,160 (100%)** | **0** |

---

## Union of Fixes & Conflict Resolution Rationale

### 1. Complementary Fixes Retained in the Union

| Origin | Files Modified | Root Cause Fixed | Impact |
| --- | --- | --- | --- |
| **PR #132 (Argon) — Fix 1** | `src/numbering.c`, `src/docx.c` | Added ECMA-376 CJK/enclosed/ordinal/bullet numbering formats (`chineseCounting`, `chineseCountingThousand`, `chineseLegalSimplified`, `ideographTraditional`, `ideographDigital`, `decimalEnclosedCircle`, `ordinal`, `cardinalText`, etc.), 1-based `w:lvlRestart` (`lvl - 1`), and `w:numStyleLink` → `w:styleLink` abstract numbering resolution. | `Matrix A-argon`: 450/540 → 522/540 (+72 cells)<br>`Matrix B-argon`: 442/540 → 514/540 (+72 cells) |
| **PR #132 (Argon) — Fix 2** | `src/docx.c`, `src/docx_edit_table.c` | Combined legacy horizontal `w:hMerge` (`restart`/`continue`) with `w:vMerge` in `src/docx.c`; marked multi-paragraph table cells (`cell->block_count > 1`) with `EXR_EDIT_CELL_OPAQUE` in `exr_edit_table_decode`; preserved `<w:pPr>` template (`opaque_xml`) when `exr_edit_table_insert_row` clones cell paragraph formatting. | `Matrix A-argon`: 522/540 → 540/540 (+18 cells)<br>`Matrix B-argon`: 514/540 → 534/540 (+20 cells) |
| **PR #132 (Argon) — Fix 3** | `src/docx_edit_io.c` | Updated `emit_para_prop` (`k == 4` `w:spacing` and `k == 5` `w:ind`) to omit zero-valued attributes (`w:line="0"`, `w:left="0"`, `w:right="0"`, `w:firstLine="0"`) when absent on the source XML element, preventing direct edits on sibling attributes from clobbering style-inherited spacing/indentation. | `Matrix B-argon`: 534/540 → 540/540 (+6 cells; `Matrix B - Matrix A` extra losses 6 → 0) |
| **PR #126 (Codex) — Text API** | `include/exr/edit.h`, `src/docx_edit.c` | Added public transactional `exr_edit_set_run_text` replacing a single `EXR_EDIT_TEXT` run while preserving block/run IDs, direct formatting, `opaque_xml` templates, and `EXR_EDIT_OPAQUE_RUN` neighbors (with full undo/redo and allocator-fault rollback). | Enables direct public text replacement for `Matrix B-codex` (`531/540 → 531/540` prior to XML ordering fixes) |
| **PR #126 (Codex) — T1-01** | `src/docx_edit_io.c` | In `exr_edit_xml_paragraph`, emit a leading `EXR_EDIT_OPAQUE_RUN` that spans `x->spans[n].open .. x->spans[pr].start` *before* `write_properties` (`<w:pPr>`), keeping comments/PIs before `<w:pPr>` in their original lexical position. | `Matrix A-codex` & `Matrix B-codex`: 531/540 → 537/540 (+6 cells each; exact OPC payloads 21/30 → 27/30) |
| **PR #126 (Codex) — T1-02** | `src/docx_edit_io.c` | In `exr_edit_docx_write`, emit the final body `<w:sectPr>` *before* trailing body-level `trivia_block` (comments/PIs after `<w:sectPr>`), and pass `replacement = NULL` when a paragraph-hosted `<w:sectPr>` is unchanged and remains on its original `<w:p>` (avoiding redundant namespace declarations). | `Matrix A-codex` & `Matrix B-codex`: 537/540 → 540/540 (+3 cells each; exact OPC payloads 27/30 → 30/30) |

### 2. Conflict & Composition Analysis

1. **`src/docx_edit_io.c` Composition (`emit_para_prop` + `exr_edit_xml_paragraph` + `sectPr` handling)**:
   - Codex's `exr_edit_xml_paragraph` fix checks whether `p->runs[0]` is a pre-`<w:pPr>` lexical trivia span (`x->spans[n].open .. x->spans[pr].start`) and emits it before calling `write_properties(b, x, pr, &p->props, 1, section, section_data)`.
   - Inside `write_properties`, `pr` is still the exact `<w:pPr>` node index in `x->tree`. When a paragraph property is left unchanged (`changed == 0` and `sectPr` is unchanged), `write_properties` emits `pr` raw (`exr_edit_xml_raw(b, x, n)`), preserving byte-for-byte identity required by `Matrix A-codex` and `Matrix B-codex`.
   - When paragraph properties *are* edited via `exr_edit_set_paragraph_props` (`changed != 0`, as in `Matrix B-argon`), `write_properties` calls `emit_para_prop(b, x, i, k, props)` where `i` is the `<w:spacing>` or `<w:ind>` child of `<w:pPr>`. Argon's zero-value omission check (`nd = n == NONE ? NULL : x->tree->nodes + n`) inspects `i`'s existing attributes and omits absent zero-valued attributes so style inheritance stays intact.
   - We verified this combined path with a dedicated union regression in `tests/test_docx_edit_io.py` (`properties` group) that simultaneously exercises pre-`<w:pPr>` comments/PIs, style-inherited `w:line`/`w:left` with `exr_edit_set_paragraph_props`, `exr_edit_set_run_text` on the text run, and post-`<w:sectPr>` trailing comments/PIs.
2. **`tests/fixtures/docx-real/` Directory Split**:
   - Both PRs originally placed 30 `.docx` files and `manifest.json` in `tests/fixtures/docx-real/` (colliding on `manifest.json` and `16-style-theme-fonts.docx`).
   - Per the merge specification, both 30-fixture sets and their generators are retained in subdirectories:
     - `tests/fixtures/docx-real/argon/` (30 fixtures + `make_fixtures.py` + `manifest.json` + `MATRIX-A.md` + `MATRIX-B.md`)
     - `tests/fixtures/docx-real/codex/` (30 fixtures + `generate.py` + `manifest.json` + `run_matrix.py` + `regressions.py` + `oracle_mutations.py` + `test_text_alloc.c` + `register.cmake`)
3. **`CMakeLists.txt` Test Registration Union**:
   - Registered `native-docx-realworld-matrix` (Argon 30×18 Matrix A & Matrix B), `native-docx-real-argon-reproducible` (`argon/make_fixtures.py --check`), and included `tests/fixtures/docx-real/codex/register.cmake` (70 Codex CTest cases: `native-docx-real-reproducible`, 60 per-fixture `noop`/`edited` cases, 7 targeted regressions, `native-docx-real-oracle-mutations`, and `native-docx-real-text-allocation`).

---

## Matrix 1: `Matrix A-argon` — Bridge Round-Trip Fidelity (Read → Model → Write, No Edits)

Each of the 30 synthetic structural `.docx` fixtures in `tests/fixtures/docx-real/argon/` is read via `exr_edit_docx_read`, held in `exr_edit_doc` without edits, written back via `exr_edit_docx_write`, and evaluated against the 18-metric verification suite (`M01`–`M18`, combining all 14 `tools/docx/verify_docx.py` checks, all 6 `tools/docx/roundtrip.py` metrics, SDK reread text hash parity, and structural XML fidelity).

### `M01`–`M18` Metric Definitions (Argon Suite)

| Metric ID | Description |
| --- | --- |
| `M01_package_xml` | ZIP CRC, XML syntax, `w:document`/`w:body` integrity (`verify_docx` #1) |
| `M02_content_types` | `[Content_Types].xml` main & part content types (`verify_docx` #2) |
| `M03_relationships` | Root & document relationships integrity (`verify_docx` #3) |
| `M04_opc_parts` | Non-main OPC parts byte-for-byte retention (styles/numbering/notes/headers/theme/media/comments) |
| `M05_sdk_reread` | Core reader `exr_document_open_memory` reread & extracted text hash parity |
| `M06_paragraphs` | Paragraph count fidelity (`roundtrip.py` #1: exact in A, +1 inserted in B) |
| `M07_characters` | Character count & UTF-8 text SHA-256 fidelity (`roundtrip.py` #2) |
| `M08_para_and_run_props` | Paragraph `pPr` presence, 480/auto line spacing, TNR 12pt (`verify_docx` #6–#9) |
| `M09_styles_and_theme` | Style inheritance chain, direct overrides (`b=0`/`i=0`, inherited line/indent), theme fonts |
| `M10_tables_and_merges` | Table count (`roundtrip.py` #3), `gridSpan`/`hMerge`/`vMerge`, nested `w:tbl`, `w:tblHeader`, multipara cell guard |
| `M11_fields` | Simple (`w:fldSimple`) & complex (`w:fldChar`/`w:instrText`) `PAGE`/`NUMPAGES`/`DATE`/`REF`/`TOC`/Chinese fields |
| `M12_numbering` | Multi-level `ilvl`, `lvlRestart`, `lvlOverride`/`startOverride`, `numStyleLink`, Chinese/enclosed numbering |
| `M13_sections_and_margins` | Section count & 4-side margins (`roundtrip.py` #6) + `verify_docx` #4/#5/#10/#11 parity |
| `M14_section_cols_and_orient` | Landscape page orientation (`w:orient`) and multi-column `w:cols`/`w:col` definitions |
| `M15_headers_and_footers` | Header/footer parts, references, `PAGE` field, and header tables (`verify_docx` #12–#14) |
| `M16_footnotes_and_endnotes` | Footnote count (`roundtrip.py` #5), `footnotePr`/`numRestart`, footnote tables, endnotes |
| `M17_graphics_and_shapes` | Image count & SHA-256 (`roundtrip.py` #4), `wp:inline`, `wp:anchor` wrap, `wpg:wgp`, `v:group` |
| `M18_annotations_and_txbx` | Textbox `w:txbxContent`, comment anchors + `comments.xml`, bookmarks, `vanish` hidden text |

### `Matrix A-argon` Per-Fixture Table (30 Fixtures × 18 Metrics = 540/540 PASS)

| Fixture | Category | Pre-Fix | Post-Union | `M01` | `M02` | `M03` | `M04` | `M05` | `M06` | `M07` | `M08` | `M09` | `M10` | `M11` | `M12` | `M13` | `M14` | `M15` | `M16` | `M17` | `M18` |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [`01-table-merged-grid-vmerge`](../tests/fixtures/docx-real/argon/01-table-merged-grid-vmerge.docx) | `tables` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`02-table-merged-hmerge-vmerge`](../tests/fixtures/docx-real/argon/02-table-merged-hmerge-vmerge.docx) | `tables` | 0/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`03-table-nested-subtable`](../tests/fixtures/docx-real/argon/03-table-nested-subtable.docx) | `tables` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`04-table-repeating-header-multipar-list`](../tests/fixtures/docx-real/argon/04-table-repeating-header-multipar-list.docx) | `tables` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`05-field-page-numpages`](../tests/fixtures/docx-real/argon/05-field-page-numpages.docx) | `fields` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`06-field-date-formatted`](../tests/fixtures/docx-real/argon/06-field-date-formatted.docx) | `fields` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`07-field-ref-crossref`](../tests/fixtures/docx-real/argon/07-field-ref-crossref.docx) | `fields` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`08-field-toc-complex`](../tests/fixtures/docx-real/argon/08-field-toc-complex.docx) | `fields` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`09-numbering-multilevel-nested`](../tests/fixtures/docx-real/argon/09-numbering-multilevel-nested.docx) | `numbering` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`10-numbering-restart-override`](../tests/fixtures/docx-real/argon/10-numbering-restart-override.docx) | `numbering` | 0/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`11-numbering-style-bound`](../tests/fixtures/docx-real/argon/11-numbering-style-bound.docx) | `numbering` | 0/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`12-numbering-chinese-counting`](../tests/fixtures/docx-real/argon/12-numbering-chinese-counting.docx) | `numbering` | 0/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`13-style-inheritance-chain`](../tests/fixtures/docx-real/argon/13-style-inheritance-chain.docx) | `styles` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`14-style-direct-override-unbold`](../tests/fixtures/docx-real/argon/14-style-direct-override-unbold.docx) | `styles` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`15-style-direct-indent-override`](../tests/fixtures/docx-real/argon/15-style-direct-indent-override.docx) | `styles` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`16-style-theme-fonts`](../tests/fixtures/docx-real/argon/16-style-theme-fonts.docx) | `styles` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`17-section-multi-margins`](../tests/fixtures/docx-real/argon/17-section-multi-margins.docx) | `sections` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`18-section-portrait-landscape-mix`](../tests/fixtures/docx-real/argon/18-section-portrait-landscape-mix.docx) | `sections` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`19-section-columns-1-2-3`](../tests/fixtures/docx-real/argon/19-section-columns-1-2-3.docx) | `sections` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`20-section-headers-first-even`](../tests/fixtures/docx-real/argon/20-section-headers-first-even.docx) | `sections` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`21-footnote-restart-each-page`](../tests/fixtures/docx-real/argon/21-footnote-restart-each-page.docx) | `footnotes` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`22-footnote-containing-table`](../tests/fixtures/docx-real/argon/22-footnote-containing-table.docx) | `footnotes` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`23-footnote-endnote-mixed-formatted`](../tests/fixtures/docx-real/argon/23-footnote-endnote-mixed-formatted.docx) | `footnotes` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`24-graphic-inline-drawing`](../tests/fixtures/docx-real/argon/24-graphic-inline-drawing.docx) | `graphics` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`25-graphic-floating-anchor-wrap`](../tests/fixtures/docx-real/argon/25-graphic-floating-anchor-wrap.docx) | `graphics` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`26-graphic-group-shapes`](../tests/fixtures/docx-real/argon/26-graphic-group-shapes.docx) | `graphics` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`27-other-textbox-txbxcontent`](../tests/fixtures/docx-real/argon/27-other-textbox-txbxcontent.docx) | `other` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`28-other-comment-anchors`](../tests/fixtures/docx-real/argon/28-other-comment-anchors.docx) | `other` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`29-other-bookmarks-and-vanish`](../tests/fixtures/docx-real/argon/29-other-bookmarks-and-vanish.docx) | `other` | 18/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`30-other-header-table-chinese-fields`](../tests/fixtures/docx-real/argon/30-other-header-table-chinese-fields.docx) | `other` | 0/18 | **18/18** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| **Total (`Matrix A-argon`)** | **8 categories** | **450/540** | **540/540** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** |

---

## Matrix 2: `Matrix B-argon` — Edit Side-Effect Matrix (`Matrix B - Matrix A`)

Each of the 30 fixtures in `tests/fixtures/docx-real/argon/` is read via `exr_edit_docx_read`, edited in a transaction (modifying target body paragraph properties via `exr_edit_set_paragraph_props`, inserting a new body paragraph via `exr_edit_insert_paragraph`, verifying table multi-paragraph cell protection and row-insertion `<w:pPr>` preservation, and testing `exr_edit_undo`/`exr_edit_redo`), written via `exr_edit_docx_write`, and compared against `Matrix A-argon`.

### `Matrix B-argon` Per-Fixture Table (30 Fixtures × 18 Metrics = 540/540 PASS, Extra Loss = 0)

| Fixture | Category | Pre-Fix B | Post-Union A | Post-Union B | Extra Loss (`B - A`) | `M01` | `M02` | `M03` | `M04` | `M05` | `M06` | `M07` | `M08` | `M09` | `M10` | `M11` | `M12` | `M13` | `M14` | `M15` | `M16` | `M17` | `M18` |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [`01-table-merged-grid-vmerge`](../tests/fixtures/docx-real/argon/01-table-merged-grid-vmerge.docx) | `tables` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`02-table-merged-hmerge-vmerge`](../tests/fixtures/docx-real/argon/02-table-merged-hmerge-vmerge.docx) | `tables` | 0/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`03-table-nested-subtable`](../tests/fixtures/docx-real/argon/03-table-nested-subtable.docx) | `tables` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`04-table-repeating-header-multipar-list`](../tests/fixtures/docx-real/argon/04-table-repeating-header-multipar-list.docx) | `tables` | 16/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`05-field-page-numpages`](../tests/fixtures/docx-real/argon/05-field-page-numpages.docx) | `fields` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`06-field-date-formatted`](../tests/fixtures/docx-real/argon/06-field-date-formatted.docx) | `fields` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`07-field-ref-crossref`](../tests/fixtures/docx-real/argon/07-field-ref-crossref.docx) | `fields` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`08-field-toc-complex`](../tests/fixtures/docx-real/argon/08-field-toc-complex.docx) | `fields` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`09-numbering-multilevel-nested`](../tests/fixtures/docx-real/argon/09-numbering-multilevel-nested.docx) | `numbering` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`10-numbering-restart-override`](../tests/fixtures/docx-real/argon/10-numbering-restart-override.docx) | `numbering` | 0/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`11-numbering-style-bound`](../tests/fixtures/docx-real/argon/11-numbering-style-bound.docx) | `numbering` | 0/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`12-numbering-chinese-counting`](../tests/fixtures/docx-real/argon/12-numbering-chinese-counting.docx) | `numbering` | 0/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`13-style-inheritance-chain`](../tests/fixtures/docx-real/argon/13-style-inheritance-chain.docx) | `styles` | 16/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`14-style-direct-override-unbold`](../tests/fixtures/docx-real/argon/14-style-direct-override-unbold.docx) | `styles` | 16/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`15-style-direct-indent-override`](../tests/fixtures/docx-real/argon/15-style-direct-indent-override.docx) | `styles` | 16/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`16-style-theme-fonts`](../tests/fixtures/docx-real/argon/16-style-theme-fonts.docx) | `styles` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`17-section-multi-margins`](../tests/fixtures/docx-real/argon/17-section-multi-margins.docx) | `sections` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`18-section-portrait-landscape-mix`](../tests/fixtures/docx-real/argon/18-section-portrait-landscape-mix.docx) | `sections` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`19-section-columns-1-2-3`](../tests/fixtures/docx-real/argon/19-section-columns-1-2-3.docx) | `sections` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`20-section-headers-first-even`](../tests/fixtures/docx-real/argon/20-section-headers-first-even.docx) | `sections` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`21-footnote-restart-each-page`](../tests/fixtures/docx-real/argon/21-footnote-restart-each-page.docx) | `footnotes` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`22-footnote-containing-table`](../tests/fixtures/docx-real/argon/22-footnote-containing-table.docx) | `footnotes` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`23-footnote-endnote-mixed-formatted`](../tests/fixtures/docx-real/argon/23-footnote-endnote-mixed-formatted.docx) | `footnotes` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`24-graphic-inline-drawing`](../tests/fixtures/docx-real/argon/24-graphic-inline-drawing.docx) | `graphics` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`25-graphic-floating-anchor-wrap`](../tests/fixtures/docx-real/argon/25-graphic-floating-anchor-wrap.docx) | `graphics` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`26-graphic-group-shapes`](../tests/fixtures/docx-real/argon/26-graphic-group-shapes.docx) | `graphics` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`27-other-textbox-txbxcontent`](../tests/fixtures/docx-real/argon/27-other-textbox-txbxcontent.docx) | `other` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`28-other-comment-anchors`](../tests/fixtures/docx-real/argon/28-other-comment-anchors.docx) | `other` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`29-other-bookmarks-and-vanish`](../tests/fixtures/docx-real/argon/29-other-bookmarks-and-vanish.docx) | `other` | 18/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`30-other-header-table-chinese-fields`](../tests/fixtures/docx-real/argon/30-other-header-table-chinese-fields.docx) | `other` | 0/18 | 18/18 | **18/18** | **0** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| **Total (`Matrix B-argon`)** | **8 categories** | **442/540** | **540/540** | **540/540** | **0** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** |

---

## Matrix 3: `Matrix A-codex` — No-Op Round-Trip & Exact OPC Payload Matrix (`noop`)

Each of the 30 mixed `.docx` fixtures in `tests/fixtures/docx-real/codex/` (`7,860`–`8,765` bytes) is evaluated by `tests/fixtures/docx-real/codex/run_matrix.py --mode noop` across 18 metrics (`C01`–`C18`: `paragraphs`, `characters`, `tables`, `images`, `footnotes`, `section_margins`, `text_sha256`, `image_sha256`, `opc_parts`, `relationships`, `tables_xml`, `fields_xml`, `numbering_styles_theme`, `sections_xml`, `notes_xml`, `drawings_xml`, `annotations_xml`, `main_xml`), plus byte-for-byte comparison of every decompressed OPC part and second-write stability.

### `C01`–`C18` Metric Definitions (Codex Suite)

| Code | Metric Key | Description | Pre-Fix `noop` | Pre-Fix `edited` | Post-Union `noop` | Post-Union `edited` |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `C01` | `paragraphs` | `tools/docx/roundtrip.py` paragraph count | 30/30 | 30/30 | **30/30** | **30/30** |
| `C02` | `characters` | `tools/docx/roundtrip.py` character count | 30/30 | 30/30 | **30/30** | **30/30** |
| `C03` | `tables` | `tools/docx/roundtrip.py` table count | 30/30 | 30/30 | **30/30** | **30/30** |
| `C04` | `images` | `tools/docx/roundtrip.py` image count | 30/30 | 30/30 | **30/30** | **30/30** |
| `C05` | `footnotes` | `tools/docx/roundtrip.py` footnote count | 30/30 | 30/30 | **30/30** | **30/30** |
| `C06` | `section_margins` | `tools/docx/roundtrip.py` section margin tuples | 30/30 | 30/30 | **30/30** | **30/30** |
| `C07` | `text_sha256` | Extracted text SHA-256 parity with expected oracle | 30/30 | 30/30 | **30/30** | **30/30** |
| `C08` | `image_sha256` | Image payload SHA-256 list parity | 30/30 | 30/30 | **30/30** | **30/30** |
| `C09` | `opc_parts` | Non-main OPC part SHA-256 map parity | 30/30 | 30/30 | **30/30** | **30/30** |
| `C10` | `relationships` | Full XML tree digest of all `.rels` parts | 30/30 | 30/30 | **30/30** | **30/30** |
| `C11` | `tables_xml` | Full XML tree digest of all `<w:tbl>` elements | 30/30 | 30/30 | **30/30** | **30/30** |
| `C12` | `fields_xml` | Full XML tree digest of all `<w:fldSimple>`, `<w:instrText>`, `<w:fldChar>` | 30/30 | 30/30 | **30/30** | **30/30** |
| `C13` | `numbering_styles_theme` | Exact digests of `numbering.xml`, `styles.xml`, `theme1.xml`, `settings.xml` | 30/30 | 30/30 | **30/30** | **30/30** |
| `C14` | `sections_xml` | Full XML tree digest of all `<w:sectPr>` elements | 30/30 | 30/30 | **30/30** | **30/30** |
| `C15` | `notes_xml` | Exact digests of `word/footnotes.xml` and `word/endnotes.xml` | 30/30 | 30/30 | **30/30** | **30/30** |
| `C16` | `drawings_xml` | Full XML tree digest of all `<w:drawing>`, `<w:pict>`, `<mc:AlternateContent>` | 30/30 | 30/30 | **30/30** | **30/30** |
| `C17` | `annotations_xml` | Full XML tree digest of comment ranges, bookmarks, `vanish`, `webHidden` | 30/30 | 30/30 | **30/30** | **30/30** |
| `C18` | `main_xml` | Complete `word/document.xml` tree digest (including `#comment`, `#pi`, text, tail) | 21/30 | 21/30 | **30/30** | **30/30** |
| **Total** | **18 metrics** | **30 fixtures × 18 metrics** | **531/540** | **531/540** | **540/540** | **540/540** |

### `Matrix A-codex` (`noop`) Per-Fixture Table (30 Fixtures × 18 Metrics = 540/540 PASS)

| Fixture & Structure | Bytes | Pre-Fix `noop` | Post-Union `noop` | Exact OPC Payloads | `C01` | `C02` | `C03` | `C04` | `C05` | `C06` | `C07` | `C08` | `C09` | `C10` | `C11` | `C12` | `C13` | `C14` | `C15` | `C16` | `C17` | `C18` |
| --- | ---: | ---: | ---: | :---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [`01-table-horizontal` · 表格：横向合并](../tests/fixtures/docx-real/codex/01-table-horizontal.docx) | 7,860 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`02-table-vertical` · 表格：纵向合并](../tests/fixtures/docx-real/codex/02-table-vertical.docx) | 7,861 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`03-table-nested` · 表格：嵌套表](../tests/fixtures/docx-real/codex/03-table-nested.docx) | 7,916 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`04-table-repeat-header` · 表格：跨页重复表头](../tests/fixtures/docx-real/codex/04-table-repeat-header.docx) | 8,765 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`05-table-multi-paragraph` · 表格：单元格多段](../tests/fixtures/docx-real/codex/05-table-multi-paragraph.docx) | 7,862 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`06-field-page` · 域：PAGE](../tests/fixtures/docx-real/codex/06-field-page.docx) | 7,877 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`07-field-numpages` · 域：NUMPAGES](../tests/fixtures/docx-real/codex/07-field-numpages.docx) | 7,911 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`08-field-date` · 域：DATE](../tests/fixtures/docx-real/codex/08-field-date.docx) | 7,951 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`09-field-ref` · 域：REF 交叉引用](../tests/fixtures/docx-real/codex/09-field-ref.docx) | 7,993 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`10-field-toc` · 域：TOC](../tests/fixtures/docx-real/codex/10-field-toc.docx) | 7,928 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`11-list-multilevel` · 编号：多级](../tests/fixtures/docx-real/codex/11-list-multilevel.docx) | 7,939 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`12-list-restart` · 编号：重启](../tests/fixtures/docx-real/codex/12-list-restart.docx) | 7,935 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`13-list-style-bound` · 编号：样式绑定](../tests/fixtures/docx-real/codex/13-list-style-bound.docx) | 7,951 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`14-style-inheritance` · 样式：三级继承](../tests/fixtures/docx-real/codex/14-style-inheritance.docx) | 7,916 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`15-style-direct-override` · 样式：直接格式覆盖](../tests/fixtures/docx-real/codex/15-style-direct-override.docx) | 7,998 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`16-style-theme-fonts` · 样式：主题字体与空格式 run](../tests/fixtures/docx-real/codex/16-style-theme-fonts.docx) | 8,037 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`17-section-margins` · 节：不同页边距](../tests/fixtures/docx-real/codex/17-section-margins.docx) | 7,995 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`18-section-landscape` · 节：横向页混排](../tests/fixtures/docx-real/codex/18-section-landscape.docx) | 8,011 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`19-section-columns` · 节：一二三栏混排](../tests/fixtures/docx-real/codex/19-section-columns.docx) | 8,006 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`20-footnote-restart` · 脚注：每页重编号](../tests/fixtures/docx-real/codex/20-footnote-restart.docx) | 8,008 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`21-footnote-table` · 脚注：带表格](../tests/fixtures/docx-real/codex/21-footnote-table.docx) | 8,070 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`22-image-inline` · 图形：内联 PNG](../tests/fixtures/docx-real/codex/22-image-inline.docx) | 7,865 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`23-image-floating` · 图形：四周环绕](../tests/fixtures/docx-real/codex/23-image-floating.docx) | 8,066 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`24-shape-group` · 图形：组合图形](../tests/fixtures/docx-real/codex/24-shape-group.docx) | 8,322 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`25-textbox` · 其他：文本框](../tests/fixtures/docx-real/codex/25-textbox.docx) | 8,015 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`26-comment-anchors` · 其他：批注锚点](../tests/fixtures/docx-real/codex/26-comment-anchors.docx) | 7,961 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`27-bookmarks` · 其他：跨 run 书签](../tests/fixtures/docx-real/codex/27-bookmarks.docx) | 7,987 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`28-hidden-text` · 其他：隐藏文字](../tests/fixtures/docx-real/codex/28-hidden-text.docx) | 7,961 | 17/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`29-header-table` · 其他：页眉表格](../tests/fixtures/docx-real/codex/29-header-table.docx) | 7,886 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`30-chinese-field-code` · 其他：中文域代码](../tests/fixtures/docx-real/codex/30-chinese-field-code.docx) | 8,040 | 18/18 | **18/18** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| **Total (`Matrix A-codex`)** | **30 fixtures** | **531/540** | **540/540** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** |

---

## Matrix 4: `Matrix B-codex` — Single-Run Text Edit via `exr_edit_set_run_text` (`edited`)

Each of the 30 mixed `.docx` fixtures in `tests/fixtures/docx-real/codex/` is read via `exr_edit_docx_read`, edited with `exr_edit_set_run_text` to replace the single target body run (`"Draft estimate: 42 units."` → `"Reviewed estimate: 57 units; 中文 & <checked>."`), written via `exr_edit_docx_write`, and compared against an independently constructed `expected.docx` oracle (where only the target text run is replaced and XML-escaped).

### `Matrix B-codex` (`edited`) Per-Fixture Table (30 Fixtures × 18 Metrics = 540/540 PASS, Extra Loss = 0)

| Fixture & Structure | Pre-Fix `edited` | Post-Union `noop` | Post-Union `edited` | Extra Loss (`edited - noop`) | Exact OPC Payloads | `C01` | `C02` | `C03` | `C04` | `C05` | `C06` | `C07` | `C08` | `C09` | `C10` | `C11` | `C12` | `C13` | `C14` | `C15` | `C16` | `C17` | `C18` |
| --- | ---: | ---: | ---: | ---: | :---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [`01-table-horizontal` · 表格：横向合并](../tests/fixtures/docx-real/codex/01-table-horizontal.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`02-table-vertical` · 表格：纵向合并](../tests/fixtures/docx-real/codex/02-table-vertical.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`03-table-nested` · 表格：嵌套表](../tests/fixtures/docx-real/codex/03-table-nested.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`04-table-repeat-header` · 表格：跨页重复表头](../tests/fixtures/docx-real/codex/04-table-repeat-header.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`05-table-multi-paragraph` · 表格：单元格多段](../tests/fixtures/docx-real/codex/05-table-multi-paragraph.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`06-field-page` · 域：PAGE](../tests/fixtures/docx-real/codex/06-field-page.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`07-field-numpages` · 域：NUMPAGES](../tests/fixtures/docx-real/codex/07-field-numpages.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`08-field-date` · 域：DATE](../tests/fixtures/docx-real/codex/08-field-date.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`09-field-ref` · 域：REF 交叉引用](../tests/fixtures/docx-real/codex/09-field-ref.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`10-field-toc` · 域：TOC](../tests/fixtures/docx-real/codex/10-field-toc.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`11-list-multilevel` · 编号：多级](../tests/fixtures/docx-real/codex/11-list-multilevel.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`12-list-restart` · 编号：重启](../tests/fixtures/docx-real/codex/12-list-restart.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`13-list-style-bound` · 编号：样式绑定](../tests/fixtures/docx-real/codex/13-list-style-bound.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`14-style-inheritance` · 样式：三级继承](../tests/fixtures/docx-real/codex/14-style-inheritance.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`15-style-direct-override` · 样式：直接格式覆盖](../tests/fixtures/docx-real/codex/15-style-direct-override.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`16-style-theme-fonts` · 样式：主题字体与空格式 run](../tests/fixtures/docx-real/codex/16-style-theme-fonts.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`17-section-margins` · 节：不同页边距](../tests/fixtures/docx-real/codex/17-section-margins.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`18-section-landscape` · 节：横向页混排](../tests/fixtures/docx-real/codex/18-section-landscape.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`19-section-columns` · 节：一二三栏混排](../tests/fixtures/docx-real/codex/19-section-columns.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`20-footnote-restart` · 脚注：每页重编号](../tests/fixtures/docx-real/codex/20-footnote-restart.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`21-footnote-table` · 脚注：带表格](../tests/fixtures/docx-real/codex/21-footnote-table.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`22-image-inline` · 图形：内联 PNG](../tests/fixtures/docx-real/codex/22-image-inline.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`23-image-floating` · 图形：四周环绕](../tests/fixtures/docx-real/codex/23-image-floating.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`24-shape-group` · 图形：组合图形](../tests/fixtures/docx-real/codex/24-shape-group.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`25-textbox` · 其他：文本框](../tests/fixtures/docx-real/codex/25-textbox.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`26-comment-anchors` · 其他：批注锚点](../tests/fixtures/docx-real/codex/26-comment-anchors.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`27-bookmarks` · 其他：跨 run 书签](../tests/fixtures/docx-real/codex/27-bookmarks.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`28-hidden-text` · 其他：隐藏文字](../tests/fixtures/docx-real/codex/28-hidden-text.docx) | 17/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`29-header-table` · 其他：页眉表格](../tests/fixtures/docx-real/codex/29-header-table.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| [`30-chinese-field-code` · 其他：中文域代码](../tests/fixtures/docx-real/codex/30-chinese-field-code.docx) | 18/18 | 18/18 | **18/18** | **0** | YES | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| **Total (`Matrix B-codex`)** | **531/540** | **540/540** | **540/540** | **0** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** | **30/30** |

---

## ZIP Container Audit vs. OPC Payload Identity

OOXML OPC part byte preservation is tracked separately from outer ZIP archive container metadata (`docs/docx-real/zip-container.json`), as documented in [DOCX-LIMITS.md](DOCX-LIMITS.md):

| Path | Whole-Archive Hash Changed | Entry Order Changed | Timestamp-Changed Entries | External-Attr-Changed Entries | Decompressed OPC Part Payloads Exact |
| --- | ---: | ---: | ---: | ---: | ---: |
| `noop` (`Matrix A-codex`) | 30/30 | 30/30 | 420 | 420 | **30/30 (100%)** |
| `edited` (`Matrix B-codex`) | 30/30 | 30/30 | 420 | 420 | **30/30 (100%)** |

---

## Regression & Acceptance Suite Summary

- **Layer Check (`tools/check_layers.py`)**: 124 objects, 0 inverse symbol references, 0 new violations, 0 inverse header includes.
- **CTest Suite (`ctest -E "^sdk-release$"`)**: **385/385 PASS (100%, 0 failures)** — includes all 314 Argon CTest cases (`native-docx-realworld-matrix` + full core/DOCX/PDF/EPUB suite), `native-docx-real-argon-reproducible`, and all 70 Codex `native-docx-real-*` CTest cases.
- **19-Book Reflow Regression**: **19/19 real books PASS** (`11,318` pages, `8,648,571` glyphs; page-count delta = `0`, changed per-page RGBA SHA-256 hashes = `0`, `needs_review = false`).
- **Evidence & Reproducibility**:
  - Argon matrices & fixtures: [tests/fixtures/docx-real/argon/MATRIX-A.md](../tests/fixtures/docx-real/argon/MATRIX-A.md), [tests/fixtures/docx-real/argon/MATRIX-B.md](../tests/fixtures/docx-real/argon/MATRIX-B.md), [tests/fixtures/docx-real/argon/make_fixtures.py](../tests/fixtures/docx-real/argon/make_fixtures.py), [tests/docx/check_realworld_matrix.py](../tests/docx/check_realworld_matrix.py).
  - Codex matrices, stage replays & fixtures: [docs/docx-real/before.json.gz](docx-real/before.json.gz), [docs/docx-real/text.json.gz](docx-real/text.json.gz), [docs/docx-real/paragraph.json.gz](docx-real/paragraph.json.gz), [docs/docx-real/after.json.gz](docx-real/after.json.gz), [tests/fixtures/docx-real/codex/README.md](../tests/fixtures/docx-real/codex/README.md).
  - Explicit capability boundaries: [docs/DOCX-LIMITS.md](DOCX-LIMITS.md).
