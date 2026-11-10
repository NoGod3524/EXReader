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

## Autosave and recovery (X4)

The shell's notes and highlights are one editable document per book. Edits,
including text still in the note editor, set its dirty bit and the window's `*`.
The note editor's Save button and Ctrl+S explicitly save the document. Closing,
returning to the shelf, or opening another book offers Save / Discard / Cancel.
Cancelling the note editor restores its opening contents in memory.

The default autosave interval is 30 seconds; `--autosave-seconds N` accepts
1–86400 seconds. Clean documents and unchanged autosave revisions perform no
writes. Notes remain at `%APPDATA%\EXReader\annotations\<book-sha256>.json`
(override with `EXREADER_ANNOTATIONS_DIR`). Their recovery copy is that original
path plus `.autosave`; autosave never changes the original JSON or the book.
On reopening the last book at startup, a newer recovery copy offers
“有未保存的修改，是否恢复？”. Recovery keeps the document dirty; Discard deletes
the copy. A missing original also permits recovery. A corrupt copy reports
“副本损坏，无法恢复” and leaves the saved original available.

`shell_save.h` is independent of the SDK and editor. It uses a same-directory
`.tmp`, `FlushFileBuffers`, and `MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`.
It validates structure and exact bytes before replacement and immediately
reads back the installed file. A flushed `.bak` restores the previous bytes
and modification time if readback fails. Failed saves keep edits dirty. The
autosave envelope contains `EXRAUTO1`, a little-endian 64-bit payload length,
CRC32 of the payload, and CRC32 of the first 20 header bytes (24 bytes total).
The JSON validator checks the schema, book identity, and every note's anchors.
A per-document Win32 lock prevents two host processes overwriting each other's
temporary files. Recovery ignores unfinished `.tmp` files.

```powershell
cmake --build build/win-host --target EXReader check_shell_save check_shell_selection
build/win-host/check_shell_save.exe selftest build/storage-check
build/win-host/check_shell_selection.exe annotations tests/fixtures/fonts/primary.ttf
python -X utf8 examples/windows/check_shell_autosave.py build/win-host/EXReader.exe C:/path/to/Reader.otf build/win-host/check_shell_save.exe build/x4-evidence
```

The acceptance script waits 35 seconds after an unsubmitted UTF-8 draft,
checks timestamps and SHA-256, force-kills and restarts the host, recovers and
compares content, rejects a truncated copy, and tests Save / Discard / Cancel.
The storage check executable alone enables fault injection: three pauses in
the production write function let the parent force-kill at a partial write,
after flush, and immediately before replacement. It also injects post-save
readback corruption and checks rollback. These hooks are absent from EXReader.
