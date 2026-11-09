# 7Z containers and locate counters

Both tasks are complete. Baseline: `db9bab66`. Machine-readable results and
per-book input/page fingerprints are in `sevenz-anchorstats-acceptance.json`.
Step records are appended to `../SEVENZ-OUT.txt`.

The engine has no liblzma dependency. `src/lzma.c` implements scalar raw LZMA and
LZMA2 decoding; `src/sevenz.c` implements SignatureHeader, plain/encoded headers,
coder bindings, CRCs, solid substreams and UTF-16 filenames. Copy and Delta use
the same bounded decode path. Existing miniz supplies CRC-32 only. Format
references: [7Z specification](https://github.com/ip7z/7zip/blob/main/DOC/7zFormat.txt)
and [official LZMA specification](https://7-zip.org/a/lzma-specification.7z).
No upstream decoder source or new third-party library was added.

The new container API is declared in `include/exr/formats.h`. It is independent
of document detection and the EPUB/CBZ ZIP implementations:

```c
exr_sevenz_options options = exr_sevenz_options_defaults();
options.max_unpack_size = 32u * 1024 * 1024;
exr_sevenz *archive = NULL;
exr_error error;
if (exr_sevenz_open("book.7z", &options, &archive, &error) == EXR_OK) {
  size_t count, size;
  const exr_sevenz_entry *entries = exr_sevenz_entries(archive, &count);
  for (size_t i = 0; i < count; i++) {
    if (!entries[i].is_directory) {
      void *data = NULL;
      if (exr_sevenz_extract(archive, i, &data, &size, &error) == EXR_OK) {
        /* Consume exactly size bytes. */
        exr_free(data);
      }
      break;
    }
  }
  exr_sevenz_free(archive);
}
```

`open_source` supports a seekable callback source and transfers ownership only
on success. Listing reads metadata, not body blocks. Extraction decodes the
selected file's complete solid block and returns only that file. The default
128 MiB limit applies to packed input and every decoded stage, including the
whole solid block; the separately configurable header limit defaults to 16 MiB.
Dictionary properties never drive a dictionary allocation: bounded output is
the history buffer. Absolute/drive/ADS paths and `.`/`..` components using either
separator are rejected before an archive handle is returned. Nothing is written
to disk. Unsupported codecs, encryption, multi-input coders, external names or
folder tables, anti-items, and chains longer than four coders are rejected.

| Required sample | Listing | Single-file extraction | Result |
|---|---|---|---|
| `fixtures/sevenz/lzma2-solid.7z` | 2 files | `second.txt`, 23 bytes | Pass; LZMA2 body and LZMA encoded header |
| `fixtures/sevenz/traversal.7z` | Rejected at open | No handle returned | `EXR_FORMAT`, stored name `../escape.txt` |
| `fixtures/sevenz/nested.7z` | 5 entries, 3 directories | `漫画/卷一/page.txt`, 21 bytes; empty file, 0 bytes | Pass; LZMA + Delta |

Fixtures are original test content. `make_sevenz_fixtures.py` generates the
Python-encoded fixtures using only the standard library. Official `7zr` 26.04
independently validated the three positive generated archives (`lzma2-solid`,
`nested`, `codecs`); its listing confirmed the traversal name without extraction.
`7zip-lzma.7z` and `7zip-lzma2.7z` were independently produced by that executable,
then decoded by the engine. To regenerate those two files, place
`Reference first file.\n` in `first.txt` and `Reference nested file.\n` in
`nested/second.txt`, then run from that input directory:

```text
7zr a <absolute-output>/7zip-lzma.7z first.txt nested/second.txt -m0=lzma -mhc=on -ms=on -mtm=off -mtc=off -mta=off
7zr a <absolute-output>/7zip-lzma2.7z first.txt nested/second.txt -m0=lzma2 -mhc=on -ms=on -mtm=off -mtc=off -mta=off
```

`exr_publication_locate_report(publication)` returns `exr_locate_report` by value;
`exr_publication_locate_report_reset(publication)` clears just those counters.
Every locate call with a publication contributes to `total_entries`, including
internal calls and failed calls. Successful exact resolutions include an
explicitly requested part start. A missing anchor contributes to both
`resolved_part_start` and `missing_anchor`; a missing part contributes only to
`missing_part`. Repeated calls count repeatedly. The prior resolution function,
fallback, deduplicated missing-target list and TOC position cache are preserved.

The following measurements reset the report after obtaining the TOC, then call
locate once for each entry:

| Book | Total | Exact | Part-start fallback | Missing part | Missing anchor |
|---|---:|---:|---:|---:|---:|
| 紅樓夢 | 108 | 108 | 0 | 0 | 0 |
| 醒世恆言 | 40 | 40 | 0 | 0 | 0 |
| Pachinko | 70 | 70 | 0 | 0 | 0 |
| Constructed EPUB | 5 | 3 | 2 | 0 | 2 |

The Release configuration registers 210 ctests: 205 baseline tests plus three
7Z groups and two locate-report groups. All 210 passed. Optional ICC, WebP,
TIFF, AVIF and PDF crypto were disabled in both baseline and candidate builds;
audio, library, text indexing, PDF, PDF editing and JPX were enabled. The 19
real EPUBs were rendered independently with the same font/layout: 11,296 pages
before and after, 8,648,640 glyphs, zero changed page hashes.

Validation commands (from the repository root):

```text
ctest --test-dir build/native --output-on-failure -j 4
python tools/check_layers.py build/native
python tests/measure_locate_report.py --dll build/native/libexreader.dll --manifest tools/regress/corpus.json --output build/sevenz/anchor-stats.json
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/native/libexreader.dll --font <Reader.otf> --layout tools/regress/layout.json --output build/sevenz/realbooks-after.json --baseline build/sevenz/realbooks-before.json --source-revision <candidate-commit> --workers 3
```

Additional decoder validation: 48 Python liblzma encoder round trips (property
variants, empty/random/repetitive data, multi-chunk LZMA2) and 176 rejected
truncated streams. The encoder is a test oracle, never an engine dependency.
To reproduce the test-only probe with GCC:

```text
gcc -shared -std=c11 -DEXR_STATIC -Iinclude -Isrc src/lzma.c src/common.c -o build/sevenz/codec-probe.dll
python tests/check_lzma.py build/sevenz/codec-probe.dll --seeds build/sevenz/fuzz-corpus
```

All three 7Z groups also passed a standalone Clang ASan/UBSan build. The
`fuzz_sevenz.c` harness repairs outer CRCs to exercise directory parsing and
also fuzzes the raw decoder. Compile with Clang's
`-fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer -g -O1`, definitions
`EXR_STATIC`, `MINIZ_NO_ZLIB_APIS`, `MINIZ_NO_ARCHIVE_APIS`, and include paths
`include`, `src`, the existing miniz source and generated miniz build directory.
Sources: `tests/fuzz_sevenz.c`, `src/sevenz.c`, `src/lzma.c`, `src/common.c`,
`src/core.c`, `src/source.c`, and the existing dependency's `miniz.c`.
Run with the generated raw seeds plus `fixtures/sevenz/*.7z` in the seed directory:

```text
fuzz-sevenz build/sevenz/fuzz-corpus -seed=2569871251 -runs=100000 -max_len=32768 -timeout=5 -rss_limit_mb=1024
```

The recorded Windows run completed 100,000 cases in 57 seconds, with no ASan or
UBSan findings (Windows leak detection disabled). Raw local logs are in
`build/sevenz/ctest.txt`, `fuzz.txt`, and `realbooks-{before,after}.json`.
On this MinGW Release build, the two new codec/container objects contain 27,256
bytes of text; the aggregate DLL grew by 28,980 bytes.

Protected-tree registration: `src/sevenz.c`, `src/lzma.c`,
`src/lzma_internal.h`, `src/publication.c`, `include/exr/formats.h`,
`include/exr/layout.h`, and this task's tests/fixtures/evidence. The new source
and header inventory is registered in `tools/layers.json`; `CMakeLists.txt`
only registers the five test groups. `examples/` and `.github/` are unchanged.
