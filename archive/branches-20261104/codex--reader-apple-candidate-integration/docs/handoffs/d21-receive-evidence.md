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
