# Windows DOCX editor: rich text (M-E2c)

Tables are rendered as cells with visible grid lines and paragraph-local
DirectWrite layouts. Left/Right and Tab enter cells; Tab/Shift+Tab move between
cells in row order. Enter splits a paragraph inside its cell. Typing into the
new empty paragraph inserts its first run in the same transaction as the text
edit; Ctrl+Z removes that input while retaining Enter and sibling paragraphs.

While the caret is in a table, a second toolbar row shows `+行`, `−行`,
`列宽+`, `列宽−`, and `删表`. Row insertion precedes the current row; deletion
removes the current row. Column width changes by +5% or −5% of its current
value, rounded to integer twips. Each action is one undo entry.
Deleting a table asks for confirmation. Ctrl+Alt+Enter inserts a paragraph
immediately below the table so typing can continue outside it.
Ctrl+S preserves table structure, all cell paragraphs and grid widths in DOCX.
Merged, shaded, nested or opaque cells retain the engine's edit protection.

The headless table acceptance exercises this same host without creating a
window, including toolbar hit testing and Direct2D border/caret pixels:

```powershell
cmake --build build/tables-host --target check_shell_table
ctest --test-dir build/tables-host -R windows-table-ui -V
```

`插入脚注` inserts a superscript reference at the caret and adds its numbered
text to the footnote area below the document. Click a footnote there to edit
multiline text, save it, or delete the note. Delete can also remove a reference
directly from the body; later notes renumber consecutively. Insertion, text
changes and deletion support Ctrl+Z/Ctrl+Y. Ctrl+S saves the notes and references
to DOCX, retaining their text and numbering when reopened.

The engine and headless host footnote checks run with:

```powershell
ctest --test-dir build/l14 -R 'native-docx-(edit-footnotes|footnotes-ui)' --output-on-failure
```

The editor toolbar above the document has bold, italic, size down/current/up,
eight text colors, and left/center/right/justified paragraph alignment.
Bold, italic, and alignment buttons show the caret's current format. Sizes
are displayed in points; each step changes the stored half-point size by two.

| Shortcut | Action |
| --- | --- |
| Ctrl+B / Ctrl+I | Toggle bold / italic |
| Ctrl+Shift+. / Ctrl+Shift+, | Increase / decrease size by one point |
| Ctrl+L / Ctrl+E / Ctrl+R / Ctrl+J | Left / center / right / justified |
| Ctrl+S / Ctrl+Z / Ctrl+Y / Ctrl+A | Save / undo / redo / select all |

Selected text is formatted in one transaction. The public engine API has no
split-run command, so selecting part of a text run formats that entire run.
Other direct properties are retained; toggling off writes an explicit false
property, including its `present` bit. Alignment changes the caret paragraph.

With no selection, formatting changes the pending typing properties without
changing existing text or marking the document dirty. Typing isolates a new
run when the pending format differs, then calls `exr_edit_set_run_props` in the
same transaction as insertion. Continued typing with that format extends the
run. Moving the caret or undoing/redoing clears pending properties; Enter
carries them into the next paragraph.

Inserting differently formatted text within an existing run uses M-E1's guarded paragraph rebuild.
Paragraphs with unmodeled templates (for example `pStyle`, tabs, or extension
attributes) reject that insertion and roll back rather than lose their XML.
Existing run formatting and paragraph alignment can still be applied there.
Empty paragraphs and run-boundary insertion use `exr_edit_insert_run`, which
retains paragraph templates and sibling cell paragraphs. Inserting within an
existing run still uses the guarded rebuild above.

DirectWrite applies family, half-point size, weight, style, and color to each
run's UTF-16 range, then handles wrapping, alignment, caret geometry, and hit
testing in the same layout. Inheritance covers `docDefaults`, paragraph styles
and `basedOn`, and character styles. Theme font tokens and conditional styles
use the host defaults. Missing font families use the current host default and
emit `font fallback: <name> -> default` on stderr. Explicit black is retained
as black; an absent color uses the current theme foreground.

Headless acceptance builds the real host and paints Direct2D into a memory DC;
it creates no HWND and uses no input injection:

```powershell
cmake -S examples/windows -B build/e2c-host -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=<installed-sdk>
cmake --build build/e2c-host --target check_shell_docedit EXReader -j 4
& build/e2c-host/check_shell_docedit.exe tests/fixtures/rich.docx build/e2c-evidence
ctest --test-dir build/e2c -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure -j 6
```

The `E2c 1` through `E2c 6` output lines cover saved bold on/off, size raster
height, red text pixel count, pending bold insertion, and distinct alignment
origins. Extra checks cover middle insertion, neighboring properties,
undo/redo, multi-run selections, style inheritance, protected template
rollback, and pixel-identical missing-family fallback. M-E1 checks also run.
