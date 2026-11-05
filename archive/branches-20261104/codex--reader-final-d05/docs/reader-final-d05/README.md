# D05 — authenticated evidence, incomplete capability audit

**Do not accept the Android product from this package.** The final Actions run
successfully authenticated its evidence, but the import/read prerequisite remains
unresolved. Of 36 named case bodies, 7 passed and 29 recorded failures, mostly
prerequisite cascades. Blocked reader capabilities were **not audited successfully**.

## Exact identities

- Branch: `codex/reader-final-d05`.
- Tested harness / producer / verifier: `d770aeacf2a2134daf03ec29216b46e77c11c62b`.
- Unchanged formal target: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- SDK subtree: `edddc463c06ed5731195cdb8f06b2df6dff7699e`, 3.41.0 / ABI 1 / core 3.40.0.
- Owner `app-debug.apk`, default optional switches false; no candidate macros,
  replacement APK, injected host test hook or direct business/JNI calls.
- APK SHA-256: `40836d0fa3fd2d3ddfed812aab33b40f3ec66f978b855b26790210673cb86741`.
- Installed APK's `lib/x86_64/libexreader.so` SHA-256:
  `6372f49de6d7840cda8f9435f6ff5c185dc33e395bcbad79605e9dcedfd37407`.
- [Run 40216989166, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40216989166):
  audit job `121240153914` success; verify job `121242769720` success.
- Final documentation seal is the commit containing this report; its exact SHA is
  returned in the delivery message. Only documentation differs from tested source.

## What was actually established

API34 `default` x86_64 image revision 2, extension 7; fingerprint
`Android/sdk_phone64_x86_64/emu64x:14/UE1A.230829.036.A1/11228894:userdebug/test-keys`.
Delta captures: **1080×2400, physical 420 dpi**. System font settings were set and
read back as **1.0, 1.3 and 2.0**. These setting changes do not establish readable,
reachable reader UI at those scales. Delta reader rotations never reached their
trigger because `open()` failed; the original suite applied landscape to the shelf
and failed its book-preservation assertion. No reader rotation acceptance.

Original suite: **5 pass / 10 fail**, unchanged source and assertions. Passing
cases: shelf semantics, hidden panels, status announcement, shelf row/filter,
and shelf display-density override. The last case read back the requested 480 dpi
and ran its original shelf checks; it is not a reader-density grant.

Delta suite: **2 pass / 19 fail**. Passing cases: default shelf semantics and
emulated DPAD focus plus More-dialog Back recovery. Hardware keyboard and TalkBack
were not run. All three scale settings have actual readback evidence; reader scale,
position, annotation persistence, re-creation and feature operations remain blocked.

`authenticated-runtime-record.json` retains the verifier output verbatim from its
Actions log. Its runtime `audit_completed=true` means **named-case ledger complete**,
not full task/capability verification. The delivery `validation.json` deliberately
uses `audit_completed=false`, `audit_execution_ledger_completed=true`, and
`evidence_authenticated=true`. Every product acceptance flag remains false.

## Findings and exact limits

| ID | Classification | Evidence and next action |
|---|---|---|
| H01 | Harness misunderstanding, **not a host cancellation defect** | Authenticated round-2 trees `delta/001-picker-cancel-before.xml` and `002-import_cancel-failure.xml` show one Back moving DocumentsUI from Download to storage root. The test incorrectly expected app cancellation. Model folder navigation explicitly in a later root-owned test; keep this original failed assertion. |
| H02 | Unresolved import prerequisite | Final `import_sample` selected the file but did not observe `Imported Sample.epub`; the expected embedded-title row was not found inside `book_list`. Inspect `delta/004-import_sample-failure.{xml,json,png}`, `delta/events.json`, `delta-logcat.txt`, and `005-touch_page-failure.*` in Actions. Host failure versus label/row-selector mismatch is **not established**. Do not count downstream failures as reader product defects. |
| P01 | Observed semantic finding | Original `organize_panel` fails `organize_container_clickable`; `OrganizationPanel.java:55` sets the named panel clickable. Evidence: `legacy/cases/organize_panel.json`, `legacy/trees/08-organize.*`, `legacy/shots/08-organize.png`. Owner should review removing container action while keeping its child actions reachable. |
| P02 | Static default-configuration gap; partial runtime evidence | `examples/android/app/build.gradle` defaults optional features off; `MainActivity.java:279–307` does not construct panels and hides `reader_more`. Account/sync menu absence was observed. Search/TOC/records/settings runtime entry checks were blocked before reaching reader, so their dynamic behavior remains unverified. Root must decide the formal product configuration, then re-audit it. |

There is no accepted import cancellation/import, page turn, reader semantics,
annotation/bookmark, stable reading position, reader rotation/rebuild, search/TOC,
records/settings or account flow. No extra clicks were used to convert the failed
cancellation case to pass. Independent import setup relaunched the host and kept
all original failures. No production fix was made.

## Authenticated artifacts

| Artifact | Bytes | Original ZIP SHA-256 | Expiry UTC | Verification scope |
|---|---:|---|---|---|
| `12607774224`, `reader-final-d05-40216989166-1` | 25,092,124 | `7935b3ffd9eac7304141c67cebf84ef0410bb3e27429d30d548c8820dd00f021` | 2026-11-24 17:43:28 | Downloaded/authenticated inside same run's verifier; exact run/attempt/source/producer, size, digest, expiry, inventory and actual APK/native hash. Missing-file, wrong-size and altered-hash negatives rejected. |
| `12607826896`, retained round 2 | 24,704,116 | `a3e12c0c3dcd1fe2592b9221c58067026ef74aa0cba57490f53d8ac75f9c9f4a` | 2026-11-24 17:28:00 | Authenticated in final audit job, separately labeled historical producer `a32a10c…`, run 40215281412 attempt 1 / job 121234967050. No successes transferred. |
| `12607804151`, verifier report | 4,681 | `4146c53d30ae8ed03f19e4e0ab8d0708a4e7bacd907bcbce55e4e79cc8d24850` | 2026-11-24 17:43:47 | GitHub upload/API metadata only; this auxiliary ZIP was not independently re-downloaded. The report itself is also printed in verifier logs and reproduced here. |

Evidence includes independent harness APKs, owner build identity, raw instrumentation
output, XML/JSON hierarchies, PNG screenshots, events, PID/Activity dumps and logcat.
Original suite pulled 61 files; delta pulled 89. Screenshot pixels were retained and
file integrity checked, **not human visually reviewed**. No local artifact download,
unpack, fixture creation, syntax check, build or test occurred.

## Retained failures and stop

1. `5a8dd7e66a00a5262f61bf118574c42e03a811d4` / run `40215041256` attempt 1 /
   job `121234243011`: SDK manager missing from PATH. No runtime or artifact.
2. `a32a10c191e8a6d2e791f81686f8f8761515a7b5` / run `40215281412` attempt 1:
   producer `121234967050` completed; verifier `121238972852` failed cross-host
   redirect authentication. The retained original ZIP was subsequently verified
   without altering bytes, scope or assertions.
3. Final `d770aeac…` run above: evidence pipeline green; capability checks still
   blocked/failing. No fourth audit execution round started.

Root follow-up: diagnose H02 from authenticated current hierarchy/logcat; repair
harness cancellation/selection assumptions without weakening expected outcomes;
then re-run the real reader and dependent paths on the formal target. Physical
Android, real keyboard, other APIs/locales, TalkBack speech/gestures, glyph clipping,
contrast, scroll reachability, release APK and complete product remain pending.
