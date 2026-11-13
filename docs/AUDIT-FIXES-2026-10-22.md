# ExReader audit fixes — 2026-10-22

All 15 findings in `AUDIT-2026-10-22.md` have implementation fixes and regression coverage. The three P1 fixes were implemented first. Changes are local and unreleased; the SDK version, ABI and library schema are unchanged.

## Fix-to-test mapping

| Finding | Fix | Regression coverage |
| --- | --- | --- |
| A01 / P1 | Compare every proposed output with every batch input before execution, including rejected jobs and file aliases. | `tests/check_convert_cli.py::scenario_batch_input_protection`: earlier/later inputs, rejected input, hard link; independent items still succeed and original input hashes remain unchanged. |
| A02 / P1 | Share null-safe page-directory cleanup across probe, allocation and expansion failures. | `tests/test_cbz.c`: oversized-image rejection returns `EXR_LIMIT` with null output; subsequent normal open/render succeeds; cancellation cleans a partially initialized directory. |
| A03 / P1 | Keep CLI overwrite authorization separate from the manifest default. | `scenario_overwrite_precedence`: five CLI/item/default combinations, including item false overriding manifest true and CLI true overriding item false. |
| A04 | Reject embedded NUL during manifest string parsing. | `scenario_manifest_nul`: input, output, ID, root, output root and field-name cases all fail before file changes. |
| A05 | Retry legal short reads; stop on cancellation, zero bytes or an oversized callback result. | `tests/test_cbz.c::source_reads`: seven-byte callbacks import successfully; invalid callbacks/cancellation return the expected error and no book ID. |
| A06 | Convert libtiff's packed associated RGBA to public straight-alpha byte RGBA. | `tests/test_image_formats.c` compares alpha and translucent color with PNG; `tests/test_cbz_formats.c::alpha_pages` compares composed pages with at most one channel-level quantization difference. |
| A07 | Resolve full member-name ties before comparing frame indices. | `tests/test_cbz_formats.c::natural_frames`: three animated members with numeric/case ties retain member order, frame order and page IDs. |
| A08 | Measure each stroke's actual outline and union its bounds, avoiding repeated expansion of the shared box. | `tests/test_font_svg.c::reliability`: one versus 100 overlapping stroked rectangles produce identical pixels without artificial limit errors. |
| A09 | Reuse canvas stroke geometry for cap/join bounds. | `stroke_reference`: full-page canvas comparisons for acute miters, very large miter limits and shear, plus equivalent padded/unpadded scenes. |
| A10 | Initialize SVG stroke to none and skip unpainted geometry. | Default versus explicit none, inherited versus explicit stroke, and blank default-line/no-paint comparisons. |
| A11 | Parse opacity's numeric value and unit in the correct order. | Equivalent decimal/percentage fill, stroke and group opacity; invalid units and out-of-range values remain rejected. |
| A12 | Traverse root paint/opacity exactly once around the selected glyph subtree. | Root/group equivalence, selected glyph inside defs, root glyph ID, inherited paint, root transform, zero opacity and cancellation. |
| A13 | Discover the previous chapter's final page under the current layout; clear cached endpoints on font changes. | Apple `ReaderModel.runSelfTest`: reopen at chapter 2, then Previous; increase/decrease font and repeat. |
| A14 | Traverse only parts marked `inReadingOrder`. | Apple self-test: skip a non-linear spine item in both directions and stop before auxiliary XHTML. |
| A15 | Restore document, pager, location, frame, endpoint cache and saved progress after a failed turn. | Apple self-test: deferred malformed chapter leaves handles/frame, persisted position, annotation location and readable page unchanged. |

The new SVG regression font has its own generator and manifest; existing reference fonts and image fixtures were preserved. The conversion contract now documents overwrite precedence, batch input protection and NUL rejection.

## Validation

- Windows GCC Release build succeeded. **163/163 CTest tests passed**, including the expanded **52/52 conversion CLI scenarios**. This run uses the generated CTest definitions with only the two conversion work/report destinations redirected to fresh audit directories.
- Windows MSVC Release build succeeded. All four focused CBZ/image/SVG CTest tests and **52/52 conversion CLI scenarios** also passed.
- The 15 new CLI scenarios were also run against the original executable: 11 defect cases failed and four valid-control cases passed. After the fixes, all 52 scenarios passed.
- The 100-item conversion benchmark passed the unchanged memory gate: batch peak **30,289,920 B**, single-item peak **28,659,712 B**, increase **1,630,208 B**, allowance **33,554,432 B**. No failed/unfinished items or temporary files remained.
- Focused CBZ, CBZ format, image format, library streaming and SVG tests passed. Python tooling compilation and diff whitespace checks passed.
- Apple regression EPUBs were checked through the rebuilt C API using the actual bundled font: reading flags `[true,false,true,false]`, the first chapter has 3 pages at size 28 and 11 at 48, and the deferred broken chapter returns `EXR_FORMAT` after a valid first page.
- **Apple UI regressions are added but have not been executed locally.** This Windows environment has no Swift/Apple toolchain. The existing macOS/iPhone/iPad CI self-test path includes them, and its checker now requires the named regression results.

Evidence is under `build/audit-fixes-20261022/`; Apple fixture verification is in `build/audit-20261022/bindings/regression-fixtures.json`. The original audit and its measurements remain historical records. Machine-readable results: `docs/validation/2026-10-22-audit-fixes.json`.
