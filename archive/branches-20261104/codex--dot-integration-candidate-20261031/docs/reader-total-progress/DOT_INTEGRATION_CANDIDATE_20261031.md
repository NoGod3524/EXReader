# Independent integration candidate
Base c44a9cf211fffa4ed6f2720ffa49a186c3b4d196. Five minimal product deltas and 16 frozen evidence files are pinned in manifest.json.
Seven jobs: F10 2x30; WebDAV 2x90; F09 90; H02 probe15+host180 =525 runner minutes. One initial round and at most one evidenced correction.
Original package guards are frozen, not claimed passed. Independent admission checks complete paths, exact product SHA256, unchanged tests and provider; all other SDK/product paths remain base by full allowlist.
F09 entry explicitly binds original run/diagnostic_overlay/crash_events/ROOT/OUT/BASE8f8acf. Copies the unchanged execution body except independent guard and current-source OPDSHash build dependency; original main/guard are not invoked or monkeypatched. Four observations and all failure assertions remain. Provider overlay is Actions detached-test-only.
WebDAV fixed SDK3.40 compatibility is separate from SDK3.42. Persistent cleanup unresolved; managed F09 AV retained; no formal promotion. H02 old failed runs preserved. No external branches changed. F03/F08, Apple full19, C02/H/J excluded.
No local builds/tests/ZIP parsing. Pending independent review before staging/push/CI.


## Initial same-source matrix receipt (2026-10-31 04:47 UTC)

This is a continuity backup, not completion or formal acceptance. Formal ledger remains 95/108; no points added.
Tested source: `8232e91cd7b9296dfcdd3096b96317eb3fa1008a`; base `c44a9cf211fffa4ed6f2720ffa49a186c3b4d196`.
[Run 41168991160 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41168991160): FAILURE, completed 04:38:56Z, six successful jobs and one failed job. Seven-job cap 525 runner-minutes. Initial round consumed; at most one evidence-based correction remains unused. Known managed failure is not a reason to spend it on an unchanged rerun.

| Lane | Job | Result and evidence |
|---|---|---|
| F10 Linux | 124442651038 | success: original 25 checks, six POSIX cases, LF parser 1 positive/4 negative; raw archives equal, zero differing bytes |
| F10 macOS | 124442650840 | success: same checks; scoped ZERO_AR_DATE recipe retained; raw archives equal |
| WebDAV Linux | 124442651063 | success: original cloud-import 47 and TLS 77; seven cleanup cases |
| WebDAV macOS | 124442651072 | success: original 47+77; GNU-specific seven-case probe correctly skipped |
| H02 probe | 124442651152 | success, metadata/step result verified; sensitive logs not read |
| H02 actual host | 124442756599 | success, build and actual account-dialog step green; no new numerical count inferred from unread report |
| F09 four consumers | 124442650995 | failure at strict final aggregate, not admission/build |

F09 original job text, not artifact inference:
- baseline-managed: 04:36:31.5441599Z System.AccessViolationException.
- candidate-managed: 04:36:32.2346861Z System.AccessViolationException.
- baseline-native: 04:36:37.510Z HRESULT/assertion-failure.
- candidate-native: 04:36:38.167Z all-assertions-passed.
- f09_driver.py line112 preserves the assertion that native cannot override managed; total remains red. No managed root cause or full F09 acceptance is claimed.

WebDAV transient EIO/EINTR cases each made two unlink attempts and left zero residue. Persistent EIO and actual EACCES(13) made two attempts but retained one same-inode/nlink2 name while OK/pub1 remained intact. product_cleanup_passed=false and crash coverage=false remain explicit. SDK3.40 frozen import-compatibility lane is separate from SDK3.42 and is not six-platform same-SDK proof.

Independent reviewer review_native_journal_contract read metadata, admission scope, F10/WebDAV safe logs and artifact metadata; writer read only F09 failed text. No ZIP downloaded/parsed outside Actions. No H02 sensitive logs read.

### Artifact identity (all source 8232e91c, same run/attempt, unexpired at read)

| Artifact | ID | Bytes | SHA256 |
|---|---|---:|---|
| F10 Linux | 13030641312 | 775946 | 1e285db6de499db0126c4ac707a934b627fc9ec8357bf2d9cba69cbfe591b31c |
| F10 macOS | 13029804244 | 855597 | 7a61b9a716d4eef1f5c210700f48cd8d544e8ec3e2a8d1706c11d597dbbb8913 |
| WebDAV Linux | 13030621287 | 12586945 | cdae2391d3f8941535b18408a14b5a1d8084590b4f655dc53ed203b471cfa929 |
| WebDAV macOS | 13030720168 | 10776079 | 447840b9d587482cf7cf7539c1979cb453a0b142444127d09b7aeb36ba66328f |
| F09 | 13030621485 | 29389 | 75d09bc34e1058fb0ceef9278bf6c3bc7b67248b9469c3c3a7cda5712cfbf798 |
| H02 probe | 13030496337 | 832 | a7acb9ddc3b8219478856df8d66f9423135b2b6edd54b3843edf7acad2bc836c |
| H02 host | 13030431962 | 2115 | 21310b6d9a064ef8eeb30a52c22bbef8a4655c7a61408c8d7d3f62a9929d072b |

Next: preserve this exact tested SHA as the integration candidate. Resolve managed UIA failure under its separate owner and explicit scope before considering an evidence-based correction; retain persistent WebDAV/crash limitations. F03/F08/Apple/C02 and external in-flight H/J work were not combined. A later documentation-only commit must not be described as tested product source.
