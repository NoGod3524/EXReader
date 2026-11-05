# Explicit conflict selection and merge commands (J11)

`EXReaderConflictActions::reader_conflict_actions` is an independently
installed C API (C++17 implementation) over the unchanged `EXReaderCommands`
0.1.0, `EXReaderRevisions` 0.3.0 and the single product SQLite provider. It adds
no schema, wire parser, SDK dependency, UI or network code. Source:
`apps/reader/conflict-actions`; installed consumers and acceptance:
`tests/reader_explicit_conflict_actions`.

```cmake
find_package(EXReaderConflictActions 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(host PRIVATE EXReaderConflictActions::reader_conflict_actions)
```

## Flow

1. `reader_conflict_open(product_path)` opens a private `reader_revisions`
   handle on the creating host worker.
2. `reader_conflict_prepare(target)` returns an immutable snapshot of the
   **complete** head set. Each head carries the revision store's own validated
   `reader_revision_head`/`reader_revision_info` and the exact retained wire
   bytes (copied with `reader_revision_get`, never re-parsed here).
3. The host shows the heads and collects the user's explicit typed fields and
   operation (`put`, `delete` or `restore`).
4. `reader_conflict_resolve_book|group|membership` passes **every** snapshot
   head as `expected_heads` to the existing `reader_command_apply_*` function.
   Exactly one new revision whose parents are all observed heads is created
   in the existing native metadata+history+outbox transaction.

No head is chosen by clock, ordering or content, and none is dropped. The
module never edits stored or received revisions.

## Contract

| Topic | Rule |
| --- | --- |
| Targets | Book (`book_key`), group (`kind`+`id`), membership (`kind`+`group_id`+`book_key`) are resolved separately. Progress and annotation targets are display-only. |
| Memory | The snapshot owns every string/array in its view until `reader_conflict_snapshot_free` (any thread). `result->command` copies IDs by value. |
| Threads | open, prepare, resolve and close use the creating worker and are not reentrant (a cancel callback that calls back returns `OWNER`). Metadata owners are separate handles; SQLite arbitrates. |
| Bounds | At most 32 heads (one merge can name at most 32 parents) and 8 MiB of wire bytes per snapshot; more returns `LIMIT`, never a truncated set. |
| Consistency | Heads are read, each retained wire copied, then heads read again; a change is retried three times, then `STALE`. |
| Cancellation | `reader_conflict_cancel` is polled before reads, between head copies and once immediately before the typed command. It is never polled after that call begins; a committed transaction cannot be cancelled. `CANCELLED` always means zero writes. |
| Commit boundary | The single `reader_command_apply_*` call. `result->committed` is 1 only after it commits (or after an exact retained no-op). |
| Stale heads | A head set that differs from the snapshot at commit time is refused by the native transaction; the module reports `STALE` after verifying the changed set. Nothing is written. |
| Errors | `reader_conflict_error` keeps a fixed message plus the native `reader_revision_error`/`reader_command_error`. Assigned revision/entity IDs stay in the result on failure. |

## Explicit rules checked before any write

* `INCOMPLETE`: a missing or foreign parent exists. Heads are still displayed;
  resolution waits for the parent, then `prepare` again.
* `NOT_CONFLICT`: one complete safe head (use the ordinary edit path), or a
  delete when every head is already a tombstone.
* `RESTORE_REQUIRED`: any head is a delete or blocked behind one; a `put`
  cannot be implicit. `NOT_TOMBSTONED`: restore needs a directly observed
  delete head. Delete, restore and put for a book, a group and a membership are
  separate entities: tombstoning/restoring a group never cascades.
* `IDENTITY`: the typed command names another entity or kind.
* `READING_HOST`: reading anchors (progress, annotation) are shown with their
  exact wire; the host resolves them, this package never navigates or resolves.
* `NEEDS_BOOTSTRAP`: membership without verified retained book history.

## Retry

Supply a 32-hex stable `revision_id`. After an uncertain result, retry **with
the same snapshot object and fields**: the native layer returns an exact no-op
(`committed=1`, `created=0`) and does not requeue. After `STALE`, prepare again
and reuse the same ID. Reusing a committed ID with a fresh snapshot is refused
(the new parent set would contain the revision itself). A durable cross-process
retry intent (like the metadata owner's pending file) is **not** provided by
this package; a host that needs it must persist the observed `head_ids`,
`revision_id` and typed fields itself.

## Installed integration example

`tests/reader_explicit_conflict_actions/consumer/api.c` is the C example built
only against the installed headers: open, prepare a tag with two heads, inspect
the view, apply an explicit `put`, free and close. `main.cpp` is the C++
driver used by the acceptance script (two real client databases exchange
revisions with `reader_revision_receive`).

## Acceptance

`.github/workflows/reader-explicit-conflict-actions.yml` runs on Linux,
Windows and macOS: protected-tree and allowed-path guards against
`f43baf9182d75907c0cb5d6f77048f27bca8c950`, installed product provider
verification, 29 named checks in `check_conflict_actions.py`, and a strict
summary job requiring every platform to report the same SHA and check list.
Covered: real two-end concurrency, late parent, tombstone then put/explicit
restore, 32/33 heads, foreign revision after prepare, retry, cancellation and
native transaction failure (outbox trigger) with history and schema preserved
and no SDK files. Not covered: UI, SDK verification, simulators/devices, audio.
