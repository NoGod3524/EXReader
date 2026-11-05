# D03: original-file export (0.1.0)

Independent opt-in static C ABI package: `apps/reader/original-export`. It is not
added to the SDK or reading defaults. It consumes only installed SDK 3.40.0/ABI1.
Fixed host start: `a826a65c9c66e43620eff61b49cb79f941a3c953`; SDK:
`9854061be331fe603a1822d9b2b36ee357154927`.

## Contract

Install with a separate CMake build and SDK prefix; downstream uses
`find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)` and links
`EXReaderOriginalExport::reader_original_export`. Public header:
`<reader_original_export.h>`. See the independent C and C++ consumers under
`tests/reader_original_export/consumer`.

The host lends its existing `exr_library` and its actual single-owner gate.
`roe_create` binds the creating thread and rejects a second exporter for that
pointer. `roe_run` is synchronous, takes 1–100 explicitly selected IDs, and
holds one owner lease until all opened sources are released. Host gate callers
must refuse direct SDK operations during callbacks. Reentry and wrong-thread
export/destruction return `ROE_OWNER`; callbacks occur only after SDK calls
return. The library must outlive the exporter. Callback functions must not
throw. The module catches implementation exceptions at its C ABI boundary.

Original bytes come from `exr_library_source`, streamed using one 64 KiB buffer;
SHA-256 is computed from those actual bytes, then the flushed staged file is
read back and hashed before publication. The SHA implementation is a local
MIT-licensed copy of the existing thumbnail component's SHA-256 primitive,
not a second SDK/parser. Format comes from `exr_library_books`. SDK 3.40 lacks
a per-ID format lookup. Its public bookshelf snapshot enumerates **all matching
library rows** and allocates an `exr_book` array plus copies of title, author,
and tags for each. At the frozen SDK source, `src/base_internal.h` defines
`EXR_MAX_ITEMS` as **4,194,304**; `exr_library_books` returns `EXR_MEMORY` when
that count/allocation guard fails (`src/library.c`). This is the implementation
limit of the frozen public API, not an O(100) metadata-memory bound or a small
aggregate byte cap. Metadata memory grows with the entire library and its
strings and can exhaust memory before that count. No private header or SQL is
used by the module. The **64 KiB claim applies only to the original-byte copy
buffer**, not total process memory, SDK metadata, source handles, or receipts.
A bounded per-ID public format getter is an SDK gap for future integration.
No original is loaded as a whole-book heap buffer.

Before any file creation, every selected source is opened and its declared
size checked. Defaults: 128 MiB/book, 512 MiB/batch. A caller may lower both or
raise the batch to at most 1 GiB; the book cap stays 128 MiB. Selection includes
duplicates in the byte budget. No SDK import limits or behavior change.

## Files, publication, cancellation

Destination must be an existing absolute UTF-8 directory (at most 3500 bytes),
without `.`/`..`, symlink/reparse components, UNC/device namespace, or unsafe
components. The host keeps it stable and controls concurrent modifications
throughout the call; no secure guarantee is made against a hostile process
renaming destination ancestors or racing a temporary entry. POSIX operations
are relative to a pinned no-follow directory FD; Windows pins directory
handles without delete sharing and rejects reparse points. Source book titles
and remote filenames are never used. Hash names are `<sha256>.<format>`.
Display mode accepts only a 1–64-byte ASCII letters/digits/underscore/hyphen
slug, rejects reserved device names, and appends `--<sha256>.<format>`.

Temporary creation is exclusive. Each file is flushed/fsynced and staged bytes
verified, then published without replacement (POSIX `linkat`; Windows
`MoveFileExW` without replace and with write-through). Existing targets count
as duplicates only if a non-aliased regular file has matching actual size and
SHA-256. Symlinks, reparse files, directories, hardlink aliases and other bytes
are conflicts. No target is overwritten.

`roe_result` is owned, including inline paths, and released only with
`roe_result_free`. Each item records status, committed/created/durable flags,
format, original SHA-256, original byte size, output path and cleanup receipt.
An output path may be a proposed path on failure; only `committed` asserts its
publication. Empty hash means the source was not fully read and verified.
Cancellation stops uncommitted items. Already published files remain; this is
not a batch transaction. A failure does not erase earlier item receipts.

`ROE_STAGED`/`ROE_COPYING` callback receipts include the exact temporary path;
the host can persist those before returning for crash recovery. Normal failure
attempts cleanup and retains `cleanup_pending` plus the real path if cleanup
fails. Process death cannot run cleanup: host-journaled orphan receipts remain
owned by that host, not silently removed by a later export. Retry opens a fresh
SDK owner and exports again; the fixture exercises actual process termination,
explicit orphan cleanup from its receipt, and successful reopen/retry; a
second real termination after publication verifies duplicate-safe reopen. The
module does not claim unattended orphan discovery or a global transaction.
A host must verify its receipt still refers to its temporary before deleting
it. There is no completion manifest, network, OS share registration, shell or
application launch, database copy, private SQL, or SDK/product mutation.

## Validation scope

All compilation, fixtures, test execution, syntax interpretation and artifact
processing run only in `reader-original-export.yml` on GitHub Actions. Three
native desktop jobs install the frozen SDK and independent package, then
compile C/C++ consumers from a fresh directory using installed headers/targets.
Nine format originals are independently byte-compared. Public SDK snapshots
cover original bytes, notes and progress; real product revision history and
outbox snapshots and raw DB hashes cover the no-write invariant. Source
invalidation is a separate explicit fixture mutation through another public
SDK owner, outside the invariant window.

The evidence job authenticates completed/success producer jobs, same
source/run/attempt, unique nonexpired artifact IDs/names, API digest, downloaded
ZIP length/hash, unique ZIP/JSON members, exact named cases and actual static
module/consumer/output/original bytes. Rejection tests mutate real reports and
binary/original/history members, and exercise duplicate/missing ZIP/JSON data.
POSIX has a real mid-stream `RLIMIT_FSIZE` write failure. Windows has an actual
locked-temporary cleanup failure and conflict publication failures; Windows
mid-stream disk-full/fsync fault injection is **UNAVAILABLE**, not a mock pass.
No system-share UI or six-device connection claim is granted.

## Recorded native evidence (2026-10-25)

Tested source: `9fdcb28dcf5bc6fe93618d260441ad483d88bc4d`; tree
`09f179920364bf658705377ce68d0f528787da69`.
[Run 40171470925, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40171470925)
completed **success**: Linux job `121103001763`, Windows job `121103001812`,
macOS job `121103001681`, strict evidence job `121103815311`. Each platform
passed 33 named consumer checks; the verifier rejected 15 mutations per
platform (45 total). Actual nine-format outputs were bound to frozen fixture
bytes, and actual installed static archives/C/C++ consumers were ZIP/hash-bound.

The initial source `a64e239a8554aa08e5e1537ba636abbd3a2c70f6` also passed
[run 40170953790/1](https://github.com/NoGod3524/EXReader/actions/runs/40170953790),
30 checks/platform and 15 verifier rejections/platform. Both runs remain
retained. No observed CI failures or original assertions were removed.

This document and `docs/validation/reader-original-export.json` are the only
changes in the final evidence-only `[skip ci]` child commit. The exact evidence
HEAD is returned separately in the handoff (a commit cannot contain its own
SHA). The JSON records every artifact ID/name/size/digest/expiry, actual binary
identities, jobs, named cases and remaining gaps. Producer ZIPs were downloaded
and rehashed in Actions; the terminal evidence ZIP has API identity metadata
only, explicitly distinguished in the record.

The measured desktop package capability passed; full D03 acceptance remains
for root review of Windows mid-stream fault-injection UNAVAILABLE, bookshelf
snapshot memory, stable host-controlled destination and explicit orphan
receipt boundaries. No share UI, six-device, host-integration or physical
power-loss claim is made.
