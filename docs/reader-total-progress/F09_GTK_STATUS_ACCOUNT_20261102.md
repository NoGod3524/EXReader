# F09 GTK current-UI status and Account evidence

Authorized 2026-11-02 16:58:09 EST: Sentinel_4490477707ac8191b0fd908a27442549.
Fixed product base: 77cbbe5e96303306dc22ca9025d9c1d760e87895.
Independent branch: audit/f09-gtk-status-account-current-ui-20261102.
Three additions; one commit/push and one Ubuntu 22.04 job, at most 45 minutes.
No automatic retry. Old source, SDK, tests, reports and formal ledger remain unchanged.

## Build identity

The pinned baseline.py lines 77-107 are the build-only model, not an invocation
of its entire Linux audit. The original raw GTK recipe is loaded unchanged;
only its existing 3.41 command arguments are adapted to 3.42 exactly as in the
already-used F09 wrapper. All original module installation and imported-target
checks remain. Preferences are installed and enabled as in that wrapper.
The unchanged packager validates executable --version == 3.42.0 1, ldd and
forbidden browser dependencies, and produces its actual source/file manifest.
An independently installed OPDSHash prefix is canonicalized by the same CMake
REAL_PATH authority and passes the original exact package validator before
any product build. Its files must stay unchanged.

## Exactly two observations

1. One invalid EPUB import submission. Identify the unique exact initial STATUS-log-named label in the source-defined
   direct main root box, then record its
   actual structural indices, name, role and process identity before/after.
   Save raw event types, detail fields, source identity and monotonic timestamps.
   Compare the old detail1 filter separately from actual
   object:property-change:accessible-name events for that same source.
   A different name alone, unrecognized event format or missing source is not a pass.
   Require original idle fields, a newer completed nonzero-error state and the
   final log/AX name match; loading transitions cannot pass. Callback errors or
   event overflow fail closed, including the exception-recording path.
   No second import submission if the chooser or asynchronous operation fails.

2. One Ctrl+Shift+A Account opening and one Escape. Record the dialog and actual
   focus, then a bounded 15-second focus timeline after Escape. Passing requires
   the dialog to disappear and real focus to be inside the main window.
   No focus setter, extra Escape, Tab workaround or product mutation.
   Capture actual account control names; do not impose stale Scan-library labels.

Registration uses the running host PID. Built, /proc/PID/exe and after-test file
hashes must agree. The existing driver launches the product and sends actual
X11 keys. Initial window activation and final owned-process cleanup are not
focus repair during the measured Escape operation.

## Interpretation and limits

The complete bounded verdict and focus timeline are printed in the job log;
the artifact retains the full event stream and original command logs.
A failed prerequisite is not_executed/false rather than an inferred product
defect. Missing observations fail the job. No old audit finding is retroactively
cleared. Success is limited to these two current-source observations:
formal_acceptance=false, screen_reader_verified=false. It does not prove
GTK-wide accessibility, iOS software read-screen coverage or six-platform
same-source acceptance. Formal 98/108 remains unchanged.
