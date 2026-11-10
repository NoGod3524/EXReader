# X6 table and image editing

The public model and commands are in `include/exr/edit.h`. Table commands and
OOXML patching live in `src/docx_edit_table.c`; image commands, inline drawings,
MIME declarations and reference cleanup live in `src/docx_edit_image.c`.
`src/export_text.c` is unchanged. Both internal headers and both new sources are
registered in `tools/layers.json`.

## Acceptance results

Final native CTest: **293/293 PASS**, including **14 new groups**. All **79**
injected model-allocation failures roll back without leaked allocations. Layer
audit: 123 objects, 1428 symbol references, zero inverse references/includes.

| Fixture | Table count before/after | Rows before/inserted/deleted | Grid columns |
| --- | --- | --- | --- |
| table | 1 / 1 | 3 / 4 / 3 | 2 |
| images | 1 / 1 | 3 / 4 / 3 | 2 |
| notes | 1 / 1 | 3 / 4 / 3 | 2 |
| sections | 1 / 1 | 3 / 4 / 3 | 2 |
| merged | 1 / 1 | 3 / 4 / 3 | 2 |
| nested + shading | 2 / 2 | 3 / 4 / 3 (outer table) | 2 |

Each fixture inserts a row, saves and reopens it, deletes the inserted row,
changes an original cell's text, saves and reopens again. Row/cell counts and
the changed text are checked in the reopened model and independently in XML.
All six #117 structural metrics and all non-main OPC payload bytes remain equal.
The merged row has one physical cell spanning two grid columns. Its other rows
have two physical cells. The nested table also remains present.

| PNG pixels | Requested points | `wp:extent` cx / cy | Reopened points |
| --- | --- | --- | --- |
| 1 × 1 | 0.75 × 0.75 | 9525 / 9525 | 0.75 × 0.75 |
| 800 × 600 | 600.25 × 450.5 | 7623175 / 5721350 | 600.25 × 450.5 |

The independent XML check divides cx/cy by 12700. Inserted PNG/JPEG and original
image payloads are compared byte-for-byte. Deleting one imported image changes
`word/media/` files **1 → 0** and image relationships **1 → 0**. Tests also cover
multiple occurrences of one ID, distinct IDs sharing one payload, a header
sharing the media, external links, image deletion inside a merged/shaded cell
containing a nested table, and deletion of a table containing images.

## #117 real inputs

| Source | Tables | Images | Footnotes | Sections | Baseline / edited metrics |
| --- | --- | --- | --- | --- | --- |
| minitab-ch10 | 10 | 17 | 0 | 1 | 6/6 → 6/6 |
| soci-syllabus | 2 | 0 | 0 | 5 | 6/6 → 6/6 |
| ohchr-40-69 | 2 | 0 | 5 | 1 | 6/6 → 6/6 |

Total: **18/18 → 18/18** using the unchanged `tools/docx/roundtrip.py`
`metrics`/`differences` auditor and hash-pinned `tests/docx/corpus.json` originals.
All 14 original tables, 17 images, five footnotes and seven sections survive.
Minitab's original cells all have shading; OHCHR has no nonempty cell eligible
for whole-cell replacement. These two inputs edit a new row's cell, remove the
new row, then persist a width edit. SOCI persists an original-cell text edit.
All three save/reopen and undo/redo checks pass. Original media and every
non-main OPC part retain identical bytes. Original-source text is not included
in the committed evidence.

## Unsupported-cell fidelity

After editing another row of the same table, the following source fragment is
still present byte-for-byte in the exported main XML:

```xml
<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:pPr><w:spacing w:line="480" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr><w:t>merged</w:t></w:r></w:p></w:tc></w:tr>
```

Additional tests retain `w:vMerge` restart/continuation, `w:hMerge`, nested
`w:tbl`, `w:shd`, comments and row-boundary bookmarks. A protected-cell text
replacement or a row edit splitting a vertical merge returns
`EXR_UNSUPPORTED` and leaves the model unchanged.

## Reproduction and evidence

```powershell
cmake --build build/native -j 6
ctest --test-dir build/native -j 6 --output-on-failure
python tools/check_layers.py build/native
python tests/test_docx_edit_table_image.py --library build/native/libexreader.dll --output build/x6-evidence all
python tests/docx/check_table_image.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/x6-real
```

There are 14 new `native-docx-edit-x6-*` CTest groups. The existing allocation
failure test additionally exercises partially copied table/cell/paragraph/run
and image payload allocations. Compact results and source hashes are in
`docs/validation/docx-x6-20261110.json`; complete generated DOCX artifacts and
logs remain under `build/x6-evidence`, `build/x6-real` and `build/native`.
The append-only work record is `OUT.txt`.
