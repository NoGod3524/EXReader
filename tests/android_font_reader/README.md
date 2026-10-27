# Android reader font preservation

This independent additive suite preserves the existing C11, navigation and reading
suites. It exercises MainActivity's real reading More → 本地字体 entry and the
existing FontPanel, SDK font import, selection and reader lease lifecycle.

All execution, fixture preparation and evidence parsing run only in GitHub Actions.
Build with `test.init.gradle` and `-PexrTestRunner=org.exreader.host.FontReaderUiTest`;
run `run_ui.py --fixtures <C11 fixtures> --font tests/fixtures/fonts/primary.ttf
--app <same-source APK> --output <evidence>` on the API 34 x86_64 emulator with
CheckJNI enabled.

Checks:

1. Import and select a valid font from the reading page. Existing documented
   next-open semantics preserve the current accepted frame. Reopen proves actual
   logical ARGB pixel changes and exactly one SDK font lease.
2. On a noninitial page, attempt bad-font import from the reading page. Assert
   rejection, unchanged selected font identity/library count and accepted frame
   (book, part/path, page index, source range, public anchor hash/kind,
   preferences point, pixels and accepted token), with the existing lease retained.
3. Exit releases all leases. Same-font reopen restores the page/position/pixels,
   reacquires one lease, and final exit releases it.

Scope: the actual native app runs in an Android emulator, not a physical device.
Document-picker activities are intercepted with Instrumentation ActivityMonitor
and return real private-file URIs. This does **not** validate system DocumentsUI.
Book setup reuses C11's SDK import of hash-verified EPUB fixtures; font operations
are performed through real UI. No TalkBack speech or overall product acceptance
is inferred. `result.json` binds source/run/attempt and installed APK hash to
native frame evidence and retained PNG screenshots; failed reports are retained.
