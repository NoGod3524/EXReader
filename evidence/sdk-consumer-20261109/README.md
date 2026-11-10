# S3 acceptance — Windows x64, 2026-11-09

Producer revision: `b0af2a55` (main at task start). SDK `3.42.0`, ABI epoch `1`.
GCC/MinGW 16.2.0, C11, Release. The producer was configured in a new temporary
build tree and installed to a release package. Its feature options and dependency
source locations are recorded in [sdk-configuration.txt](sdk-configuration.txt).
Optional codecs disabled there retain their public entry points; the consumer
test exercises EPUB pagination and rendering.

Consumer root (retained):

```text
C:\Users\Oscar\AppData\Local\Temp\exreader-consumer-n4hry411
```

Its `project/` and all seven build trees are outside the repository. `sdk/`
contains only `include/` and `lib/` (44 files, hashes in
[package-sha256.json](package-sha256.json)). No repository CMake cache or source
is used by these builds. Windows DLL bytes were copied from the package's `bin/`
to the consumer's `lib/`. The installed `.a` dependency closure is unchanged.

Replay from that root in PowerShell:

```powershell
$sdk = "$PWD/sdk"
foreach ($mode in 'static','shared','runtime') {
  cmake -S project -B "build-$mode" -G Ninja "-DSDK_ROOT=$sdk" "-DMODE=$mode" -DCMAKE_BUILD_TYPE=Release
  cmake --build "build-$mode" --config Release --verbose
}
./build-static/consumer.exe assets/smoke.epub assets/font.otf static.png
./build-shared/consumer.exe assets/smoke.epub assets/font.otf shared.png
./build-runtime/consumer.exe assets/smoke.epub assets/font.otf runtime.png "$sdk/lib/libexreader.dll"
```

All exact invocations, working directories and return codes, including destructive
cases, are in [report.json](report.json); each has a separate configure/build/run
transcript.

```text
PASS mode=static title="Platform delivery smoke" pages=216 render=...\static.png
PASS mode=shared title="Platform delivery smoke" pages=216 render=...\shared.png
PASS runtime symbols=389
PASS mode=runtime title="Platform delivery smoke" pages=216 render=...\runtime.png
```

All three exit 0 and produce identical PNG SHA-256:
`e5a6984d9bd0823b3b0a350d31553384479e85ae7519d71986612d662fa4a8e8`.
[render.png](render.png) is the first page, visually checked with the copied Arial
font. [consumer-imports.json](consumer-imports.json) independently confirms only
the shared consumer imports `libexreader.dll`; runtime loads it explicitly and
static links component archives. The MinGW static consumer also uses the
toolchain's `libwinpthread-1.dll` runtime.

ABI: **baseline 389, actual 427, missing 0, added 38**. The baseline was not
modified. Every addition is an intentional public API already declared in the
release headers: dictionary 6, document CFI 7, 7z formats 6, and layout APIs 19
(CFI, SSML, footnotes, publication index, locate reports, extended open, reader
style). No additional vendor/internal exports appear on Windows. Full symbol
names and binary hash are in [abi.json](abi.json). The machine contract's five
post-baseline publication-index entries are reported separately.

Both destructive requirements passed:

```text
# headers-only: compile succeeds, link exits 1
ld.exe: cannot find -lexreader: No such file or directory
collect2.exe: error: ld returned 1 exit status

# only copied headers changed, static/shared/runtime each exit 4, no PNG
SDK_VERSION_MISMATCH: header=3.43.0 library=3.42.0; headers require a newer SDK library
```

The new ABI policy tests and existing binary-parser tests pass. The existing
installed-SDK CTest entry repeats the full consumer contract in a second fresh
directory with the default MIT fixture font; see [ctest.txt](ctest.txt).
The PR's existing Native desktop jobs run that same entry without changes to
`.github/`. Incremental completion records are in [S3-OUT.txt](../../S3-OUT.txt).
