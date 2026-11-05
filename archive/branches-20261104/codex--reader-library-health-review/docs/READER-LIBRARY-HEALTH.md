# J14: library health

Read-only health check of one product catalog against one local SDK library.
This page is the module contract and the validation record. It is not a host
feature: no host surface, repair action, sync entity or wire change ships here.

- Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Branch: `codex/reader-library-health`
- Package: `apps/reader/library-health` (optional, installed CMake package
  `EXReaderLibraryHealth 1.0.0`)
- Consumers: `tests/reader_library_health/consumer` (installed-only C probe and
  C++17 consumer)
- Workflow: `.github/workflows/reader-library-health.yml`

## What it reports

Exactly one verdict per delivered active catalog row, in catalog keyset order
(`sort_title`, `book_key`):

| Verdict | Meaning |
| --- | --- |
| `verified` | Mapped; the retained original's size equals `source_bytes`, its full SHA-256 equals the identity in `book_key`, and both ends still hash the same after the read. |
| `cloud_only` | Catalog metadata with no local SDK mapping (`sdk_book_id = 0`). |
| `mapping_missing` | The mapped SDK ID has no retained original (`exr_library_source` returned `EXR_ARGUMENT`). |
| `source_unavailable` | The SDK refused to open the source for another reason (for example `EXR_DATABASE`, `EXR_LIMIT`). |
| `size_mismatch` | The retained size differs from the catalog's `source_bytes` (short or long original). |
| `read_failed` | A read returned nothing, a short/out-of-range read, or the source was invalidated mid-read. |
| `hash_mismatch` | The full read completed and the SHA-256 differs from the catalog identity. |
| `limit_skipped` | The original is larger than `max_book_bytes`; it was not read and is not healthy. |

Only `verified` is healthy. Nothing is repaired, deleted, downloaded, imported
or written. The scan reports; the host decides what to do.

## Public API

`reader_library_health.h` exposes:

- `reader_health_options_init` / `reader_health_cursor_init` (zero-fill plus a
  magic tag; a cursor not produced by this build is `argument`).
- `reader_health_create(catalog, library, options, &scanner, &error)` — borrows
  one open `reader_catalog` and one open `exr_library`, binds to the calling
  thread, allocates one read buffer, and never closes either owner.
- `reader_health_step(scanner, &cursor, visit, context, &info, &error)` — one
  bounded step, delivering at most `rows_per_step` rows.
- `reader_health_destroy(&scanner, &error)` — frees the scanner only.
- `reader_health_verdict_name` / `reader_health_status_name` — stable names used
  by the validation reports.

### Identity and strings

`book_key` is the product identity `format:sha256` (lowercase hex). Row strings
and the delivered row itself are borrowed for the duration of one visit call.
The scanner copies `sort_title` per step and reuses the same storage, so a host
that keeps a row must copy it.

### Threads, reentry and ownership

- The scanner binds to the creating OS thread. That thread must be the catalog's
  owning worker and, serially with every other user, the `exr_library` owner.
  `reader_health_create`, `step` and `destroy` on another thread return
  `thread` without touching state.
- A call made from inside the visit or progress callback returns `reentry`. The
  callback must not call the scanner, close the owners or free the scanner.
- The creating thread must outlive the scanner; binding is by OS thread identity.
- No thread, server, plugin or WebView is created.

### Errors

`reader_health_error.code` is one of `ok`, `cancelled`, `argument`, `memory`,
`catalog`, `thread`, `reentry`, `internal`; `detail_code` carries the catalog
return code for `catalog` failures and `message` is a bounded ASCII detail.

### Commit boundary and cursor

A row is delivered only after its verdict is final. The cursor advances exactly
past delivered rows, before the visit call, so a host stop request cannot lose a
row. Cancellation, an unobservable source or a catalog failure never advance the
cursor. A cursor is plain data; it can be copied and used with another scanner of
the same catalog (the catalog pointer is checked), and it rejects a foreign
catalog with `argument`. The cursor borrows that pointer, so the catalog must
stay open while the cursor is in use; a released catalog's address may be reused
by the next open.

### Hard limits (fixed in the header, never widened here)

| Limit | Default | Maximum |
| --- | --- | --- |
| `rows_per_step` | 32 | 200 (the catalog page limit) |
| `buffer_bytes` | 64 KiB | 1 MiB (minimum 4096) |
| `max_step_bytes` | 64 MiB | 1 GiB |
| `max_book_bytes` | 512 MiB | 2147483647 |
| `max_total_rows` | 100000 | 1000000 |
| `sort_title` | — | 4096 characters (16385 bytes) |
| `book_key` | — | 72 bytes |

A caller may lower a maximum but never raise it. A step materializes at most
`rows_per_step` catalog rows plus one buffer; a new row is not started once the
step budget is spent, so one row may exceed `max_step_bytes` by at most one
book. The whole original is never loaded: reads go through one fixed buffer and
the streaming SHA-256.

## How the data is read

- Catalog: `reader_catalog_page` only (keyset paging, limit 1..200, active rows
  only). No SQL, no private table, no soft-deleted rows.
- SDK: `exr_library_source` only, then `read_at` in `buffer_bytes` chunks,
  `release` on every path. Both ends are re-read after the hash so an original
  invalidated or changed during the read is `read_failed`, never healthy.
- Cancellation is polled before a step, between rows and between buffers.
  `control.progress` reports `EXR_STAGE_READ` with bytes of the current book.

## Cloud validation (Actions only)

No build, fixture, parser or test runs locally. `.github/workflows/reader-library-health.yml`
guards `HEAD == GITHUB_SHA`, the fixed start as an ancestor, the frozen SDK tree
(`9854061be331fe603a1822d9b2b36ee357154927`), the product migration
(`f32bb8aa18ed3de286900f19ce4230fd93435dd0`) and the J14 path list, then:

1. installs the unchanged product catalog provider;
2. builds and installs the frozen `reading-library` SDK preset;
3. builds and installs `EXReaderLibraryHealth` from that SDK and the catalog;
4. compiles the C probe and C++ consumer from the install prefixes only
   (no source-tree include path);
5. generates 2202 catalog rows over four real formats (EPUB, PDF, CBZ, TXT) and
   runs the installed consumers.

The 2202 rows are exactly: 2185 verified mappings, 4 cloud-only, 4 missing
originals, 4 same-length hash mismatches, 2 short originals, 2 long originals and
1 row above `max_book_bytes`. The validator re-hashes every original with
`hashlib`, compares the catalog and library database bytes before and after the
scan, and checks the named cases:

- `main_*`: 2202 delivered rows, keyset order, per-row identity and verdict,
  exact verdict counts, step count, hashed-byte agreement, and a second pass with
  `rows_per_step = 7` that must deliver byte-identical rows.
- `cancel_*`: cancel after ten delivered rows keeps exactly those ten and a
  restart completes without loss; cancel inside a read delivers nothing and the
  same row is `verified` on a clean rescan.
- `budget_*` and `limit_*`: a 4096-byte step budget splits rows across steps and
  `max_total_rows = 12` stops at twelve rows and continues to all forty with a
  raised limit.
- `reentry_*`, `wrong_thread_*`: callbacks and foreign threads are refused and
  the owner thread still completes the scan.
- `wrong_catalog_*`: a cursor from another catalog is `argument`; a fresh cursor
  works.
- `change_during_scan`: an SDK book deleted from a second connection while the
  scan runs becomes `mapping_missing` and is not healthy.
- `invalidate_mid_read`: a commit from a second connection during a read yields
  `read_failed` with partial `bytes_read`, and a later scan is `verified`.
- `memory_*`: a 16 MiB EPUB is streamed into the SDK and scanned with a 4096-byte
  buffer; peak working-set growth must stay within 8 MiB, far below the original
  and consistent with one buffer plus the SQLite page cache.
- `cpp_*`: the installed C++ consumer reproduces the C rows and refuses a wrong
  thread and reentry.

The `evidence` job downloads all three platform ZIPs through the GitHub API,
recomputes each ZIP digest, requires the same `head_sha`/`run_attempt`, checks
the named jobs and the artifact validity window, and requires the three row
digests and verdict counts to agree.

## Acceptance record

Root在独立分支 `codex/reader-library-health-review` 修复两处取消边界：首次取消回调前先设置防重入状态；原件观察完成后、推进游标前再次轮询取消。新增回归实际在取消回调内调用step/destroy，以及只在最终读取进度回调请求取消并重试未推进游标。严格汇总另核原始具名结果及真实C/C++消费者文件摘要。

修复 source `10b038a55fabea493e3ef858d3171e8c65a54f0b` / [run 40163483001](https://github.com/NoGod3524/EXReader/actions/runs/40163483001) / attempt1 的Windows、Linux、macOS及严格汇总全部success。原2202行扫描、取消、跨线程/重入与安装后C/C++消费者保留；严格汇总重新下载三个ZIP、核实际消费者字节及原始新增取消用例，`problems=[]`，三平台行摘要仍为 `88c48114…4035fce`。新工件/作业完整身份在JSON的 `root_review` 中；原版测量与失败记录继续单列归原受测source，不转作新版本性能观测。宿主接线尚未完成。

Tested source `a600cf3df53fdc8b97e47872e44f9b5c5ff6becb` (branch
`codex/reader-library-health`), run
[40125980818](https://github.com/NoGod3524/EXReader/actions/runs/40125980818)
attempt 1, workflow `.github/workflows/reader-library-health.yml`. All four
jobs succeeded. The evidence commit on top of that source changes this page and
`docs/validation/reader-library-health.json` only.

| Platform | Job | Artifact | Bytes | SHA-256 | Valid until |
| --- | --- | --- | --- | --- | --- |
| Linux | `120967348438` | `reader-library-health-Linux-40125980818-1` (`12573166855`) | 8554923 | `f39a75fed7f18e106428ed77841c04717b7e6ad189ba1227c43e79e6e36689f4` | 2027-01-22 |
| Windows | `120967348623` | `reader-library-health-Windows-40125980818-1` (`12573401731`) | 5812423 | `549b2dab9fd17ff11758fde6c89b7d6c8cfb4cc97bb4686a641e2e7793706179` | 2027-01-22 |
| macOS | `120967348588` | `reader-library-health-macOS-40125980818-1` (`12573501492`) | 7369301 | `68c71a9acd95db7c8df73d61a9c48b477d44b36edc56b5e36688c2be02707002` | 2027-01-22 |
| Evidence | `120968255753` | `reader-library-health-evidence-40125980818-1` (`12573791344`) | 888 | `1b2b9a167464a4465449ad5070d09749348e41ea24f41c8209b6ba9b9e1a77bf` | 2027-01-22 |

The strict evidence job authenticated all three ZIPs through the GitHub API,
recomputed each digest, required the same `head_sha` and attempt, checked the
named jobs and the artifact validity window, and compared the platform reports:

- 2202 rows on every platform, one shared row digest
  `88c481146e90464229df4963b9d338a5d46e58d5a59ceaa83ddf4a2674035fce`;
- verdicts exactly `verified 2185, cloud_only 4, mapping_missing 4,
  size_mismatch 4, hash_mismatch 4, limit_skipped 1`;
- 37 aggregate checks per platform, zero failures;
- the SQLite catalog and library files are byte-identical across platforms
  (catalog `b6cc837a9ef11a9c…`, library `106d3de4c69842ef…`), and both are
  unchanged before and after every consumer;
- the installed C++ consumer reproduced the C rows and the reentry and
  wrong-thread refusals.

Measured bounds: 69 steps for 32 rows each, 315 steps for the 7-row replay,
1614527 original bytes hashed per platform, and a 16,778,436-byte EPUB read with
a 4096-byte buffer and peak growth 0 (Linux), 0 (Windows) and 1,490,944 bytes
(macOS) against the 8 MiB budget.

Original failures are retained as failed runs, not rewritten: the bounded-copy
`-Werror` build (40123501809), the duplicated CBZ originals and missing scenario
directories (40123963341), and two rounds of over-strict cancellation, row-limit
and cursor-catalog expectations (40125446068, 40125579495). Each fix is a source
or test change in the tested history above.

## Limits and non-goals

- Not a host feature: no UI, action, navigation or scheduler integration.
- Not a repair path: no delete, download, re-import, mapping or metadata write.
- Not sync: no wire, entity or anchor change; no SDK private SQL.
- Catalog rows inserted or deleted *while a step runs* are outside the tested
  scope; the scan is a keyset snapshot and new rows appear only if they sort
  after the cursor.
- Performance and accessibility budgets for any host surface are not claimed.
