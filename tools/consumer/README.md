# Standalone SDK consumer contract

Run against an installed Release package with the same platform, architecture and
compiler ABI as the consumer:

```sh
python tools/consumer/run.py --sdk /path/to/published-sdk --generator Ninja \
  --allow-added "Intentional public APIs added since the docs/ABI.md baseline" \
  --journal S3-OUT.txt --report-dir evidence/sdk-consumer
```

The generator creates a new system temporary directory and retains it for replay.
`--work-dir` selects a **nonexistent directory outside the repository**;
`--generate-only` creates the project and assets without building them. `--font`
selects a font to copy; the default is the repository's small MIT test font.
Use a normal OpenType font for readable screenshots. No build cache is copied.

The generated project has `CMakeLists.txt`, `main.c`, and a frozen list of the
symbol names in `docs/ABI.md`. Its SDK directory contains only `include/` and
`lib/`. Windows runtime DLLs are copied unchanged from the release's `bin/` to
`lib/`; all other installed include/lib files are copied unchanged. SHA-256s are
recorded in `package-sha256.json`. The generated project does not read repository
sources, build trees, package registries, or the original package location.

Replay from the printed temporary path (use `consumer.exe` on Windows):

```sh
cmake -S project -B build-static -G Ninja -DSDK_ROOT=/absolute/path/sdk -DMODE=static
cmake --build build-static --verbose
./build-static/consumer assets/smoke.epub assets/font.otf static.png

cmake -S project -B build-shared -G Ninja -DSDK_ROOT=/absolute/path/sdk -DMODE=shared
cmake --build build-shared --verbose
./build-shared/consumer assets/smoke.epub assets/font.otf shared.png

cmake -S project -B build-runtime -G Ninja -DSDK_ROOT=/absolute/path/sdk -DMODE=runtime
cmake --build build-runtime --verbose
./build-runtime/consumer assets/smoke.epub assets/font.otf runtime.png /absolute/path/sdk/lib/libexreader.so
```

Use `libexreader.dll`/`exreader.dll` or `libexreader.dylib` as appropriate. The
shared mode links the Windows import library and copies its DLL alongside the
executable. Runtime mode links only the platform loader, calls
`LoadLibrary`/`GetProcAddress` or `dlopen`/`dlsym`, and resolves every baseline name.
Static mode links the installed core component archives and their private vendor
archives. This SDK has no aggregate `libexreader.a`; its full CMake package also
imports the DLL's `bin/` path, so the two-directory consumer uses direct linking.

Each mode checks release and ABI versions before opening the book, totals pages
across its parts, renders the first page, rejects blank pixels, and prints the
title/page count/PNG path. The runner requires identical PNG bytes across modes
and scans actual compile commands, verbose build output and CMake cache for
repository/original-package path leaks.

Destructive cases retain their complete commands and diagnostics:

- `headers-only` provides only copied headers: compilation must succeed, then
  linking must fail specifically because `exreader` is missing.
- `newer-headers` increments the **copied header's** minor version, leaving every
  library unchanged. All three modes must exit with `SDK_VERSION_MISMATCH` and
  must not produce a render file. ABI epoch mismatch is also rejected by the C
  consumer. These checks are consumer startup policy, not implicit SDK behavior.

`check_abi.py` reuses the existing PE/ELF/Mach-O/archive parser. The frozen document
baseline remains 389 symbols; `contract.json` has five later publication-index
symbols, reported separately. Missing baseline symbols always fail. Additions
require `--allow-added` with a reason and are listed in full; this does not claim
the export sets are identical. Unix's existing internal/vendor exports are
described in `docs/ABI.md` and must be included in the reason when testing Unix.

```sh
python tools/consumer/test_check_abi.py
python tools/abi/test_check_exports.py
```

The existing PR desktop CI runs `installed-consumer-contract` through
`tests/sdk_components` on Windows, Linux and macOS. Its report is retained in the
component build's `consumer-contract/` directory. No workflow file is needed.
