# POSIX new-target recovery candidate — 2026-10-29

## Current status

Implementation/source-review packet; **no native run or 270/270 result yet**.
The predecessor e1cbfb31ac965fd34dd7d96356c157746a399418 passed run
[40840574068/1](https://github.com/NoGod3524/EXReader/actions/runs/40840574068):
198/198 focused groups, including Windows refusal-only. That result is not a
result for this successor. Historical failures, old companion assertions and
all frozen SDK bytes remain unchanged. Formal new credit is 0 and full P0/F12
remain incomplete.

Owner approval at 09:14:51 UTC covers exactly five modified migration owners
and five additions on `codex/migration-new-target-recovery-20261029`, after
independent actual-source review: one first run and at most one independently
reviewed repair, 45 Linux +45 macOS +20 Windows =110 configured runner minutes
per round, **220 maximum**. No other workflows, old assertions or budgets change.

## User-visible capability and limits

Explicit `migrate --create-target --target ABSENT --pack PACK --recovery-font FONT`
constructs a genuinely new private DELETE-mode library with the real importer,
waits for the actual SDK-owning child to exit successfully, validates a separate
standalone image, and publishes by native no-replace rename. It never replaces
an existing public target. `recover-migration --create-target` is the sole
explicit pending-creation continuation. After creation ACK, ordinary candidate
reads use a private verified view; a subsequent migration takes a fresh current
baseline and the existing real-owner comparison under the same permanent lease.
Later ordinary writes are retained, not overwritten with an old private image.
The coordinator returns `counts:null` rather than fabricated zero import counts;
its identity-bound `private_import_report` points to the retained actual child
report and durable successful parent wait proof.

Supported profile: owned regular files, stable cooperative private namespace,
Linux ext4/macOS APFS, same source/destination filesystem, bounded inputs and
native capability checks. The private image must be DELETE mode, with no WAL,
SHM or rollback journal before standalone work and after the worker exits.
Unexpected private WAL is a retained refusal, **not** silently checkpointed or
converted. Public applications may subsequently choose WAL; current-state
observation and the existing C route preserve it. Windows/new-target support is
not inferred from its eight unchanged unsupported-platform cases.

Preview/strict policy/cancel may leave an explicitly retained private attempt,
with no public target. At most one preserved second import attempt is allowed
for a failed or unknown first child. Once SEALED, no importer replay is allowed.
Missing durable parent wait/result proof cannot be reconstructed from a free
lock or a complete image. Required bounded EPUB validation still needs the
exact identity/hash-bound font. The candidate is finite-capacity, not an
arbitrary-size/unlimited-retry replacement for the old program.

Atomic visibility and observed directory fsync are separate. SIGKILL controls
are not physical power-loss tests. There is no guarantee that arbitrary hardware
failure preserves application writes between public-name visibility and parent
sync. No full physical cleanup, global SQLite I/O observer, Windows durability,
old-v3 automatic adoption, old `--break-lock` downgrade immunity or new formal
P0 acceptance is claimed.

## Exact ten-path manifest

Modified owners:
1. `extras/migration/CMakeLists.txt`
2. `extras/migration/src/lm_main.c`
3. `extras/migration/src/lm_recovery.c`
4. `extras/migration/src/lm_recovery.h`
5. `extras/migration/src/lm_recovery_worker.c`

Additions:
6. `extras/migration/src/lm_new_target.c`
7. `extras/migration/src/lm_new_target.h`
8. `tests/migration/new_target_recovery_20261029/run.py`
9. `.github/workflows/migration-new-target-recovery-20261029.yml`
10. this document.

The old ordinary/transaction executable paths remain outside the recovery macro.
The unchanged 198-group drivers, old companion, SDK, old schema6 producer and
fonts are byte-frozen. The new workflow checks exactly these A/M entries against
e1cbfb31; it does not invoke the predecessor's intentionally incompatible
four-path source guard. No same-SHA full companion pass is claimed. Existing
provider-map checks remain expected-input/graph corroboration, not a proof of
unique symbol-to-archive ownership.

## Canonical state and lifetime protocol

One permanent `anchor.json` has magic `EXRCREATE1`, truthful initial public
absence, public-path digest, parent/root identities, exact executable/worker/
font/retained-pack descriptors, outer lease/barrier and slot-registry binding.
A descriptor is `[present, dev+ino hex, SHA256, size]`; absent descriptors are
strictly empty. JSON field order/count/types and full canonical bytes are checked,
including actual record inode, predecessor digest and recomputed seal. Unknown
keys/phases, gaps, reordered/replaced records and foreign aliases refuse.
This is custody-bound integrity, not cryptographic anti-rollback storage against
a malicious same-UID actor rewriting/truncating all history in place.

Creation phases share the physical `record-NN.json` sequence with the
`EXRCREATE1-C` suffix. There is no nested recovery root, root move, policy unlink,
or fabricated pre-existing generation. Original producer identifies immutable
image/import/plan names; later observer/coordinator runs do not rebind them.

| Phase | Required literal evidence |
|---|---|
| ANCHOR | Parent/root/pack/lease/barrier and finite registry durable; public absent |
| PRIVATE_ATTEMPT (at most2) | Exclusive empty image, immutable request and dedicated inherited liveness inode durable before launch |
| PRIVATE_FINISHED | Parent actually reaped successful child; full child report says actual SDK COMMIT; exact image/plan/result retained |
| VERIFY (at most2) | New durable independent seal-worker identity/request; same image; no promotion from inferred wait status |
| SEALED | Real DELETE/exclusive locking-mode readback under held SQLite file lock; bounded full snapshot, public projections and ledger; no sidecars after worker exit |
| PUBLIC_VERIFY (at most2, only ambiguous visibility) | New durable liveness/request, actual public SDK writer, isolated complete current snapshot/projections and exact planned ledger; later ordinary metadata allowed, never replayed |
| PUBLIC_ADOPT | Exact planned inode installed by no-replace; source-root and destination-parent sync observed, or guarded current-state adoption after unknown acknowledgment |
| CREATE_ACK | Exact owned planned mirror installed and synced; public inode retained; not released-fence transaction permission |
| PUBLIC_BASE / OPENING / owner comparison | Existing suffix BASE/OPENING encoding takes fresh current snapshot and then real-owner full parity + ledger. Only this admits new importer work |
| PREP / MIRROR / ACK | Existing strict immutable evidence bindings and literal actual COMMIT reporting |

A partial record/use file is a retained refusal. On restart, complete visible
bytes alone are not assumed durable: after exact chain/worker exclusion under
the outer lease, the candidate fsyncs the actual identity-bound prefix/anchor,
registry/use files and all admitted suffix records, then both root and public
parent directories and rechecks the chain. This re-establishes observed native
file-content ordering after an earlier uncertain fsync; it never rewrites the
public database and does not claim physical power-loss qualification. A rename that succeeded before
its directory sync leaves SEALED plus the exact public inode. Recovery never
restores old bytes; it requires current full supported-state verification under
a new real owner and the retained planned ledger. Missing/foreign lineage,
changed ledger, both names missing, or foreign public/mirror entries refuse.
Equal bytes do not waive inode ownership. Fresh public-observation report, clone,
canonical stream and projection have separate immutable descriptors from the
original SEALED proof; adoption and later prefix checks retain both. Initial ACK
return rechecks the entire prefix, owned public mirror, target inode and worker
exclusion after its final rendezvous, and refuses any premature suffix record.
Legitimate later suffix records instead pass the existing strict R/C parser.

### Process exclusion, including the spawn gap

Each import/seal/public-observation process receives only stdio plus FD3, an
already locked separate open-file-description `flock` lease. The parent creates
and durably binds it before `posix_spawn`, allowlists that one FD, then **closes
its duplicate without LOCK_UN**. No SDK/SQLite or outer migration lease FD is
inherited. The fresh child validates actual FD identity, independent-lock BUSY,
request/output-root/image/pack/font bindings, and rechecks the entire envelope
after final test rendezvous immediately before SDK access. Main requires the
exact `import` request kind and private image/output/producer path relationship;
workers require their actual mode. Unknown/mismatched typed internal channels
and absent required pack/image/font bindings refuse without reaching the SDK.
FD3 remains open
through process exit. A restart acquires every retained exact child lock under
the outer lease, never infers death from a PID, never kills an unrelated process,
and never recreates a missing lease.

Subsequent creation-context capture/scan children also have durable lifetime
coverage, without changing old existing-target profile spawns. Eight immutable
slot lock inodes and eight write-once use-file inodes are precreated and bound by
one immutable registry manifest. Every restart validates and independently
acquires **all eight locks**, even if an output directory disappeared. Missing or
replaced lock/use/manifest inodes refuse. A use file is initially exactly empty;
before launch it receives one canonical bounded request/output identity/nonce/
predecessor binding, is fsynced, and is never reset/truncated by the candidate.
Partial/noncanonical use records refuse. Each used output/request must remain
exactly present. All eight capacity slots are reserved from the start; deletion
cannot reclaim budget. Only a same-process known spawned/not-yet-reaped child
has an active-slot exception, with no retained parent duplicate masking exit.
After wait/reap, independent acquisition is mandatory again.

The private seal uses SQLite `locking_mode=EXCLUSIVE`, an actual exclusive
transaction acquisition, then a READ snapshot while retaining the exclusive
file lock. This avoids using backup_step against a source write transaction.
Both locking mode and DELETE mode are read back under the retained lock. Native
reader/writer BUSY controls must establish the real boundary. The source remains
private until every SDK/image worker is excluded; mode/sidecar/identity/full-state
checks still follow lock acquisition. No lock alone is a complete-close proof.

## Resource accounting and admission

Hard ceilings remain: 64 MiB per bounded input/output stream and private physical
file, 512 MiB retained evidence, 128 names, 32 total record/reservation units,
12 per-attempt reserve; canonical records/requests/use files at most8192 bytes.
No bound is asserted on frozen SDK ordinary public-target WAL/journal growth.

- Eight slot reservations are charged even while empty; eight lock/use pairs
  plus one manifest require17 fixed names.
- First successful creation uses6 ordinal records; a first real C adds5. Total
  charged record units are6+8+5=19; a second five-record C yields24. Thus the
  authored useful route contains three distinct real packs (creation plus two C
  generations), then a further attempt must refuse its12-unit reservation. This
  leaves the unchanged12-unit pre-attempt
  reservation feasible at the first C admission. Extra interrupted attempts,
  seal attempts or public observations consume additional prefix units; none
  reset counts or extend the32-unit ceiling.
- Import execution reserves7×64 MiB+4 MiB before SDK work: physical image and
  sidecars, bounded source/worker/output allowances. Every native child has
  RLIMIT_FSIZE64 MiB, CPU30 seconds; parent polls retained physical/log bytes and
  waits at most35 seconds under a120-second coordinator deadline.
- Seal/current observation reserves6×64 MiB+4 MiB. Capture uses the inherited
 388 MiB envelope and scan196 MiB. Backup steps at most64 pages, 4096 calls and
 16384 reserved page-copy work, with monotonic30-second progress deadline.
- **Before public rename**, already retained bytes/blocks plus388 MiB future
  capture +12×8192 record bytes +1 MiB slack must fit512 MiB; names must retain
 24 worker/output and12 record slots. No reservation is counted twice, and no
 public publication occurs merely because a smaller prefix fits.
- Actual inventories, names and free-space checks remain authoritative; the
 default successful small-fixture path must be proven in Actions, not inferred
 from these ceilings. Full captures/public projections and all retained prior
 attempts still count. Capacity refusal leaves the public target absent before
 publication, or existing public state unchanged afterward.
- New Python driver reuses unchanged bounded Child/process/log/report machinery:
 spawn-time120-second deadline, 2 MiB/process,16 MiB/case streams,1 GiB+16 MiB
 case allowance,64 MiB report reserve and4 GiB pre-case workspace reservation.
 No local test/build/fixture/artifact execution is permitted.

## Required finite Actions acceptance

36 new groups on each POSIX OS, plus unchanged198 =270 total:
Linux131, macOS131, Windows8 refusal-only. The new groups cover complete minimal
and known-partial import, strict policy, nine formats/projections, two later-writer C generations,
preview/cancel, ten crash positions, no-overwrite/alias/provenance/parent failures,
real private WAL and pinned reader refusal, parent-kill orphan/spawn-gap/FD
semantics, transport/deadline faults, orphan seal, later visible writers,
ABA/current parity versus changed ledger, capacity, all pre-SDK entrypoints,
and installed independent standalone oracles. Subcontrols do not add formal
credit or inflate36 into independent recovery counts.

Acceptance requires a useful create→publish→guarded read→ordinary writer→fresh
real importer C route, preservation on every calibrated refusal, every unchanged
198 assertion passing, and exact native artifact/log identities. A missing native
capability is failure, not skipped success. First run and at most one reviewed
repair are authorized; any further round or extra path requires a new checkpoint.

## Source references for implementation constraints

- [SQLite backup API](https://www.sqlite.org/c3ref/backup_finish.html): a source
 write transaction can return SQLITE_LOCKED; source and destination are distinct.
- [SQLite locking mode](https://www.sqlite.org/pragma.html#pragma_locking_mode):
 exclusive-mode file locks are retained until connection close or explicit mode
 transition/access. This is a connection setting, not journal-mode conversion.
- [SQLite WAL](https://www.sqlite.org/wal.html): the main file alone can omit
 committed WAL content; hence private WAL publication remains unsupported.
- [Linux flock](https://man7.org/linux/man-pages/man2/flock.2.html) and
 [Apple flock](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/flock.2.html):
 inherited duplicate OFDs share the lock; explicit unlock is not duplicate close.
