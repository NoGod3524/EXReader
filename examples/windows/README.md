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
python tools/quality/check_cleanup2_shelf.py build/win-test/EXReader.exe path/to/Reader.otf build/shelf-evidence
```

The acceptance driver sends real HWND messages and records the application state.
The old phase-a/b/c and 17-control accessibility checks are retired; their history
is in `docs/ui/archive/legacy-17-control/`. The current shelf runner checks the
single grid/list shelf, scrollbar, empty state, tags and five book roundtrips.

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

## Acceptance-only executable

Product builds default to `EXR_READER_TEST_DRIVERS=OFF`. To run the existing
acceptance scripts, configure a separate build with
`-DEXR_READER_WINDOWS_SHELL=ON -DEXR_READER_TEST_DRIVERS=ON`. Script paths and
`--drive` arguments stay unchanged. The driver unit and its command strings are
excluded from the product. This option belongs only to this consumer project;
the root build and SDK logic are unchanged.

The native 17-control screen and its numeric command IDs 101–117 have been removed.
Both consumer projects always use the shell. `shell_shelf.inc` is the single
bookshelf painter; `shell_recent.inc` retains content-anchor persistence.
