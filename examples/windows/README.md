# Windows reference host (WP13)

`reader.c` is the complete Win32 host. This directory contains the independent
consumer build so the host can be built without changing the integration-owned
`examples/CMakeLists.txt`.

## Build against an installed SDK

```powershell
cmake -S examples/windows -B build/win-host -DEXR_SDK=C:/path/to/stage -DCMAKE_BUILD_TYPE=Release
cmake --build build/win-host --config Release --parallel 4
```

The SDK must be installed from the same source revision (`cmake --install build/native
--config Release --prefix stage`) and its aggregate runtime must be the shared library
(`exreader.dll`). The build copies the runtime next to `EXReader.exe`.

The installed SDK exposes the same consumer project as `stage/examples/windows`, because
the top-level install rule copies the whole `examples` directory.

## Package and accept

```powershell
python tools/build_windows_host.py --sdk stage --binary build/win-host/Release/EXReader.exe --output build/wp13-windows
python tests/windows_host/make_fixtures.py --output build/wp13-fixtures
python tools/check_windows_host.py --package build/wp13-windows/EXReader --output build/wp13-evidence --sdk stage --manifest build/wp13-windows/build.json --fixtures build/wp13-fixtures --selftest-report build/wp13-windows/report.json
```

The acceptance driver sends real `WM_COMMAND`/`BM_CLICK`/`WM_KEYDOWN`/`WM_LBUTTONDOWN`
messages to the created controls and records what the application observed. It is not a
replacement for the SDK's unit tests and does not claim a screen-reader audit.

## Runtime files

The packaged payload needs `EXReader.exe`, the installed `exreader.dll`, `Reader.otf`,
`OFL.txt`, the license directory, and the sample books. User data lives under
`%LOCALAPPDATA%\EXReaderHost` (override with `--data`):
`library.sqlite` holds the bookshelf, progress and annotations; `host.ini` holds only
font size, zoom, window size and the last active book.

New EPUB imports use the stored-source bounded chapter reader and schema 7
chapter-local progress/notes. Existing memory-import EPUBs retain their original
global positions and notes, including after exact deduplication. PDF/CBZ open via
`exr_library_fixed_source`. See `docs/WP13-WINDOWS.md` for the current H8 candidate,
budgets and cloud acceptance status.

## Body font manager

The host builds one immutable `exr_font_manager` before opening a book and frees
it after all layout workers stop. The executable directory and the platform's
user/system font directories are indexed by the SDK. `font-index.cache` in the
profile stores the persistent index; `typography.log` records the request,
resolved family/file, fallback status and manager creation time/cache counters.

The default request is CJK serif (Noto Serif SC/CJK SC, Source Han Serif SC,
SimSun), followed by the configured sans families. Noto Serif SC variable body
weight stays at 400. Reading settings show the resolved family and file, with
`已回退：无衬线` when the serif request resolves to a configured sans family.

`--font FILE` restricts discovery to that required file and requests its indexed
family, preserving an explicit variable font's own default weight.
`--font-config FILE` loads the SDK's version-1 configuration instead; this takes
precedence over `--font`. For an isolated fallback check, set `platform_dirs = no`,
point `font_file` at Reader.otf, and set `serif = Noto Serif SC` and
`sans_serif = Noto Sans CJK SC`. A missing required location fails startup.

Build with an SDK exposing `exr/font_manager.h` and its 12 symbols. Measured
startup, real-book page hashes and DPI-aware UI captures are documented in
[`font-manager-host evidence`](../../docs/ui/evidence/font-manager-host/README.md).

## X3 host editing

Build the shell against an SDK with #119 (`exr/edit.h`):

```powershell
cmake -S examples/windows -B examples/windows/.build-edit -G Ninja -DEXR_SDK=C:/path/to/stage -DEXR_READER_WINDOWS_SHELL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build examples/windows/.build-edit --target EXReader --parallel 4
```

Open DOCX/TXT from **File → Open** (`Ctrl+O`). The document starts in reading
mode. **Edit → Editing mode** (`Ctrl+E`) explicitly enables typing. Clicking or
dragging in the body moves the caret or selects text; Shift+arrows extends the
selection. Arrows, Home/End, Ctrl+Home/End, Backspace, Delete and Enter operate
on the editable model. Ctrl+wheel zooms. The caret is a DPI-scaled vertical
stroke, blinking every 500 ms only while the body has focus.

Contiguous `WM_CHAR` input shares one SDK transaction until a 1000 ms pause,
navigation, selection, focus loss or another command. Thus typing ten characters
continuously takes one Ctrl+Z. Enter, deletion, cut, paste and each IME result
are separate transactions. Ctrl+Y and Ctrl+Shift+Z redo. History retains 100
transactions. Chinese preedit is underlined in the layout without changing the
model; `GCS_RESULTSTR` commits the entire result once. The system receives both
caret/candidate bounds and `IMR_QUERYCHARPOSITION` screen coordinates, following
the [Microsoft IME contract](https://learn.microsoft.com/en-us/windows/win32/intl/imr-querycharposition).

Ctrl+A/C/X/V uses `CF_UNICODETEXT`; CRLF/CR paste creates paragraphs, including
empty ones. Tables and opaque objects display as object placeholders and cannot
be deleted here. The surface presents editable text; it does not preview Word's
full page formatting.
Text replacement rebuilds the affected paragraphs with #119's insert/delete
commands. Modelled paragraph/run properties and inline object bytes are copied;
unmodelled paragraph XML templates are not retained by that replacement path.
Preserving those templates needs an in-place text command in the engine API.

Ctrl+S saves the current file; Ctrl+Shift+S opens Save As. A title-bar `*` marks
changes. Closing, opening another document or returning to the shelf asks
Save/Discard/Cancel when needed. Saving writes and flushes a temporary file in
the destination directory before replacing the original; errors retain the dirty
state. An SDK with X1 (`exr_edit_docx_read/write`) uses the model directly.
Without X1, DOCX uses #118's text exporter and refuses saves that normalize the
model's bytes; TXT remains available. `-DEXR_READER_WINDOWS_EDIT=OFF` builds the
reading-only shell with an older SDK.

With an X1 SDK, run the reproducible model/HWND/save checks and collect hashes:

```powershell
python examples/windows/check_shell_edit.py --build examples/windows/.build-edit --output examples/windows/acceptance-edit --clean-first
```

The host and both checks compile under `-Wall -Wextra -Werror` (MSVC `/W4 /WX`).
The HWND check runs in its own hidden window and drives native dialog buttons
inside that test process. It verifies edit-mode gating, ten-character burst undo,
Unicode/paragraph navigation, clipboard, drag selection, DPI/zoom geometry,
preedit isolation, DOCX save/reopen, 20 undo/redo steps, all three close decisions
and preservation of a locked destination. It does not certify a physical IME.
See [the acceptance record](acceptance-edit/README.md) for results and the remaining
visible-window checks.
