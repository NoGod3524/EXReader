# L07 keyboard and accessibility acceptance

This lane's existing-file allowlist was empty. The lane adds a native DOCX
command panel and a build-only integration overlay; it does not overwrite the
three shared host files. `run.py` checks each insertion context exactly once and
emits `build/l07-a11y/integration.patch` for review and integration.

```powershell
python -X utf8 tests/docedit_a11y/run.py
```

For offline dependency reuse, supply `--dependency-cache <CMakeCache.txt>`.
Only FetchContent source paths are reused; the SDK and both host executables
are built from this worktree. No ctypes tests are added.

The driver calls the integrated host's `de_key`, `page_procedure(WM_CHAR)` and
DOCX file-dialog completion. It opens, enters a table with Ctrl+T, types Chinese
and an emoji, saves with Ctrl+S, reopens and checks text and formatting. It also
checks selections, undo/redo, run/paragraph and cell traversal, row mutations,
empty cells and actual image insertion. It creates no HWND and never injects
OS input. The standard file dialogs and native focus drawing require manual
screen-reader verification; this driver does not claim that verification.

User paths after applying the generated patch:

* Ctrl+O: normal host open-file dialog; F2: enter DOCX editing.
* Ctrl+T: enter the first/next table; F6: open the command panel or return to body.
* Tab / Shift+Tab: native controls in creation order, with visible native focus.
* Enter / Space: activate a command button. Esc: return to body.
* In table text: arrows / Home / End move, Shift selects, Backspace / Delete
  remove text, Ctrl+A selects the current text run, Enter visits the next run.
* Previous/next cell, next text run, add/delete row, formatting, image file
  chooser, save and return-to-body buttons are all reachable with Tab.
* Ctrl+S: save. Table changes share the document's Ctrl+Z / Ctrl+Y history.

Every panel control receives `host_a11y_describe(control, NULL, ChineseHelp)`.
The current table field description includes row, column, paragraph, text run
and whether the cell is protected. Run-local editing preserves sibling runs,
paragraphs and formatting. Merged, nested and opaque cells retain engine
protection. A newly inserted image is 240 × 180 points; the file limit is 64 MiB.

Integration touches `examples/reader.c`, `shell_docedit.inc` and
`shell_docedit_input.inc` only. The standalone acceptance CMake project needs no
edits to the shared Windows CMakeLists or DOCX fixture registration.
