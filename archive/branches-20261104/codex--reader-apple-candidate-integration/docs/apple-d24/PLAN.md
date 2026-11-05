# D24 Apple large type

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
Owns only ReaderScreen in `examples/apple/HostViews.swift`; D21 owns other
account/receive portions of that file. No SDK, historic tests or budgets changed.

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
