# Reader bulk organization (J10)

`EXReaderBulkOrganization::reader_bulk` (`apps/reader/bulk-organization`) applies one
explicit organization action to at most 100 selected books: favorite set/clear, and
add/remove for shelf, tag and series. It runs the existing typed commands through the
installed desktop metadata owner (`prepare -> stage -> apply -> finish`). It adds no
schema, wire entity, sync traffic, SDK access or product SQL, and creates no thread.

Fixed start `f43baf9182d75907c0cb5d6f77048f27bca8c950`; branch `codex/reader-bulk-organization`.

## Contract (see `include/reader_bulk.h`)

- **One item, one transaction.** Each book commits or not on its own. A batch is never
  atomic and is never reported as such. Results are per item: `COMMITTED`, `UNCHANGED`
  (already in the requested state; no revision), `CONFLICT`, `DEPENDENCY_DELETED`,
  `MISSING`, `NEEDS_BOOTSTRAP`, `FAILED`, `NOT_RUN`, with `committed`, `created`,
  `replayed`, `conflict` flags.
- **Observed heads and retry ID.** Each item reports the complete head set seen by
  prepare (also for conflicts) and the stable revision ID assigned at stage time.
- **Hard limits.** 1..100 distinct books per request; book key <= 72 bytes; group ID 32
  lowercase hex; head set <= 32; journal <= 512 KiB; ordinal base <= INT64_MAX-100.
- **Memory.** Inputs are borrowed for the call; results go into a caller array
  (`capacity >= book_count`, else `CAPACITY`). Nothing is returned for the caller to free.
- **Threads / reentry.** Open, calls and close run on the worker that created the
  borrowed `reader_metadata_owner`. Callbacks run inside the call and must not use the
  handle or owner. The wrong thread or reentry returns `OWNER`.
- **Cancel.** Polled once per item, before it is prepared, never between stage and finish.
  Committed items stay committed; remaining items are `NOT_RUN`; the journal stays
  resumable (`CANCELLED`).
- **Commit boundary.** An item is committed when the owner's `apply` returns OK.
- **Errors.** Preflight errors (`ARGUMENT`, `JOURNAL_ACTIVE`, `FOREIGN_PENDING`) change
  nothing. Owner failures mid-batch return `METADATA` with the journal kept.
  A pending owner intent not belonging to the batch is never touched (`FOREIGN_PENDING`).

## Recovery journal

A private sidecar (`journal_path`, atomic flushed temp file + rename, CRC-32 checked,
bound to the product database) is written before the first item, after each item is
staged (retry ID + observed heads) and after each commit. After process death
`reader_bulk_resume` replays a staged item from the owner's saved intent with its
original ID and heads, or detects through `reader_revision_get` that it already
committed (`committed=1, created=0, replayed=1`). A finished batch keeps its journal
until `reader_bulk_acknowledge`, so the report survives a crash. `reader_bulk_abandon`
drops an unfinished journal without rolling anything back.

Known narrow window: a kill between the owner's stage and the journal rewrite leaves
`heads_known=0` for that one item after recovery (the owner's own saved intent still
uses the original heads for the commit).

## Host integration example

```c
reader_bulk *bulk; reader_bulk_open(owner, product_path, journal_path, &bulk, &err);
reader_bulk_request req = {sizeof req, READER_BULK_SHELF_ADD, shelf_id, next_ordinal,
                           keys, n /* <= 100 */, {ui, poll_cancel, on_progress}};
reader_bulk_item_result items[100]; reader_bulk_summary sum;
st = reader_bulk_run(bulk, &req, items, 100, &sum, &err);   /* on the owner worker */
if (st == READER_BULK_OK || st == READER_BULK_CANCELLED) show(items, sum);
reader_bulk_acknowledge(bulk, &err);                         /* once shown */
/* at startup: if (reader_bulk_inspect(...) == OK) resume or abandon first */
```
`tests/reader_bulk_organization/consumer/` holds the installed C and C++ consumers.

## Acceptance

`.github/workflows/reader-bulk-organization.yml` (Linux, Windows, macOS) builds the
unchanged product chain, installs the package, compiles consumers from install trees only,
and `check_bulk.py` judges with an independent sqlite3 reader: 2,202 books in batches of
<=100, mid-batch conflict and deleted dependency, repeat/retry, missing/legacy books,
cancel/resume/abandon, real process kills before and after commit, damaged journal,
untouched unselected books, history and outbox. `check_artifacts.py` verifies the
same-run artifact IDs, bytes, SHA-256 and reports. Scope: native module only; no host UI,
no real account, no audio, no device or product-performance claim.
