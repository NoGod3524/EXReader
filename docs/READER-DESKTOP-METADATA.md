# Desktop typed metadata adapter

Accepted source: `17eacd2de77dbf5b75bfab68ab2677174ebc0315`.
Accepted run: [40047847396](https://github.com/NoGod3524/EXReader/actions/runs/40047847396), attempt 1.
Both same-source installed-consumer jobs completed successfully. Completed job
logs and artifact identities are recorded in
[reader-desktop-metadata.json](validation/reader-desktop-metadata.json).

| Platform | Job | Source / protocol / sync / projection / typed commands | Adapter |
| --- | --- | --- | --- |
| Linux | 120733531257 | 77 / 59 / 33 / 32 / 33 | 29/29 |
| Windows | 120733531036 | 76 / 59 / 33 / 32 / 33 | 29/29 |

The original product catalog ctest also passed on both platforms. The two
nonempty, unexpired same-source artifacts have verified API SHA-256 digests:
Linux `12541483605` (3,215,671 bytes), Windows `12542745017` (4,591,954 bytes).
Logs confirm `accepted=true` for every suite and the 29 unique adapter checks.

The independently installed C API is in
`apps/reader/desktop-metadata/include/reader_metadata.h`; its target is
`EXReaderDesktopMetadata::reader_desktop_metadata`, version 0.1.0.
It depends on the existing installed commands, revisions and product catalog
packages. All use the same product SQLite provider. The frozen SDK eight trees,
product `001_catalog.sql` and schema-v1 revision wire are unchanged.

## Host contract

The creating host worker owns both catalog and revisions handles. GTK can keep
the owner on its existing worker; Windows can open and close an owner within
each serialized worker job. No native handle crosses to the UI thread.

Preparation copies product metadata and the complete observed head set into an
immutable snapshot. A second observation checks that heads and graph did not
change across the metadata read. A concurrent change asks the host to refresh;
concurrent heads, missing parents and blocked restoration remain explicit.
Group views retain deleted metadata; membership views distinguish an absent
join from retained tombstone history. UI code copies the view and keeps the
native snapshot on its owner until it submits or closes that editor.

Staging allocates stable revision and entity IDs before any producer runs and
durably publishes one bounded pending sidecar. It records the original heads,
all typed fields and the product-path binding. A pending intent cannot be
replaced by another action. Atomic publication uses a flushed temporary file,
rename and Linux directory synchronization; Windows requests write-through.

`apply_pending` commits through the existing typed producer and keeps the
intent. `finish_pending` precisely retries the same intent, then clears it.
After process death, the host reopens and replays the original IDs, fields and
heads. An old exact-ID retry does not reapply metadata or requeue an acknowledged
revision. Cleanup refusal after a successful commit reports
`COMMITTED_PENDING_CLEAR` and `committed=1,pending=1`. Explicit abandonment is
allowed only while that revision has not committed.

Book bootstrap remains explicit. The host verifies exact retained original
format, SHA-256 and size through the public SDK. `stage_bootstrap` preserves
the prepared product title, author, favorite and NFC sort title, including
existing user edits. A practical editor flow is to bootstrap before accepting
new user input, finish it, prepare again, and then save the user's edit as one
typed transaction. Existing committed SDK originals and local mappings are
retained when later product work fails.

## Cloud checks

`reader-commands.yml` preserves the original source, protocol, sync, projection
and 33 typed-command checks, then builds the installed adapter and independent
C/C++ consumers. The adapter adds 29 checks, including:

- a single verified native product SQLite provider and C ABI consumption;
- product metadata preservation during explicit verified-source bootstrap;
- favorite, nested shelf, tag, series and three membership mutations;
- stale expected-head refusal with zero metadata/history/outbox writes;
- concurrent native writes while preparing coherent metadata/head snapshots;
- actual process termination before commit and after commit before acknowledgement;
- precise old-ID replay after a newer edit, without metadata replay or requeue;
- owner/thread exclusion, pending replacement refusal and safe abandonment;
- bounded, corrupted, truncated and wrong-database journal refusal;
- actual cleanup denial that preserves the committed result and retry intent.

The initial source `4ae0f7e6f763d6e9f4d5814f1c20bb870003d497` passed
[40047257430](https://github.com/NoGod3524/EXReader/actions/runs/40047257430)
on Windows and Linux with the original suites plus 28 adapter checks. Source
`78a4195cc603a772badb9d6847467cd3d1b8bf8a` added the concurrent snapshot
guard and its 29th check, passed on both platforms in
[40047579022](https://github.com/NoGod3524/EXReader/actions/runs/40047579022).
The final candidate additionally rejects missing book metadata pointers before
staging; its installed C consumer verifies that rejection without writes.
Each run remains evidence only for its own source.

## Scope

This package supplies the native desktop adapter. It performs no network work
and changes no SDK database. Original-source verification is a host obligation;
the native consumer's proof fixture does not grant SDK verification acceptance.
Desktop UI wiring, mobile acceptance, remote projection and product-wide
completion remain separate work. Builds and tests run only in GitHub Actions;
local operations are source/document and Git work.
