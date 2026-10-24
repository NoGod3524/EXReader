# Shared desktop metadata owner

`EXReaderDesktopMetadata::reader_desktop_metadata` is an installed C API for
the Windows and GTK host workers. It uses the installed typed commands,
revisions and product catalog packages, including their single product SQLite
provider. It has no SDK, UI or network dependency.

Configure this directory after installing `EXReaderCommands` and its existing
dependencies. A separate consumer uses:

```cmake
find_package(EXReaderDesktopMetadata 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(host PRIVATE EXReaderDesktopMetadata::reader_desktop_metadata)
```

Keep `reader_metadata_owner` on its creating worker. GTK may retain it on the
existing worker; Windows can open and close one inside each serialized job.
The native handles and snapshots remain on that worker. Copy the snapshot's
view strings, fields and state before presenting them on a UI thread.

The host flow is:

1. `reader_metadata_open(product_path, pending_path, ...)` acquires the private
   pending-file owner lock and opens both native handles on that worker.
2. At startup, inspect any existing pending command. Replay or explicitly
   abandon an uncommitted intent before accepting another edit.
3. `prepare_book`, `prepare_group` or `prepare_membership` copies the current
   product metadata and complete head set. Heads/graph are checked before and
   after the metadata read; a concurrent change asks the host to refresh.
   Conflicts and missing book bootstrap are returned explicitly. Preparation
   does not choose a conflict head or project received remote metadata.
4. `stage_*` receives that same snapshot and the typed user edit. It allocates
   both stable IDs for a new group and persists all typed fields, original
   expected heads and identities before calling any producer. One pending
   intent cannot replace another. The private sidecar is limited to 128 KiB;
   it has lengths, a format marker, a checksum and a product-path binding.
5. `apply_pending` calls the existing producer and retains the intent after
   commit. `finish_pending` precisely reapplies/verifies that same intent and
   then removes it. A host may call `finish_pending` directly for the normal
   submit-and-acknowledge path. After process death, replay uses the saved
   payload and original heads; it never reconstructs them from current rows.

The journal publishes through a flushed temporary file and an atomic rename;
Linux also synchronizes its containing directory. The Windows rename requests
write-through. A commit followed by cleanup refusal returns
`READER_METADATA_COMMITTED_PENDING_CLEAR` with `committed=1,pending=1`.
Cancellation of a reading/search job must not discard an accepted metadata
intent or turn this committed result into a cancelled operation.

Legacy book bootstrap is a separate explicit action. First the host verifies
the retained original through the public SDK, then passes its format, SHA-256
and length to `stage_bootstrap`. That stage preserves the prepared product
title, author, favorite and NFC sort title. Ordinary book edits and memberships
return `NEEDS_BOOTSTRAP` until retained book history exists. The adapter does
not verify original files or extend a transaction into the SDK database.

The existing `reader-commands.yml` retains its source/protocol/sync/projection
and 33 typed-command checks, then builds this installed module and independent
C/C++ consumers. `tests/reader_metadata/check_metadata.py` checks the actual
native provider, typed mutations, expected-head refusals, exact replay,
concurrent snapshot reads and real process kills before and after commit.
All builds and execution belong to Actions; acceptance is recorded only after
the complete same-source Windows/Linux run succeeds. Desktop UI integration
and source verification remain separate host acceptance work.
