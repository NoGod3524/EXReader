# C07 independent paging evidence audit, 2026-10-30

Base: 2b5222ad2af4c92e7f239d6ab4d355fba6859974.
Branch: codex/dot-c07-paging-audit-20261030.
Owned additions only: scripts/audit/dot_c07_paging_audit_20261030.py,
.github/workflows/dot-c07-paging-audit-20261030.yml, this document.
The legacy auditor and its original 97 controls/restore8 rules are unchanged.

## Pinned producer
Source 7f15fe49374cd9389e2106837351d4bbd5e56113.
Run 41134343005 attempt 1; artifact 13016305109.
Original ZIP: 1011359 bytes,
SHA256 0c926a7cdc47e6a870d0ee237c6c3de4b3e794713f9d8f7d0c2db03f4b76ba38.
Its preserved 29 metadata + 8 GTK + 9 installed synthetic API checks passed.
This is not a claim that the new independent audit has passed.

## Audit contract
One authorized push/run with two jobs; no automatic retry.
The audit job runs original 97 controls and separately 30 additional controls,
then authenticates the exact completed producer run/attempt/artifact.
New negative controls recompute file hashes to reach semantic rejection rules.
Strict ZIP screening precedes the old extraction, rejecting duplicate raw names,
canonical path collisions, traversal, absolute paths and symlinks. Original
500-member/256MiB limits remain. Redirected downloads remove Authorization.

The original ZIP is retained after fixed byte-size/digest verification. The
auditor checks source-bound manifest hashes, nine ordered call receipts,
102 typed-command setup receipts and read-only immutable SQLite contents:
51 deleted synthetic books, 102 retained wire revisions with exact byte hashes,
PUT -> DELETE parents and 102 untouched outbox records. No SDK mapping is claimed.
SQLite uses extension loading disabled and trusted_schema=OFF.

The rehash job downloads the exact audit artifact ID emitted by the first job
within this run, and independently rehashes retained original.zip. It does not
download a replacement producer ZIP. Failure receipts upload with always().
Every syntax check, control, SQLite operation, ZIP download and parse runs only
in GitHub Actions. The cloud machine only edits source and reads git/log metadata.

## Limits
API JSONL is producer observation, not independent API re-execution.
SQLite consistency cannot establish execution chronology.
Synthetic paging is not GTK behavior or SDK-original proof.
Legacy restore8's restart/sort assertions retain the prior documented limits.
No full F05, six-platform, physical-device or production P0 acceptance is granted.
Formal acceptance remains 95/108. Original failures and prior candidates remain.

## Pre-run review correction
The database contract is schema version 3 after the producer's exact 001/002/003 migrations, not initial schema version 1. Synthetic controls execute those pinned SOURCE migrations in Actions; no hand-written substitute schema. The audit rejects Boolean substitutions for integer limits, found fields and gate references. Original 97 controls and paging 30 remain unchanged; three separately reported database negative controls cover deleted-state drift, a foreign parent with recomputed wire hash, and a mismatched raw body hash. Fixtures construct mutations before INSERT and retain all original immutable triggers. This remains candidate-only evidence, not acceptance promotion.
