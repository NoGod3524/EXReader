# Migration recovery preflight — isolated qualification, 2026-10-29

## Current status

Two Actions validations are terminal. Linux/macOS each passed only the four
typed-serializer controls in the second run; their other 37 cases failed during
seed creation, before the intended recovery checks. Windows did not enter the
case driver. **Zero recovery scenarios have qualified.** A second repair is
source-only and requires a new round checkpoint before publication/execution.
This package
does not integrate recovery into the migration tool, retire a product intent,
restore a database, or establish full P0 acceptance. Existing v3 intents remain
pending. The earlier 75/75 retention result is not recovery qualification; the
old 29-case and historical candidate 65-case failures remain preserved.

This implements the independently reviewed five-path plan
`64a8eb75c33107fb2cfda79daa71eca5d5377662924477ea0a95e5e2c8a795d4`, with
the explicitly narrower physical-fault and durability observations below.
All builds, tests, fixture generation and artifact interpretation execute only
in GitHub Actions. Local preparation is source editing/review and Git identity.

### Retained first validation failure

[Run40807421445](https://github.com/NoGod3524/EXReader/actions/runs/40807421445),
attempt1, source `2743d8a1e586552ff5a0c434d2151572b2a08169`, tree
`d155716e909e54ade5642e4a9121229c57b15070`: all three exact-source admission steps,
current SDK/tool builds, actual SDK3.40/tool builds and new C consumer native
compile/link completed successfully. All three jobs then failed the unchanged
single-SQLite-provider assertion with `AssertionError: []`. Qualification steps
were skipped, so this is **zero executed cases**, not125 failures or passes.

The consumer CMake target scanner incorrectly included `LINK_ONLY:` in a
generator-expression token; that is not an actual target, so recursion missed
the SQLite provider. Source tracing also found that the installed package exports
`EXReader::vendor_exr_sqlite` as an INTERFACE wrapper and
`EXReader::vendor_file_exr_sqlite` as the sole STATIC provider, not the originally
assumed build-tree name. This follows unchanged `cmake/modules.cmake:75–78` and
`cmake/install_dependencies.cmake:14–24`. The scoped repair parses exact complete
namespace/genex entries, requires this exact wrapper and one STATIC provider,
and adds Actions-configure plain/genex/empty and malformed/ambiguous refusal
controls. The strict single-implementation condition, native map checks,
all125 authored cases, SDK,
product, old tests and budgets remain unchanged. Closure evidence is also printed
to Actions logs before the assertion. This is the one planned repair validation,
not a weakened admission rule.

First-run uploaded artifacts (API metadata, contents not parsed locally):

| OS / job | Artifact ID | Bytes | ZIP SHA256 |
| --- | --- | ---: | --- |
| Linux /123229582291 |12868268858|66233|`a973c79df08e07aa4b608f8288115cba2811f8f3b24a17d87e203909311bb43d`|
| macOS /123229582690 |12868558615|184883|`41965589cf89ac5d46b2c48bda8c94e22f98a53b4191b0a0305c58d87d196ef4`|
| Windows /123229582595 |12869041682|400950|`81a3b596488612891f331136e3d65d16483fa293e63f1b401d4a3afeac67ef04`|

### Retained repair validation failure and proposed next round

[Run40808511383](https://github.com/NoGod3524/EXReader/actions/runs/40808511383),
attempt1, source `edeadbcaba13d33b514944d44d1ec6fec6e768d3`, tree
`4df401f1dd9108a00526b90a23f1aaa6843e4f12`: all source admission and native
current/old SDK/tool/consumer builds passed. The exact wrapper plus sole STATIC
closure was measured successfully on every platform. Linux/macOS provider-map
admission also passed. Their driver results were each **4/41**, with only
`typed-vector-none`, `typed-vector-rowid`, `typed-vector-type` and
`typed-vector-cell` passing. All 37 other cases stopped in `seed()`; this is not
37 observations of failed recovery semantics. Windows failed the map conjunction
before the driver, so its 43 authored cases were **unrun**, not passed or failed.

The full unchanged `legacy_data.dataset()` deliberately contains an audio
original that cannot be stored. The seed omitted the original full-fixture
producer's explicit `--allow-partial` flag (`tests/migration/run_cases.py:127,
139,329`). Actual reports correctly returned `policy-strict`, one unsupported
`audio-original-not-storable` for `b-audio`, zero conflicts, and no publication.
The orphan is instead an expected **unlocated** `orphan-note`, retained in the
ledger; it is not the unsupported cause. The proposed seed repair preserves
every original item, requires exit0/result success/code ok, exact full counts,
that single known unsupported item, all six specific unlocated reasons, all
5 book and16 annotation records in the ledger (cover remains separately stored
by the frozen producer), and the unchanged later public projection/parity tests.
It cannot accept an arbitrary partially imported database as a valid seed.

The Windows failure was the unlabelled conjunction of `sqlite3_open_v2`,
`sqlite3_backup_init` and `sqlite3.c` substrings. **Which conjunct was missing
has not been observed**: no artifact bytes were parsed locally. The source-only
repair prints each historical predicate and actual symbol lines before admission.
[Microsoft documents /MAP as listing each public symbol's defining .obj file](https://learn.microsoft.com/en-us/cpp/build/reference/map-generate-mapfile?view=msvc-170).
The proposed Windows-specific check therefore requires exactly one definition
of each exact API symbol from `exr_vendor_exr_sqlite[.lib]:sqlite3[.c].obj`;
seven Actions-only positive/foreign/prefix/malformed parser controls accompany
it. Unknown formats still refuse. Both exact target-closure checks, the archive
check, POSIX map criteria, runtime/header identity and no-second-implementation
condition remain mandatory. This is a native-format hypothesis to validate,
not a claim that the previous map has already proved the hypothesized spelling.

Second-run uploaded artifacts (API metadata only):

| OS / job | Artifact ID | Bytes | ZIP SHA256 |
| --- | --- | ---: | --- |
| Linux /123233052816 |12868678752|339752|`f4a5fcdf0d15fe5f39cee656e2ad07bd29beacc6fe3064e8f554ec5b5bae1b72`|
| macOS /123233052549 |12869366595|459079|`71ec4ddaae998d1ce5c4326849edae7533f9dc9416602dc04e04e2c19f8e1f00`|
| Windows /123233052712 |12869377413|401319|`d1ab09b99da8e37f620ccc9cdc15df151267685097dd615a2576beafe18085a9`|

The initial **first validation + one repair** cap is exhausted. Proposed next
scope: one further three-system validation on one reviewed successor SHA,
41+41+43 authored cases, existing60-minute/job and fail-fast-false settings;
only this package's `run.py`, workflow and this document change. C/CMake,
SDK/product/old tests and predecessor bytes remain unchanged. No third run or
successor publication is authorized by this paragraph. Obtain the round-scope
checkpoint and independent source clearance first; a further failure remains
red and requires the same bounded disposition, not unlimited retries.

## Exact source and runtime scope

Base: tested `fedac0c42c4253f686be4239c4cf45e7e3bf1e1b` (tree
`61721ce521ee2dcd30c7c27d751d070775489f3f`). New branch:
`codex/migration-recovery-preflight-20261029`. Exactly five added files:

1. `tests/migration/recovery_preflight_20261029/CMakeLists.txt`
2. `tests/migration/recovery_preflight_20261029/probe.c`
3. `tests/migration/recovery_preflight_20261029/run.py`
4. `.github/workflows/migration-recovery-preflight-20261029.yml`
5. `docs/MIGRATION-RECOVERY-PREFLIGHT-20261029.md`

The workflow requires this exact A-only delta against the tested base. Every
SDK, SQLite, product source, prior test, prior workflow and budget stays byte-for-
byte unchanged. The consumer links the installed SDK and the pinned public
SQLite 3.54.0 header already used by the migration consumer. It compiles unchanged
`lm_util.c` and `lm_mirror.c` solely for JSON/SHA/file helpers; it does not compile
another SQLite or alter public API results. CMake's imported dependency closure,
native link map and exact header/runtime source-ID equality supply provider
evidence. No private SDK structure, replacement VFS or global log callback.

Actual schema6 producer: SDK3.40 commit
`c2d23c29a3b2096c2236fdb414dcd1e66d3243b4` and its original migrator. Schema7:
the unchanged current transaction candidate. Fixtures include TXT, EPUB, PDF,
CBZ, legacy notes, progress, fixed notes and audio checkpoints/bookmarks.
Linux/macOS/Windows have independent jobs, 60 minutes each, fail-fast false.
First validation plus at most one independently reviewed repair validation is
the initial round limit; retain failures and request a scope checkpoint if more
are needed. No workflow-dispatch duplicate is needed after an admitted push.

## What the consumer proves if its checks pass

1. A real public SDK migration owner holds the target transaction before baseline
   capture. A separate READONLY|PRIVATECACHE SQLite reader pins its committed
   snapshot. `read_uncommitted=OFF`, trusted schema off, extensions disabled or
   omitted, URI options forbidden, no attached databases. An actual read and
   `sqlite3_txn_state(main)==READ` are required. Direct readers close through the
   same SQLite implementation, never by a raw target descriptor. Metadata-only
   target identity checks do not drop POSIX process locks.
2. Public SQLite backup makes a distinct, exclusive-create validation clone from
   that same reader. Its full manifest equals the baseline before SDK open.
   Only the clone gets ordinary SDK open. Schema6-to7 permits exactly the three
   bounded-EPUB tables and their one index, with exact SQL definitions; every
   existing schema object and typed row is retained. Public SDK traversal checks
   original/source byte parity, notes, progress, audio, reflow/fixed document
   opening and EPUB public metadata. It also emits each returned public value
   (including source/cover hashes, unresolved note ranges and binary fixed-note
   selectors); the independent driver compares them to the pre-owner fixture
   projection before releasing the clone pause toward baseline publication.
   **Bounded EPUB content refuses**, rather
   than being silently counted as qualified.
3. External clean-exec writer probes must observe actual BUSY before, during and
   after every secondary reader/backup/clone close. A separate lifetime control
   demonstrates an SDK source retains its owner after void close, releases it,
   and observes real `sqlite3_close==SQLITE_BUSY` with a live statement before
   finalizing and closing. Every original owner process exits before a fresh
   verification process is launched; no SQLite handle survives into that exec.
4. Baseline is fully written, synced and closed before immutable intent/custody,
   before a simulated external mirror, before the uncommitted SDK ledger change.
   The SDK's literal `finish(0)` status is reported, not interpreted as absence
   of internal I/O errors. No non-OK SDK return is assumed or fabricated.
5. The fresh verifier owns `BEGIN IMMEDIATE`, full comparison and provisional
   decision publication in one process. It rechecks WRITE transaction state,
   autocommit0, target/evidence identities and bytes at the final boundaries.
   Other writers must be BUSY through decision publication. Any observed API,
   integrity, FK, namespace, interruption, I/O or close error refuses. It never
   writes data/schema, copies a DB image back, deletes journals or clears v3.
   SQLite's own hot-journal recovery may perform engine I/O on open.
6. Every restart, including one with an existing decision, reacquires the fence
   and recomputes parity. Killing after durable decision, then committing a
   changed canary, must make restart refuse without overwriting that later data.
   No-op and ABA-to-baseline controls can match **current state only**. A receipt
   is never historical rollback/COMMIT proof or reusable product permission.

## Frozen logical manifest format

`EXRPF1\n` followed by query records. A query record is `Q`, little-endian u64
UTF-8 label length, label bytes, u64 column count, zero or more rows, then `E`.
Each row starts `R`. Each cell is a storage-class tag plus u64 payload length:
`N` NULL/zero bytes; `I` signed integer's 64-bit little-endian representation;
`F` finite IEEE754 binary64 little-endian; `T` exact UTF-8 bytes; `B` exact BLOB.
NULL, empty TEXT, empty BLOB and embedded NUL remain distinct. Manifest maximum
is 64 MiB; excess or allocation failure refuses rather than truncates.

Order: application_id, user_version, encoding; complete sqlite_schema sorted
by type/name BINARY; each table sorted by name BINARY: table_xinfo, index_list,
foreign_key_list, index_xinfo for index names sorted BINARY, all columns plus
hidden rowid ordered by rowid. The expected catalog comes from the trusted
clean fixture producer before mutations, not the damaged target. Unknown or
virtual/shadow schema, unsupported tables/triggers and catalog drift refuse.
Integrity and FK checks are additional checks, not interchangeable with parity.
The independent Python serializer separately derives typed expected values;
four hand-specified vector controls cover duplicate/null keys, hidden rowid,
NULL/empty/NUL values, INTEGER versus REAL and an 8193-byte binary payload with
a boundary-crossing zero. Separate cell/type/rowid mutations prevent a vacuous
two-identically-buggy-hash comparison. This is supported **logical state**, not
raw SQLite/WAL byte equality, freelist/history or application completeness for
unimplemented formats.

## Authored controls (execution status distinguished above)

41 top-level cases on Linux/macOS; Windows adds two native WAL-read cases = 43.
Subchecks remain individually present in each case's raw logs and result data.

- Schema6/7 × DELETE/live WAL: real owner, clone, fence, no-op/ABA, stale receipt,
  changed writer preservation. WAL pins an old reader **before** a committed
  canary, requires actual incomplete checkpoint telemetry, and keeps the
  checkpointer/pin live through capture. PASSIVE and FULL checkpoint attempts run
  at each capture and verifier rendezvous while the child still holds its owner/
  snapshot/final-decision fence; each requires a fresh read of the canary and
  records actual blocked/incomplete telemetry. After pin release, checkpoint converges
  without changing the manifest.
- Real DELETE journal deletion refusal for each schema on all three OS; actual
  SDK return retained, then a fresh verifier after fault removal. POSIX directory
  permissions and Windows no-delete-share handle must calibrate first.
- Real SDK 16 MiB uncommitted ledger write induces a DELETE spill/BUSY negative
  baseline control for each schema. **This does not claim natural schema6-open
  spill was reproduced.** No baseline-backed intent/decision or stale pre-open
  fallback is allowed on the unavailable-reader branch.
- Windows only: a native page1 byte-range lock, separate failed ReadFile, then
  actual IOERR from the fresh public SQLite verifier; consumer mmap0 is explicit.
  This is not attribution to the SDK rollback path and not Linux/macOS coverage.
- Typed serializer controls; retained source/unfinalized statement lifetime;
  hardlink and POSIX symlink/Windows reparse alias refusals.
- Content with equal ledger, storage type, rowid, trigger, index, unknown schema,
  FK damage; invalid stored PDF as a public SDK application-invariant refusal;
  real Python FTS virtual/shadow schema rejected by the SDK consumer.
- Truncated intent, equal-byte replaced baseline, foreign mutex nonce, absent or
  foreign target, late equal-byte intent/baseline replacement at final fence.
- Baseline/intent/mirror/mutation process-kill boundaries; failed evidence read,
  failed new decision creation, native existing-decision rename refusal, actual
  public SQLite query interrupt. The immutable consumer does not itself rename
  decisions; the rename test is accurately a native retention control.
- A real product v3 cancellation remains pending and unchanged even after a
  separate provisional comparison; normal current product COMMIT still releases
  its owned barrier and permits an ordinary writer, preserved by idempotent retry.
  Writer rendezvous also require a competing sidecar actor's exclusive-create
  attempt on the already-owned test mutex to fail without changing its bytes.

## Limits that remain even if every authored case passes

- Trusted stable directory/cooperating-process scope only. File identity/SHA and
  the separate test custody witness are **not cryptographic authentication** if
  an actor can replace the entire trust boundary. Identity rechecks are not
  hostile-between-check atomic filesystem CAS.
- The test-owned nonce mutex serializes this experiment's cooperating sidecar
  actors; SQLite's reservation alone does not fence arbitrary mirror writers.
  No claim that existing old binaries honor this new test protocol.
- POSIX file+parent-directory fsync is checked. Windows uses the inherited CRT
  `_commit` file-flush helper (not a directly instrumented FlushFileBuffers call),
  but parent-directory durability is not
  established and is reported false. Process-kill success is not a power-loss
  guarantee on any platform; Windows automatic-retirement admission is unearned.
- Native physical WAL failure on Linux/macOS remains unqualified. The DELETE
  unlink fault does not imply non-OK SDK rollback: the frozen SDK/SQLite can
  acknowledge success despite cleanup I/O. Logical recovery and physical cleanup
  are distinct; `physical_cleanup_verified=false` remains in every report.
- Close/decision uncertainty leaves evidence provisional. No product consumer
  interprets these receipts. Existing v3 lacks a complete baseline; it cannot be
  retroactively cleared from ledger equality or SDK OK. A future production
  state machine, protected custody, full supported-format traversal and platform
  durability need separate design/source review and integration authority.
- No new pass of the old 25/29/65/31/17 suites is claimed on this SHA. This isolated
  workflow does not replace or edit those gates. Full P0 remains false.

## Evidence contract

Each artifact includes source identity/exact five-path admission, complete build
logs, native provider map/closure, all child stdout/stderr outside denied fixture
directories, fixture/evidence bytes, executable hashes and `result.json` with
every expected case accounted for. Native fault calibration failures are red,
not skips. Cleanup attempts restore permissions/handles and preserve child logs;
failure is retained. Terminal run SHA, job/attempt, artifacts, exact pass/fail
scope and unexecuted stages will be recorded only from Actions results.
