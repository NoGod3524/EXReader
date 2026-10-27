# D24 Apple large type

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
Owns ReaderScreen in `examples/apple/HostViews.swift`. After native AX evidence
identified the redundant account banner during reading, D21 and the coordinator
agreed to the minimal presentation-only extension: HostRootView publishes a
read-only `HostReadingRouteKey`; `HostAccountRoot` in `HostAccountViews.swift`
hides the separate banner only while reading and supplies an environment action
to the existing chooser. The reading More menu keeps `account.choose` reachable;
chooser dismissal restores the intended More accessibility focus target in code.
D21 retains LibraryScreen receive UI and all account/sync owners. No HostAccount,
HostModel, synchronization/session behavior, SDK, historical test or budget changed.
See [RESULTS.md](RESULTS.md) for accepted same-source evidence and real-device /
VoiceOver limitations.

Current source already has a compact horizontal tool strip and 44pt back target.
Preserved prior evidence: `docs/READER-APPLE-ACCOUNTS.md` records the actual
667×375 maximum-type iPhone page as only 659×51.5pt; old busy-layout feedback
and offscreen AX access failures were previously repaired, not claimed missing.
D24 removes a separate compact status row and prevents horizontal tool labels
from wrapping into tall rows. It adds an explicit persistent hide/show control,
without changing system text size or losing the reader owner/session.

Actions must run iPhone SE small-screen and iPad native UI, maximum system type,
landscape/portrait, page area and real tool operations; retain original suites.
VoiceOver audible output and physical devices remain unverified.
