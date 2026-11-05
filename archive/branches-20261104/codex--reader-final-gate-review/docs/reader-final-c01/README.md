# C01 final-product evidence gate

Independent verifier above the existing 12-slot native collector (`tests/reader_hosts_341/aggregate_native.py`, unchanged). It reads a root-supplied run table (`run-table.json`, schema 1) and grants nothing without live GitHub evidence.

## What one entry must prove (`authenticate`)

- the run exists, `head_sha` equals the declared `source_sha`, workflow path matches, run completed `success`, declared attempt exists;
- the jobs of **that attempt** include every declared job, all `success`, all share source/run/attempt, no hidden failed step;
- each declared artifact belongs to that run and source, is not expired, API digest and byte size equal the declaration, and its `created_at` lies inside the attempt's job window;
- the original ZIP is downloaded in Actions and its byte size and SHA-256 equal the declaration; declared `programs` (member -> SHA-256) and `reports` (identity fields) are checked inside the ZIP.

Nothing from different sources, runs, attempts or jobs is combined into one entry.

## What a scope needs (`classify`, `evaluate`)

Scopes: `sdk`, `modules`, `host`, `bidirectional`, `default_ui`, `performance`, `packaging`, `physical_device`. A scope is `verified` only when every cell (platform or direction) has an entry that is authentic **and** has an allowed kind **and** source equals `product_source` **and** declares verified program hashes. `physical_device` accepts only `kind: physical_device`; `performance` also needs an approved budget (`budget.approved` + SHA-256); `bidirectional` needs both `android_to_apple` and `apple_to_android`; `sdk` needs the approved 3.41 / frozen 3.40 SDK pair. `complete_product` is true only when `product_source` is set, every scope is verified and there are no problems.

## Refusals exercised

Synthetic (`test_final_gate.py`): foreign source, run source, nonexistent/mixed attempt, mixed-attempt job, artifact outside the attempt window, missing job, failed job/run, expired flag/time, API digest, declared digest, tampered ZIP bytes, wrong program hash, absent program member, report identity, duplicate artifact, simulator-only physical, unapproved budget, wrong SDK pair, one-way only, missing scope.

Live (`--derived-controls`): the same checks applied to mutations of one real entry, plus the real old rejected run 40203714083 as read-only negative control.

## Use

Actions only (`reader-final-c01.yml`, push to `codex/reader-fw-c01` or dispatch with `run_table`). Exit 0 means the gate behaved; add `--require-complete` to also demand `complete_product`. Round 1 inventories binary members (`binaries[]` in `result.json`) so root can pin program hashes into the table.
