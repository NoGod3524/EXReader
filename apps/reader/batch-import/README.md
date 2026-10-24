# EXReaderBatchImport 0.1.0

Optional installed C package for bounded, user-selected folder import. It has
two independently callable phases:

1. `reader_batch_enumerate_*` walks one selected root with fixed
   depth/directory/candidate/path/pending bounds. It never caches the whole tree,
   never follows symbolic links or directory junctions, and accepts only regular
   files whose extension is one of the nine SDK formats.
2. `reader_batch_import` takes 1..100 candidates and imports them serially
   through the installed `EXReaderSideload`. Each candidate is reopened,
   revalidated and copied to one stable file in the caller's private
   `staging_dir` before the SDK opens it. The package never writes product SQL
   and never performs catalog/revision/outbox mapping.

No thread, watcher or resident task is created. Enumeration may run on an I/O
worker; import must run on the borrowed library's SDK owner.

## Build

```
cmake -S apps/reader/batch-import -B build/batch-import -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=/path/to/reading-library/stage -DCMAKE_PREFIX_PATH="/path/to/sideload-prefix;/path/to/reading-library/stage" -DCMAKE_INSTALL_PREFIX=/path/to/prefix
cmake --build build/batch-import
cmake --install build/batch-import
```

The package version is 0.1.0; the public header is `reader_batch_import.h` and
the CMake target is `EXReaderBatchImport::reader_batch_import`.

## Limits

| item | default | hard maximum |
| --- | ---: | ---: |
| batch size | 32 | 100 |
| recursion depth | 0 (non-recursive) | 16 |
| directories visited | 4096 | 10000 |
| candidates | 4096 | 10000 |
| path bytes (UTF-8) | 4096 | 32768 |
| pending enumerator bytes | 1 MiB | 8 MiB |

`complete=1` is returned only for a normal end. A configured bound, an
overlong entry or an unreadable directory sets `truncated=1`; the caller must
not report that scan as complete.

## Result semantics

`committed=1` means the SDK import returned success. `created=1` means a new
SDK row; `created=0` and `DUPLICATE` mean the exact bytes matched the oldest
existing SDK row, whose metadata is untouched. A failed or cancelled item is
never reported as committed. Cancellation stops later uncommitted work but every
already committed result is returned.

The optional `on_result` callback runs after the SDK call for that item has
returned and before the next item starts. It must not reenter the library or
this module. Product mapping is a later root-owned transaction.

## Acceptance

The package is exercised by `tests/reader_batch_import` and
`.github/workflows/reader-batch-import.yml` on Windows, Linux and macOS.
See `docs/READER-BATCH-IMPORT.md`.
