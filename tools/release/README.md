# EXReader shared-library SDK

Open an EPUB, print its title, page count and table-of-contents count, and render
the first page to a grayscale PGM with the 64-line `examples/minimal/main.c`.
The package includes an EPUB and a small test font, so the first run needs no
downloads. Run the commands below **from the extracted package directory**.

### Windows (MSVC x64)

Open **x64 Native Tools Command Prompt for VS 2022**, then start `powershell`.
The package uses the MSVC x64 C ABI and the static C runtime.

```powershell
$env:PATH = "$PWD\lib;$env:PATH"
cl /nologo /W4 /Iinclude examples\minimal\main.c lib\exreader.lib /Feminimal.exe
.\minimal.exe examples\minimal\sample.epub examples\minimal\font.ttf page-1.pgm
```

### Linux (x64)

Install a C compiler (for example `sudo apt-get install build-essential`).

```bash
cc -std=c11 -Wall -Wextra -Iinclude examples/minimal/main.c -Llib -lexreader -Wl,-rpath,'$ORIGIN/lib' -o minimal
./minimal examples/minimal/sample.epub examples/minimal/font.ttf page-1.pgm
./bin/exr-info examples/minimal/sample.epub examples/minimal/font.ttf
```

### macOS (arm64)

Install Apple Command Line Tools with `xcode-select --install`.

```bash
cc -std=c11 -Wall -Wextra -Iinclude examples/minimal/main.c -Llib -lexreader -Wl,-rpath,@loader_path/lib -o minimal
./minimal examples/minimal/sample.epub examples/minimal/font.ttf page-1.pgm
./bin/exr-info examples/minimal/sample.epub examples/minimal/font.ttf
```

`page-1.pgm` is a binary P5 image. Open it in an image viewer that supports PGM.
For your own book, replace `sample.epub` and `font.ttf` with your EPUB and a font
covering its characters. The bundled test font has limited glyph coverage.
Pages depend on the font and the default 720 × 1040 layout. The example counts
the publication's flattened TOC entries and renders zero-based page 0.

`bin/exr-info --version` prints the SDK version. `bin/exr-info book.epub font.ttf`
prints version, format, title, page count and TOC count (use `.exe` on Windows).
It handles the reflow formats EPUB, TXT, HTML, FB2, DOCX, RTF and MOBI/KF8.
The example returns 0 on success, 2 for incorrect arguments and 1 on failure.

The SDK layout is identical across platforms:

```text
include/exr/*.h        15 API headers plus version.h
include/exreader.h    compatibility umbrella header
lib/                  exreader.dll + exreader.lib (MSVC), or libexreader.so/dylib
bin/exr-info[.exe]     Windows also carries the DLL beside the CLI
examples/minimal/     main.c, sample.epub, font.ttf, FONT-LICENSE.md
share/exreader/       dependency license texts
LICENSE  THIRD_PARTY_NOTICES.md  README.md  VERSION  SHA256SUMS
```

The DLL name follows the compiler: MSVC uses `exreader.dll`/`exreader.lib`;
MinGW uses `libexreader.dll`/`libexreader.dll.a` (compile with
`gcc -std=c11 -Iinclude examples/minimal/main.c -Llib -lexreader -o minimal.exe`).
Linux includes the SONAME files; macOS uses `@rpath` dylibs. Keep `lib` beside your
application, or configure the platform's library search path. Headers are C11
and usable from C++. The source-build commands below disable AAC; third-party
licenses are under `share/exreader/licenses`.

`SHA256SUMS` covers every package file except itself. On Linux run
`sha256sum -c SHA256SUMS`; on macOS run `shasum -a 256 -c SHA256SUMS` before
compiling. From a source checkout, `python tools/release/check_release.py PACKAGE`
also checks names, versions, headers, architecture and at least 389 API exports.

### Build and package from source

Windows (PowerShell, CMake, Python 3.10+, Visual Studio 2022 C++ tools):

```powershell
cmake -S . -B build/sdk-release -G "Visual Studio 17 2022" -A x64 -DEXR_BUILD_TESTS=OFF -DEXR_BUILD_JNI=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/sdk-release --config Release --target exr-info --parallel 4
& tools/release/build_packages.ps1 -BuildDir build/sdk-release -OutputDir dist -Configuration Release
```

Linux x64 (native CI or WSL Ubuntu; CMake 3.24+, C compiler, Perl, Python 3.10+):

```bash
cmake -S . -B build/sdk-release -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TESTS=OFF -DEXR_BUILD_JNI=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/sdk-release --target exr-info --parallel 4
sh tools/release/build_packages.sh build/sdk-release dist Release
```

macOS arm64 (native CI or Apple Silicon, with the same tools):

```bash
cmake -S . -B build/sdk-release -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 -DEXR_BUILD_TESTS=OFF -DEXR_BUILD_JNI=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/sdk-release --target exr-info --parallel 4
sh tools/release/build_packages.sh build/sdk-release dist Release
```

Each script collects an existing build, verifies it, writes the file hashes and
creates `dist/exreader-<VERSION>-<platform>.zip` (Windows) or `.tar.gz` (POSIX).
Enable `EXR_BUILD_TESTS` and run `ctest --test-dir build/sdk-release -C Release
-R sdk-release --output-on-failure` to package, extract into a fresh directory,
execute this README's three commands and verify the rendered pixels and CLI.
The existing native PR workflow runs that test on all three platforms.
