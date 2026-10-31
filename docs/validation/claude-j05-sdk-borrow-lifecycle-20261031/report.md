# J05 SDK 3.42 library/source/pager borrow lifecycle — result: passed (C ABI, Linux x86_64 only)

Independent evidence; not wired into any gate. SDK, production owners and old tests untouched.

## Identity
Frozen SDK 8357eafa28423a7ab93ba08b823af80f01ad1505 checked out and verified (`git rev-parse`), built with preset `reading-library`, installed, and the consumer built via `find_package(EXReader)` against that install stage (static link; `ldd` shows only libm/libc). The program reports `exr_version()=="3.42.0"`. Installed library/header SHA-256 values are in `summary.json`. Runs: 41155286626 failed (consumer missed `EXReader::exr_core` link; build error only), **41155465446 attempt 1 success** (commit cfc419d2), evidence artifact 13024018870 (sha256:ce3af9c4...83cc6). 2 of 3 budgeted runs used.

## Contract used (include/exr/library.h, layout.h)
`exr_library_source` returns a source that "keeps the database alive after library_close"; the caller releases it or hands it to `exr_txt_pager_create`, which on success owns it and releases it when the pager is freed; on failure the caller keeps ownership; a commit through another connection invalidates sources.

## Observation
Real OS state: open file descriptors under `/proc/self/fd` pointing at the library database (or its -wal/-shm/-journal). Not a wrapper counter. 65 checks, 0 failed.

## Results
- No borrow: close → fds 1→0 immediately.
- Normal chain, all 6 release orders of {pager A, pager B, raw source}: pagers read and source bytes match before close; after `exr_library_close` the database fd stays open and all three borrowers still work (new pages, byte compare); fds stay open while any borrow remains; fd = 0 after the last release.
- Cancel: cancel flag set after close request → `exr_pager_get` returns EXR_CANCELLED, fd still open, 0 after pager free.
- Failure: `exr_txt_pager_create` with NULL font fails, returns no pager, source remains caller-owned and readable; manual release → fd 0. A real commit through a second connection makes the pager's next uncached page fail (not stale success); after releases and closing the other connection, fd 0.

## Limits
C ABI on Linux only: not JNI/Android, Swift/Apple, Windows, nor six-platform. Repeated close/release is undefined by the header and not tested; book deletion through the owner and extreme resource-exhaustion failures are not covered. Whether to feed this into the P0 gate is a separate decision (H01 untouched).
