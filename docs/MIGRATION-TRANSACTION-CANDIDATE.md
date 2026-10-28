# SDK 3.42 transaction migration candidate

This isolated branch is an experimental candidate, not a release or a safety
acceptance. Frozen SDK commits and the earlier failure run
[40629804211](https://github.com/NoGod3524/EXReader/actions/runs/40629804211)
remain unchanged. The original migrator remains present and retains its known
file-replacement race; do not use it concurrently with a writer.

The separate `exreader-legacy-migrate-tx` executable uses candidate SDK 3.42,
ABI 1. Its migration owner takes a SQLite write transaction before opening and
upgrading schema 6, uses savepoints for SDK operations, and stores the migration
ledger inside the same database transaction. The first transaction can import a
prior `.legacy-map.json` when no internal ledger exists. Afterwards the database
ledger is authoritative; `export-ledger --target LIB --output NEW_FILE` exports
compatible JSON for review. Do not treat an old sidecar as current after that
point. This interface and its handling of failures are under validation.
For a new target, the candidate creates a private stage and publishes it only
after commit using a no-overwrite operation. An abruptly terminated process can
leave a `.migrating-*` stage; the tool does not automatically delete an
unowned stage. Retain it for diagnosis and remove it only after confirming that
no migration process owns it. An existing target is never replaced by this
candidate.

Normal SQLite writers on the same database must honor SQLite locking, including
WAL mode. This does not constrain code which replaces, deletes or copies the
SQLite database or its WAL/SHM files. Stop all old file-replacement migrators,
keep the target path stable, and coordinate the app host lifecycle so no such
operations occur during or after migration. An SDK 3.40/schema-6-only client
cannot reopen an upgraded schema-7 library. The host must not automatically
restart an incompatible old binary. This is a host requirement, not an advisory
lock that prevents unrelated file replacement.

The existing GTK owner calls `exr_library_open` from `linux_reader_open` in
`examples/linux/reading.c`; it drains reader-owned sessions, closes the SDK
library and releases its product lock in `linux_reader_close`. Apple opens its
owner in `examples/apple/HostSDK.swift`; Android opens it in
`examples/android/app/src/main/cpp/exreader_host_jni.c`. None currently invokes
the transaction migrator or waits for it before opening. A product integration
must stop new work, drain and close the actual owner and its readers, run and
observe the migration result, then reopen and refresh the owner before admitting
work. Account/sync and other processes which replace library files must also be
stopped. The product locks currently in hosts are not a substitute for this
lifecycle integration and do not bind arbitrary SQLite clients. This lifecycle
is not implemented or accepted by the candidate workflow yet.

The candidate needs cloud results for the original checks, both schema versions,
real WAL, ordinary concurrent writers, crash recovery, ledger export/import,
rollback, retries, and actual host lifecycle before it can be accepted. macOS and
real user libraries must not be inferred from Linux or Windows. No result from
this candidate supersedes the retained earlier failure.

## Evidence and unresolved gate

Push run [40634335005](https://github.com/NoGod3524/EXReader/actions/runs/40634335005),
attempt 1, tests `be684cde87f0d00d0d5116c9f413f8bfa33a3011`. The Linux job
passed the transaction checks for schema 6 and 7 in rollback-journal and real
WAL mode, including blocked ordinary writes, later committed writes, failure,
process death before and after commit, retry, and refusal of a damaged internal
ledger. It also passed new-target crash/retry and full JSON ledger export and
idempotence checks, and the actual GTK reader backend open/close/reopen probe
with page background enabled. The original executable separately passed its
65 scenarios/135 checks, 31 review checks and 17 browser checks. The unchanged
65 scenarios run against the transaction executable passed only 52 and failed
13; the Linux job is therefore red. Windows passed its transaction step and
original executable scenarios and review checks; its browser and unchanged
candidate scenarios were still running when this record was written. macOS
was queued.

Some failed assertions require an automatically maintained external JSON
sidecar, a replaced stage, or an explicit retained pre-image after simulated
file rollback. The candidate instead has an authoritative SQLite ledger, an
explicit JSON export, and no replacement or file pre-image for an existing
target. Other failing checks include legacy migrator lock and fault-reporting
expectations. The unchanged assertions have not been altered or granted by
the newer transaction tests. In particular, the separate GTK probe is not an
integrated host entry point, and Apple/Android/Windows host lifecycles remain
unverified. A reviewable compatibility and acceptance mapping, remaining
candidate behavior, and actual host orchestration are still required.

The follow-up [run 40635037173](https://github.com/NoGod3524/EXReader/actions/runs/40635037173),
attempt 1, tests `270468c283f615d644312734185af58d4baa6f32`. Its Linux job
passed the four schema/journal transaction cases, new-target crash/retry, full
ledger export/idempotence, and the GTK backend lifecycle beginning with a real
SDK 3.40 schema 6 library; it also passed the legacy executable's 65/135,
31 review and 17 browser checks. The same job failed the unchanged candidate
scenarios at 52/65 (111/128 recorded assertions). The Windows job was still
running and macOS queued when this was recorded. These results do not grant
final acceptance or product UI integration.
