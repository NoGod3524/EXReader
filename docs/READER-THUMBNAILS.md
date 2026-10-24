# EXReaderThumbnails 0.1.0

Optional install package (`apps/reader/thumbnails`) that turns a book's author cover, or the first page of a
PDF/CBZ, into a bounded RGBA thumbnail and keeps the results in a bounded, self-healing LRU directory cache.
Public C ABI (`reader_thumbnails.h`, C11 callable, C++17 implementation, static library, no threads).
It uses only the installed frozen SDK (3.40.0, ABI 1): `exr_library_blob(cover=1)`, `exr_image_page_dimensions`,
`exr_image_decode`, `exr_viewport_create`, `exr_fixed_render`. It reads no SDK private SQL, adds no product
schema and never writes the original book, the library or any user data.

## Contract

| Entry point | Source of pixels | Origin label |
| --- | --- | --- |
| `rth_cover_from_library` | `exr_library_blob(cover=1)` of a borrowed `exr_library` | `RTH_ORIGIN_AUTHOR_COVER` |
| `rth_cover_from_encoded` | host-verified encoded image bytes (PNG/JPEG/…) | `RTH_ORIGIN_AUTHOR_COVER` |
| `rth_preview_from_fixed` | `exr_fixed_render` of page `request.page` of a borrowed PDF/CBZ `exr_fixed_document` | `RTH_ORIGIN_FIRST_PAGE_PREVIEW` |
| `rth_cache_find` | cache only (library cover or preview key) | as stored |

* A book without a stored cover is the normal placeholder state: `RTH_OK`, `origin == RTH_ORIGIN_NONE`,
  `pixels == NULL`, nothing cached. A first-page preview is never reported as an author cover and vice versa;
  the origin is part of the cache identity, so the two never alias.
* Bounded source/file EPUB imports store no cover. The module does not open the ZIP, parse the package or load the
  whole book to invent one; those books are placeholders (or the host may render nothing / supply its own encoded cover).
* Output: RGBA8, straight alpha, `stride == width*4`, contain-fit into `request.width × request.height`, never upscaled.
  Scaling is an integer, alpha-weighted box filter (fully transparent texels carry RGB 0) so output is deterministic
  across platforms. Previews render directly at the reduced scale and then take the same final fit.
* Borrowed handles (`exr_library`, `exr_fixed_document`) and the cache belong to one owner thread. Calls are
  synchronous; a call from another thread, or re-entry from a control callback, returns `RTH_ARGUMENT` and changes
  nothing. This holds for **every** entry point that takes a cache — `rth_cache_open`, `rth_cache_stats`,
  `rth_cache_clear`, `rth_cache_find`, the three cover/preview calls and `rth_cache_close`; a refused close leaves the
  cache alive. `rth_control.cancelled` is polled on the calling thread (before decode, per output row, before publish
  and inside `exr_fixed_render`); cancellation clears the output and publishes nothing.
* No C++ exception crosses the C ABI: every entry point catches `std::bad_alloc` (→ `RTH_MEMORY`) and any other
  exception (→ `RTH_IO`), and ownership is by construction, not by the catch: the cache is held in a `unique_ptr` until
  `*out` is filled (a failure holds no lock and leaves no partial cache), the borrowed `exr_library_blob` is freed by a
  scope guard on every path, and the thumbnail pixels stay owned until after the store returns, so a failure inside the
  store leaves `width/height/stride/origin` 0, `pixels` NULL and no cache entry or temporary, and the cache still
  stores on retry. A directory path or file name this platform cannot represent is a status, never a termination.

## Identity and limits

Cache identity (stored verbatim in each file and compared on every read, so a file-name collision cannot mis-hit):
`format + SHA-256 of the verified original + origin + source tag (lib | fix | enc:<sha256 of the encoded bytes>) +
output box + page + background + algorithm tag`. The host supplies the verified format and SHA (`rth_sha256_hex`
is provided).

| Limit | Default | Hard maximum |
| --- | --- | --- |
| `max_edge` (output width/height) | 512 | 1024 |
| `max_entries` | 256 | 4096 |
| `max_total_bytes` (cache directory) | 64 MiB | 512 MiB (minimum 4096) |
| `max_source_pixels` (decoded source) | 16,777,216 | 16,777,216 |
| `max_encoded_bytes` (encoded cover) | 8 MiB | 16 MiB |

Source dimensions are read with `exr_image_page_dimensions` and refused (`RTH_LIMIT`) before any decode allocation;
all dimension arithmetic is 64-bit. Output boxes above `max_edge` are refused without allocation.
`max_entries` and `max_total_bytes` are a **hard bound on the cache directory**: a cache handle exists only while the
directory holds no more own entry files and no more own entry bytes than those limits allow (`rth_cache_open` deletes the
surplus in the same pass that adopts the rest, so `RTH_OK` is a statement about the whole directory, not about an
observed prefix). A directory holding more own entry files than the scan ceiling `max(4096, max_entries*64)` (at most
65536) is refused with `RTH_LIMIT` and no cache instead of being adopted partially.

They bound nothing else. Decoding a cover transiently allocates `width*height*4` bytes inside the SDK;
`rth_thumbnail.decoded_bytes` and `rth_stats.peak_decoded_bytes` report that separately from `rth_stats.bytes`, and
`max_source_pixels` is the only bound on it. An entry larger than `max_total_bytes` is returned but not stored
(`stored == 0`, `rejected` counted). The temporary file of a publish may briefly exist beside the cache.

## Cache directory

Files `rth-<32 hex>.rth` (magic, key, size, payload SHA-256, RGBA payload), `rth-index.txt` (LRU ticks) and one
temporary per publish.

**Publishing.** The bytes go to `rth-tmp-<16 hex session>-<8 hex sequence>.tmp`, created with exclusive-create
semantics (`O_CREAT|O_EXCL|O_NOFOLLOW` / `CREATE_NEW|FILE_FLAG_OPEN_REPARSE_POINT`), flushed, and published with a
same-directory platform atomic replace (`MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)` on Windows, `rename(2)`
elsewhere). A name that already exists — including a hard link planted by someone else — is never opened, so no file
outside the cache can be truncated or rewritten through a temporary. Reading an entry opens it without following
symbolic links or reparse points and only accepts a regular file (`O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT` plus a
reparse-point attribute check). A failed replace is reported: `rth_cache_open` and `rth_cache_clear` return `RTH_IO`
and `rth_stats.index_failures` counts it, instead of silently keeping a stale index.

**One owner per directory.** `rth_cache_open` takes an OS lock on `rth-owner.lock` — `flock(LOCK_EX|LOCK_NB)` on POSIX,
an exclusive open without sharing on Windows. A second open returns `RTH_BUSY` and no cache: that covers another handle
in the same process, another process, and a handle whose holder died (the OS releases the lock with the process, so a
crash never blocks the directory). There is no multi-process LRU and no shared budget: one handle owns the directory and
every OK open is the only writer.

**Bounded working set, hard directory bound.** The directory is walked once; entries are made room for and inserted one by
one, so the retained map never exceeds `max_entries` and the directory is never collected into an in-memory list
(`peak_retained_entries` is the true map peak, taken after the insert, and is <= `max_entries`). Every own entry file the
pass meets is either adopted or deleted — damaged, larger than `max_total_bytes`, or over the count/byte cap — so when
the pass ends the directory itself satisfies the limits; `scanned_files`, `own_candidates` and `scan_deleted` report the
work. Unrelated files are never deleted. Files are created exclusively under a per-open unpredictable token and published
with the atomic replace above; `open` removes the pre-0.1.0 temporaries at once and current-naming temporaries only when
older than 600 s (a younger one may belong to a live process).

**Eviction and repair.** LRU eviction runs on count and bytes; recency persists across close and reopen (the index is
published atomically on every change and at close). A damaged entry (bad magic, length, key, or payload digest) is
deleted and counted in `corrupt_rebuilt`, then rebuilt from the source on the next request; a damaged or missing index
is rebuilt from the directory. Open never touches files it does not recognise by name. Reopening with smaller limits
evicts down to them.

## Evidence

`.github/workflows/reader-thumbnails.yml` builds the SDK, installs this package and compiles an installed C11 consumer,
a C++17 probe and the regression consumer `thumb-regress` on `ubuntu-22.04`, `windows-2022` and `macos-15`. Expected
pixels are produced independently by `tests/reader_thumbnails/make_fixtures.py`; PDF/CBZ previews use generated
originals with known colours plus the repository's `pdf-public.pdf` and `comic.cbz`. Cache bytes, decoded-image
bytes, scanned files, the retained-entry peak and process RSS are recorded per scenario as raw measurements only.

`thumb-regress` runs as separate processes and judges the contract with the public ABI that existed before the
fixes, so the same source fails on the reviewed implementation and passes on the fixed one: LRU recency written by one
process and judged by an independent reopen with a smaller entry bound; a hard link planted at a temporary name
(external bytes must stay byte-identical); a live cache's fresh temporary versus a stale one; an index that cannot be
replaced atomically; re-entry refused by the statistics call; a directory far larger than the old scan budget; an
unrepresentable directory path; and the owner lock across a live holder and a killed one.

`thumb-fault` replaces the global `operator new/delete` inside its own binary and makes the n-th allocation throw, then
walks every allocation point of `open`, of a cover that already holds thumbnail pixels, and of the borrowed-blob path,
counting live allocations: each failure must report a status, leave an empty output box, leak no cache/blob/pixels/
temporary and leave the cache able to store on retry.

See `docs/validation/reader-thumbnails.json` for the run-bound results; nothing here grants product performance, host
UI, six-platform or release status.
