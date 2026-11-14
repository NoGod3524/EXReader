# Binary PowerPoint table fixtures

`plain.ppt` and `merge.ppt` were created with PowerPoint 16.0 COM
`Shapes.AddTable(2,2,60,80,360,180)` and `SaveAs(format=1)`. The slide is
720×540 points. The first row of `merge.ppt` is horizontally merged.
`manifest.json` records SHA-256, original row/column dimensions, fills,
border color and width, text and placement. The PNGs are PowerPoint exports
after reopening the saved binary files.

Run `pwsh -File tests/fixtures/ppt-tables/generate.ps1` on Windows with
PowerPoint to regenerate both files, reopen them and refresh the manifest
and exported PNGs. Generation uses native COM and PowerShell only. Tests use
Python's standard library and the native `exreader-ppt-shape-probe` output.

The actual table is an OfficeArt `F003` group. Its header's tertiary FOPT
`F122` contains `tableProperties` PID `039F=1` and complex
`tableRowProperties` PID `03A0` (opid `C3A0`): `count=2`, `allocated=2`,
`elementSize=4`, two 720-master-unit minimum heights. This is not a
ClientData recInstance or an external sequence of TableRow/TableCell records.
`0F9F` is `TextHeaderAtom`. The group has `F010` ClientAnchor, cells have
`F00F` ChildAnchor, rectangular `F00A` instance 1 and `F00D` ClientTextbox.
The A/B text is legal `TextBytesAtom` (`0FA8`). Borders are child line shapes
(`F00A` instance 20) with RGB `lineColor` PID `01C0` and width PID `01CB` =
38100 EMUs = 3 points. The merged table has three cell rectangles instead of
four and its upper vertical divider segment is absent.

`check_ppt_tables.py` checks real fills, widths, A/B glyph bounds, merge
geometry and extracted dimensions/text. Independent synthetic records cover
truncated/inconsistent row metadata, missing table records, conflicting
merge rectangles, stale merge divider lines, valid/invalid outline text
references, overflow clipping and both 200-dimension limits. CJK checks use
the shared host-font split; normal fixtures tolerate only font/glyph
fallback warnings. All other normal-fixture warnings fail the test.
