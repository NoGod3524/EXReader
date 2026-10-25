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

## Original J11 acceptance

`.github/workflows/reader-explicit-conflict-actions.yml` runs on Linux,
Windows and macOS: protected-tree and allowed-path guards against
`f43baf9182d75907c0cb5d6f77048f27bca8c950`, installed product provider
verification, 29 named checks in `check_conflict_actions.py`, and a strict
summary job requiring every platform to report the same SHA and check list.
Covered: real two-end concurrency, late parent, tombstone then put/explicit
restore, 32/33 heads, foreign revision after prepare, retry, cancellation and
native transaction failure (outbox trigger) with history and schema preserved
and no SDK files. Not covered: UI, SDK verification, simulators/devices, audio.

## T02 targeted review (2026-10-25)

The review starts at `37fdc830d75eee8590120d52d4d881102e0d9dc4` on
`codex/dot-conflict-actions-review`. The original tested source is
`be093a95d5eb6beceb23ce5ba76cac3a79610555`; its delivered HEAD differs only
in `docs/validation/reader-explicit-conflict-actions.json`. GitHub API review
confirmed run `40140153887`, attempt 1, all three native consumer jobs and
the original summary completed successfully. Those historical results remain
attributed to that source, not to this review's changes.

The implementation was followed through the installed C/C++ consumers,
`prepare`/`resolve`/`close`, public revisions/commands/metadata contracts, and
the native `reader_revision_local_project` transaction. No conflict module
source change was justified: complete observed parents reach the transaction;
exact retained retries precede the head comparison; new commands compare
current heads inside the transaction; dependency activation failures roll
back history, projection and outbox. Reading anchors remain display-only.

The confirmed defect was the original summary's evidence trust boundary:
matching JSON SHA, platform and check arrays did not authenticate actual
upstream jobs, run attempt, ZIP identity or the executed consumer binaries.
This review replaces that summary with API-authenticated completed/success
jobs, source/run/attempt-specific unique artifact names, nonexpired API
ID/size/digest checks, Actions-only ZIP SHA/size recomputation, duplicate ZIP
member/report and duplicate JSON-key rejection, and hashes of the actual
installed C/C++ executables and installed package files. Downloaded ZIPs are
not extracted or executed. The installed package SHA hashes its sorted
path/role/byte/SHA manifest. Every platform and the summary enforce the review
base, frozen SDK and unchanged product provider/schema paths.

All original 29 named behavior checks are retained. Three targeted regressions
add changed-field collision on the same snapshot/stable ID, snapshot view
lifetime after owner close with cross-worker release, and membership restore
refusal until both the group and book have been explicitly restored. The
strict verifier has executable rejection fixtures; these test verifier
behavior, not substitute platform acceptance.

### Verified T02 acceptance

Tested source: `f800907fac3097fb99e3ea52e8b8066c4c23f499`.
[Run 40164827613, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40164827613)
is completed/success. The independent installed consumers passed all 32 named
behavior checks on Linux (job `121083628879`), Windows (`121083629016`) and
macOS (`121083629051`). Strict summary job `121084471719` passed its 35
verifier cases (one positive, 34 rejections) and authenticated/recomputed all
three actual platform ZIPs and their native consumers/package manifests.

| Artifact | ID | ZIP bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Linux | 12587876434 | 1827222 | `5801cc7dd3030b57eb95647437fef584bf18618745f5ef72ae3e5b0d0ef7bd6b` |
| Windows | 12587816553 | 1882828 | `ba68c3f2752acab176f019cac9fce81783fce7a491873e60059e08a8db65a625` |
| macOS | 12587801883 | 1645112 | `4e8eeeb24ce177e479842173ce79ce4141467acd1658d32878f521864acbce72` |
| Summary | 12588410433 | 5354575 | `965f43f52839168d59c9c58f9480f434b075ce08a9afdde1b34590b71f39392e` |

The API reports all four artifacts nonexpired, expiring
`2027-01-23T05:14:52Z`. The summary artifact retains the three verified original
ZIPs, `summary.json` and `rejection-checks.json`; its own identity is from the
upload/API metadata, not recursive self-certification. Full artifact names,
native C/C++ consumer hashes/sizes, installed package manifest hashes, all
named results and historical failures are in
`docs/validation/reader-explicit-conflict-actions.json`.

No T02 run failed. Original run `40139960162`, attempt 1, at
`00a9b3e01738970a50392077dbae9d11a382b9c9` is preserved: summary job
`121009814018` failed `AssertionError: []` because its report glob found no
files, despite three successful platform jobs. The original successor
`be093a95d5eb6beceb23ce5ba76cac3a79610555` corrected the glob. Neither failure
nor historical artifacts have been removed or relabeled.

This final evidence-only `[skip ci]` commit changes only this document and
the validation JSON relative to the tested source. Source, tests and workflow
remain exactly those exercised above. No local build, test, syntax check,
fixture generation, service, benchmark or artifact processing was performed.

Unchanged scope gaps: no production-host UI integration, SDK original-source
verification, UI desktop controls, simulators/physical devices, accessibility,
performance grant, audio, or durable cross-process retry intent. Native
Windows/Linux/macOS command-line consumers are not UI/device acceptance.
