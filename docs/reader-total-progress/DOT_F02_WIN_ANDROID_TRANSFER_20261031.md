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

Status: six-file observation draft, not yet run. The earlier failed run above and its original artifacts remain unchanged. New exclusive branch: codex/gpt-f02-online-observation-20261031, fixed parent f47f7c374524d2774e9a61cba44f63a5b7580916. Product source/blobs remain fe947bec25a56f40538677ffa9fb2a5e1e351b08; SDK8357eafa28423a7ab93ba08b823af80f01ad1505 remains fixed.

Only six paths may differ from that parent: F02ReceiveTest.java, run.py, source_lock.json (branch identity only), fetch_sender.py (budget metadata only), the existing dot-f02-win-android-transfer workflow and this document. No product, SDK, build adapter, init.gradle or independent verifier change is authorized.

Observations add named substeps, fixed assertion-reason enums, filtered test method/line frames, status categories, published panel eligibility, SDK counts from the original owner query and transport-cache metadata. UI observation waits at most200ms; an optional post-failure SDK count uses its owner and a2-second wait, marks unavailable on timeout, and never interrupts host work. They preserve the original corrupt check body, all original need conditions, polling/timeout values and the12000-byte first-byte XOR1 response. Observer capture failures remain optional evidence, not replacements for product assertions.

Server evidence distinguishes marker consumption, authentication and successful corrupted-response send. Per-phase process evidence records adb return code, instrumentation code, native evidence presence and Java phase result before the original combined guard. Runtime endpoint bytes join the existing private-output scan; raw logcat text is replaced by bounded hash/size and filtered test frames. No arbitrary exception message, credentials or raw runtime URL is published by new observation records.

The one approved observation uses one Ubuntu job with30-minute ceiling, initial attempt only, no automatic correction/rerun. Source admission, original sender authentication, unchanged SDK/app build and original driver run in that job. Original20 assertions remain in the driver; completion is measured, not assumed. The12-control independent audit is not scheduled by this observation workflow. Actions alone perform syntax/build/test/fixture/ZIP operations. After terminal results, only this document may be sealed [skip ci]. Formal95/108 remains.
