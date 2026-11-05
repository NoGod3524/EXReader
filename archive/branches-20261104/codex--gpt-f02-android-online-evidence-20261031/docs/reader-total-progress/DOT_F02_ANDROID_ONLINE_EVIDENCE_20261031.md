# F02 retained Android online evidence: completed diagnostic

Result: retained artifact authentication and parsing **completed successfully**. The original F02 product run remains **failed**, F02_accepted=false, formal **95/108**. This diagnostic did not run the product.

## Fixed identities and scope

- Diagnostic tested source: [`9eb960de8ed9b1e755f3446844e85d36f40750bf`](https://github.com/NoGod3524/EXReader/commit/9eb960de8ed9b1e755f3446844e85d36f40750bf).
- Exclusive branch: `codex/gpt-f02-android-online-evidence-20261031`.
- Fixed parent: `f47f7c374524d2774e9a61cba44f63a5b7580916`, the document-only F02 failure seal.
- Original product source: `fe947bec25a56f40538677ffa9fb2a5e1e351b08`; original failed run41233481729/A1, Android job124632394760.
- Diagnostic [run41235413651/A1](https://github.com/NoGod3524/EXReader/actions/runs/41235413651), job124638035902 `diagnose`, completed/success. Push event2026-10-31T19:41:41Z; job interval19:41:43–19:41:53Z.

The tested diagnostic adds exactly these three paths; all product, SDK and old-test blobs remain unchanged:

- `.github/workflows/dot-f02-android-online-evidence-20261031.yml`
- `tools/reader_composition/f02_android_online_evidence_20261031.py`
- `docs/reader-total-progress/DOT_F02_ANDROID_ONLINE_EVIDENCE_20261031.md`

The later [skip ci] seal changes only this document. Its SHA is a documentation identity; the diagnostic's CI identity remains9eb960de8ed9b1e755f3446844e85d36f40750bf.

## Authenticated original input

The only downloaded project artifact was [receiver13054812884](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054812884), `f02-android-receiver-41233481729-1`,20160253 bytes, SHA-256 `f0370e0f441a6f34b764bb2e3e1be420d0f88106614684dc79525e5ccd1180a4`.

Actions verified the exact failed run/attempt/source, Android job and artifact metadata, then original ZIP bytes and digest. The parser rejected unsafe paths, case aliases, duplicate members, encrypted/symlink/special entries and unbounded decompression; it checked member lengths/CRCs and recorded member hashes. No ZIP entry was extracted or executed. Embedded producer, build and online-report identities agree withfe947bec /41233481729/A1.

The ordinary log reports `artifact_verified=true` and `diagnosis_completed=true`. This means the retained evidence was authenticated and read; it is not a new runtime acceptance or independent replay of product assertions.

## Exact observed failure boundary

The original online report records these completed checks:

| Check | Recorded result |
|---|---|
| strict_sdk342_shared_provider | passed |
| fresh_activity_empty_sdk_and_mapping | passed |
| actual_sync_scans_sender_wire_without_import | passed |

The active failed check is **`corrupt_original_rejected`**, exception class **`AssertionError`**, online_passed=false, completed_count=3.

The frozen test groups corruption setup, receive, waiting for the integrity-failure status and the empty-library checks under this name. The original report saved only `failure_type` and `active_check`; it did not save the inner exception message or stack. Therefore the artifact identifies this check group but does not identify its exact failing call or inner assertion. It does not establish whether the cause was a status wait, an empty-library check or another statement in that group.

Raw `proc-online.txt` **exists**: PID2392, all four UIDs10141. These values match the online report. Raw native evidence SHA-256: `deaa7079c57a5ee87f77d63bb9008d35810992f8f37a76cd8593785566b0896e`. In the original run.py:58 conjunction, native evidence is therefore present and online_passed is false.

The raw instrumentation text contains final **`INSTRUMENTATION_CODE: 0`** and `F02_ANDROID online checks=3 passed=false`. The original Java harness uses its failed-phase finish branch. The adb subprocess return code was not persisted separately; the producer's earlier guard required returncode==0 before reading this report. That subprocess fact is an inference from fixed producer control flow, not a separately retained numeric observation.

Exact inner assertion text and stack are **insufficient evidence**. Emulator boot/offline warnings are not assigned as root cause. Offline and second offline-process phases were not reached; the original12 independent mutation controls did not execute.

Only fixed identities, known check names, numeric process/result values and a bounded exception class are published. Arbitrary report strings, URLs and credentials are not echoed.

## Diagnostic artifact and budget

[Artifact13055233340](https://github.com/NoGod3524/EXReader/actions/runs/41235413651/artifacts/13055233340), `f02-android-online-evidence-41235413651-1`, contains `summary.json` and `inventory.json`.

- ZIP2489 bytes.
- SHA-256 `1e53b0a13ae97785e75bf97c3bec6cef71a68973697f14b0afd1399316b477e2`.
- API expiry2027-01-29T19:41:41Z; unexpired when sealed.
- Upload log and API ID/bytes/digest agree.

Authorization was one Ubuntu job with15-minute ceiling, one attempt. The one slot is consumed; actual job interval10seconds, API run duration13seconds. No rerun, rebuild, emulator, product execution or DAV/network replay occurred. No correction is authorized by unused time.

Source/Git/docs remained on the approved lap25002 native terminal -> normal saved official instabox@0.8.52 -> existing VM m_agqxv2s72g5vwdtsifu5cnmml4. All syntax and original ZIP operations ran in Actions. Desktop Commander was unused.

The two earlier document publications are complete: F02 failure seal f47f7c374524d2774e9a61cba44f63a5b7580916 and independent continuity snapshot [fb942660c7efcaf3d415fc4281d8d32c02f70c44](https://github.com/NoGod3524/EXReader/blob/fb942660c7efcaf3d415fc4281d8d32c02f70c44/docs/reader-total-progress/EXREADER_C02_WEBDAV_HANDOFF_20261031.md), each single-document [skip ci] with zero added CI.

Any product/harness correction or new runtime evidence needs a new explicit scope and budget. The original failed run and all six artifacts remain. Formal95/108 and external owner scopes remain unchanged; no main/shared branch, PR, tag or release was changed.

Evidence document prepared at 2026-10-31T19:44:03.472709+00:00 / 2026-10-31 15:44:03 EDT.
