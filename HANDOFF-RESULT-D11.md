# D11 final handoff — acceptance refused

Three complete CI iterations used; no fourth run. All six fixed targets executed. Final independent evidence audit completed, but six-platform action/focus consistency **accepted=false**. Windows and GTK passed 17 named semantic rows each. iPhone/iPad passed 16 each; macOS passed 15 with picker-precondition failure; Android passed 4 before catalog-observer failure. No cross-round scope transfer.

## Exact identities
- Branch: `codex/reader-dot-d11`.
- Base: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Final tested harness: `e0e898e1df372fa3b3de4145cf2f1f4ddec01eb4`; tree `20f9223d7620e999a3d703e26fcfe26bf0dcbe07`.
- Final run: [40229380899](https://github.com/NoGod3524/EXReader/actions/runs/40229380899), attempt 1. All eight jobs terminal; verifier failed only Android/macOS native execution. A redundant run-level curl read was denied; it was not used as acceptance evidence.
- Final docs seal: documentation-only commit containing this file, parent final tested harness, commit message includes `[skip ci]`; exact resulting SHA reported to root after publication (cannot self-embed its own commit hash).
- SDK source: `edddc463c06ed5731195cdb8f06b2df6dff7699e`. Apple SDK original producer `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`, run40203714083/1. All fixed target identities below differ intentionally from harness.

|Target|Target source|Native job|Result|
|---|---|---:|---|
|windows|`9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`|121277857729|17/17 rows passed; native success|
|gtk|`803098e9df1a365a9b8e206805c2d179aca8501f`|121277857711|17/17 rows passed; native success|
|android|`4a04a9cc74dde67f755c87e87b278d63a254a3ac`|121277857692|4/17 rows passed; native failure|
|macos|`15dab6b2270dc296ed6239db67ced2e22d255e65`|121277857684|15/17 rows passed; native failure|
|iphone|`5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`|121277857658|16/17 rows passed; native success|
|ipad|`5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`|121277857702|16/17 rows passed; native success|

Guard121277618988 success; independent verifier121284450082 failure. The consumer's recorded job list shows itself in progress because it is running; externally retrieved final job metadata confirms verifier failure.

## Original ZIP authentication
All seven original ZIPs were downloaded/byte-hashed/expiry/run/attempt/source/job-bound **inside final Actions consumer**, not locally. Every expiry below is 2027-01-23T20:08:49Z. This table is not the consumer-upload ZIP; it identifies original producer evidence.

|Original ZIP|ID|Bytes|SHA-256|
|---|---:|---:|---|
|d11-source-40229380899-1|12612108909|224538|`66d1d7d8aba2bfccc78fe494d13633e33d115a5815f57bccac0a3ede1f3a263c`|
|d11-windows-40229380899-1|12612498747|18690005|`96e0fc4cb1c85029fe6fabf45f8b5141ea660a8d7365ef50e41aa01b32de2c63`|
|d11-gtk-40229380899-1|12612785112|36899095|`a70a87ea600ecae54b5daba1e4321b2d28a65a2fdf1d93d2d67858c54d1e583e`|
|d11-android-40229380899-1|12612648550|22933843|`08a4dd2cce879746333de4d274481d2a3f7a87ce6c0994522e8342fa8e32289a`|
|d11-macos-40229380899-1|12612624054|147578089|`738b9c5b5814fb21c8ae58e14cf131f95ef3a3676fbc852b657c63324964e0ff`|
|d11-iphone-40229380899-1|12611684890|42845155|`3a367d946fb7437fdeb8b5b50a0a15af6907794186576ee9dfbf4cfc99b4289e`|
|d11-ipad-40229380899-1|12612837851|43281918|`c9f0b1f9597448077ca891a8d0a28a86936538be3cff6b5561eb528dd3edf3f3`|

## Actual programs

|Target|Actual program SHA-256|Bytes|
|---|---|---:|
|windows|`5d0d0009ca0fb11eaf6c59f5a677476ee6b5e5ef68b8fda903f09a763464b757`|7820800|
|gtk|`4bb3597d43f6d818a5f8a8b78a1f0fb330e31d839065a4dff298febf63559742`|10279568|
|android|`a4627d562df9c2436a9f91f1371112de5ad6801e4f43544546c412195e1d0c74`|26955244|
|macos|`c7b04981cb7d18330e43af15774e7e3846147f8e13fa6d959f55646130527602`|6938416|
|iphone|`a334f3cb77dfe42c6dc3f3f42dfd942b70d91ab8bc68a08c232ae465371097a4`|6973664|
|ipad|`9fc1599bd8409a301e7a67f88eb472f6d4c2a2ef7bd8bee2cca6e949904eb2f1`|6973616|

Fresh desktop pre-ZIP mode/link/size/hash records are bound in `*-program-attributes.json`; Apple executable mode493 (0755), non-symlink is recorded before ZIP and app tar preserves attributes. No chmod/re-sign identity repair. Original Android APK program permissions beyond bytes are not granted.

Configuration: Windows compact ON/raw3 OFF/review OFF; GTK compact/raw3 ON; Apple PAGE_THEME ON/raw3 OFF/review OFF, unsigned. Actual Android APK DEX BuildConfig confirms SEARCH/NAVIGATION/READING/PREFERENCES/PAGE_THEME/SYNC true and SELECTOR_BYTES_CANDIDATE false, not inferred from branch naming. Original APK producer40207467982/1, artifact12604537792,133598571 bytes, SHA2569ea2858145313296d39792d867794db1be687eb70dec38f155dcd1dfe156bf06, expiry2027-01-23T15:33:00Z; installed APK digest equals authenticated input. Apple SDK original ZIP identities and jobs retained in `round3.json` producer/sdk records.

## Complete named checks and failed/missing scopes
Checks: back, resume, import, cancel, next, previous, search, directory, records, settings, close.search, close.directory, close.records, close.settings, disabled_noop, continue_after_return, no_unexpected_revision. Every target has all17 rows; unexecuted rows remain pending. Complete raw values and execution failures are in `docs/reader-dot-wave2/d11/round3.json`; `ROUND3.md` explains path boundaries and exact next diagnostics.

- Windows/GTK: all17 executed/passed, actual modal descendant focus visible/enabled, source hashes and independent revision/outbox unchanged. GTK uses More-menu, **not Ctrl+Shift+R**. Windows tests book-open modal path, not D08 shelf-search focus restoration. Neither overturns prior package failures.
- Android: cancel/import/next/previous passed; expected `files/reader-catalog.db` absent from observed listing, aborting independent snapshot before 13 remaining checks. Observer failure, not product mutation; exact actual path unresolved. Round2's15 rows remain separate historical evidence.
- macOS: reading and disabled Find no-op passed; picker Cancel unique enabled/hittable native-window descendant precondition failed line68 after45s. Cancel row remains pending plus failed testcase, not a pass. Catalog mutation unverified.
- iPhone/iPad: both native cases pass, including picker cancel and disabled Find no-op; independent source/catalog mutation unverified.
- Apple import is actual fixture-native entry, not unrestricted production picker import; settings is page-theme only; resume is reopen, not dedicated Continue. Modal keyboard focus on Apple/Android remains unverified. Physical keyboard/screen-reader/physical-device/full-product grants all false.

Ten negative controls reject missing target, source-only, touch-as-keyboard, main-window-as-modal focus, duplicate action, wrong program, partial report, failed action, invisible focus and wrong source. Evidence authentication is not a complete product grant.

## Retained history / root entrypoints
Round1 harness9eb9f65ba258f3e00f6e67f9d090dbce8a879029 run40225647982/1; round2 harness940616fd5d84e20873530b3f615a9187f3d5a517 run40227580106/1. Both failed and remain in ROUND1/ROUND2 + JSON; original D06 failures preserved in PRIOR-D06.md and authenticated logs. Driver causes addressed progressively, never relabeled green. All builds/tests/syntax/fixtures/screenshots/artifact download/parsing only Actions; local source/docs/Git only.

Root entrypoints: this handoff; `.github/workflows/reader-dot-d11.yml`; `tests/reader_dot_wave2/d11/verify.py`; `docs/reader-dot-wave2/d11/ROUND3.md` and `round3.json`. No product/SDK/old-test/default-branch/PR/release changes. Further diagnosis requires separately authorized work beyond exhausted three-round budget.

## Publication authorization and read-only blocker
Authenticated explicit approvals: Sentinel_3f7a7f4cfa648191a35b1bc973b55f74 at19:20:18 and Sentinel_a25cfda0b7c88191a24872861872469a at20:06:51 (exact final monitoring/publication/Actions/docs request). Later redundant curl status request was rejected despite direct approval reread and one identical reviewed retry; session88139 output poll also rejected. That operation stopped; no alternate status route was used. All final job and consumer evidence already existed from previously successful calls. Original commit denials remain historical and resolved by explicit owner approvals.
