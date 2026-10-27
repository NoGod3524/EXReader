# D22 Android receive

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.

Existing product already has a native session, revision projection, an explicit receive dialog and SDK import mapping. No dependency cherry-pick was necessary. The previous receive refused missing caches and closed the reading session even for duplicate receive. Remote-only shelf rows ignored clicks.

Changes reuse the existing bounded HTTPS WebDAV transport and immutable `exreader-sync-v1/objects/<prefix>/<sha>.<format>` naming. A separate transfer executor has no SDK handles. It checks cache hashes, retrieves absent or corrupt originals into unique staging names, validates exact length/hash, and atomically publishes only verified cache bytes. Cancel and Activity background invalidate tasks without waiting on network I/O. SDK mapping remains on the existing host owner. Duplicate mapping verifies the SDK original without closing a reading session or overwriting local paths/positions. Pending organization intents block receive. Remote-only shelf rows offer explicit receive.

All compilation, fixtures and verification run only in the dedicated Actions workflow. It retains the original organization, sync, picker/process recovery and C11 navigation/reading suites, and adds an independent actual-Activity receive runner using the same built host and HTTPS service. Existing source assertions and SDK files are unchanged. The D22 suite adds missing-cache corruption, truncated transfer, cancellation/retry, actual reader opening, cache repair, missing mapped-cache retrieval, and offline reader reopen after process restart.

This is not yet an acceptance report. Same-source Actions results and physical-device gap must be recorded before handoff. Android emulator results must not be described as real-device acceptance.

First run `40447481793`, attempt 1, source `e06b96e13f161e34f08713b1fb20b461249dc791`: builds, original organization sync, picker/process recovery, original sync UI and strict 3.41 adapter passed. D22 runner stopped in initial sync because its new offline marker probe incorrectly trusted `adb exec-out` exit status; fixed to use `adb shell` remote exit status (no assertion relaxation). Original C11 navigation independently failed `cancel_real_resolve_then_close_and_retry_is_clean`: `Actual visible directory row missing: First & chapter`, after 13 checks passed. Its tests/source remain untouched and the coordination owner has been informed. Original evidence artifact 12709359602 is retained. Added explicit original-transfer background/retry coverage.
