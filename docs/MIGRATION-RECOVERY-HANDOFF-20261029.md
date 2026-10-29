# Isolated durable handoff qualification — 2026-10-29

## Status and authority

Authored, not executed. No native success, production recovery or full P0 is
claimed here. Source review must precede the first feature-branch publication.

The owner explicitly confirmed at 04:15:17 UTC the proposed five NEW paths,
Linux/macOS 126 top-level checks, first validation plus at most one independently
reviewed in-package repair, 120 configured runner-minutes in total. This package
implements the design reviewed at SHA256
`b617350eb1f4a827a79b9c8d450c74000c1ccb3be70117ea7d428a7530eacf57`.
It replaces the rejected capture-only production proposal with an end-to-end
test-only protocol. No production owner is modified.

Base: `c16c44dc5a9c8ea31460fddc5741ac332ec28e74`.
Feature branch: `codex/migration-recovery-handoff-qualification-20261029`.

Exactly five additions, no modified predecessor bytes:

1. `tests/migration/recovery_handoff_20261029/CMakeLists.txt`
2. `tests/migration/recovery_handoff_20261029/handoff.c`
3. `tests/migration/recovery_handoff_20261029/run.py`
4. `.github/workflows/migration-recovery-handoff-20261029.yml`
5. `docs/MIGRATION-RECOVERY-HANDOFF-20261029.md`

The workflow enforces this exact A-only delta against the tested base. SDK,
SQLite, product owner, existing 125/25/29/65/31/17 tests, assertions, budgets and
all predecessor workflows stay unchanged. No global logger, private SDK handle,
replacement VFS or manufactured SDK result is introduced. The helper is not
installed as a production command and never consumes real user data.

## What the new protocol must establish

The C consumer owns the actual public SDK migration transaction continuously
from the fresh comparison through the mirror operation, bounded title/ledger
work and actual COMMIT. The Python driver observes and verifies; it cannot send
an acknowledgment saying comparison succeeded. The helper launches the frozen
readonly scanner itself with native isolated `posix_spawn` descriptors.

* **R — current-baseline retry:** no complete literal COMMIT ACK exists. A fresh
  owner takes the lifetime lease and SDK writer, then requires full supported
  canonical baseline byte equality. Only the same owner retries the bound work.
  A changed later writer is preserved/refused. No-op/ABA equality means current
  parity, not historical rollback. Missing ACK never proves COMMIT failed.
* **C — known COMMIT, new successor:** only this helper's actual
  `exr_library_migration_finish(owner,1)==EXR_OK` may create an ACK. A later owner
  revalidates/synchronizes the immutable chain and exact owned mirror, checks
  current internal ledger against the acknowledged plan, captures a fresh
  baseline under its own writer, then performs distinct new work. It never
  replays the previous pack. Later ordinary metadata/progress remain intact.

The actual proxy work updates only book 1's title through `exr_library_update`
and sets the exact planned ledger through the public migration API. Full table,
catalog and public-value oracles retain every other field. It is **not** the
entire product importer. Real SDK3.40/schema6 has no internal ledger; its first
planned ledger call adds exactly the current SDK's
`CREATE TABLE exr_migration_ledger(id INTEGER PRIMARY KEY CHECK(id=1),data BLOB NOT NULL)`
and one specified row, in addition to the pinned schema6-to-7 upgrade whitelist.
The C-successor catalog includes precisely these intended objects. Missing-ACK
schema6 may be rejected by the frozen scanner's catalog mismatch rather than a
later baseline predicate; that actual reason is retained, not relabeled.

## Permanent anchor, ownership and failure states

The anchor, old shared `.migrate-lock`, original pending snapshot, mirror preimage,
baseline and all complete/partial records are retained, even on success.
“Retirement” is logical supersession, not physical deletion. The experiment has
no normal unlink-the-active-pointer state and no GC or database-file restoration.
An unsafe disposable-pointer unlink followed by a real directory-sync refusal
must still be blocked by the independent permanent anchor.

Fixed-size, zero-initialized native records bind exact self inode, preceding
record SHA, run/parent nonce, target/root/lease identity and input/output digests.
They include corruption-detecting seals; these are **not cryptographic authority
against a same-user attacker rewriting the private directory**. Native binary
layout is local to the exact qualification executable/platform, not a production
portable storage format. Unknown/truncated records, gaps, foreign equal-byte
files, aliases, unavailable fields or stale ownership refuse. Records cannot
supply arbitrary filesystem paths. The entire bounded chain is checked again
before each side effect and at explicit final rendezvous boundaries.

| Boundary | Restart rule |
| --- | --- |
| S1: anchor created, sync not confirmed | Recognizable pending; no SDK open permitted before durable baseline record |
| S2: durable anchor/input/BASE | Fresh lease, complete provenance and full R proof required |
| S3: SDK owner acquired | Scanner/clone failure never releases admission; retain/refuse |
| S4: owned copy and prepared mirror record durable | Only exact before/after identities may be reconciled under fresh proof |
| S5: mirror synced, actual DML uncommitted | Literal rollback or void-close observation is not retirement permission |
| S6: COMMIT attempted, no ACK | Full original baseline or refuse; a successful but unacknowledged COMMIT must not be replayed |
| S7: literal COMMIT ACK visible, sync uncertain | No same-process success; restart must re-sync/validate and use C, never R replay |
| S8: COMMIT/ACK sync observed, SDK closed | Original process still holds lifetime lease until exit |
| S9: producer exited, C independently validated | Only new bounded work under a fresh baseline and same live owner |

Mirror restoration first archives the owned planned bytes, syncs them, and
records the exact before/after identity. A separate owned copy restores an
original mirror, or the exact owned destination is removed if original absence
was captured. The sole bytes are never consumed. A publication/unlink followed
by failed parent sync leaves anchor, originals, archive and prepared record.
Restart completes only the known transition after fresh baseline comparison.

## Lease, scanner and entrypoint boundaries

The lifetime lease uses `flock` on a private regular file, not process-scoped
fcntl record locks and never on the database. The opened fd's device/inode must
equal the snapshotted/anchored path; it is rechecked after flock. The fd remains
open through SDK finish, void close and final reporting. Native controls check
unrelated/second lease-fd closes, scanner exit, producer death and a still-live
stopped scanner. Only original process exit releases the lease. Unsupported
native spawn isolation is a compile/capability failure, not a fallback fork.

Input reads check the actual opened fd as well as pre/post path metadata. If an
input is replaced by the SDK target between lstat and open, the attempt refuses
and quarantines that CLOEXEC fd until process exit: closing it under the parent
writer would release classic POSIX locks. Hash/read/record/GO-token paths and
evidence/ACK sync opens follow this rule. A deliberate after-lstat replacement
control must observe the quarantined fd and continued external-writer BUSY at the
refusal rendezvous. This is not a claim that pre-lstat alone removes TOCTOU.
Existing-file reads and sync/lease opens are nonblocking; an ACK replaced by a
test-owned FIFO must refuse rather than hang. Its original ACK is kept separately
and only the exact test-created FIFO is removed after the observed refusal.

The old scanner does not emit nonce or executable/output digests. Instead the
parent's immutable launch envelope binds exact executable SHA, request nonce,
target/catalog/root/output-directory identity, bounded argv and waited child
PID/status. The parent verifies output identity/hash and full bytes. Wrong nonce,
partial report, missing/other-nonce output, killed child and equal-byte replacement all refuse while an
external writer still proves the parent's SDK writer remains BUSY.

The unified gate is a **test model**, not actual product dispatch integration.
It covers migrate with absent/present flag, dry-run and break-lock, recover-mirror,
dump, verify, export-ledger and inspect-with-target before any SDK/SQLite open or
export output creation. Help/version/inspect-without-target are no-target cases.
Only explicit `protocol-admit` may enter R/C after provenance/lease prechecks.
Actual old3.40 default use remains excluded by the shared lock; explicit old
`--break-lock` is unsupported. A real product-generated v3 without baseline is
retained/refused, not retroactively adopted by test receipts.

## Actual bounds and fault labels

* Private files/directory modes 0600/0700; no symlink/hardlink adoption. Supported
  stable owner-private local namespace only; no hostile-between-check CAS claim.
  Native statfs must identify ext-family on Linux or APFS on macOS; an unknown
  filesystem is a capability refusal, not silently counted as local/durable.
* Canonical stream/file limit 64MiB; native record <=8KiB, at most32 records and128
  private path entries. Private evidence <=512MiB, including failed temps,
  archives and sidecars. Every C creation reserves its maximum before writing.
* New resource path checks page size/count, at most64 pages per backup step,
  conservatively reserves64 pages of work for **every** call against16384 total
  and4096 calls, and checks monotonic30-second deadline/cancel. Net page progress
  and reserved work are different report fields. Clone-only max_page_count and
  RLIMIT_FSIZE constrain file growth; source cache/PRAGMAs are not changed.
* Frozen preflight capture still uses `backup_step(-1)` for its already-qualified
  small fixtures. New bounds are not retroactively attributed to it.
* Parent C drains scanner stdout/stderr through pipes with a hard combined64KiB
  cap. The driver drains every native stdout/stderr through bounded pipes and
  reserves256KiB per live invocation including scanner logs. Per-case logs16MiB;
  native CPU30 seconds, scanner30 seconds, top-level case120 seconds.
* Driver reserves1GiB for the next complete case **plus16MiB logs and64MiB bounded
  aggregate receipt** before creating any fixture against a4GiB workspace ceiling,
  then reserves known fixed fixture-write maxima
  before seed/capture/resource/negative-control creation. Failure evidence is not
  erased to obtain more room. The >512MiB sparse-input refusal control is measured
  and then only those explicitly created test-owned sparse files are removed.
* Sync calibration closes the exact owned directory fd, calls actual `fsync`, and
  requires EBADF. This proves sync-descriptor unavailability, **not disk EIO or
  power-loss durability**. Native permission rename/unlink faults are separately
  calibrated. The DELETE test records literal SDK rollback status even if it is
  OK with a retained journal. No internal I/O observation is inferred: reports
  explicitly say `io_observation="not-installed"`.

## Authored checks and round cap

Per POSIX OS:4 schema6/7 × DELETE/live-WAL R→COMMIT→C scenarios;8 crash boundaries
each with all4 schema/journal subchecks;10 adversarial groups for the gate, lease,
later writers/ABA, ownership, native publication, sync/restore uncertainty,
ACK/scanner/void-close uncertainty, DELETE rollback observation, new backup
resource limits, and namespace/provenance/cumulative bytes. All subchecks are
recorded. A missing calibration is failure, not a skipped success.

Linux22+unchanged41 and macOS22+unchanged41 =126 top-level checks. The44 new tests
must qualify independently; the82 rerun prerequisite checks are not new handoff
acceptance. Prior Windows43/43 remains historical only. Each of two jobs has a
30-minute timeout, fail-fast false; first plus at most one reviewed repair means
maximum120 configured runner-minutes. Further rounds require the next explicit
checkpoint. One automatic push run per reviewed SHA; no duplicate dispatch.

All builds, fixtures, tests and artifact interpretation occur only in Actions.
No local test/syntax/build execution is evidence. Any failure is preserved with
exact SHA/run/job and raw bounded output before a scoped reviewed repair.

## Prerequisite and remaining P0 gates

The unchanged predecessor qualified125/125 on SHA
`c16c44dc5a9c8ea31460fddc5741ac332ec28e74`,
[run40811564289](https://github.com/NoGod3524/EXReader/actions/runs/40811564289).
It measured current baseline parity, not historical rollback or production
admission. Its two earlier failed runs and the original red65/29 gates remain
retained; neither test-only package relabels them as green.

Even a complete pass here only qualifies this synthetic POSIX proxy protocol.
The next production proposal must coherently integrate trusted baseline capture,
every real pre-open entrypoint gate and same-owner admission with the actual
importer, then rerun unchanged companion tests on that integration SHA. Windows
lease/ACL/inheritance/directory durability, oldv3 without provenance, larger or
unsupported inputs, pre-baseline SDK failures, physical cleanup, power loss and
hostile namespace custody remain explicit gates. `product_admission` and
`full_p0_acceptance` remain false. No capture-only production state is deployed.
