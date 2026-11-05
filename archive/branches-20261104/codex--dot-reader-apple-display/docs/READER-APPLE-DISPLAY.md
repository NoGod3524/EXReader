# Apple reader display lease — D06

Independent Objective-C static component, version 1.0.0. No SDK link or new parser,
schema, settings store, service, screen recording, accessibility permission, host
integration or theme modification. The surrounding repository remains SDK 3.40 / ABI 1.

## Public boundary and installation

`extras/apple-reader-display` installs `libAppleReaderDisplay.a`, `ADRDisplayLease.h`
and the `AppleReaderDisplay::AppleReaderDisplay` CMake imported target. Configure
this package independently, never the root reader build. macOS requires Foundation
and IOKit; iOS requires Foundation and UIKit (iOS 15+). Use ARC. The installed-header
example is `extras/apple-reader-display/examples/ReaderDisplayExample.m`; the probe
apps are additional fresh-directory installed-library consumers, not existing hosts.

All calls, factories, diagnostics and explicit close/cancel belong to the main
thread. Wrong-thread operations return `ADRStatusWrongThread` without touching
state. There are no callbacks/reentry hooks or asynchronous API completions. At most
64 open leases exist per process; close returns capacity. Retain one native lease
per reading operation. Close and cancel are identical, synchronous, idempotent and
permanent. A failed IOPM release retains its ID and returns IO so close can retry.
Dropping the last reference cleans up; off-main deallocation queues cleanup on the
main queue and is not a synchronous release boundary. Prefer explicit close.

`setEnabled:hostActive:brightness:` changes only its own request. Brightness is nil
or an NSNumber with finite value in [0,1]; NaN, infinity, out of range and wrong
runtime type are rejected. No string input exists (Unicode parsing is inapplicable).
Non-thread update errors withdraw this lease's prior holdings and allow explicit
retry; another owner's requests are never withdrawn. Diagnostics contain only
fixed statuses, scalar ownership and native error codes, not document/window titles.
There are no preferences to commit, transaction or file write in the component.

## iOS ownership and lifecycle

The factory binds a real connected scene, its UIWindow and its UIScreen. Requests
are held only while explicitly enabled, hostActive, the actual scene is foreground
active, and the bound window is visible with nonzero alpha. UIKit scene deactivation,
background, window hidden and disconnect notifications withdraw holdings. Disconnect
permanently closes. A normal reactivation/visible notification may reacquire a
still-enabled request. Hosts must call update after changing alpha or other custom
visibility policy; arbitrary view occlusion is not inferred. Moving a window to a
different scene/screen invalidates this lease and requires a new one.

`UIApplication.idleTimerDisabled` is **application-wide**, not window-local. A
main-thread coordinator counts this module's holding leases, saves the pre-first
value, and conditionally restores it when the last holder leaves. Closing one scene
cannot clear another scene's module lease. External writers should coordinate with
this API: an external write equal to the module's current value is inherently not
identifiable; the module does not claim universal ownership arbitration.

`UIScreen.brightness` is **screen-wide**, not window-local. Only one module lease
may own brightness on a screen; a conflicting active request fails without partial
idle acquisition. The value is saved before a write, verified through the real
getter, and restored only if it still equals the module's last write (tolerance
0.00001). Actual external changes relinquish brightness without restoring or
reapplying; another explicit update may retry using the new baseline. UIKit
brightness notifications and release-time getters detect changes. Same-value writes
and the infinitesimal gap between an external cross-process write and a getter /
setter cannot be atomically arbitrated by the public API. Only the main screen is
eligible for brightness; external-screen brightness returns UNSUPPORTED. Idle
leases may be associated with external scenes but still affect the whole app.

## macOS ownership and limits

Each holding lease owns exactly its own public
`kIOPMAssertionTypePreventUserIdleDisplaySleep` IOPM assertion ID. No global assertion
release, assertion retain, manual display wake or PreventSystemSleep assertion is
used. The host provides active/background policy explicitly. Apple notes that a
display-idle assertion also inhibits idle system sleep while held; it does not
override lid/manual/system sleep. macOS brightness is UNSUPPORTED, with no private
DisplayServices/IORegistry fallback. IOPM failures return actual UNAVAILABLE or IO.

SIGKILL cannot execute library cleanup. macOS OS-owned assertions are verified to
disappear with process termination. iOS tests verify a new process has no library
leases and a fresh application idle property; they do **not** claim that abrupt
termination restores a screen-wide brightness value on physical hardware.

## Real validation and evidence

All builds, syntax checks, test/probe execution, simulator actions, fixtures and
artifact operations run only in `.github/workflows/reader-apple-display.yml`.
Every job checks exact HEAD, fixed ancestor a826a65c9c66e43620eff61b49cb79f941a3c953,
frozen SDK 9854061be331fe603a1822d9b2b36ee357154927 and the full exclusive whitelist.
macOS probes create/query/release real IOPM assertions and independently query a
real SIGKILLed process. iPhone and iPad probes run real UIKit apps, windows and
scenes, dual leases, wrong-thread calls, real property changes, background through
Settings, foreground, termination and relaunch. Real multi-scene requests are
attempted; an unavailable scene service stays PENDING. iphoneos is separately
compiled and verified unsigned; it is not run or published. Simulator signing is
ad-hoc solely to permit local simulator launch, not distribution signing.

The predeclared exact named cases are in `tests/reader_apple_display/contract.json`.
Any failed case is retained and rejects collection. Only explicitly listed missing
simulator/hardware capabilities can be PENDING. Native apps hash their actual
executable and report the compiled source/run/attempt and installed archive/header
identity. Verifiers compare original source, actual Mach-O/static archive, link map,
symbols, installed header, all native phase reports and actual process IDs.
The final authenticate job independently checks completed/success upstream jobs on
the attempt-specific API, unique artifact names/IDs, nonempty bytes, expiry and API
digest; downloads each ZIP **in Actions**, recomputes its size/SHA256, rejects
duplicate JSON/ZIP members, and verifies every inventory member. Forty named
negative tests mutate copies of the actual authenticated artifacts and job metadata;
original artifacts remain unchanged. The complete authenticated proof is in the
Actions job log (`D06_AUTHENTICATED_EVIDENCE=`) and its step summary. There is no
self-authenticating generated report artifact or recursive evidence-archive claim.

Simulator readbacks are not physical backlight or sleep evidence. Physical iPhone,
iPad, external displays, interruptions from Control Center on real hardware and
root's host integration remain pending regardless of a green workflow.

## Public Apple references consulted

- [UIApplication idle timer](https://developer.apple.com/documentation/uikit/uiapplication/isidletimerdisabled)
- [UIScene lifecycle](https://developer.apple.com/documentation/uikit/uiscene)
- [UIScreen brightness](https://developer.apple.com/documentation/uikit/uiscreen/brightness)
- [Public display-idle assertion](https://developer.apple.com/documentation/iokit/kiopmassertiontypepreventuseridledisplaysleep)
- [IOPM assertion operations](https://developer.apple.com/documentation/iokit/1557078-iopmassertioncreatewithdescripti)

The exact public SDK header digests used by each actual compiler are archived with
the native output. Run-specific identities and preserved failures are recorded in
`docs/validation/reader-apple-display.json` only after final source validation.
