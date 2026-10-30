# Apple mobile annotation lane — final closeout, 2026-10-29

Lane status: stopped after the current candidates reached terminal results. No next helper candidate, feature package, release, PR or default-branch merge is started. The fixed catalog stays **95/108**.

## Final tested source and scope

- Branch: `codex/apple-mobile-annotation-directory-resume-20261029`.
- Final tested source: `141304d36e451d34c2720f74ce0b3da4f412df3a`.
- Feature helper blob: `993b01d8d811cf47105086f0dc21fd167aec61b5`.
- Run: [40958251556](https://github.com/NoGod3524/EXReader/actions/runs/40958251556), attempt **1**, completed **failure**.
- This lane uses SDK **3.41.0**, ad-hoc macOS and iOS simulators. It is not the shared public SDK3.42 product candidate.
- The SDK jobs preserved the original five feature test bodies and Team24 driver by explicit baseline identity checks. The 24 interaction-attempt cap, 90-second helper wait and original 240-second test allowance stayed intact.
- Product source, SDK core, original 34 old cases and teardown termination were not changed.

## Final original producer evidence

All rows below belong to source `141304d36e451d34c2720f74ce0b3da4f412df3a`, run `40958251556`, attempt `1`.

| Host / gate | Job | Terminal result | Original case result |
| --- | --- | --- | --- |
| macOS SDK | 123743963551 | success | original SDK build and account terminal checks |
| iOS simulator SDK | 123743963146 | success | original SDK build |
| macOS native | 123750471241 | success | 39/39 = feature 5/5 + base 13/13 + control 13/13 + search 4/4 + theme 4/4 |
| iPhone native | 123750471325 | failure | 37/39 = feature 3/5 + all original 34/34 |
| iPad native | 123750471332 | failure | **unavailable**: no original native ZIP or completed result report was published |
| original ZIP authentication | 123795487452 | failure | whole-run authentication not accepted |

The iPhone producer result marks `testNativeAnnotationPreviewConfirmCancelAndDuplicate()` Failed at the four-minute allowance and `testNativeHistoryAfterFoundAndLargeRotationExit()` Failed with reported duration 3m16s. The other three feature cases passed. Its latest raw ZIP has been retained but a new independent raw-XCTest diagnosis of those two final failures was not completed. No passed result from an earlier source is transferred to this source.

The final iPad job metadata says completed/failure at 2026-10-29T23:28:48Z, while its native step remains in_progress and artifact-upload step pending in the returned payload. The completed-job log request returned GitHub BlobNotFound, and the run's complete artifact list has no iPad native ZIP. This is an evidence gap; the exact underlying job failure and case counts are unknown. No failure cause is invented and no rerun was made to replace the missing result.

### Final artifacts

| Artifact | ID | Bytes | ZIP SHA-256 |
| --- | --- | --- | --- |
| macOS native | 12937236043 | 315251067 | `57cbf50c8d8794a08935a4c12641351580fe3648fa1b6b4ab39f358fb2ceb87a` |
| iPhone native | 12939157786 | 470359292 | `17237d31e21df747d4baf771f918947886428aec9eef5e37746caabcedde6a18` |
| iPad native | not produced | unavailable | unavailable |
| macOS SDK | 12935421676 | 22415968 | `2119b2b0d451c7b18adb47698706725f4206e1629b524143980ec42c58a8f142` |
| iOS simulator SDK | 12934408734 | 22408136 | `4e8d2a5c5ba65513d92bb91ee0bc9c0c74adb6389e9d1fde3f4fa5d635e0dbf2` |
| original authentication | 12941990202 | 6183 | `b9d09cefb57ad22b8334f823c79912bb5c5f5cfbbf80b0fbcc4b361747f5150e` |

## Retained predecessor and diagnostics

First continuation source `fc336333cd67bf8871e2602777ec857312de06cb`, feature blob `f7a3ddefc25d7a901dc0ef810dc66d850b9cb20f`, [run40946665738](https://github.com/NoGod3524/EXReader/actions/runs/40946665738), attempt1, completed failure:

| Host | Job | Cases | Artifact | Bytes | ZIP SHA-256 |
| --- | --- | --- | --- | --- | --- |
| macOS | 123706425329 | 39/39 | 12932825603 | 315293952 | `c43d0068161a90893f0afbdf8b6fe3409fa9b3c6373f488a09153929fe23eabf` |
| iPhone | 123706425691 | 38/39; annotation case timed out | 12935408569 | 440064294 | `d6420ccbff6f312ec9f2e8461d04410d5963a7f28400186deec00ec72100b8dc` |
| iPad | 123706425461 | 38/39; annotation case timed out | 12934491128 | 479945377 | `cc696e4d3060c7e2a2c6cf2f55e283bd5e7323ff082cfe949e39d1fb37e6d90a` |

The predecessor's original authentication job `123757046722` failed. Its artifact `12935519031` is 8124 bytes with SHA-256 `59db1a60ab5bb75fd2ab84c478346522176c4e1cf707da638f5f0bec72f41341`.

Completed original-ZIP diagnostics, all run in Actions:
- [40946269661](https://github.com/NoGod3524/EXReader/actions/runs/40946269661), source `c8cb7ecf21973e0cec731048901e3ac763e59689`: authenticated both retained 55ec mobile ZIPs, parsed their original wave3 xcresults and exported attachments. It confirmed valid/invalid file selection had progressed beyond the old picker-root blockage. Both original annotation cases still exhausted the budget.
- [40957669683](https://github.com/NoGod3524/EXReader/actions/runs/40957669683), source `2384cbd0c7c591ed99c56f95fe69eab2d7661cb2`, job `123741867646`: authenticated the exact fc iPad ZIP and parsed its original xcresult. Inspection artifact `12934367542`, 16497930 bytes, SHA-256 `fb3b1b8a06b6e951680544fd2a935aa2df9a14390542b3c989a382a942ef4140`.
- [40957964706](https://github.com/NoGod3524/EXReader/actions/runs/40957964706), source `45a49ce266d4649d2c27a0ab5e1743dcffd674d5`, job `123742940671`: authenticated and printed the same retained fc iPad native log on Linux.

The fc iPad log shows all annotation assertions completed at t231.30s, including exact duplicate confirmation and retained reading position. Teardown then invoked the unchanged app.terminate; the log contains both a 245.241-second passed line and the timeout. The raw xcresult marks the case **Failed** at 240 seconds. The passed text was not accepted. Repeated coordinate-bound scroll resolutions motivated the final app-coordinate/fast-drag helper change, but that final candidate still failed on iPhone and lacks usable final iPad evidence.

Earlier retained source `55ec49020383ef5073f47502b300ab0b5d0a7cae`, run40935165396, attempt1 remains failed. Its iPhone original artifact `12928097306` is 436248547 bytes, SHA-256 `b7f3125fb508ecc417e59ca083f7ba89aa9e5308971c2aa483a1aab30adad7bb`; iPad artifact `12928855897` is 485229238 bytes, SHA-256 `6f576fe25c63e1ce2571c6672430d809da32eb269332143a9b24bcc483f86d02`. Original 622-source failure records are preserved in the handoff and prior continuation note.

The first diagnostic run40945989730 failed before parsing because inspect.py shadowed Python3.14's inspect module. The reader was renamed and successful diagnostic runs above preserve that history. A final iPhone read-only diagnostic preparation did not create a commit or run; the diagnostic branch was reread and remains at `45a49ce266d4649d2c27a0ab5e1743dcffd674d5`.

## Acceptance and stop boundary

- Source edits and their actual CI outcomes are recorded separately.
- No mobile annotation host acceptance or total-catalog increment is granted.
- No independent final-source acceptance exists.
- No physical-device, six-platform shared-source, complete-product, SDK3.42, F01/F07/F11 or release claim is made.
- The shared public integration branch has its own source and results, owned by the root agent; this lane never edited that branch.
- This closeout changes documentation only, with `[skip ci]`. Its commit is not the tested source.
- **Lane A has stopped.** No further helper candidate, producer retry, new work package or background wait is active.
