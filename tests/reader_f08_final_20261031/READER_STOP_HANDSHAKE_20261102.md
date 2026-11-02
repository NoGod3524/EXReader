# F08 reader owned-stop handshake: one narrow round

Prior actual source: b7970bfbe7d1a54e2b41dcbde25bbe4d27472fa0.
Native run: native-lap25002-20261101T231437Z; producer 41336873192 attempt 1,
artifact 13095882137. Native sample failed after 562.6339847 seconds, not its
1200-second cap. Hardware admission passed; display remained 1920x1200 at 60 Hz.
Original Shelf UI: 9 passed / 1 failed / 0 skipped. Picker-return failure remains
unresolved: multi-select was enabled, but the reader import also succeeded after
a single click. Do not assume a missing confirmation button or disable multi-select.
This candidate does NOT change the old Shelf driver, product or SDK.
All ten original cases still run; overall F08 may still fail.

Reader public actions: 7 passed and 1 predeclared n/a. Helper cleanup destroyed
the activity before the host's explicit native stop. Both actual collector
footers said activity_destroy; the original ready-prefix guard correctly rejected
them. The fix publishes authenticated action readiness before helper cleanup,
then requires nonce/source/run/attempt/actual helper and product PID binding,
original callback replay, explicit native stop and confirmed Window identity
before acknowledging cleanup. Ready bytes and original validation fields remain
frozen. Actual two-stream guest footer time must precede helper cleanup.
Missing, stale, mismatched, prematurely closed or overdue proof is rejected.

Original 8 reader actions/assertions, 180-second cohort, 10-second cleanup reserve,
210-second instrumentation cap and total 1200-second native cap are preserved.
The new 18 synthetic handshake controls are not native evidence; do not claim
they passed until Actions runs. Existing tests, thresholds, first frames, outliers,
source contract and original source guards are unchanged.

Workflow .github/workflows/f08-final-linux-20261031.yml with scope=android-native
runs only original control (20 minutes) and android_build (20 minutes, original
inner build cap unchanged). sample, audit, windows_build, sdk, apple_native and
apple_audit explicitly skip. Dedicated branch codex/f08-reader-stop-handshake-20261101
also excludes those jobs even if full is selected accidentally. Other branches
retain the previous full default. No six-platform acceptance is implied.

Freeze and independently review the real commit before the one dispatch.
Authenticate its NEW five-APK artifact, original API receipt, full same-source
bundle, size/digest/manifest and native admission. Do not reuse old b797 evidence.
Use one fresh LAP25002 output directory and one original 1200-second sample;
do not automatically rerun. Preserve all old failures and packages.
