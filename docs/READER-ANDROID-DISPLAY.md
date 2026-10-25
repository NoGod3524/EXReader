# D05 Android reader display

Independent native Android AAR and installed-app probe. Public API, examples,
ownership, lifecycle/generation behavior and limits are in
[`extras/android-reader-display/README.md`](../extras/android-reader-display/README.md).
The existing Android host and SDK are unchanged.

## Acceptance plan (fixed before first execution)

- API34 x86_64 actual installed AAR consumer: 23 named UI cases in
  `tests/reader_android_display/contract.py` covering numeric and system brightness,
  validation atomicity, thread/reentry/lease guards, conditional restore,
  cancellation/retry, independent windows, real focus loss/pause, actual orientation
  recreation, explicit recreation, destruction, hidden windows and stale tokens.
- Five process/manifest/global-property cases: real active process force-stop,
  absent old PID, different reopened PID, default new Window, no app permissions
  or services, read-only comparison of global brightness before/after.
- Aggregate authenticates same source/run/attempt producer job, exact unique
  artifact and upload-log identity, expiry, API digest, actual ZIP size/hash,
  unique ZIP/JSON members, exact cases, original module Git tree, AAR/classes.jar,
  packaged and pulled installed APK bytes, and runtime APK/AAR identities.
- Rejection regressions mutate copies of **that actual authenticated artifact**;
  neither generated reports nor synthetic binaries receive platform credit.

All compilation, lint/syntax checks, native execution, fixtures and artifact
processing occur only in GitHub Actions. Local work is source/docs/Git only.
Initial validation status: pending first Actions run; no capability granted yet.

## Deliberate limits

The library owns only current Activity Window properties. Android does not expose
an authorship stamp for identical external writes: cooperating host code must
release before same-value edits. No global policy, setting or persistence is
claimed. Window callbacks must not throw. Host must deactivate when the reader
pane is hidden inside a still-visible Activity. Formal integration remains root's
responsibility. Physical backlight, battery/power behavior, OEM real-device
behavior and accessibility are UNAVAILABLE, not inferred from emulator properties.
