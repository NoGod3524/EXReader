# Native C validation

## 0.4 structured EPUB model

Local Windows Release tests cover the document tree, parent/sibling connectivity, UTF-8 ranges,
spine ordering, non-linear and auxiliary chapters, nested lists, table cells, inline styles,
embedded style text, EPUB 3 navigation, footnotes, source ownership, and PNG/CSS resource reads.
Link tests include chapter-local fragments, cross-chapter targets, Chinese IDs and filenames,
literal percent signs in paths, missing targets, unsafe traversal, external URIs and invalid encoding.
Missing chapters, duplicate manifest entries, malformed XHTML, external entities and excessive
nesting are rejected. Oversized non-text resources fail on demand without inflating them at open.
Image-only publications retain structure even though the text renderer has no pages to produce.
Original fixtures are reproducible with `python tests/make_structure_fixtures.py`.

The existing format, layout, rasterization, conversion and SQLite integration tests also pass.
Workflow runs for the current commit validate desktop runtime and mobile cross-compilation;
historical run links below cover the earlier implementation.

2026-10-15. Native engine 0.3.0 replaces the JavaScript source on the primary development line.

Local Windows / MinGW GCC 16.2 / CMake 4.4 checks passed:

- C11 shared library and standalone renderer build, with warnings treated as errors for engine sources.
- Native integration suite: format decoding, UTF-16 surrogate handling, EPUB spine order/path resolution, blocked XML entities, ZIP expansion limits, page geometry, glyph coverage, position persistence across reflow, hit testing, native rasterization, six conversion round trips, SQLite metadata/cover/annotation persistence, cascade deletion and database backup/reopen.
- Corrupted copies of FB2, EPUB, DOCX, RTF and MOBI fixtures are opened and released to exercise parser failure paths.
- Independent Python PNG check validates chunk CRCs, decompression, scanline structure and rendered ink. Python is a test tool, not a runtime dependency.
- Chinese filenames and output paths exercised through the native Windows CLI.
- Installed SDK includes the public C header, native shared library, CLI and third-party license texts.
- Actual rendered Chinese page: native-page.png. Uses the locally installed Microsoft YaHei font; the font file is not redistributed.

GitHub workflow native.yml checks Windows, Linux, macOS, ASan/UBSan and mobile cross-compilation. Results must be read from the workflow; adding a job does not establish that platform support has passed. Mobile cross-compilation checks do not constitute device runtime or application-package validation.

## First native CI

[Run 38839605921](https://github.com/NoGod3524/EXReader/actions/runs/38839605921) passed all six jobs: native runtime tests and SDK installation on Windows/MSVC, Linux/GCC and macOS/Clang; AddressSanitizer/UndefinedBehaviorSanitizer; Android ARM64 cross-compilation; iOS/iPadOS ARM64 device and simulator cross-compilation. This run covers the initial native implementation at 60e3e03. Later changes add font metric caching and installed-SDK smoke checks and are checked separately.

## Local performance sample

Windows, MinGW GCC 16.2, Release build, system Microsoft YaHei font. A generated repetition-based Chinese text of 2,919,999 UTF-8 bytes (approximately one million characters) produced 2,223 pages and a native rasterized first page. Process CPU time reported by the CLI was 3.339 seconds before caching repeated font metrics, and 0.086 seconds after caching. This is a synthetic sample, not a general publication benchmark. Cold and reused-font layouts are compared after font-size changes to detect stale metrics.
