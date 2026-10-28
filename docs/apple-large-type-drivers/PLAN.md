# Apple large-type driver package

Source: 716c1409168960a276e282ce694d32ed82497bc9, the current common-source durable organization candidate. Independent branch codex/dot-apple-large-type-drivers.

The original D24 40-case per-platform run 40588875308 passed on its own source; it is not proof of the newer organization composition. Shelf run 40628095796 likewise completed its large-type production control checks successfully. The exact newer pair described by the request is not yet identified; preserve this distinction rather than invent a failure lineage.

This package reproduces current-source maximum system font reading and organization entry/operations/return with raw XCTest trees and screenshots on iPhone SE and iPad. It retains the original D24 test and all 39 existing native reading/navigation/search/theme/feature cases unchanged. The initial independent two organization tests deliberately use direct visible/hittable/full-window assertions so an offscreen control cannot silently pass through a coordinate fallback. Failures remain in original runs and artifacts.

No original-save, organization-toggle or migration lifecycle test is modified. No product change has been made at this initial diagnostic source. All compilation, syntax, fixture generation, UI execution and artifact parsing occur only in GitHub Actions. Simulator evidence does not prove VoiceOver speech or physical devices.

## First actual round (retained)

Run 40649528425 / source e1df2706d38d310148a560079b77d9a6b992f865: iPhone D24 and all 39 unchanged historical cases passed; the two new organizer probes failed before organizer entry at a test-only fixture button full-frame assertion. The actual AX tree shows its 201.5pt height exceeds the 160pt test-fixture scroll viewport. This is a diagnostic setup assumption, not a demonstrated production organizer defect. iPad passed all 42 cases, including the two organizer probes. The original test file is retained verbatim under retained/OrganizationLargeTypeUITests-initial.swift and its original run/artifact is not deleted.

The minimum diagnostic imports the actual EPUB through the application at ordinary OS size as setup, then independently sets, reads back and records maximum OS type before testing reading and organizer. Production control hittability/full-window assertions and maximum-size conditions remain unchanged. This setup change does not claim the original maximum-type test-only import geometry is fixed. The broad runner is manual-only during focused diagnosis to avoid spending P0 runner capacity on duplicate full suites. A final common-source full round remains required after the diagnostic stabilizes.

## Confirmed product defect

Focused run 40673513910 / fbd16c509a8b818dd88c914b5d465a70f52bc32b passed real import setup and maximum-type portrait on iPhone, plus both iPad orientations. Its iPhone landscape failed on the actual organizer Done button. Ubuntu-only inspection 40677656931 authenticated/downloaded the prior artifact in Actions and retained its exact landscape log: in a 667x375 window Done is at (550.5,-56.5,100.5,63.5), and the group ScrollView is at y410 with height0. This establishes off-window UI, not a guessed XCTest locator issue.

The narrow product fix gives iOS a pinned organizer header and one scrollable form/group body, without the desktop-only 400pt minimum height. Model/storage/lifecycle/toggle behavior is unchanged. The focused tests retain strict hittability and full-window containment after genuine scroll gestures, and now also create a group through the maximum-type form before returning to reading. No coordinate bypass is used.

## Focused form follow-up

Run 40678267136 / 39740c65f261ddc0c760757e3469f6fc8a5d778e retained failure while the newly added creation flow exercised the keyboard. Raw iPhone portrait AX shows Done now inside the window at (258.5,56,100.5,63.5); the organizer viewport is 343x263.5, while the horizontal Save control wraps to 94.5x263.5 and the name remains keyboard-focused. iPad portrait completes creation/return; landscape and iPhone save visibility remain failed.

The next narrow change makes primary actions vertical only at accessibility type sizes and supplies the ordinary Done submission path for name/ordinal focus. The test submits with the actual Return key, asserts keyboard dismissal, then performs the same real scrolling, full-frame and hittability checks. No maximum type reduction, coordinate bypass or budget change is used.

Run 40682402006 / 0e5c6498d6a567fe23aa6126ac947d4126c93851: iPad focused setup/portrait/landscape passed; iPhone setup and portrait creation/return passed. iPhone landscape retained failure because the new driver's whole-page swipe oscillated past Create. Done now lies at (550.5,16,100.5,63.5); Save is 244.5x77.5 rather than wrapping into a tall column. The next diagnostic is iPhone-only and changes only the reveal gesture to bounded edge-based scrolling, keeping eight attempts and all original geometry/hittability assertions. This is not a coordinate-tap workaround and cannot establish both-platform final acceptance.
