# F02 Windows to Android fixed-input validation

Current fixed-slice result: **passed**, source98d2542f3d9849bbcb81f134c6327b59240043b3 / run41240919804/A1. All20 original Activity checks,12 semantic controls and additional cold-cache raw-evidence checks passed. Formal **95/108** and F02_accepted=false remain. The complete current result and artifact identities are in the final section; earlier failed records remain below.

## Original first-run record (retained)

Result: **failed; candidate not accepted**. Formal progress remains **95/108**. This document seals the result of the one authorized round; it does not authorize a correction or another run.

### Fixed identities

- Exclusive branch: `codex/gpt-f02-win-android-transfer-20261031`.
- Tested source: [`fe947bec25a56f40538677ffa9fb2a5e1e351b08`](https://github.com/NoGod3524/EXReader/commit/fe947bec25a56f40538677ffa9fb2a5e1e351b08).
- Source parent/base: `f59425f00af9069a22dc9cef2399ae84e3a62648`.
- SDK: `8357eafa28423a7ab93ba08b823af80f01ad1505`, 3.42.0 / ABI1. The C02+WebDAV SDK7271829 was not substituted.
- Exact11 manifest: [`source_lock.json`](https://github.com/NoGod3524/EXReader/blob/fe947bec25a56f40538677ffa9fb2a5e1e351b08/tests/reader_f02_win_android_20261031/source_lock.json).
- Production MainActivity.java blob: `c98cb87a86ab95ae9498cf9ab5dce68e9c4dd369`.
- Production BookStore.java blob: `be6dc75e0f77d0a975c21dc7dddeea31b46d5d81`.

The source commit changes exactly the two Android production files, the eight approved harness/workflow paths, and this document. JNI, SDK, existing tests and old assertion bytes remain frozen. A subsequent document-only [skip ci] seal has the tested source as its parent; it must not be used as a replacement test identity.

### Actual Actions result

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

### Preserved original artifacts

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

### Implementation and reused input

The two production edits prepare a verified private TXT reading copy from the existing SDK original on its owner thread. A unique staging file stays unpublished until the existing HostTask page publication transaction; cancellation or abandonment removes only its own staging file. The canonical verified reading copy and host path preference publish inside that transaction. Copy recovery does not import another SDK book, generate a product revision or send PUT. The build passed; this first run does not establish the complete runtime behavior.

The original real Windows sender input remains separate from the current consumer identity:

- Source `3b416378337a73c62423857e4340d469d357038d`, seal/base `f59425f00af9069a22dc9cef2399ae84e3a62648`.
- Successful original run41169386789/A1; sender artifact13030748486, `f02-windows-41169386789-1`.
- Original ZIP6354365 bytes, SHA-256 `4771f705c20c7230e13a193cbf44eb8b0c3a03ea4da208fbef26ad82fa033a8a`.
- Original TXT12000 bytes, SHA-256 `5f00b41f874d60348d6dc237873759906e5f0ed28b05bb399a6699bbc3c7b38f`; cross-host key uses format plus raw SHA, not a shared local SDK row ID.

Admission reauthenticated that original ZIP using the frozen original verifier. The Android fixture restores only the archived byte-identical Windows PUT store under fresh private HTTPS credentials. This is not a fresh same-source Windows execution or evidence of a continuously online Windows service.

The new adapter derives required commands from the frozen D22 recipe and explicitly supplies3.42.0 for SDK/module/Gradle inputs. The original D22 suite allows3.40/3.41 and EPUB; it was not weakened or falsely claimed passed in full. Its original page-themeOFF and3.41 gate are unchanged.

### Budget, route and continuation boundary

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

## Approved cold-cache full validation round (2026-10-31)

Status: sole full round completed/success; tested identity and actual evidence follow. New exclusive branch codex/gpt-f02-cold-cache-validation-20261031, parent3ba9dbefe975b60cd6d3b6d2dac6d186f43c637b. Product source remainsfe947bec25a56f40538677ffa9fb2a5e1e351b08; SDK8357eafa28423a7ab93ba08b823af80f01ad1505 and archived real Windows sender remain fixed.

Exact six paths: F02ReceiveTest.java, run.py, source_lock.json (branch identity), fetch_sender.py (budget metadata), existing workflow and this document. Independent authenticate.py, build.py, init.gradle, product and SDK files are frozen. The additional independent cold-cache checks live in the approved workflow, avoiding a seventh path.

The original sync remains first. Before corrupt mode the test requires native/controller FINISHED,256 shards, no busy flags/pending SDK task, a transfer-owner queue barrier and stable epoch; SDK0/local_id0; and the exact12000-byte verified active cache. It atomically moves that one inode once into a new0700 app-private test directory, verifies identity and absence, and refuses any rebuilt active cache. It never loops deletion, restores isolated bytes or forces an owner to cancel.

Original corruption, truncation, cancellation, empty-SDK/cache assertions and timeouts remain. Normal receive must add a real original GET and obtain correct bytes. Duplicate receive must add no original GET; unrelated metadata traffic is allowed. Original20 Activity checks, offline reopening and12 independent controls remain intact. Isolated raw bytes and numeric native stat evidence are retained. New counter publications count original-request arrivals and atomically replace only a test counter file, so a late response does not create a new request.

Workflow is restored to admission10 + Android60 + independent15 =85 runner-minute ceiling, exactly one initial attempt, no automatic correction/rerun. Original independent assertions run first; workflow-contained verification then recomputes the new isolation, exact XOR1 and GET-boundary evidence from its authenticated original ZIPs. All syntax/build/test/fixture/ZIP handling remains Actions-only. Any result is followed only by document [skip ci] sealing. Formal95/108 remains.

## Complete cold-cache result

**Passed for this fixed archived-Windows-input / Android-emulator slice.** [Run41240919804/A1](https://github.com/NoGod3524/EXReader/actions/runs/41240919804) is completed/success at tested source [98d2542f3d9849bbcb81f134c6327b59240043b3](https://github.com/NoGod3524/EXReader/commit/98d2542f3d9849bbcb81f134c6327b59240043b3), branchcodex/gpt-f02-cold-cache-validation-20261031, parent3ba9dbefe975b60cd6d3b6d2dac6d186f43c637b. The later seal changes only this document; use98d2542f3 as the CI source identity.

The round modifies exactly the six approved harness/workflow/document paths. Product source remainsfe947bec25a56f40538677ffa9fb2a5e1e351b08; MainActivity blobc98cb87a86ab95ae9498cf9ab5dce68e9c4dd369 and BookStore blobbe6dc75e0f77d0a975c21dc7dddeea31b46d5d81 are unchanged. SDK8357eafa28423a7ab93ba08b823af80f01ad1505 remains3.42.0/ABI1. Original authenticate.py blob9fcdc67c466e32b940bc4081a4517014eb028f3b is unchanged. No seventh source path was needed.

### Actual jobs, original checks and audit

| Job | UTC interval | Actual result |
|---|---|---|
| admission124654451614 | 20:52:35–20:52:52 | success: pinned original sender, fixed SDK/product guards, exact six current paths and retained Java assertions/timeouts/XOR1 input |
| android124654552379 | 20:52:54–20:58:33 | success: build plus all original Activity checks |
| authenticate124655822564 | 20:58:35–20:58:49 | success: unchanged original audit/12 controls, followed by new raw-evidence recomputation |

Actual phases were online13/13 (PID2444), offline4/4 (PID2739) and reopen3/3 (PID2830), all UID10141. Each adb subprocess returned0; raw native evidence was present; instrumentation finish codes were-1 and Java phases passed. The original audit independently checked those three raw PID/UID records, stable SDK book1, exact SDK original bytes, actual reader/source frames, screenshots, closed owners, removed download cache, server stop and fresh-process offline reopening.

The original ordinary audit log records **passed=true, errors=[], receiver.checks=20**. All **12 semantic controls** were rejected for their original specified reasons: sender-source, sender-PUT, wire-hash, receiver-attempt, receiver-key, receiver-GET, receiver-SDK-bytes, receiver-open, runtime-sdk, runtime-apk, cache-eviction and process-restart. No original assertion, timeout or count was lowered.

The workflow-contained additional implementation records **F02_COLD_CACHE_AUDIT passed=true, errors=[]**. It reads the original authenticated input/receiver ZIPs retained by the unchanged independent job; it does not trust only producer success flags.

### Cold/warm cache proof

Before isolation, the controller and native session were FINISHED(state4), completed_shards256, epoch3. Preparing/receiving/projecting/closing/pollQueued/sdkTask flags were false before the transfer queue barrier, after it and after the move. SDK books0 and remote local_id0 were retained. No owner was cancelled or forced closed to create that precondition.

The verified initial12000-byte cache had dev65062, inode319641, nlink1, UID10141, mode0600 and original SHA-256 `5f00b41f874d60348d6dc237873759906e5f0ed28b05bb399a6699bbc3c7b38f`. Its single atomic move into the new0700 app-private isolation directory preserved every identity field. The active path was absent afterward. Nine subsequent boundary observations recorded active_exists=false. The isolated original remained intact and was uploaded as `cold-cache-isolated-original.txt`; independent verification compared its raw bytes to the original Windows body and recomputed numeric raw stat evidence. There was no loop deletion or restoration from isolation.

The actual authenticated corrupt GET is raw event259: HTTP200,12000 bytes, response SHA-256 `25f030d1715ea011f46442dc8ebd073c1ecdaa2836713e700b678e14ec208d03`. Independent code rebuilt the expected first-byte-XOR1 body from the Windows original and matched that digest. Corrupt/truncate/block modes were all actually consumed. The original error-status and empty-SDK/active-cache assertions passed.

Five original-object requests were recorded: initial sync(id1), corrupt(id2), truncate(id3), block(id4) and normal receive(id5). The normal receive boundary advanced the original GET count **4 -> 5**, with a new non-fault request returning the exact original bytes. The new active cache used inode319644, distinct from isolated inode319641. No isolated cache was copied back.

Duplicate receive kept the original GET count **5 -> 5**; its active cache dev/inode/size/hash stayed unchanged and the original SDK-one-book assertion passed. This comparison is for the target original only; unrelated metadata traffic is permitted. Counter publications count request arrivals and are atomic, so a delayed prior response does not masquerade as a new duplicate GET.

### Build and preserved artifacts

The build report and independent runtime APK checks bind:

| APK | Bytes | SHA-256 |
|---|---:|---|
| host.apk | 27439236 | `08f0878602d19ddd4e06b36136c7459f795d5599c28e12f7369bbf7eb768c9c6` |
| test.apk | 269312 | `9190256e03b3f82ba72da6949912ff83991164af3a102cbb91cff5116788aab1` |

All six artifact identities below match ordinary upload logs and API metadata, exact source98d2542f3 /41240919804/A1. They were unexpired at seal; expiry2027-01-29T20:52:25Z.

| Artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| f02-android-input-41240919804-1 | [13056919452](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13056919452) | 12687487 | `e751848fa3dd88f54faba33e4ead5fa91a43e4acd4f9975be274ee9771f8168e` |
| f02-android-independent-41240919804-1 | [13057039510](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13057039510) | 34060965 | `5b7f555953568fc9d66f25ca800fb2425155ca06c6c87317486e834551fc380a` |
| f02-android-build-41240919804-1 | [13057228958](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13057228958) | 20127607 | `5426f89912f2a84451763f7f64a42e6db6d3a23b1e107f2214bc3e20fb8e2d58` |
| f02-android-receiver-41240919804-1 | [13057791050](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13057791050) | 21324132 | `8b62ed3843455ee4f60e3b439690614e444b090b14c0af90c618d10f1d4573b1` |
| f02-android-status-41240919804-1 | [13057791056](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13057791056) | 289 | `a222b47a3da898b79503de9b6cf41cee0c0cea3efc1386be17c4223c0d4c9d9c` |
| f02-android-admission-41240919804-1 | [13057870068](https://github.com/NoGod3524/EXReader/actions/runs/41240919804/artifacts/13057870068) | 625 | `08927430f6de381c84bde9ae32baec64549f6b17c4ea44add15d2a58945f801b` |

Read `summary.json` in independent artifact13057039510 for the original20/12 audit and `cold-cache-verification.json` for the additional isolation/XOR1/GET recomputation. Its `input.zip` and `receiver.zip` are the authenticated original producer ZIPs. Receiver13057791050 contains the raw isolated original/stat, original request/event records, phase reports/native records, SDK originals and screenshots. ZIP download/parsing remains Actions-only.

### Budget and claim boundary

This new approval allowed one85-minute round (admission10 + Android60 + audit15). One of one is consumed. Actual job intervals total370seconds, **6.17 elapsed runner-minutes**; run wall duration384seconds. Unused ceiling time does not authorize another run. No correction or rerun occurred.

All earlier failed runs and artifacts remain, including41233481729 and41237500791; diagnostic41235413651 and all prior seals remain identifiable above. New public observation records are limited to fixed enums, filtered test frames, hashes and numeric identities. Private credentials/runtime endpoint and arbitrary exception/logcat strings are excluded; safe_upload=true. Source/Git/docs used the approved original VM/native CLI route; all syntax/build/runtime/fixture/ZIP operations were Actions-only.

The original sender remains archived real Windows source3b416378337a73c62423857e4340d469d357038d /41169386789/A1 /13030748486, not a new-source Windows run or continuously live Windows service. Android is an emulator. The fixed slice proves original transfer, rejection under the real injected faults, cache reuse and SDK-backed offline reopening. Physical Android, six-target coverage and complete formal F02 acceptance are not conferred. **F02_accepted=false; formal95/108 remains unchanged.** External owners, main/shared branches, PRs, tags and releases remain untouched.

Cold-cache evidence document prepared at 2026-10-31T21:02:54.799417+00:00 / 2026-10-31 17:02:54 EDT.


## Approved same-source Windows -> Android round

Implementation pending its sole Actions round. Base86d38aec32a53bafff80d8f01fd677e10a4e5e64; exclusive branchcodex/gpt-f02-same-source-win-android-20261031. The previous accepted cold-cache source98d2542f3d9849bbcb81f134c6327b59240043b3/run41240919804/A1 and all earlier failures remain above. This package changes the input provenance contract and adds evidence; it does not modify production, Java, the SDK or the old Windows recipe.

Exact six changed paths relative to this base:

| Existing path | Minimal change |
|---|---|
| tests/reader_f02_win_android_20261031/fetch_sender.py | source admission, current Windows artifact/SDK proof authentication, installed evidence capture |
| tests/reader_f02_win_android_20261031/authenticate.py | independent current-run ZIP refetch, original12 controls, four provenance controls, cross-host SDK proof |
| tests/reader_f02_win_android_20261031/run.py | current authenticated input binding only; remaining receive/fault/offline body unchanged |
| tests/reader_f02_win_android_20261031/source_lock.json | exact scope, historical identities, fixed SDK/shared trees and budgets |
| .github/workflows/dot-f02-win-android-transfer-20261031.yml | one admission -> Windows -> Android -> independent-audit graph |
| docs/reader-total-progress/DOT_F02_WIN_ANDROID_TRANSFER_20261031.md | this contract and later actual results |

Frozen inputs: SDK8357eafa28423a7ab93ba08b823af80f01ad1505 (3.42.0/ABI1), product MainActivity blobc98cb87a86ab95ae9498cf9ab5dce68e9c4dd369 and BookStore blobbe6dc75e0f77d0a975c21dc7dddeea31b46d5d81. The source lock records SDK core tree/blob IDs for src/include/cmake/CMakeLists.txt/bindings, compared against the fixed SDK commit. Shared apps/reader tree004a0b08be8568407475b8bafe8472bd216516b8 and extras tree61fccfdaa6786ecd87dc9a7939c7d63314af4f11 come from the accepted product candidate and match the old tested Windows producer3b416378337a73c62423857e4340d469d357038d. They are compiled from the single new checkout H, not replaced with the SDK repository's different product module tree.

Java F02ReceiveTest.java blobcb5b00397eced744364cb38706476512e0b3942c, build.py blob646c4b2926b8749d157e47dfea3cb40b0c241b74 and init.gradle blobbb80155000e317e6024552d3cfde6143372514cf remain frozen. Old Windows windows_send/build/helper/verify_sender files remain unchanged. Admission compares the original20 audit body and12 negative-control implementation against the accepted base; the receive body after input binding, original corruption bytes/timeouts and cold precondition are preserved.

Every job checks out the same full github.sha H. Windows reuses its installed static SDK build, >=26 package self-checks, real picker import, account sync/actual HTTPS PUT, six sender checks and public installed-SDK original readback. Unrelated old Windows compact/account/organization/forward-scan suites are not rerun or newly claimed by this narrow slice.

The Windows upload step exports artifact ID and SHA256 directly to dependent jobs, separately for f02-windows and f02-windows-sdk. Android fetches only those outputs and verifies current H/run/attempt, successful producer job/time window, exact artifact names, API bytes/digests and the raw ZIP hashes. The source lock retains the old13030748486 identity solely as history and negative input; there is no archived-input fallback. Original TXT stays12000 bytes, SHA2565f00b41f874d60348d6dc237873759906e5f0ed28b05bb399a6699bbc3c7b38f, corrupt response remains first-byte XOR1.

SDK evidence is platform-specific: Windows proof retains installed .lib archive bytes, headers/configs, raw link map/cache, packaged host/inspector and package selftest. It is a static-reading build, not a Windows SDK DLL requirement. Android retains installed SDK/provider/header/config bytes, actual APK JNI bytes and host CMake-cache evidence. Shared ELF loaded-image comparison preserves code/data identity if Gradle strips non-loaded symbols; both full-file hashes and the loaded-image hash are recorded. The fingerprint binds exact SDK core and shared-module Git objects, rather than only a3.42.0 string.

The separate audit re-fetches this run's original Windows ZIP and SDK ZIP from the producer outputs and requires exact byte equality with the archives Android consumed. It re-runs the unchanged sender semantics, Android20 semantic checks and original12 named/reasoned controls, independently recomputes both installed SDK proofs, and runs four additional controls: old artifact, cross-source SHA, wrong attempt and a self-consistent wrong SDK fingerprint. Only after those pass may summary.same_source_windows become true. The existing separate workflow code then recomputes raw cold-cache isolation/stat, owner completion, exact XOR1 response and normal/duplicate target-GET boundaries.

One initial push-triggered attempt only: admission10, Windows30, Android60, audit15, total115 runner-minute ceiling. There is no automatic correction/rerun. This budget is based on the old selected Windows steps totaling235s (build189s, sender6s) and the accepted Android339s/audit14s, with cold-build margins. The old Windows whole-suite1588s included other UI suites outside this slice. Unused ceiling does not grant another run. Failure artifacts and original assertions must remain.

Source/Git/docs use only the approved native lap25002 -> saved official instabox@0.8.52 -> original VM route. All project syntax/build/test/fixture/benchmark/ZIP operations run in Actions. No Studio/C02/Apple/F08/UI or other-owner integration; no shared dirty tree, main/shared branch, PR/tag/release. Same-source proof still means artifact-carried Windows PUT store replayed by the Android test HTTPS server, not one continuously live cross-machine server. Android is an emulator. Full six-target F02 and physical-device acceptance remain open; formal95/108 and F02_accepted=false remain unchanged.

Contract prepared 2026-10-31T21:34:25.333117+00:00.


## Actual same-source initial result: failed, no rerun

The sole [run41244498593 / attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41244498593) completed **failure** at fixed tested source [ce6b908c5fa4447ad9f24e24c81bb68346f86420](https://github.com/NoGod3524/EXReader/commit/ce6b908c5fa4447ad9f24e24c81bb68346f86420), parent86d38aec32a53bafff80d8f01fd677e10a4e5e64. Exactly the six approved paths differ from that parent. A later document-only [skip ci] seal does not replace this CI source identity.

| Job | UTC interval | Actual conclusion |
|---|---|---|
| admission124664998847 | 21:38:03–21:38:13 | success |
| windows124665042028 | 21:38:16–21:43:21 | failure |
| android124666185584 | skipped at21:43:22 | not executed |
| authenticate124666184650 | 21:43:24–21:43:35 | failure on upstream windows |

Admission completed Python syntax checks, SDK8357/core/shared-source freeze, exact six-path admission, unchanged Java assertions/timeouts/XOR1 input, unchanged original20 audit semantics, original12 controls and the receiver body after input binding. No syntax/build/runtime/fixture/ZIP processing ran locally or in the VM.

Windows hash-owner setup, canonical installed prefix, SDK source gate, native display, pinned UI automation installation, frozen SDK342 build/package and installed public SDK inspector build all succeeded. The installed proof capture succeeded at21:42:46.5486398Z: rolewindows,82 retained files, static-reading, contract fingerprint1288327c2c16dc07923872830606ec7aaaf9829b5b5ab092c91103eb29725644. This is producer capture, not independent acceptance of those archives.

The failed step is **Native Windows import and actual HTTPS PUT**,21:42:46–21:43:09. Its ordinary log ends with the fixed disclosure:
F02_FAILED stage=native_transfer error_type=PermissionError.
The process exited1. No F02_WINDOWS_CHECK completion record is present in the ordinary log. The frozen driver catches the exception without a stack or Windows error code; ordinary evidence does not identify the failing call or prove its root cause. Do not infer a UI, shell, permissions-policy or product defect from the exception class alone. The retained sender artifact is522 bytes and is not accepted as successful PUT evidence.

Android did not start. New Android20 checks, offline phases, original12 controls, new4 provenance controls and separate cold-cache recomputation were **not executed in this round**. Independent summary is passedfalse/errors["AssertionError: upstream windows"]/same_source_windowsfalse/F02_acceptedfalse/formal95/108. The audit gate stopped before downloading producer/receiver archives; its small result artifact contains no accepted Windows/Android original-archive comparison. No old green outcome is substituted for this failed new combination.

### Preserved actual artifacts

All five API IDs, byte counts and SHA256 digests match the ordinary upload logs for this source/run/attempt. They were unexpired at seal and expire2027-01-29T21:38:01Z. Original ZIPs were not downloaded or parsed in this conversation, on the local machine or VM.

| Artifact | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| f02-android-independent-41244498593-1 | [13059595020](https://github.com/NoGod3524/EXReader/actions/runs/41244498593/artifacts/13059595020) | 332 | `29810f267ec51f4dae1fc4861ba1246637cc77fcdb979ed8cde89c0e86b1d855` |
| f02-windows-sdk-41244498593-1 | [13059575162](https://github.com/NoGod3524/EXReader/actions/runs/41244498593/artifacts/13059575162) | 16341199 | `0e93c8b2c1ce0794b17f41496375fe0fd5b2d4a54efe3006d10a13f301cb7f64` |
| f02-windows-41244498593-1 | [13059495494](https://github.com/NoGod3524/EXReader/actions/runs/41244498593/artifacts/13059495494) | 522 | `d16a8c84e6452807d7db2ba8532da7e3842c0ae6c3b0d8bec2a68c1b73afe3a4` |
| f02-windows-build-41244498593-1 | [13059246488](https://github.com/NoGod3524/EXReader/actions/runs/41244498593/artifacts/13059246488) | 63073 | `eeba8c29c197377250b47eb7324f7f4f2a8b30cc8e4625f82bcaeae34b1042a6` |
| f02-android-admission-41244498593-1 | [13058486623](https://github.com/NoGod3524/EXReader/actions/runs/41244498593/artifacts/13058486623) | 531 | `281e76911e92d4f61c464afdcc3abc03fdf78f921114229bcb7b0917c7ef4a8f` |

The sender report, installed proof and bounded build logs remain available for a separately authorized Actions-only diagnosis. First inspect the retained report and SDK/package evidence against the exact above artifact identities; if they lack the failing call/error code, propose minimal redacted stage/errno observation before changing product or test behavior. Reading the ZIP or starting another run is not authorized by unused minutes in this round. No speculative correction was made.

The one initial round is consumed: **1/1**,115 runner-minute ceiling. Actual non-skipped job intervals total326seconds, **5.43 elapsed runner-minutes**; run wall interval335seconds. Unused ceiling does not authorize a correction or another attempt. No rerun/dispatch occurred. All earlier green and failed inputs/runs/seals remain unchanged.

Source/Git/docs remain on the original VM through approved native lap25002/official saved-login InstaBox; DC remains unused. No production, Java, SDK, old Windows recipe or external owner path changed. Same-source transfer acceptance remains unproven; the previous archived-sender Android cold-cache slice remains accepted only at98d2542f3/run41240919804. Physical-device/six-target/full F02 acceptance and formal95/108 do not change.

Failed-round seal prepared 2026-10-31T21:47:53.406772+00:00 / 2026-10-31T17:47:53.406772-04:00.
