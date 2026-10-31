# F02 Windows to Android: sole first-run evidence

Result: **failed; candidate not accepted**. Formal progress remains **95/108**. This document seals the result of the one authorized round; it does not authorize a correction or another run.

## Fixed identities

- Exclusive branch: `codex/gpt-f02-win-android-transfer-20261031`.
- Tested source: [`fe947bec25a56f40538677ffa9fb2a5e1e351b08`](https://github.com/NoGod3524/EXReader/commit/fe947bec25a56f40538677ffa9fb2a5e1e351b08).
- Source parent/base: `f59425f00af9069a22dc9cef2399ae84e3a62648`.
- SDK: `8357eafa28423a7ab93ba08b823af80f01ad1505`, 3.42.0 / ABI1. The C02+WebDAV SDK7271829 was not substituted.
- Exact11 manifest: [`source_lock.json`](https://github.com/NoGod3524/EXReader/blob/fe947bec25a56f40538677ffa9fb2a5e1e351b08/tests/reader_f02_win_android_20261031/source_lock.json).
- Production MainActivity.java blob: `c98cb87a86ab95ae9498cf9ab5dce68e9c4dd369`.
- Production BookStore.java blob: `be6dc75e0f77d0a975c21dc7dddeea31b46d5d81`.

The source commit changes exactly the two Android production files, the eight approved harness/workflow paths, and this document. JNI, SDK, existing tests and old assertion bytes remain frozen. A subsequent document-only [skip ci] seal has the tested source as its parent; it must not be used as a replacement test identity.

## Actual Actions result

[Run41233481729 / attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41233481729) was triggered once by push at2026-10-31T19:17:09Z. It completed **failure** at19:25:24Z. There was no rerun or workflow dispatch.

| Job | Actual result | UTC interval |
|---|---|---|
| admission124632309554 | success: new Python syntax, exact11/source guards, fixed SDK trees and original Windows sender identity verified | 19:17:11–19:17:31 |
| android124632394760 | failure: SDK/app/test build accepted; first online instrumentation phase failed | 19:17:34–19:25:12 |
| authenticate124634220221 | failure: refused failed Android prerequisite | 19:25:14–19:25:23 |

The ordinary build log records `F02_ANDROID_BUILD accepted=true`, fixed SDK8357/3.42.0, preserved original assertions and matched app/test outputs:

| Build output | Bytes | SHA-256 |
|---|---:|---|
| host.apk | 27439236 | `f8dd190f68b0554a1acdbc32460fd9b2605c1ee5ed6d01eb8e4e43f91b8f775b` |
| test.apk | 261052 | `cb5993c89a92f32520744840e00157a89c398b5fc6da531a556d2847d0b7656e` |

These are build identities; a complete successful runtime APK/provider proof is not claimed.

At19:25:01Z the producer emitted `accepted=false, safe_upload=true, phases=1, F02_accepted=false`. The traceback stops at `instrument('online')` in run.py:120 and the condition `native is not None and value['passed']` at line58, with `AssertionError: actual online checks`. The downloaded ordinary log does not expose the individual failed Java check. Its underlying online report/instrumentation output is preserved in the receiver artifact as `online-report.json` and `online-instrumentation.txt`.

The run did **not** reach the offline or second offline process phases. Expected20 checks are not reported as20 passes; their complete execution was not established. The independent ordinary log records `passed=false`, `errors=["AssertionError: upstream android"]` and `F02_accepted=false`. Its12 semantic mutation controls did **not** run, because the prerequisite failed before ZIP re-verification.

## Preserved original artifacts

All six artifacts below belong to exact source fe947bec25a56f40538677ffa9fb2a5e1e351b08, run41233481729/A1. API metadata and ordinary upload logs agree. They were unexpired at this seal, with API expiry2027-01-29T19:17:09Z. No artifact was deleted or overwritten.

| Artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| f02-android-input-41233481729-1 | [13054437090](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054437090) | 12687486 | `f27ab7903ae2c1214a7570ef7de91404a19cc5a6e90377ee7de500ec2a614c69` |
| f02-android-admission-41233481729-1 | [13054526664](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054526664) | 622 | `2fc6c34dd9fac52a8afdb07cf02cbb8dfcceaeb72ca33e26dcc35a5951debec1` |
| f02-android-receiver-41233481729-1 | [13054812884](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054812884) | 20160253 | `f0370e0f441a6f34b764bb2e3e1be420d0f88106614684dc79525e5ccd1180a4` |
| f02-android-build-41233481729-1 | [13054842797](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054842797) | 20119609 | `b986362ab766371a0b0d1759bc7c23c0f70d96f0dd1ae20087207e2aa664df48` |
| f02-android-status-41233481729-1 | [13054907670](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13054907670) | 296 | `7ab66d61a99e088b93cc1353c57dcfeabbb070fa9ae3ed477af858ea0e6b5eff` |
| f02-android-independent-41233481729-1 | [13055221098](https://github.com/NoGod3524/EXReader/actions/runs/41233481729/artifacts/13055221098) | 319 | `4871495df04e7c6d164871236eee7056a9e05173b5f0d2353dee3bbffa0d9941` |

The independent319-byte ZIP is a failed prerequisite summary, not a successful verification archive. Receiver evidence was uploaded only after its generated-credential scan passed. Artifact ZIPs have not been downloaded, unpacked or parsed locally or in the VM.

## Implementation and reused input

The two production edits prepare a verified private TXT reading copy from the existing SDK original on its owner thread. A unique staging file stays unpublished until the existing HostTask page publication transaction; cancellation or abandonment removes only its own staging file. The canonical verified reading copy and host path preference publish inside that transaction. Copy recovery does not import another SDK book, generate a product revision or send PUT. The build passed; this first run does not establish the complete runtime behavior.

The original real Windows sender input remains separate from the current consumer identity:

- Source `3b416378337a73c62423857e4340d469d357038d`, seal/base `f59425f00af9069a22dc9cef2399ae84e3a62648`.
- Successful original run41169386789/A1; sender artifact13030748486, `f02-windows-41169386789-1`.
- Original ZIP6354365 bytes, SHA-256 `4771f705c20c7230e13a193cbf44eb8b0c3a03ea4da208fbef26ad82fa033a8a`.
- Original TXT12000 bytes, SHA-256 `5f00b41f874d60348d6dc237873759906e5f0ed28b05bb399a6699bbc3c7b38f`; cross-host key uses format plus raw SHA, not a shared local SDK row ID.

Admission reauthenticated that original ZIP using the frozen original verifier. The Android fixture restores only the archived byte-identical Windows PUT store under fresh private HTTPS credentials. This is not a fresh same-source Windows execution or evidence of a continuously online Windows service.

The new adapter derives required commands from the frozen D22 recipe and explicitly supplies3.42.0 for SDK/module/Gradle inputs. The original D22 suite allows3.40/3.41 and EPUB; it was not weakened or falsely claimed passed in full. Its original page-themeOFF and3.41 gate are unchanged.

## Budget, route and continuation boundary

Authorization: one round, admission10 + Android60 + independent15 = **85 runner-minute ceiling**. That single slot is consumed. Actual job intervals total487seconds, approximately8.12 elapsed runner-minutes; API run_duration_ms=495000 is8.25 wall minutes. The timing endpoint reports zero billed UBUNTU milliseconds, which is billing metadata rather than a statement that the jobs took no time. Unused time under the ceiling does not authorize another round.

All source/Git/docs operations used lap25002 native terminal, saved normal official instabox@0.8.52 and existing machine m_agqxv2s72g5vwdtsifu5cnmml4. The reviewed source was committed and pushed through that verified route. Desktop Commander remained blocked and unused. All builds, syntax checks, fixture creation, tests and ZIP handling ran only in GitHub Actions.

Next action requires a separately approved bounded Actions diagnostic to inspect the retained original receiver ZIP, identify the failed online case and decide whether a harness or production correction is necessary. No correction or additional CI was attempted under this first-round authorization. Retain all six artifacts and the failed run.

Formal F02 still requires its original six-target coverage and the required common upload/download/open loops across real host applications. This failed archived-Windows-to-Android-emulator slice does not establish physical Android, six-target acceptance, a common new-source Windows producer, complete20-check runtime success or12-control independent acceptance. The authoritative catalog was not edited; formal95/108 remains. External UI/F08/F09/Apple/C02 owner scopes remain untouched. No main/shared branch, PR, tag or release was created.

Evidence document prepared at 2026-10-31T19:28:39.267433+00:00 / 2026-10-31 15:28:39 EDT.

## Approved passive observation round (2026-10-31)

Status: sole observation round completed/failure; actual evidence follows. The earlier failed run above and its original artifacts remain unchanged. New exclusive branch: codex/gpt-f02-online-observation-20261031, fixed parent f47f7c374524d2774e9a61cba44f63a5b7580916. Product source/blobs remain fe947bec25a56f40538677ffa9fb2a5e1e351b08; SDK8357eafa28423a7ab93ba08b823af80f01ad1505 remains fixed.

Only six paths may differ from that parent: F02ReceiveTest.java, run.py, source_lock.json (branch identity only), fetch_sender.py (budget metadata only), the existing dot-f02-win-android-transfer workflow and this document. No product, SDK, build adapter, init.gradle or independent verifier change is authorized.

Observations add named substeps, fixed assertion-reason enums, filtered test method/line frames, status categories, published panel eligibility, SDK counts from the original owner query and transport-cache metadata. UI observation waits at most200ms; an optional post-failure SDK count uses its owner and a2-second wait, marks unavailable on timeout, and never interrupts host work. They preserve the original corrupt check body, all original need conditions, polling/timeout values and the12000-byte first-byte XOR1 response. Observer capture failures remain optional evidence, not replacements for product assertions.

Server evidence distinguishes marker consumption, authentication and successful corrupted-response send. Per-phase process evidence records adb return code, instrumentation code, native evidence presence and Java phase result before the original combined guard. Runtime endpoint bytes join the existing private-output scan; raw logcat text is replaced by bounded hash/size and filtered test frames. No arbitrary exception message, credentials or raw runtime URL is published by new observation records.

The one approved observation uses one Ubuntu job with30-minute ceiling, initial attempt only, no automatic correction/rerun. Source admission, original sender authentication, unchanged SDK/app build and original driver run in that job. Original20 assertions remain in the driver; completion is measured, not assumed. The12-control independent audit is not scheduled by this observation workflow. Actions alone perform syntax/build/test/fixture/ZIP operations. After terminal results, only this document may be sealed [skip ci]. Formal95/108 remains.

## Actual passive observation result

The sole observation [run41237500791/A1](https://github.com/NoGod3524/EXReader/actions/runs/41237500791) completed **failure**. Tested observation source is [bea7e55a7843091f006e9dfeca20d21e4f6adbdb](https://github.com/NoGod3524/EXReader/commit/bea7e55a7843091f006e9dfeca20d21e4f6adbdb), parentf47f7c374524d2774e9a61cba44f63a5b7580916. Product source/blobs remainfe947bec25a56f40538677ffa9fb2a5e1e351b08; SDK8357 remains fixed. The later document-only [skip ci] seal is not a replacement CI identity.

One Ubuntu job124644248033 ran2026-10-31T20:08:41Z–20:15:41Z:420seconds,7.00 elapsed runner-minutes. API run duration423seconds. One of one30-minute slots is consumed; no correction/rerun occurred.

Source admission, new Python syntax, original Java assertion/timeout/polling/corrupt-body guard and SDK/app/instrumentation build passed. The ordinary build report records SDK8357/3.42.0, host.apk27439240 bytes SHA-256 `f2236549dda67320d0e425847b63a02ae74d6089e0eb51d40d681b709ecee2bc`, test.apk264756 bytes SHA-256 `9a7e9695c94302edb2db184b7ea4c5d3f1a4a3f06360233f22cac5c65786bbd1`. Production MainActivity and BookStore blobs still match the two fixed identities above.

### Failure and actual preconditions

The failed check remains `corrupt_original_rejected`; the new substep is **`wait_integrity_status`**, reason **`ui_target_timeout`**, exception classAssertionError. Filtered test frames identify `until:196 -> status:208 -> online lambda:300`. A timeout snapshot records120767ms since the check began. The original120-second wait and expected integrity-failure substring were retained.

The ordinary observation log records:

| Point | Actual evidence |
|---|---|
| Before setting corrupt mode | cache_exists=true; regular file;12000 bytes; SHA-256 `5f00b41f874d60348d6dc237873759906e5f0ed28b05bb399a6699bbc3c7b38f`, exactly the valid original |
| Published remote row before receive | busy=false; target_present=true; receivable=true; selection4; deleted=false; revision_present=true; bytes12000; local_id0; TXT and expected SHA match |
| Timeout/failure | status categoryreceived; same valid cache bytes/hash; local_id1 |
| Post-failure SDK owner sample | books1; sdk_sample=owner_read. This is a passive sample, not an executed empty-library assertion |
| Fault injection | fault_observations=[]; mode marker still exists at timeout/failure. No mode_consumed or corrupt_sent event was recorded |

The observed valid-cache precondition and unchanged [SyncOriginal.receive](https://github.com/NoGod3524/EXReader/blob/fe947bec25a56f40538677ffa9fb2a5e1e351b08/examples/android/app/src/main/java/org/exreader/host/SyncOriginal.java#L23) point to the valid-cache return before network fetch. The download-negative preparation therefore did not establish a cold cache, and its fault injection branch was not reached. Waiting for an integrity failure while a valid cached original is received explains this round's assertion timeout. This is a source-supported interpretation of the observations; no production branch hook was added.

The evidence does not identify which earlier operation populated that cache. It does not test corrupt-byte rejection on this round's download path. No test precondition, original assertion, response byte mutation, product code or SDK was corrected after the result.

### Process/result separation

The online adb subprocess return code is directly recorded as **0**. Native evidence is present, SHA-256 `2dffa49ed0059cc53a0fddeff69f04133c6e493fe78bd5179ac53d995919f5da`. Instrumentation text is1208 bytes SHA-256 `55c3bfcf48f93855a801b3e15f32d14edd9702bcbab9c97f6d316d233450f210`, final instrumentation code0. Java phase_passed=false. These separate values establish an assertion failure with a retained native record and completed adb process.

The phase stops at the integrity-status wait; the later SDK-empty/cache-empty assertions, remaining online cases and two offline phases are not reported as executed. The12-control independent audit was not scheduled. Produceraccepted=false, safe_upload=true, phases1, F02_accepted=false, formal95/108.

### Retained observation artifacts

API and ordinary upload log IDs/bytes/SHA-256 agree for all five artifacts. Each belongs tobea7e55a7843091f006e9dfeca20d21e4f6adbdb /41237500791/A1, was unexpired at seal and expires2027-01-29T20:08:38Z.

| Artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| f02-android-input-41237500791-1 | [13055304800](https://github.com/NoGod3524/EXReader/actions/runs/41237500791/artifacts/13055304800) | 12687486 | `285b9b7013cbfb2c92e9f03ac38e66fda8fc259890001b11acc8d8ae715f98a3` |
| f02-android-admission-41237500791-1 | [13055749697](https://github.com/NoGod3524/EXReader/actions/runs/41237500791/artifacts/13055749697) | 623 | `b5aed14a00516e90a8df8f1650562e5699f15430435e6581bd0e0de21795df9f` |
| f02-android-status-41237500791-1 | [13056019313](https://github.com/NoGod3524/EXReader/actions/runs/41237500791/artifacts/13056019313) | 296 | `bd037ac078d0299625c5d9b6cbd5faaeb6f460c02e7e131d17738edf893456d4` |
| f02-android-build-41237500791-1 | [13056525560](https://github.com/NoGod3524/EXReader/actions/runs/41237500791/artifacts/13056525560) | 20122908 | `aa454ee9afa7aa22599fa79c0d4b19f620dc2384e2a3bcf69e5ae10302d0969e` |
| f02-android-receiver-41237500791-1 | [13056650102](https://github.com/NoGod3524/EXReader/actions/runs/41237500791/artifacts/13056650102) | 20132356 | `ddb9d4d7b69a48c934e04f57d1f885286ff6ad6ad75b00659489e95c2706840d` |

Receiver evidence includes original phase/instrumentation and native records, `online-process-observation.json`, `online-phase-observation.json`, fault observations and filtered failure-logcat hash/frames. New public observations use fixed enums and filtered test methods/line numbers. Credentials, raw runtime endpoint and arbitrary exception/logcat text are excluded; the private-output scan passed. All syntax, builds, fixtures, runtime checks and ZIP handling stayed in Actions; original ZIPs were not downloaded or parsed locally or in the VM.

The original failed run41233481729, its six artifacts, diagnostic41235413651 and its sealed report remain preserved. This round does not accept full F02 or execute its12 independent controls. Formal95/108 and external owner scopes remain unchanged.

Any cold-cache negative setup or further verification requires a new exact scope and budget. No cache removal, assertion relaxation, production fix or new runtime was performed under this observation authorization. Only this document is sealed after the result.

Observation evidence document prepared at 2026-10-31T20:19:54.361948+00:00 / 2026-10-31 16:19:54 EDT.
