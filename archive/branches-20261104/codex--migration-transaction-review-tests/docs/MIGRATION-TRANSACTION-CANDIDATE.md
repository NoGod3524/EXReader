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

Normal SQLite writers on the same database must honor SQLite locking, including
WAL mode. This does not constrain code which replaces, deletes or copies the
SQLite database or its WAL/SHM files. Stop all old file-replacement migrators,
keep the target path stable, and coordinate the app host lifecycle so no such
operations occur during or after migration. An SDK 3.40/schema-6-only client
cannot reopen an upgraded schema-7 library. The host must not automatically
restart an incompatible old binary. This is a host requirement, not an advisory
lock that prevents unrelated file replacement.

The candidate needs cloud results for the original checks, both schema versions,
real WAL, ordinary concurrent writers, crash recovery, ledger export/import,
rollback, retries, and actual host lifecycle before it can be accepted. macOS and
real user libraries must not be inferred from Linux or Windows. No result from
this candidate supersedes the retained earlier failure.
