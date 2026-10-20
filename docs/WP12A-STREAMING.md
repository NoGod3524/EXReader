# WP12a streaming import and large media

WP12a adds a source-based import path for large originals and verifies the
existing audio readers against 1 GiB media. It does not change the in-memory
API or the SQLite schema (still schema 6).

## API

```c
/* Borrowed for the call; bytes are copied into SQLite in 64 KiB chunks. */
exr_status exr_library_import_source(exr_library *library, exr_format format,
                                     const exr_source *source, const char *title,
                                     int64_t *id, exr_error *error);
exr_status exr_library_import_source_unique(exr_library *library, exr_format format,
                                            const exr_source *source, const char *title,
                                            int64_t *id, int *created, exr_error *error);
/* Convenience wrappers; the file is opened as a bounded source, not slurped. */
exr_status exr_library_import_file(exr_library *library, exr_format format,
                                   const char *path, const char *title,
                                   int64_t *id, exr_error *error);
exr_status exr_library_import_file_unique(exr_library *library, exr_format format,
                                          const char *path, const char *title,
                                          int64_t *id, int *created, exr_error *error);
/* Read a stored CBZ through SQLite blob I/O; pages are decoded on demand. */
exr_status exr_library_fixed_source(exr_library *library, int64_t id,
                                    const exr_fixed_open_options *options,
                                    exr_fixed_document **out, exr_error *error);
```

CBZ is the currently supported source format because it already opens from a
random-access source. Other formats return `EXR_UNSUPPORTED` from the streaming
entry points; the existing memory APIs are unchanged.

Example:

```c
exr_source source;
exr_error error = {0};
if (exr_file_source("large.cbz", &source, &error) == EXR_OK) {
  int64_t id; int created;
  exr_status status = exr_library_import_file_unique(
      library, EXR_CBZ, "large.cbz", "Large book", &id, &created, &error);
  source.release(source.context);
  if (status == EXR_OK) {
    exr_fixed_document *doc;
    exr_library_fixed_source(library, id, NULL, &doc, &error);
    /* exr_fixed_pages/exr_fixed_render read only the pages they need. */
    exr_fixed_free(doc);
  }
}
```

## Buffer scope and limits

The 32 MiB claim applies to **SDK-owned buffers during the operation**, not to
the mapped/input file, the compressed original, or the SQLite database file:

- one 64 KiB source/compare chunk;
- SQLite's configured page cache (default 2 MiB; the import does not raise it);
- one SQLite blob-write page and statement/bookkeeping overhead;
- the CBZ central directory and per-page headers (bounded by the CBZ header
  budget; the 1 GiB padding member is ignored and never read).

Process peak working set and private bytes are reported separately. Database
growth is reported but is not counted as a buffer. The blob API and
`SQLITE_MAX_LENGTH` cap a single stored original at 2 GiB - 1; larger inputs
return `EXR_LIMIT` before any row is inserted.

## Transactions, cancellation and dedup

- The row insert and every blob chunk are one `BEGIN IMMEDIATE` transaction.
  Cancellation, source read failure, a blob write failure or a commit failure
  rolls the transaction back; the book row and blob disappear together.
- `_unique` compares same-format, same-length stored sources byte-for-byte in
  64 KiB chunks before inserting. A match reuses the oldest ID and reports
  `created=0`; no metadata, progress, cover or notes are overwritten.
- Lookup and insert are serialized with the library database mutex, matching
  the existing unique-import contract.
- After a failure or cancellation, reopening the database shows the previous
  book count and the same dedup result. `native-library-stream` covers a
  successful import/dedup/reopen, mid-write cancellation, an injected source
  read failure and an exclusive storage lock.

## Large-media evidence

Generated outside Git by `tools/generate_large_media.py`:

| Input | Bytes | SHA-256 |
| --- | --- | --- |
| 1 GiB CBZ (two 2x2 PNG pages + ignored 1 GiB stored member) | 1,073,742,306 | `ba52336a206f8d0ce26ac109d3f8a36049a8646bc57dbeb27130c0c2ccb27a80` |
| 1 GiB WAV (8 kHz mono PCM16, 536,870,912 frames) | 1,073,741,868 | `60e75b097241b20774749e0881cccfd2cfbd22b38ecd3a9d9b727bb161e318e1` |

Measured by `tools/wp12a_media_probe.c` (Windows x64, MinGW GCC 16.2, Release):

| Probe | Result |
| --- | --- |
| Streaming CBZ import, first | 13.36 s, 1,074,839,552-byte database, 2 pages |
| Duplicate streaming import | 3.03 s, same ID, `created=0` |
| Added private peak during 1 GiB streaming import | 4,595,712 bytes (4.38 MiB; includes SQLite page cache) |
| Whole-process peak during streaming import | 5,423,104-byte working set / 1,052,672-byte private peak |
| Streaming read/render of stored CBZ | via `exr_library_fixed_source`, 2x2 page |
| 1 GiB WAV open + reads at start/middle/end | 0.0006 s, 12,288 frames, 16 KiB output + 4 KiB stack |
| Legacy in-memory baseline (64 MiB CBZ) | 67.1 MiB source copied, added private peak ≈ 67.5 MiB |
| Legacy 1 GiB path | rejected by the 128 MiB memory API before allocation |

The baseline is the same CBZ at 64 MiB through `exr_library_import()`; it must
retain the whole source and SQLite's transient copy. The streaming path's added
buffer is 64 KiB, three orders of magnitude below the 32 MiB ceiling and
independent of the 1 GiB input size.