# F06 same-source package identity

This isolated Actions workflow builds six distribution archives from one exact
commit. It does not replace the original behavioral gates or assert full F06
release readiness. `source` admits only this package's paths above the recorded
common candidate; SDK, hosts, existing tests and packaging helpers remain intact.

Windows uses the existing C09 Wave3 module/configuration recipe with content-bound
cloud and TXT progress enabled. GTK uses the installed raw compact host. Android
executes the exact existing composition build steps (including instrumentation
compilation, but **not** claiming those UI suites ran). Apple uses the installed
raw/Wave3 public product and host producers, with page theme enabled.

The original S20 archive and unpack tools authenticate every byte. Desktop entry
checks inspect relocated native dependencies; they are not a new GUI regression.
Android installs the extracted debug APK on API34 x86_64, pulls the installed APK
and checks its hash before launching the resolved Activity. Apple installs and
launches the extracted universal simulator app on iPhone and iPad, checking the
installed executable hash. iPhone/iPad share a universal app but have distinct
actual simulator installation records and archives.

Each target stores its build configuration, producer manifest, source/run/attempt,
archive and executable hashes, original archive, unpack and entry reports. The
same-run aggregator rejects missing targets or mismatched source/configuration,
records GitHub artifact IDs/digests/links, and never borrows earlier successful
runs. Failed attempts and original tests are retained.

These are unsigned/ad-hoc/debug development distribution packages: Windows lacks
Authenticode/installer; Linux is a GTK3-dependent portable archive, not deb/rpm;
macOS lacks Developer ID/notarization; Android is x86_64 emulator/debug, not ARM64
physical-device/store; Apple mobile packages are arm64 **simulator**, not device
IPAs or App Store submissions. No tag, release, mainline merge or publication.

Integration: transplant only this directory and its workflow, then intentionally
update the recorded common base and allowlist if integrating other packages; run
all six on the resulting exact SHA. Do not call this run evidence for a later SHA.

## SDK 3.42 composition preparation

The F06 tools were transplanted from source
`0b16cf4cabcb573ade064114f5db76e91fa1a620` onto common candidate
`b61cd85fb19c9347b020d9b66b53a7d474c57f5d`. The source guard now pins that
base and the Windows packaging adapter explicitly selects SDK 3.42.

This preparation is untested. The Linux, Apple and Android packaging recipes
still require review and adaptation to SDK 3.42 and their host version gates;
do not treat the earlier six-package run as evidence for this source. The
workflow is deliberately not triggered by this preparation branch. After those
dependencies and the Windows host follow-up are integrated, pin the resulting
common base and run all six producers and the authenticator on one exact SHA.
