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

## Third iteration (not full acceptance)

Source `f9a2e5e7c2ecef9d8eb7ab5f08163d756782b1af`, Actions [40454046298](https://github.com/NoGod3524/EXReader/actions/runs/40454046298), attempt 1. Native receive and original regressions now use independent jobs. iPhone receive job `122025648966` succeeded, including real HTTPS fault controls and offline position restart. Its raw artifact is `12714661331` (ZIP SHA-256 `d684a36983244329d929cefc6ff746670085b0b29a922e9e56cea3f9e618ccbe`). macOS original job `122025649039` and iPhone original job `122025649067` each passed all original 39 cases in the five retained phases.

macOS receive job `122025649123` failed the new test's line 67 nonzero-page assertion, which compared `reader.location.label` directly. The original cross-platform tests read AXValue when AXLabel is empty; the new test now uses the same actual native snapshot semantics, asserts a nonempty initial position, still requires a genuinely changed position, and still requires exact restoration after offline restart. It records the actual initial/saved strings. No reading implementation, position expectation or original test is changed. The failed native result remains artifact `12715608336`, ZIP SHA-256 `1f97a46e0591ffe855c7ff0a2fc5fd010334d7d7b293b63b8aaa72261595d27f`.

The current native UI fault test controls only the Actions fixture and its own CI app cache: corrupt-cache/wrong-hash rejection, interrupted response, cancellation while receiving, missing-cache retry, and remote-object-unavailable restart. It does not install an alternative product UI or bypass SDK imports. Exact app identity, existing SDK linkage checks, xcresult, executable-containing ZIP and raw same-run ZIP authentication are required for acceptance.

The third iteration's iPad receive job `122025649105` also succeeded, including the full native fault/restart/position case and concurrent-history owner checks (artifact `12715938627`). These passes belong only to `f9a2e5e7c2ecef9d8eb7ab5f08163d756782b1af`; the AX-reading correction still requires its own same-source full run.

## Fourth iteration and cancellation publication repair

Source `b649a9d90451d3df9c798618daa8d71f52a74140`, Actions [40466429222](https://github.com/NoGod3524/EXReader/actions/runs/40466429222), attempt 1. macOS receive `122064616168` and iPhone receive `122064616114` passed, so the AXValue correction is now verified on macOS without weakening position assertions. Original iPad job `122064616110` passed all 39 original cases; the preceding third-run theme failure had been `simctl ui … appearance light` timing out at the original 45-second budget, which remains unchanged. Other fourth-run jobs are still pending at this record's creation; no final aggregate claim is made.

Source review identified a real cancellation publication gap: a receive page can commit and enqueue its main callback; cancellation between enqueue and delivery previously caused the success callback to clear busy and return without a cancellation message or shelf refresh. Cancellation now immediately publishes its state, keeps the owner busy until settled, and the final callback refreshes committed shelf changes while preserving cancellation. Completion carries an exact receive identity, so callbacks belonging to an earlier receive or a closed account cannot overwrite newer state. This is a host publication repair, not a change to SDK transaction or account binding behavior.

The independent native `ReceivePublicationReview.swift` executes the actual product model's publication methods with deterministic main-queue ordering. It requires immediate cancellation state, no early owner release, cancellation surviving a queued success, committed shelf refresh, old success/error isolation, a subsequent normal receive, visible failure, and closed-account rejection. It is additional to, not a substitute for, the real HTTPS owner and three-platform native UI tests. Product and test changes require another complete same-source run; fourth-run successes are retained only as fourth-run evidence.
