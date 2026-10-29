# Windows product migration: next implementation package — 2026-10-29

This is source-only preparation against
`5db9c2c0b574b0e63675a38b0653f3a9bdd2cb1c`, which includes the POSIX
existing/new-target recovery implementation from `acf892d4fe852dda4ed668589af53f7b3694f679`.
The Windows 67-group continuation is a prerequisite, not the product port.
No product source is changed by this document.

## Exact current entry and owner chain

| Existing code | Current behavior | Windows integration seam |
|---|---|---|
| `extras/migration/src/lm_main.c:2813` (`real_main`) | `ln_route`, then `lr_gate`, run before target SDK access | Keep this pre-open gate; add a real Windows `lr_*` implementation rather than bypassing it |
| `lm_main.c:2166` (`prepare`) | `lr_prepare -> lr_opening -> lr_owner_attempted -> exr_library_migration_open -> lr_owner_started -> lr_compare_restore` | Same real SDK writer must remain alive for full baseline/public projection comparison and importer work |
| `lm_main.c:2184` | Read internal ledger; validate/load existing `.legacy-map.json` | Preserve both exact mirror and ledger lineage; missing/foreign sidecars remain explicit outcomes |
| `lm_main.c:2374` | Original `process_book/process_note` results, then `verify_library` | Use the actual importer, full original counts and unresolved selectors, never the title-only qualification proxy |
| `lm_main.c:2382` | ledger_set, `lr_publish`, literal migration_finish(COMMIT), `lr_ack`, SDK close, `lr_complete` | No success before actual commit, observed child completion and final evidence/mirror checks |
| `lm_main.c:2009` (`cleanup`) | On uncommitted owner: literal rollback request, SDK close, `lr_owner_closed`; retain all evidence | Same on Windows; rollback status is not proof of physical cleanup or authority to erase evidence |
| `examples/reader.c:6264` | Windows host initializes mutex and immediately opens its persistent SDK library | Place pending-recovery admission before this open; current ordinary open can itself upgrade an old database |
| `examples/reader.c:6124` (`host_cleanup`) | Wait host job, clear sessions/frames/records, stop account, shut down Wave3, close SDK, then release profile locks | Reuse this ordering in a dedicated suspend/reopen path; keep product/profile locks across migration and reopen |

The host's source/document ownership is real:
`apps/reader/desktop/windows_source.inc:19` creates fixed/bounded/reflow
sources from `g.library`; `windows_catalog.inc:152` and
`windows_import_organize.inc:135` use `g.library_lock`. A mutex alone does
not release the persistent SDK library, retained source handles or font leases.
The profile locks are acquired before ordinary SDK open at
`examples/reader.c:6244–6255` and currently live until `6172–6173`.
Do not release them during the migration handoff.

## Blocking gaps before production enablement

1. **There is no Windows recovery implementation yet.**
   `lm_recovery.c:59–73` provides only `recovery-platform-unqualified`
   stubs. `lm_new_target.c:40–54` also refuses Windows. The standalone
   CMake file builds/installs the real recovery worker only in its non-Windows
   branch. A green test adapter cannot satisfy these missing calls.

2. **The persisted identity formats differ.**
   `lm_mirror_file.identity[33]`, POSIX recovery record IDs and `ln_prefix`
   encode device+inode; the Windows adapter requires volume64+FileID128,
   48 hexadecimal characters plus NUL. Do not truncate to the old field or
   silently reinterpret existing v1/v3 records. Introduce a separate Windows
   protocol/version and full 49-byte IDs in its own opaque state; reject old
   unknown pending evidence. The SDK/ABI and old mirror formats remain frozen.

3. **Durable mirror publication is not supplied by the adapter.**
   `wr_rename_new` supports no-replace publication inside one owned root.
   The production sidecar lives beside the public library, outside the private
   recovery root, and can already exist. The port needs an explicit
   PREP/archive-original/publish-new/ACK transition with retained copies and
   exact original absence/identity, all while the same SDK owner is held.
   Never substitute overwrite/copy-delete or unpin an active namespace.
   Admission must prove the public parent custody and native same-directory
   operation; a normal inherited Windows profile ACL is not automatically
   the adapter's explicit protected private-root ACL.

4. **Worker liveness must be part of the protocol.**
   The current `rscan` uses posix_spawn, flock/OFD-style lease inheritance,
   closefrom/CLOEXEC and waitpid. Windows must use the already qualified
   suspended process + explicit handle list + supervisor-owned Job Object,
   anchored slot IDs and pre-I/O envelope rechecks. A free slot or an orphaned
   complete result cannot manufacture this invocation's wait proof.
   Build a UTF-16 wmain worker entry with bounded strict conversion, source
   hash binding, a single installed SDK/SQLite provider and real full scanner.
   Do not install the test probe as the production worker.

5. **No directory-fsync equivalence has been established.**
   FlushFileBuffers/file-write-through, actual visibility, actual directory
   flush result and retained uncertainty are different facts. Name the
   measured Windows durability profile in the result; any unsupported edge
   must retain/refuse. This package cannot grant physical power-loss safety.

## Smallest next production slice

Implement **existing-target Windows recovery only**, behind a distinct
candidate build/feature switch. Keep Windows `--create-target` refused until a
separate private-import/seal/no-replace publication port is actually verified.
This is a deliberate staging boundary; neither F12 nor full P0 closes on it.

Minimum owner/file changes:

- `extras/migration/CMakeLists.txt`: choose a new
  `src/lm_recovery_win32.c` for Windows `lr_*` calls, link
  `lm_recovery_win32_platform.c` only to the explicit candidate, build/install
  the real Windows worker with the exact existing SDK. Leave both old CLI
  targets and POSIX selection unchanged.
- New `extras/migration/src/lm_recovery_win32.c`: implement every declared
  `lr_*` entry with a Windows-specific canonical persistent format,
  full FileIDs, permanent shared barrier, lifetime lease, full chain validation,
  same-owner R comparison and C-successor lineage. No generic success stubs.
- `extras/migration/src/lm_recovery_worker.c` plus a small Windows worker
  entry/transport file: share the real supported-schema scanner and public
  projection traversal; bind the exact request/output/target/producer and
  inherited liveness handle before SDK I/O.
- `extras/migration/src/lm_main.c`: preserve the owner chain above; only add
  Windows cancel/status plumbing and literal JSON outcomes needed by the host.
  Keep source transaction/ledger/mirror semantics and original importer counts.
- New `apps/reader/desktop/windows_migration.inc`, corresponding state header
  and CMake feature wiring, with narrow calls in `examples/reader.c`:
  startup pre-open admission and a scheduler-owned suspend/migrate/reopen flow.
  No migration work on the UI thread and no new private SDK entry points.

A dedicated host flow must stop accepting new jobs, settle commit barriers,
cancel/wait account and ordinary jobs, retain a public-state selection snapshot,
release retained reading sources and Wave3 font leases, then close the SDK.
It must retain product/profile locks, launch the exact installed candidate,
observe literal result plus successful wait, and reopen/rebuild shelf metadata
only after admission permits it. Failure/cancel/unknown COMMIT shows a retained
pending state and explicit retry using the original bound pack. Closing the UI
or a test-only callback is not a substitute for this production lifecycle.

## Mandatory acceptance for that slice

- Re-run the unchanged 43 preflight + 24 native groups and exact installed
  single-provider/map checks on the new product source; retain the original
  failed runs and their raw tracebacks.
- Add actual importer schema6/7 × DELETE/WAL runs with original book/note
  counts, covers/source bytes, bounded EPUB selectors, unresolved cases and
  exact internal ledger + `.legacy-map.json` compatibility.
- Preserve the original 65 scenario, 31 review and 17 browser contracts as
  separate reports. An intentional unsupported profile is a named refusal,
  never an invented pass or a lowered case count.
- Kill/cancel at opening, baseline comparison, mirror preparation/publication,
  COMMIT-before-ACK and ACK-before-final-sync; independently inspect fresh
  current state. Later ordinary writers and uncertain COMMIT cannot trigger
  blind replay/restoration. Original v3 pending evidence remains untouched.
- Run a real host with an active borrowed source/font lease and queued job,
  perform suspend/close/migrate/reopen, verify the same book/position, and prove
  competing host/migrator exclusion through all source-release/SDK-close edges.
  Exercise actual process restart, failed recovery and successful explicit retry.
- Record Windows new-target, real-device deployment and physical power-loss
  boundaries separately. Full P0/F12 and the remaining 11 joint-delivery items
  remain unaccepted until their actual gates pass.

No catalog update or extra test run is authorized by this source-only plan.
