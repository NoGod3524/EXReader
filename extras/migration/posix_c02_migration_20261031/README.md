# Synchronous POSIX C02 migration owner

This standalone Linux/ext4 and macOS/APFS command uses the installed frozen SDK3.42 and the existing ABI2/ABI3 controller. It imports and proves a private image synchronously in its own process. It launches no C01 workers and changes no frozen SDK/C01 source.

The independent authority is always pc02_user_authority(): the passwd home/.exreader-c02-admission configuration. It is never taken from a migration package, environment override or CLI parameter. Explicit SDK-backed exreader-c02-admission create/enroll is required. Existing C01 markers/locks remain untouched and cause refusal.

Build with absolute EXR_SDK, PC02_SDK_PREFIX, WH_PREFIX and WH3_PREFIX plus PC02_BUILD_SOURCE/RUN/ATTEMPT. The build writes pc02-provider-inputs.txt and embeds its source hash identity. Normal installation includes only exreader-c02-migrate; explicit Actions controls are never installed. The transformer reuses process_pack_rows from lm_main.c without its production legacy CLI or C01 worker path.

Commands:

- exreader-c02-migrate migrate /absolute/library.sqlite /absolute/input.exrpack [--allow-partial]
- exreader-c02-migrate recover /absolute/library.sqlite
- exreader-c02-migrate verify /absolute/library.sqlite /absolute/input.exrpack

All actual SDK owners and source borrows close before member publication/terminal proof. Source DB/mirror/pack bytes are hashed from actual descriptors. The pack is independently copied into a reserved private object before INPUT; the old DB is copied only after durable PENDING. Original DB/mirror native IDs and complete bytes survive publication in retained sibling objects. PREPARED binds the exact closed, independently SDK-verified pair. Recovery uses only exact original descriptors, registered object IDs, complete canonical journal records, protected floor/head and fresh actual SDK proof.

## Canonical INPUT and PREPARED

Every field below has byte alignment1: char/byte arrays only; wire sizes are static assertions. Strings occupy fixed-size NUL-terminated buffers and unused bytes are zero. Native IDs are device/inode u64 little endian. A file is89 bytes: nativeID16, byte length u64, lowercase SHA64 plus NUL.

INPUT is13844 bytes:

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 8 | PC02IN01 |
| 8 | 296 | frozen wh_binding fields |
| 304 | 325 | frozen wh_gates fields |
| 629 | 4096 | original library absolute path |
| 4725 | 4096 | original external pack path |
| 8821 | 4096 | fixed independently configured authority |
| 12917 | 49 | random token48hex plus NUL |
| 12966 | 128 | two reserved stage basenames64 |
| 13094 | 128 | two retained basenames64 |
| 13222 | 64 | reserved private journal directory basename |
| 13286 | 64 | reserved private pack basename |
| 13350 | 89 | original DB |
| 13439 | 89 | original mirror, zero bytes if absent |
| 13528 | 89 | original external pack |
| 13617 | 89 | retained private pack copy |
| 13706 | 32 | two stage native IDs |
| 13738 | 16 | private journal directory native ID |
| 13754 | 88 | original grant gen8/seal64/targetID16 |
| 13842 | 1 | original mirror present:0/1 |
| 13843 | 1 | allow-partial:0/1 |

Original grant, original target, generation, input SHA and manifest reconstruct the exact canonical native B seal. This is checked during recovery, including after a complete C/Binding update.

PREPARED is251 bytes: magic PC02OUT1 at0, original INPUT payload SHA65 at8, two exact prepared file89 values at73. It is inside the native immutable metadata envelope; no temp is promoted into it.

## Actual journal and production floor

Directory nativeID comes from INPUT, mode0700. Final ACK names are exactly ack-001..ack-256, no holes/aliases. Unique .pending-PID-SERIAL files are mode0600, never promoted by recovery and retained as failure evidence.

ACK is296-byte header + canonical line1..2047 bytes + seal64. Header: PC02ACK1 at0, actual selfID16 at8, ordinal u64 at24, manifestSHA64 at32, INPUT SHA64 at96, native B seal64 at160, line length u64 at224, canonical lineSHA64 at232. The line starts296; footer is SHA256(header+line) as64 lowercase hex bytes. The whole raw ACK SHA includes the footer. Every read independently checks actual fstat identity, complete bytes/size and canonical frozen FSM history.

Actual ACK O_EXCL temp write/fsync/readback precedes atomic NOREPLACE final publication+directory fsync+readback. Then production FLOOR352 binds canonical lineSHA, actual ACK nativeID16 at272 and whole ACK rawSHA64 at288. Every prior floor must use352; the old272 component format is explicitly refused by the production journal. Independent committed head and envelope layouts remain described in ../posix_c02_admission_20261031/MIGRATION_PROTOCOL.md.

A complete final ACK is always observed, including before its floor commit. Only explicit fresh exact recovery catches floor/head up through that already proven ACK history. Ordinary append requires exact old tip and old floor. No completed ACK or head record is discarded to obtain an older valid prefix.

## Qualification batches

The Actions workflow retains the original run_cases.py SHA and all65 historical cases with explicit LM_HISTORICAL_TEST_BASELINE=ON. Those unsafe old behavior controls cannot be installed. Default old CLI builds reject mutation before SDK/lock/break-lock and hold fixed-authority shared custody throughout read commands.

The first actual owner batch has36 named SDK/native cases: complete data and source annotations, second generation, absent mirror, no automatic unregistered adoption, all old write entrypoints, all full-record state/member/metadata/head/ACK process cuts, exact original preservation, lost terminal retry, temp non-promotion, complete ACK before floor, native ID replacement, holes and protected old-tip rollback. It preserves raw source objects, unique paused/final custody copies, original authority bytes and independent fstat/size/SHA observations. The external ZIP auditor must independently match every native ID and raw ACK before claiming journal_bound=true.

Explicit recover also handles verified partial native B/C/head tails through an independently durable archive and protected Repair plan. It preserves every complete ACK/C/head record, proves private original/prepared images with the actual SDK, and blocks ordinary readers until protected completion. The [Repair protocol](../posix_c02_admission_20261031/REPAIR_PROTOCOL.md) defines exact wire layouts, candidate uniqueness, retry boundaries, preserved namespaces and SDK FD lifetimes.

The original migration-result.json retains its36-case profile. A separate repair-result.json reports20 actual Repair cases: each short-write class, all1701..1706 process cuts, repeated interruptions with plan2, complete-prefix rollback/refusal, selected C restoration, later generation after pre-BEGIN restoration, namespace checks and actual authority ACL refusal. Damaged, pre-apply1702, successful DONE and refusal snapshots preserve actual source FD bytes/IDs separately from archive-copy IDs. Independent ZIP audit supplies Repair qualification; producer booleans do not establish it. These tests use process interruption and keep power_loss=false.
