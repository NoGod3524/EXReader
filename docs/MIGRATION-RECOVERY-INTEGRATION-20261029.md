# Real existing-target recovery candidate — 2026-10-29

## Status

The first source-reviewed candidate was published and built in Actions; its
new worker/fixture failed at link admission, before any new recovery case ran.
**No native build, fixture, test, artifact parse or runtime pass has been performed locally.** This
is not full P0 acceptance and is not a change to the installed SDK or old test
contracts. The first and at most one independently reviewed repair round are
bounded to 610 configured runner-minutes across the two same-SHA workflows.

The previous isolated qualification, source
`14e3d0c60428a9baf33f2982d70689c0d654d3e0`, run `40820464299`, passed 126/126:
41 unchanged preflight plus 22 isolated handoff groups on each POSIX platform.
That result did **not** qualify this real importer, Windows handoff, new-target
publication, complete entity traversal or production P0. It is a prerequisite,
not an acceptance result for these changed owners.

## Exact scope and user-visible availability

Two modified owners:

- `extras/migration/CMakeLists.txt`
- `extras/migration/src/lm_main.c`

Nine additions:

- `extras/migration/src/lm_recovery.h`
- `extras/migration/src/lm_recovery.c`
- `extras/migration/src/lm_recovery_worker.c`
- `tests/migration/recovery_integration_20261029/CMakeLists.txt`
- `tests/migration/recovery_integration_20261029/fixture_probe.c`
- `tests/migration/recovery_integration_20261029/run.py`
- `.github/workflows/migration-recovery-integration-20261029.yml`
- `.github/workflows/migration-recovery-integration-companion-20261029.yml`
- this document

The separate executable is `exreader-legacy-migrate-recovery`; its installed
sibling is `exreader-migration-recovery-worker`. The two original executables
retain their prior compile branches and behavior. The new macro alone selects
the recovery protocol and still calls the real original `process_book`,
`process_note`, ledger and full importer validation routines.

This candidate supports **existing regular singly linked targets on native
Linux ext filesystems or macOS APFS only**, with a private, cooperatively stable
parent namespace. Windows and a missing target return a precise unsupported
result before target SDK open, target creation, recovery root, output or stage.
They never fall back to either old migration implementation. Network filesystems,
symlink/reparse/hardlink namespaces and unknown catalog shapes are unqualified. Embedded NUL/invalid UTF-8 or non-TEXT
public string fields refuse instead of allowing two C string projections to
truncate or coerce them identically.

After the real target SDK opening marker, cancellation or `--dry-run` can leave
persistent evidence requiring the explicit
`recover-migration --pack ORIGINAL --target LIBRARY` command. A successful
preview is **not** reported as recovery-ready: `dry-run-recovery-required` is a
nonzero pending result. Actual rollback request and literal SDK status are
reported separately; SDK OK does not prove physical cleanup or no internal I/O.

An existing bounded-storage EPUB requires `--recovery-font FONT` for actual
public bounded-pager validation. This optional dependency is read-only,
identity/hash-bound and limited to 64 MiB. No font or SDK source is modified.
Without it, a bounded EPUB baseline refuses before target SDK open. Actual
part/path, note/progress selectors and public FOUND/MISSING/AMBIGUOUS resolution
are observed without manufacturing a global anchor or forcing FOUND. Memory
snapshot EPUB and bounded EPUB retain their distinct storage contracts.

The bounded profile can reject legitimate large libraries, many bounded EPUBs,
large packs or exhausted evidence chains. Unlimited repeated migration,
evidence compaction, font substitution, worker replacement, Windows and
new-target support are not silently supplied. Old targets/readers and ordinary
writers remain usable after the process exits; default old migrators remain
blocked by the owned shared barrier. Old `--break-lock`, manually deleting the
anchor or selecting an old binary are unsupported downgrade paths, not a
universal protection claim.

## Persistent protocol and real owner lifetime

`T.migration-recovery/anchor.json` and `T.migrate-lock` are never removed by this
candidate. A separate exact-identity `flock` lease remains alive through SDK
close, final reporting and process exit. It is not a classic process-wide
`fcntl` mutex. No record after a released SQLite writer is permission to mutate
without reacquiring the real SDK owner and comparing a fresh full snapshot.

Records are canonical explicitly encoded JSON, not native ABI structs. Every
record binds its own inode, ordinal, previous record digest, exact target/root/
parent, generation, run nonce, original pack digest and retained copy, baseline,
original mirror preimage, planned mirror, lease, shared barrier, worker and font.
Unknown keys/order/types, missing/gapped/replaced records, aliases, changed
identities and incomplete objects refuse; they are not adopted by byte equality.
This is trusted private-directory provenance, not cryptographic authentication
against a hostile same-UID actor.

| Boundary | Next permissible action | Failure/restart disposition |
|---|---|---|
| No reservation | Metadata/capability and validated pack | Unsupported target/platform creates no target state |
| Partial root/anchor/barrier | No target SDK | Recognizable incomplete state remains refused, never deleted |
| Complete durable anchor, no BASE | Read-only capture and public clone validation | Explicit retry only; no whole-state rollback claim |
| BASE/FRESH durable | Reserve capacity, append/sync SDK_OPENING | No target SDK before complete marker and exact checks |
| SDK_OPENING durable | Recheck after rendezvous, actual migration_open | Failed/unknown opening remains R-required |
| Same real SDK writer alive | Isolated full committed-snapshot comparison | Changed baseline/unknown output refuses without releasing fence for admission |
| R parity established | Restore only exact owned mirror via retained preimage copies | Prepared/restored edges and originals survive uncertainty |
| Importer completed uncommitted | Exact plan + separate work file; PREP | No sole evidence consumed |
| Planned mirror published | Sync source/destination parents, MIRROR record | Failure retains permanent anchor and originals |
| Before COMMIT | Recheck entire chain/target/owned mirror after last pause | Foreign equal-byte inode still refuses before COMMIT request |
| Literal successful COMMIT | ACK written, then synchronized | Missing/partial/foreign ACK never creates success or automatic R |
| Valid acknowledged generation | Explicit fresh C baseline, then new SDK owner/full recompare | Later ordinary writes preserved; old pack is not replayed over unknown COMMIT |
| SDK owner closed | Exact final chain/mirror check, retained lease | No raw target restoration, journal deletion or evidence retirement |

R compares current full supported content with the original baseline; changed
later state refuses rather than overwrites. No-op/ABA commits may have equal
current state: equality is **current parity**, not proof that a historic COMMIT
never occurred. C requires actual ACK lineage and exact internal ledger bytes,
but ledger equality alone is not recovery proof: every C generation captures a
fresh full baseline and repeats the comparison under its new live owner.

`migrate` (including dry-run/break-lock), explicit recovery, recover-mirror,
dump, verify, export-ledger and inspect-with-target all enter the pre-SDK gate.
Pending policy is not implicitly recovered by a read command. Admitted reads
operate on a coherent private clone, never a schema-upgrading SDK open of the
actual target. Existing-root reads hold the protocol lease. Initially rootless
reads recheck that no permanent root/shared barrier/legacy intent appeared during
capture; an earlier coherent SQLite snapshot is not current policy permission.
Rootless reads also bind the actual original mirror to the same snapshot ledger,
retain its exact identity through return, and copy only those validated bytes
to the private clone sidecar; artificial clone-side absence does not hide
original divergence.

The worker is an independent `posix_spawn`/exec, with inherited descriptors closed,
no inherited SDK/SQLite handles or lease FD. Its launch envelope binds actual
executable digest, request nonce, target and output-root identity, waited PID/
status, exact result and independently reread output. Worker claims are not
accepted from timeout, partial result, missing output or another nonce directory.

Under a live parent writer, raw same-parent reads use open/fstat identity checks.
An actual target-alias or unknown descriptor is quarantined until process exit,
not closed and thereby allowed to drop SQLite's classic POSIX locks. Special
files use nonblocking/no-follow opens; directory sync opens O_DIRECTORY. Exact
checks at controlled boundaries are not an atomic compare-and-swap filesystem
API: stable/cooperative namespace custody remains required.

## Content and resource admission

The target is read through the pinned SDK public SQLite implementation selected by the imported target graph in a
private-cache READ snapshot with read_uncommitted OFF. Canonical framing includes
schema objects, table columns, index definitions, foreign keys, hidden rowids,
all supported typed values, application/user versions and integrity/FK checks.
The accepted catalog derives from a separate SDK-created private profile, with
only exact known schema6-to-7 additions and ledger DDL admitted.

A private backup must match the entire original canonical baseline. SDK opens
only that clone for pre-open public validation: all original rows remain exact,
only the explicit schema6 upgrade is permitted, and independent public getter
projections are compared with the original pinned snapshot. Source extents and
bytes, covers, metadata, reflow/fixed notes, all supported format values,
progress, bounded EPUB and audio are included. The Actions oracle separately
checks expected typed values and fixture records; two matching native serializers
alone do not qualify correctness.

Resource formulas (new owned evidence/worker profile, **not a whole SDK disk cap**):

- Each canonical/projection/file/clone stream: at most 64 MiB. Worker explicit
  outputs have an aggregate 192 MiB and 24-file cap, including per-book bounded
  EPUB diagnostics. Native clone main/WAL/journal each have RLIMIT_FSIZE 64 MiB;
  the fixed private SDK profile and small sidecars have separate reserved slack.
- A capture reserves `6*64 MiB + 4 MiB` before launch; scan reserves
  `3*64 MiB + 4 MiB`. Parent inventory includes actual allocated blocks and every
  private run/scanner log, with 512 MiB total and 128 names. It refuses if the
  next complete reservation cannot fit; it does not reclaim earlier evidence.
- Backup: 64 pages/step, at most 4096 calls and 16384 conservatively reserved page
  copies. Pinned source transaction and nonincreasing remaining pages reject
  restart. Worker CPU/wall supervision is 30 seconds; killed children are waited.
- Before target SDK open, conservative planned logical size is
  `baseline + 2*pack bytes + 8*manifest bytes + 8 MiB*book count +
  128 KiB*note count + 16 MiB`, required to fit 64 MiB. This includes cover and
  representation slack; real larger inputs refuse rather than become a C result
  that the next generation cannot scan.
- Planned mirror side effects reserve three projected streams plus 12*8 KiB
  records and 1 MiB stream slack. Record capacity is 32, with at least 12 slots
  reserved before a target SDK opening. A successful fresh attempt uses BASE/
  OPENING/PREP/MIRROR/ACK; R can add restore-prepared/restored. Error paths append
  no invented disposition, and partial records consume capacity.
- The test driver reserves one GiB plus logs/report headroom per case before new
  fixture creation against a four-GiB workspace envelope. Native children have a
  120-second process deadline and bounded drained output, not unbounded files.

SQLite target/main/journal/WAL growth and opaque SDK allocation still obey the
unchanged SDK/importer constraints, not the worker's clone cap. Native ENOSPC,
EIO and power-loss outcomes cannot be inferred from an actual EBADF sync control.
Physical journal deletion is never a recovery acceptance criterion here.

## Validation, unchanged red evidence and budgets

Authored new top-level groups: 32 Linux +32 macOS +8 Windows unsupported controls.
Expected refusals are explicitly labeled, not successful recovery operations.
The POSIX groups include all four schema6/7 x DELETE/live-WAL combinations, eight
crash boundaries, full five-book/sixteen-note legacy fixture with exact known
partials, nine formats/bounded EPUB, actual R/C and three generations, later
writers, all actual command entries, native fault observation, foreign artifacts,
actual-FD alias controls, resource and transport failure boundaries.

Each POSIX job separately reruns the unchanged 41 preflight +22 handoff groups.
Thus the new workflow has 198 top-level groups, while the companion retains every
original job, assertion and budget unchanged after its name/trigger. Source
admission enforces exactly these 11 A/M paths against tested14e3d0c6; all other
SDK, test, owner and workflow bytes remain unchanged.

The original companion accepts its real ancestor/ABI guard and invokes the
usual original executables. Its old candidate results previously included61/65
and genuine transaction-architecture mismatches. They remain failures unless
this run actually proves otherwise; no altered test or status label hides them.
The old29 mirror matrix has a fixed main.c hash and is not invoked by this
companion: it must not be represented as29 fresh passes for changed main.c.

New workflow:45 Linux +45 macOS +20 Windows =110 configured minutes. Unchanged
companion:3*60 +15 =195. One same-SHA round is305, first plus at most one reviewed
repair is610. No duplicate run follows repeated approval. A third round requires
an explicit new checkpoint. Link maps corroborate expected archive/symbol presence alongside the exact
imported-target graph and runtime header/source-ID check; these substring checks
are not a claim of independent symbol-to-member unique-provider attribution.
No recovery runtime pass is claimed for the first candidate or the source-only
repair below.


## First Actions failure and one bounded repair

Published source `a4ad810d79c3b74d84112b5cc03cb2c6eafe2344` (tree
`988fb19d21470327c07935826bf3bc43e6e98940`), integration run
`40834122503` attempt 1, failed on all three platforms at the native-build step.
Linux job `123314807987` and macOS job `123314807981` could not link the new
recovery worker; Windows job `123314807631` could not link the new fixture.
Undefined public symbols include publication open/free/parts, bounded pager
create/free/anchor resolution and layout/chapter defaults. **Zero of the 72
new integration groups executed**, and the 126 unchanged prerequisite groups
were skipped in this workflow; they did not pass on this SHA.

The worker and fixture linked only `EXReader::exr_library`. The unchanged SDK
layer manifest makes library depend on formats/PDF, not layout; its installed
`EXReader::exr_core` supplies render→layout→formats, including these bounded
publication/pager APIs. The minimal repair adds that existing public core
target to those two new consumers only. It does not add a second SQLite
provider, alter the installed SDK, replace real public calls, or change case
bodies/assertions. The ordinary and transaction targets keep their link lines.
No SDK options, old tests, workflow commands or runner budgets change.

The unchanged full companion run `40834122480` on this same SHA also encountered
the worker link failure on both POSIX jobs before its historical test gates.
Its later browser/artifact commands consequently reported missing generated
inputs; those downstream failures are retained, not relabelled as old scenario
passes. The full companion finished `failure` at 07:20:50 UTC. Windows job
`123314808162` actually ran the ordinary original 65/65 (135/135 checks), actual
schema6 upgrade check, and ordinary browser 17/17. Its transaction candidate
reported 60/65 (129/135 checks), review 31/31 and browser 17/17. The five retained
scenario failures are adoption labeling, DB backup-stage expectation, the
partial-write composite stage predicate (the other three preservation checks
passed), no leftover evidence after ledger-publish refusal, and exit6/raw-DB
preimage expectations. The fourth now conflicts with inherited v3 pending
retention; it must not be described as the earlier 61/65 result. The separate
transaction/writer/WAL script stopped at its actual `recovery-unverified`
assertion, not a full pass. The aggregate job `123317021653` failed with missing
POSIX evidence. None of those old-candidate results validates the new recovery
candidate, whose new tests did not execute.

Only the two package-owned CMake files and this document change in the repair.
Independent source review must precede its publication, after both first-round
runs finish. The repaired SHA gets at most one automatic integration/companion
pair under the existing two-round/610 configured-minute cap. A source-level
link dependency correction is not a native linkage or recovery pass.

## 07:47 authorized harness-only follow-up — source work, not a new pass

The completed second round used `65dd64a5cd7b616aa15a262f635ea01870ba1e13`,
integration `40835216735` and companion `40835216722`, both failure. New group
counts were Linux21/32, macOS29/32 and Windows8/8 expected platform refusals;
preflight41/41 each POSIX and isolated handoff20/22 Linux,22/22 macOS. All three
ordinary companion suites passed65/65, while the old transaction candidate stayed
60/65 (129/135), review31/31 and browser17/17, with its separate writer/WAL test
stopping at inherited v3 recovery-unverified. These historical failures remain.
No full P0, physical-cleanup or Windows recovery acceptance follows.

On 2026-10-29 at07:47:39 UTC the owner confirmed a separate three-file test-only
follow-up: new test driver, new integration workflow and this document, one
isolated198-group round/110 configured runner-minutes, no repair rerun. Production
and old test bytes were to remain unchanged. The proposed branch is
`codex/migration-recovery-integration-harness-20261029`; the old companion trigger
does not match it. Its prior65dd64a5 red results are historical, not a new-SHA
companion pass.

Source changes select official setup-python3.12 and calibrate real numeric
SQLITE_BUSY against an independent held writer, then successful writer admission
after release, plus numeric syntax/read-only non-BUSY controls. The old41/22
prerequisite scripts also run under the selected PATH interpreter; their source
and assertions stay unchanged. Exact Python executable/version and Python SQLite
version are recorded separately from the frozen SDK/SQLite provider. No ctypes
SQLite loader, numeric fabrication or message-string fallback is used.

The new test continue-token publisher uses a complete private0600 temporary,
file sync/close, native no-replace atomic rename and parent sync. It binds the
actual directory and file identities, checks9 bytes and single link, never
replaces a preexisting final name, and only cleans its exact temporary inode.
Linux renameat2/RENAME_NOREPLACE and macOS renameatx_np/RENAME_EXCL are public
libc APIs with explicit argument types; unavailable capability fails admission.
There is no hardlink nlink2 window or visible incomplete final pathname. Positive
and negative controls retain the actual numeric/permission/identity evidence.
Matched valid-token positives and attack-specific original reasons distinguish
intended negative outcomes from the former unrelated0644-token refusal.

Primary API references used for source design:
- [Python numeric error-code availability](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Error.sqlite_errorcode)
- [Official setup-python](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md)
- [Linux exclusive rename](https://man7.org/linux/man-pages/man2/renameat2.2.html)
- [Apple public exclusive-rename flags and prototypes](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/stdio.h)

Source inspection during this repair found a real additional product gap:
afterS4, the chain checks serialized baseline descriptors but does not recheck
the actual active baseline inode. The existing same-byte foreign-baseline
negative could have been masked by the malformed token. That assertion is
preserved, not weakened. The currently granted three-path harness package does
not authorize changing `lm_recovery.c`; publication and the sole110-minute run
are held pending a separately reviewed/authorized fourth-owner repair decision.
No product edit or new runtime success is claimed here.

The frozen old handoff's direct final-path `.go` write is also a concrete race
candidate against its strict double-read size/time checks. Its two generic
Linux failures do not name the failing file/predicate, so this runtime cause
remains unproven. No old handoff helper, harness, assertion or gate is modified.


## 07:59 additional exact owner authorization — active evidence repair

At07:59:58 UTC the owner explicitly added only
`extras/migration/src/lm_recovery.c` to the above three paths (four total), keeping
the same single110-minute198-group allowance, no repair rerun. This supersedes
the preceding publication hold for that precise scope after actual source review;
it does not extend SDK/old test/other owner permissions or establish a pass.

Every successful chain admission now rechecks the active BASE/FRESH's actual
baseline, retained pack and retained original-mirror preimage against their
recorded presence/inode/size/SHA. Pack bytes also bind to the recorded pack SHA;
preimage bytes bind to the original mirror bytes while retaining the private
copy's own inode. Expected absence is checked rather than silently ignored.
For each distinct PREP producer in the active generation, its immutable
plan-<PREP.run>.bin must match recorded identity/content and planned-after bytes.
A copied plan descriptor in a later OPENING/RESTORE record does not change that
original producer filename. Old active ACK evidence is checked before a new
FRESH generation; the existing owner/ledger comparison remains unchanged.

Legitimately renamed work/restore paths are excluded from this immutable set;
their current mirror/transition checks remain intact. Checks use the existing
actual-fd target-alias quarantine path, never raw DB descriptor open/close.
Each distinct file is bounded by its recorded size,64MiB per file and512MiB
cumulative immutable bytes per chain check; streaming double reads add bounded
I/O, not unbounded copies or a whole-disk guarantee. At most32 PREP references
are considered, duplicate producer names cannot bind different plan identities.
No persistent format, rollback/COMMIT state, namespace assumption or cleanup
policy changes; no file is deleted or restored by these new checks.

Before COMMIT, a changed referenced file causes refusal with rollback requested
and evidence retained. After actual COMMIT, the same detection preserves literal
committed status but prevents success/acknowledged completion; it does not claim
rollback or rewrite the DB. New additive subcases substitute equal-byte foreign
baseline/pack/preimage/plan atS4/S5 andS6/S7, preserving strict original negative
predicates and checking exact causes, no pre-COMMIT request, post-COMMIT content,
restart refusal and later ordinary writer retention. Existing absent-original-
mirror and normal schema6/schema7 DELETE/WAL R/C cases remain required.

The historical65dd64a5 companion result is now explicitly **not product-byte
identical** to the new recovery executable: the one-file owner delta is declared.
Old ordinary/transaction target source and all companion source/assertions remain
unchanged. No new-SHA companion result is claimed or automatically run on the
new branch. This focused110-minute validation remains the precise approved scope,
not a concealed305-minute pair or an extra retry.

Current status: implementation awaiting independent four-path source review;
no local native execution, fixture generation, tests or artifact parsing, no
new branch publication or run yet, and no runtime acceptance claim.
