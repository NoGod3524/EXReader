# Desktop reading display leases (D07)

Independent installable static C ABI for Windows and Linux GTK3. No host changes,
SDK dependency, settings persistence, brightness control, daemon, global power
policy, `xset`, or suspend requirement. Fixed SDK remains 3.40.0/ABI1.

## Host integration

Build/install `extras/desktop-reader-display`, then
`find_package(EXReaderDesktopDisplay 0.1 CONFIG REQUIRED)` and link
`EXReaderDesktopDisplay::display`. The installed header is
`exr_desktop_display.h`; C/C++ consumers are in `examples/`. The host creates one
lease for a live top-level `HWND` or `GtkWindow*`, calls `set_active(1)` only for
active reading content, renews before the bounded lease expires, observes the
snapshot, and calls cancel/close when leaving reading. Leases do not migrate
between native windows. Destroy then create a new lease for a new window.

The API copies a strict 1–256-byte UTF-8 reason and rejects malformed Unicode,
controls, wrong struct sizes, invalid active values, and lifetimes outside
100–600000 ms. It permits at most 64 live leases. Native UI owner thread only;
wrong-thread calls do not mutate state. No user callbacks or exceptions cross
this C ABI. Calls from native host event handlers are supported; nested API
operation dispatch is rejected. Observe output is untouched on API argument,
thread, or reentry errors. A successfully closed handle cannot be reused.

The host must service its Win32/GTK default event loop: expiry and reconciliation
are driven by 50 ms UI timers, not a background service. A blocked event loop can
delay expiry; close/cancel before stopping it. GTK custom thread-default contexts
are not supported. GTK creation must be on the GTK initialization/main thread;
the toolkit offers no public global query to prove that precondition. Subsequent
calls enforce the captured owner thread. Unix bus authentication uses GLib's
native timeout; name-owner/release calls use 1 second and Inhibit 2 seconds.

## Platform scope

Windows creates a separate real `PowerCreateRequest` handle per active lease,
sets **only** `PowerRequestDisplayRequired`, and clears/closes only that handle.
A chainable per-lease window subclass handles deactivate, minimize, hide and
window destruction; timers reconcile actual foreground visibility. Two leases
have distinct handles. An OS failure is UNAVAILABLE, not successful inhibition.
[Microsoft PowerCreateRequest](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powercreaterequest)
and [PowerSetRequest](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest)
explicitly distinguish display from system-sleep requests; this module never
asks to prevent all system sleep.

Linux uses the existing `org.gnome.SessionManager` session D-Bus service with
**IDLE flag 8 only**, never SUSPEND flag 4. The native GTK window's XID is supplied
on X11; active/visible/mapped/iconified state remains owned by GTK. Each lease
owns its private session-bus connection, unique service owner and cookie, rather
than borrowing or clearing GtkApplication's inhibitors. One async request per
lease carries the original generation and service owner. A late reply after
cancel/hide/destroy is released against that owner. Close/timeout disconnects the
private sender, including any cookie whose reply was lost. Missing, denied,
zero-cookie, lost-service and lost-connection cases are UNAVAILABLE. Reconnect
requires explicit activation; no fallback to broader power inhibition occurs.
[GNOME SessionManager API](https://gnome.pages.gitlab.gnome.org/gnome-session/re04.html)
and [GTK inhibit contract](https://gnome.pages.gitlab.gnome.org/gtk/gtk3/method.Application.inhibit.html)
define the cookie and individual release behavior. This session-specific backend
is deliberately not claimed as universal Linux/portal support. IDLE can affect
session locking according to desktop policy; it does not override explicit
suspend or grant brightness control.

## Validation and limitations

Only GitHub Actions builds, installs, compiles fresh C/C++ consumers, runs native
probes, creates fault services, and handles artifacts. Every job checks exact
HEAD, fixed-start ancestry, frozen SDK and the complete path whitelist. No
existing Windows or GTK host is changed. Named expectations are fixed in
`tests/reader_desktop_display/cases.py` before execution. Linux fault cases use a
clearly labeled deterministic service, separately from the real GNOME-session
availability probe; fault success cannot grant real service capability.

The workflow preserves native process output/exit codes, module and consumer
binaries, failure logs and separate real-session output. A downstream job checks
same source/run/attempt, actual completed successful native jobs, unique artifact
name/ID, expiry, nonempty bytes, API digest, recomputed ZIP size/SHA, duplicate
ZIP/JSON rejection, exact named original results and every original binary/raw
hash. It executes rejecting mutations, not a fabricated success summary.

Remote native handles/cookies are not a physical laptop-screen or energy test.
Wayland, battery impact, lid behavior, suspend interactions, lock-screen policy,
host integration and full-product acceptance remain ungranted. Windows process
cleanup is independently observed with `powercfg /requests` when available; an
unobservable request is UNAVAILABLE rather than inferred from a child exit.
Real API resource-exhaustion failures are handled but not intentionally induced
on a shared runner. No failure expectations are relaxed to make CI green.

See `docs/validation/reader-desktop-display.json` for exact tested source,
retained runs, artifact and actual binary identities after Actions completes.

## Verified Actions handoff (2026-10-25)

Tested source: **`1e66921ad7c7c4e09742ff8c6ce94a5848f85014`**.
[Run 40172124474, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40172124474)
completed successfully:

| Job | Measured results |
| --- | --- |
| Linux `121104991570` | 49 PASS; physical screen/energy and Wayland UNAVAILABLE |
| Windows `121104991894` | 34 PASS; physical screen/energy UNAVAILABLE |
| Authentication `121105198936` | Both native artifacts authenticated; 47 executable rejection cases PASS |

Linux separately exercised an actual GNOME session, not the fault fixture:
cookie `971186983`, `/org/gnome/SessionManager/Inhibitor2`, flags **8** and expected
application identity were observed; after killing the actual child process,
GetInhibitors returned no remaining inhibitor. Windows separately observed the
child's power request disappear through `powercfg /requests` after termination.
These grant native request/lifecycle evidence, not physical display persistence.

Final native artifact IDs: Linux `12590402582` (49986 bytes), Windows
`12590781168` (38812 bytes); supplemental authenticated summary `12590457662`
(1415 bytes). Full ZIP/API digests, expiries, actual module/consumer SHA-256s,
job/source identities and negative case names are in the adjacent JSON evidence.

Retained failed runs: `40171667144` (Linux libc helper-name collision) and
`40171773778` (two-window fixture left reader 1 active, so it correctly
reacquired after reader 2 destruction). The original failing reports/artifacts
remain recorded; the zero-cookie teardown assertion was preserved. The fixture
now explicitly deactivates reader 1 and asserts it remains released. Native
restore-reacquisition coverage remains intact. Run `40171982938` then passed;
final source additionally fixes and tests unavailable-service state surviving
hide/show without silently retrying after a service reconnect.

The handoff evidence commit changes **only this document and its JSON evidence**
with `[skip ci]`; its code, tests, workflow and installed module tree are identical
to the tested source. No host, T/J package, default branch, release or tag changed.
