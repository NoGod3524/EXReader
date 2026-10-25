# S14 — existing font library on the approved SDK3.41 candidate

Fixed start: `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` (branch `codex/reader-next-s14`).
Reused library: `1563f4abb85ccd28c3a0aae3e9913f4330536215` (`apps/reader/font-library`).
Approved SDK3.41 candidate: `edddc463c06ed5731195cdb8f06b2df6dff7699e`; frozen SDK3.40:
`9854061be331fe603a1822d9b2b36ee357154927`.

This package does **not** write a second font parser, a second store, a second manifest or a raw
API. It re-carries the existing library into the common source candidate, adds an explicit
`EXR_SDK_VERSION` selection (3.40.0 default, 3.41.0 explicit), and proves the reuse with
recomputed git object identities in Actions.

## What actually changed

Only the two build-description files of the reused module differ from the pinned commit:

| file | change |
| --- | --- |
| `apps/reader/font-library/CMakeLists.txt` | `EXR_SDK` prefix hint, `EXR_SDK_VERSION` cache variable restricted to `3.40.0`/`3.41.0`, `find_package(EXReader ${EXR_SDK_VERSION} EXACT ...)` |
| `apps/reader/font-library/EXReaderFontLibraryConfig.cmake.in` | installed dependency is `find_dependency(EXReader @EXR_SDK_VERSION@ EXACT ...)`, so the installed package can only resolve the SDK it was built against |

`include/reader_font_library.h`, `src/library.cpp` and `src/sha256.hpp` are byte-identical to the
pinned library; `tests/reader_next_s14/guard.py` and `run.py` recompute their git object ids and
refuse the report when they differ from `1563f4ab`. The public C ABI, the on-disk `RFL1` manifest,
the byte semantics, the limits (16 MiB font / 64 entries / 128 MiB directory, hard 64/256/512 MiB,
32 live leases / 128 MiB encoded bytes), the cancellation stages, the private-directory and path
rules, "a failed import never invalidates stored fonts" and the font owner/lifetime rules are
unchanged.

## Why an SDK selection instead of a second implementation

The public font surface is identical between the frozen 3.40 pin and the approved 3.41 candidate:
`include/exr/text.h`, `include/exr/font.h`, `include/exr/core.h` and every `src/font*.c` file are
byte-identical (`git diff 9854061b edddc463 -- <font surfaces>` is empty; the workflow re-proves it).
The only real incompatibility is the CMake package version: the installed
`EXReaderConfigVersion.cmake` is `SameMajorVersion` while the original module hard-coded
`find_package(EXReader 3.40.0 EXACT)`, which cannot resolve a 3.41.0 install. The complete
difference list and the evidence commands are in [`COMPATIBILITY.md`](COMPATIBILITY.md).

## Build and use

Actions only for this package; the workflow is `.github/workflows/reader-next-s14.yml` and triggers
only on `codex/reader-next-s14`.

```sh
cmake --preset reading-core
cmake --build --preset reading-core
cmake --install build/reading-core
cmake -S apps/reader/font-library -B build/font-package -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DREADER_FONT_LIBRARY_BUILD=ON -DEXR_SDK_VERSION=3.41.0 \
  -DEXR_SDK="$PWD/build/reading-core/stage" \
  -DCMAKE_PREFIX_PATH="$PWD/build/reading-core/stage" \
  -DCMAKE_INSTALL_PREFIX="$PWD/build/font-stage"
cmake --build build/font-package
cmake --install build/font-package
```

The module stays default **OFF** and is never wired into the product or default SDK build. A
consumer uses `find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)` and links
`EXReaderFontLibrary::reader_font_library`; the installed config resolves exactly one `EXReader`
version. Selecting the other SDK makes configuration fail instead of mixing two providers.

## Named cases

The original suite is reused with unchanged names: 49 common cases plus the POSIX
(`posix-source-and-directory-symlinks-rejected`, `posix-real-short-write-preserves-old`) or Windows
(`windows-removal-commit-uncertain-recovery`, `windows-junction-rejected`,
`windows-locked-manifest-publish-failure-preserves-old`) cases, driven by the same
`probe.cpp` `suite` mode. This package adds:

- `s14-unicode-path-duplicate-import` — Unicode directory, Unicode selected path and display
  name; re-importing the same bytes returns `created=0` and keeps the first display name.
- `s14-invalid-font-preserves-selected-set` — corrupt and truncated inputs are refused with
  `RFL_FONT` and the stored set is unchanged.
- `s14-reopen-unicode-directory-identity` — close/reopen of the Unicode directory keeps the
  record identity and the borrowed SDK font, while remove/close stay `BUSY` until the lease is
  released.
- `s14-installed-sdk-version-selected` — the installed C consumer links the requested SDK
  (`exr_version()` and the printed token are bound to the selection).
- `s14-installed-package-binds-exact-sdk` — the installed package config names exactly one
  `EXReader` version with `EXACT`.
- `s14-wrong-sdk-selection-rejected` and `s14-invalid-sdk-selection-rejected` — configuring the
  module or a consumer against the other or an unsupported SDK fails.
- `s14-single-sdk-provider` — the exported target set references only `EXReader::exr_core`.
- `s14-reuses-pinned-module-bytes` — header and sources still hash to the pinned library
  objects.

## Test material and licence

The only font material is Adobe Source Serif 4.005R from
`adobe-fonts/source-serif@2823e993c53fca27c5c8749f529b56a5a7c77b6b`: `TTF/SourceSerif4-Regular.ttf`,
`OTF/SourceSerif4-Regular.otf` and `LICENSE.md` (**SIL Open Font License 1.1**, `OFL-1.1`). Git
blob identities and byte counts are pinned in `run.py` and verified on the received bytes; the
licence file is retained in the evidence and its text is asserted. The two-face TTC is generated in
Actions only from two copies of that unmodified TTF with pinned `fonttools 4.58.0`; the corrupt
and truncated fixtures are derived from the same file. No third-party font ships in this package.

## Boundaries and open items

- The font chooser UI and the settings/preferences wiring are **not** part of this package; they
  belong to root. No shared preferences, host, product schema, product SQL or SDK file is edited.
- SDK3.41 remains an **unaccepted candidate** here: acceptance and same-source final verification
  are root's step, and this package never rewrites the frozen SDK tree.
- Process termination is exercised; sudden power loss, filesystem/controller durability and
  network shares are not claimed. There is no collection face enumeration; explicit face
  selection only.

## Root独立验证器修复（尚未授予）

保留原失败与未执行项。本轮未修改字体库实现、公开头、默认版本或安装图。
三个native负例按唯一role=suite选择真实日志/命令，不再按commands[1]猜顺序；伪造CASE前必须确认恰好命中一次。
合成自检改用真实harness的命令顺序（C消费者、三项预期configure拒绝、suite、s14等），以覆盖原错位。
所有42项拒绝控制与四套平台/SDK组合仍完整执行；本地不做语法、构建或测试。
