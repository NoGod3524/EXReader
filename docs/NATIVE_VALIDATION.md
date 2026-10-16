# Native C validation

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
