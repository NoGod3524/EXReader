# F09 GTK current-UI status and Account evidence - R2

Original authorization: 2026-11-02 16:58:09 EST,
Sentinel_4490477707ac8191b0fd908a27442549.
R2 authorization: 2026-11-02 17:46:32 EST,
Sentinel_151db1a116e081919a82464feb846fd7.

Product base stays 77cbbe5e96303306dc22ca9025d9c1d760e87895.
R2 parent is 8047eef0cfeda7c765c5f2970f2cccc7cc9ed8d7, on
audit/f09-gtk-status-account-current-ui-20261102.
Exactly the existing three diagnostic files change. One non-force commit/push,
one new Ubuntu 22.04 job at most 45 minutes, no automatic retry.
Old product, SDK, tests, reports and formal ledger remain unchanged.

## Retained R1 result

Run 41537973237/A1 built SDK 3.42.0 / ABI 1 successfully; the unchanged raw
installation checks passed 34/34 and the actual running binary matched the
package manifest. The single Return did not close the file chooser. No final
refused-import state was observed; Account was not executed.
There were 676 collector errors, all "AX sibling index unavailable".
These are not evidence of a product status-event failure or an Account defect.
The original run/artifact 13185480802 and all three approved log readbacks remain.

## Unchanged build

The pinned baseline.py lines 77-107 remain the build-only model; its full Linux
audit is never invoked. Keep original raw GTK module installation, installed
checks and the exact existing 3.41-to-3.42 command adapter, plus preferences.
The original packager checks --version == 3.42.0 1, ldd and forbidden browser
dependencies and records source/file hashes. OPDSHash is independently installed,
canonicalized by CMake REAL_PATH, checked by the original package validator and
verified unchanged after the product build. R2 does not rebuild different code
or weaken any product/build check.

## One independent observation per path

Both cases use the same built binary but separate fresh profiles, one owned
host launch and cleanup per case. Failure of the status case cannot skip the
Account case. This is not a repeat of either observation.

Status:
- Bind the unique exact STATUS-log-named label in its original root-box location.
- Send F1 once. Wait for the owned chooser to be active and actually focused.
- Send Ctrl+L; wait for its editable focused Location Layer entry, then enter
  the invalid EPUB path once and read its exact full text back through AT-SPI.
- Reuse the original compact flow: initial Return plus at most three further
  confirmations, checking the same chooser and unchanged path each time.
  Stop immediately when it closes. Never reopen F1 or retype/re-import.
- Wait for original idle fields, a newer nonzero-error state and matching final
  log/AX message. Loading transitions cannot pass.

Account:
- From its own fresh host, press Ctrl+Shift+A once, observe focus inside the
  real dialog, then Escape once and capture a bounded 15-second focus timeline.
- Require dialog disappearance and actual focus inside the main window.
  No grab_focus, Tab workaround, repeated Escape or product modification.

## Event identity and failures

Save raw event type/detail/time before querying any source. Do not walk every
transient chooser node's structural tree in the callback. Bind status events
to the retained actual status GObject reference and owned PID, not just matching
names/roles or screen coordinates. Check the target's structural identity
before/after the operation. A target identity/query error, unidentifiable
name-change source or overflow is a failure. A non-target source query error
is retained and separately disclosed; it is not a claim of complete AX-stream
coverage. The original detail1 filter is reported separately.
Only an actual bound target name-change event can satisfy the status rule.

The recorder pins its owner PID at creation. Raw-field errors fail closed.
After deregistration it joins the event thread for at most five seconds, takes
a locked final snapshot and rechecks late errors. Event shutdown/save failures
never bypass owned-host cleanup. Incomplete shutdown stops the next case; a
normal status assertion failure with clean shutdown does not skip Account.

Per-case reports print the exact error, bounded first source errors, input and
focus observations, program hashes and cleanup result in stdout. Full raw events
and logs remain in the artifact. Missing readiness/evidence fails that case;
there is no inferred pass or silent retry.

Success remains limited to these two new-source observations:
formal_acceptance=false, screen_reader_verified=false, old_suite_executed=false.
It does not retroactively clear old failures or prove GTK-wide accessibility,
iOS software read-screen support or six-platform same-source acceptance.
Formal 98/108 remains unchanged.
