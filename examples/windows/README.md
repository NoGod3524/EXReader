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
