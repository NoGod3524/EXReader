# D21 Apple receive — in progress, not accepted

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
Own branch: `codex/dot-d21-apple-receive`.

Existing Apple code already received immutable reading records and annotations and ran the native sync transport, but completed book scans did not project remote books into the shelf or attach originals through the SDK. Existing `HostCatalog.attach`, immutable `HostImportCopy`, `HostSession.importBook` and the existing `exreader-sync-v1` object path are reused. No new protocol or SDK change.

## Original failed iteration (retained)

Source `d2a9bb78ed3afe8f75dd473d08481e1277fa614f`, Actions [40447795759](https://github.com/NoGod3524/EXReader/actions/runs/40447795759), attempt 1.
Both SDK producer jobs succeeded. The actual macOS account terminal callback consumer compiled the changed account/catalog files and passed. All three new native consumers failed before their own compilation at `tools/apple_swift.py:44`: `RuntimeError: Raw products are bound to another actual SDK`. The new driver had passed the `sdk-input` download layout to a helper that requires the original installation prefix. No native receive/UI acceptance follows from that run. The subsequent original-suite step was skipped and its absent-artifact upload failed; those are retained failures, not original suite results.

Correction: download the exact same-run macOS producer artifact directly into its original `build/raw3-ios-sdk/macos` installation layout for that consumer. Preserve all manifest/prefix/identity bytes and checks. Keep the original `sdk-input` download for the unchanged original native UI runner. No path-substitution experiment, SDK replacement or validation bypass.

## Scope

Product owner: `examples/apple/HostAccount.swift`, `HostCatalog.swift`, `HostModel.swift`. Only `LibraryScreen` wiring in `HostViews.swift`; D24's `ReaderScreen` remains untouched. Standalone tests/workflow live in `tests/reader_d21_apple_receive` and `reader-d21-apple-receive.yml`.

Projection only inserts absent safe book metadata. Existing local title/favorite/progress and active SDK session remain authoritative. Conflicted or deleted histories do not choose a clock winner. A cloud shelf row explicitly downloads/validates an immutable private original, rechecks selected revision, then uses existing SDK import/mapping before opening. Local mapped books open without credentials. Corrupt private caches are quarantined before verified replacement; a failed or cancelled transfer leaves existing SDK books intact.

Validation is Actions-only. The pipeline retains unchanged base, reading, navigation, search, theme and wave3 suites, with original same-source/run/attempt artifact authentication. New native owner cases cover cache absence/corruption/retry, wrong-hash and interrupted HTTPS, in-flight cancellation, duplicate metadata preservation, an old local book, and concurrent remote roots. New UI cases exercise explicit connect/sync/open/restart on macOS, iPhone simulator and iPad simulator. All claims remain pending actual job results.

Physical iPhone/iPad and VoiceOver are not executed; simulators are not real devices. No mainline merge, tag, release or SDK candidate is authorized or performed.

## Second iteration and original diagnostic

Source `5fe9a9d7a23a1e70cbd0d4270b520f61f7523466`, Actions [40448440042](https://github.com/NoGod3524/EXReader/actions/runs/40448440042), attempt 1. Both SDK producers passed. macOS job `122006578895` and iPad job `122006578921` reached the final `concurrent-history-keeps-local` command after the native UI command returned success, then failed `actual_https_sweep`. The test consumer generated a new account UUID on each process invocation, violating the public session's intentionally persistent product-store UUID/root binding. Preserve that protection: the fixture now persists and reloads its own original profile. No product binding or validation is loosened.

Those two jobs also retained original-suite failures. The same job had run an intentional-failure-prone native test helper before the old suite, and its uncaught Swift top-level error produced a macOS crash notification dialog (visible in the raw original UI log). It also left a selected fixture account. The next workflow uses independent receive and original-regression jobs rather than sharing app state. This is an isolation correction, not proof that every old failure is explained; the next same-source original suites must actually pass. The new helper prints errors and exits nonzero without generating a crash dialog.

macOS original failures included wave3 annotation preview / history-large-rotation, reading-control failures, and live system appearance; iPad original base failure was `test09BusyReadingBackAndBookOwnership`, with wave3, control, search and theme scoped phases passing. Raw job logs/artifacts remain on the original run; no assertion or original driver is changed.
