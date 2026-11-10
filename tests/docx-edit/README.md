# X5: editable DOCX regression

Run the native shared SDK's headless regression through ctest:

```powershell
cmake -S . -B build/native
cmake --build build/native -j 4
ctest --test-dir build/native -L docx-edit --output-on-failure -j 4
```

The suite registers **20 tests**: six fixtures × content/structure/properties,
one byte-for-byte fixture regeneration check, and one table-deletion negative
control. Each positive test executes the entire pipeline and all undo checks.
The three categories have separate verdicts and output directories.

The required APIs are `exr_edit_docx_open`, `exr_edit_docx_write`, and the editing
commands in `exr/edit.h`. The checker imports the unchanged #117
`tools/docx/verify_docx.py` and `tools/docx/roundtrip.py`. Missing APIs or checker
files fail with their exact names. As with the existing ctypes oracles, this
suite is registered for native, unsanitized shared SDK builds.

## Pipeline

1. Check manifest counts, bytes, SHA256, 3×3 table geometry, heading style, and
   distinct section margins. Open through the engine, check model paragraph,
   table, and section counts, save, and compare the whole OPC package.
2. Insert five paragraphs. Modify the first three **original** paragraphs'
   font, size, alignment, line spacing, and indentation. Split the fourth new
   paragraph at a UTF-8 boundary after Chinese text. Delete the fifth new
   paragraph. The net paragraph increase is five.
3. Save to `edited.docx`, reopen that disk file through the engine, and compare
   the selected metric category. Content checks compare both independent XML
   text and reopened engine text. Property checks compare both XML attributes
   and reopened native properties. Save the reopened model again and require
   package equivalence, including every drawing/note/header part.
4. Undo all 13 commands individually; require an empty history; save, reopen,
   and save again. The main XML tree must equal the original tree, including
   attributes, order, and text. Every other OPC part must equal the original
   bytes. This permits ZIP metadata differences while preserving the document.

All generated output is under `build/native/docx-edit/<fixture>-<category>/`.
Each directory contains `opened.docx`, `edited.docx`, `reopened.docx`,
`undo.docx`, `undo-reopened.docx`, and a JSON report with expected/actual values
and library/checker SHA256 hashes. A failed rerun overwrites the report status.

## 18 indicators per edited fixture

Six indicators (paragraphs, characters, tables, images, footnotes, section
margins) use #117's `roundtrip.metrics()` directly. Expected
paragraph/character changes are calculated from the edit batch; the four
preservation measurements must remain equal. The remaining checks use #117's
`Package`, namespace/attribute helpers, and native reopened properties.

| Category | Indicators |
| --- | --- |
| content (3) | paragraphs; characters; ordered paragraph text plus heading styles, including native reread text |
| structure (12) | tables; images; footnotes; ordered section margins; endnotes; section count; image payload hashes; complete table XML; complete drawing XML; footnote/endnote references; linked header XML/PAGE fields and section references; complete non-main OPC part inventory and hashes |
| properties (3) | fonts (all four rFonts attributes); half-point sizes (sz and szCs); paragraph properties including spacing, indentation, and alignment |

The six fixtures therefore produce **108 metric verdicts** across 18 positive
ctest cases. Undo equivalence and the initial/reopened package checks run in
addition to these indicators.

### #117's fixed formatting profile

The original `verify()` has 14 fixed profile checks. It requires every text run
to be Times New Roman/12pt, every paragraph double-spaced, every section's
margins one inch, and a used PAGE header. This suite deliberately changes font,
size, and spacing; the sections fixture deliberately has different margins;
the first five minimal fixtures have no headers.

Each edited artifact also runs that original function. The JSON report retains
its actual PASS/WARN/FAIL rows and XML context. The suite asserts the complete
expected status map, and separately checks the exact requested edits and
preserved structure with the 18 indicators above. Fixed profile FAIL rows are
never relabelled PASS. See `RESULTS.md` for both sets of counts.

## Deliberate failure

The negative ctest first edits the real table fixture through the engine, then
deletes its `w:tbl` directly with ZIP/XML tools. Its child regression must exit
1 and print **`表格数 1→0`**. The parent fails if either condition is missing.

To inspect that failing child directly, substitute the native library path:

```powershell
python tests/docx-edit/run.py --library build/native/libexreader.dll --fixture table --case structure --output build/table-broken --damage-table
```

To check a separately hand-modified edited artifact, replace `--damage-table`
with `--check-output build/hand-modified.docx`. This uses the same expected edit
batch and the same assertions as the normal positive test. The candidate file
is read without modification.

## Pre-merge dependency integration

This branch starts at `aaf8aecc`, before X1's bridge and #117 are merged. The
test-only changes do not introduce their implementation into `src/`. Two CMake
cache values allow testing the actual compiled bridge and unchanged checker
from their dependency worktrees:

```powershell
cmake -S . -B build/native -DEXR_DOCX_EDIT_TEST_LIBRARY=C:/path/to/X1/build/native/libexreader.dll -DEXR_DOCX_EDIT_VALIDATOR_DIR=C:/path/to/117/tools/docx
ctest --test-dir build/native -L docx-edit --output-on-failure -j 4
```

On an integrated source tree, clear the override so future edits always test
the current build: `-DEXR_DOCX_EDIT_TEST_LIBRARY=`. The default library is
`$<TARGET_FILE:exreader>` and the default validator directory is `tools/docx`.
The current pre-merge run's exact dependency hashes are in `evidence/summary.json`.
