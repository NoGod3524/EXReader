# SDK3.40 versus SDK3.41: what the installed package really differs in

Frozen SDK3.40 `9854061be331fe603a1822d9b2b36ee357154927`, approved SDK3.41 candidate
`edddc463c06ed5731195cdb8f06b2df6dff7699e`. All commands below are git-only reads of the two
trees; nothing is rebuilt or re-parsed locally.

## 1. The whole diff between the two pins

```
git diff --stat 9854061be331fe603a1822d9b2b36ee357154927 edddc463c06ed5731195cdb8f06b2df6dff7699e
```

27 files: the new `sdk-page-background` workflow, its documentation, its fixture generator and
probe, one new public entry point in `include/exr/render.h`, its implementation in
`src/raster.c`, a version bump in `include/exr/base.h`, `CMakeLists.txt` and
`cmake/versions.cmake`, and the per-test `CMakeLists.txt` edits that the new test target needed.

The common source candidate at the fixed start already equals that candidate for every protected
tree:

```
git diff --exit-code edddc463c06ed5731195cdb8f06b2df6dff7699e HEAD -- \
  src include cmake CMakeLists.txt bindings tests/fixtures \
  .github/workflows/native.yml .github/workflows/reliability.yml      # empty, exit 0
```

## 2. The font surface is byte-identical

```
git diff --exit-code 9854061be331fe603a1822d9b2b36ee357154927 edddc463c06ed5731195cdb8f06b2df6dff7699e -- \
  include/exr/text.h include/exr/font.h include/exr/core.h \
  src/font_bitmap.c src/font_color.c src/font_colr_v1.c src/font_outline.c \
  src/font_path.c src/font_svg.c src/fonts.c src/pdf_font.c           # empty, exit 0
```

so `exr_font_create`, `exr_font_input`, `exr_font_source`, `exr_font_count`,
`exr_font_has_glyph`, `exr_font_free`, `exr_shape`/`exr_shape_defaults` and
`exr_layout_create` keep the same declarations, the same ABI 1 and the same behaviour. The library
compiles unchanged against either install; no conditional code, no raw API and no second parser was
added. The evidence job re-runs both diffs and fails the report if either becomes non-empty
(`font_surface_unchanged` must be true).

## 3. The one real incompatibility: the CMake package version

| item | SDK3.40 | SDK3.41 | consequence for this module |
| --- | --- | --- | --- |
| `project(EXReader VERSION ...)` | 3.40.0 | 3.41.0 | `EXReaderConfigVersion.cmake` advertises 3.40.0 / 3.41.0 |
| `EXR_VERSION` (`include/exr/base.h`) | "3.40.0" | "3.41.0" | `exr_version()` string check in the C consumer |
| `EXR_CORE_VERSION` | "3.39.0" | "3.40.0" | component version only; `core` component name unchanged |
| `include/exr/render.h` | — | `exr_render_page_background` | additive; unused here |
| `src/raster.c` | — | background painting | internal; unused here |
| installed config | `SameMajorVersion`, `set(EXReader_VERSION "3.40.0")` | `... "3.41.0"` | the module and its installed config must pin one exact version |

The original module hard-coded `find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core)`
and installed `find_dependency(EXReader 3.40.0 EXACT ...)`. Against a 3.41.0 install both fail
(`EXACT` is a string comparison, not a range). That is the only incompatibility, and it is a
build-description one: the fix is the `EXR_SDK_VERSION` cache variable plus the substituted
dependency in the installed config, which is exactly the convention the other reader modules in
this tree already use (`EXR_SDK_VERSION` default `3.40.0`, `3.41.0` explicit).

## 4. Installation identity is proven, not assumed

For every job the harness records and the verifier re-checks:

- `installed/lib/cmake/EXReaderFontLibrary/EXReaderFontLibraryConfig.cmake` contains exactly one
  `find_dependency(EXReader <version> EXACT CONFIG COMPONENTS core)` and its <version> equals the
  requested selection; the other version must not appear and `@EXR_SDK_VERSION@` must be
  substituted.
- the installed `EXReaderConfig.cmake` declares `set(EXReader_VERSION "<version>")` for the same
  version — one SDK per prefix, and one prefix per job.
- the installed `EXReaderFontLibraryTargets.cmake` references only `EXReader::exr_core`
  (`s14-single-sdk-provider`).
- the installed `include/exr/text.h` equals `git show <selected SDK commit>:include/exr/text.h`
  (case `frozen-installed-font-header`, now bound to the selected pin instead of an unconditional
  3.40 comparison).
- the installed C consumer prints `installed-c-abi-sdk340` or `installed-c-abi-sdk341` from the
  configured tag, and checks `exr_version()` and ABI 1 at the same time.

## 5. What is deliberately not claimed

- SDK3.41 is an unaccepted candidate. This package installs it, links against it and reports the
  exact tree hash, but acceptance and final same-source verification stay with root.
- No SDK3.40 install is patched, copied over, or mixed into a 3.41 prefix; each job builds and
  installs exactly one SDK from its pinned source (`git archive 9854061b` for the 3.40 job).
- Power-loss durability, network shares and a font-face enumeration API are outside the contract,
  unchanged from the original package.
