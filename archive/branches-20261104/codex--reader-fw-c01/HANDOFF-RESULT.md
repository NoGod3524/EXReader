# C01 HANDOFF-RESULT

Status: gate tool accepted; complete_product=false (by design: no product source, missing scopes).

- Branch: `codex/reader-fw-c01`, base `0889f7d1e9a537c6c1b05456547e016b26e1cd85`
- Tested source: `d222e2fcb41c2285065339ef654131313362ffb8` (docs-only seal commit follows it on the branch)
- Paths: `tests/reader_final_c01/` (final_gate.py, test_final_gate.py, summarize.py), `.github/workflows/reader-final-c01.yml`, `docs/reader-final-c01/` (README.md, run-table.json, validation.json), `HANDOFF-RESULT.md`. Nothing else touched; 12-slot collector unchanged.

## CI (3 of 3 rounds, all success, attempt 1)

| run | source | note |
| --- | --- | --- |
| 40213698559 | ecb8858e | protocol+collect ok; result JSON not shown in log, so no evidence readable |
| 40213898978 | 3e3ec116 | added summarize.py; real table collected, binary inventory logged |
| 40214238250 | d222e2fc | program hashes pinned from inventory; final run. jobs protocol 121231814803, collect 121231844305 |

Final result artifact: id 12607007028 `reader-final-c01-result-40214238250-1`, 17542 bytes, sha256 d1c9b1bdc10b5783694b9937da29f19edd686d326db46e63c06019a7ef239d40, expires 2027-01-23T16:58:49Z (not downloaded locally; content read from the run log).

## Results

- Synthetic protocol (protocol job): foreign source, run source, missing/mixed attempt, mixed-attempt job, window, missing/failed job, failed run, expired flag/time, API/declared digest, tampered ZIP bytes, wrong/absent program hash, report identity, duplicate artifact, simulator-only physical, unapproved budget, wrong SDK pair, one-way, missing scope: all refused.
- Real table, 6 entries authenticated live against original ZIP bytes (run/attempt/jobs/artifact ID/bytes/sha256/expiry): Windows compact 40201283788, GTK compact 40206458217, Android raw3 40207467982, macOS raw3 40196978163, Android->Mac receive 40210925809, raw metadata 40209325599. All `authentic_not_counted` ("product source not integrated"); real program hashes verified inside ZIPs for 5 entries (Windows EXReaderProduct.exe, Android host-debug.apk, Android->Mac android-peer apk+libexreader.so, GTK and macOS static libs); the modules entry declares none.
- Real negative: old failed run 40203714083 refused ("run did not complete successfully").
- Live derived controls from a real entry (all refused): foreign source, nonexistent attempt, missing job, wrong digest, wrong program hash, expired ZIP, simulator-only, budget unapproved, one direction only.
- Scopes: all 8 pending; complete_product=false, performance/physical/bidirectional false.

## Not verified / for root

- Set `product_source` after unified integration and re-run with the final run table (`workflow_dispatch` `run_table`, or edit `docs/reader-final-c01/run-table.json`).
- No evidence for sdk, performance, packaging, physical_device, apple_to_android, iOS host (only the failed run). GTK host executable and macOS app program hashes are not pinned (inventory catches only recognized binary extensions; GTK/macOS pins here are libraries).
- No owner defect detected; no owner code changed. No PR, default-branch push, tag or Release.
