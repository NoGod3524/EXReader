# F09 Windows KB-06 current-UI acceptance scope

Authorized 2026-11-02 18:51:37 UTC, Sentinel_572d8023e39c8191966bb89f4d2a29ad.
Base: 5a57ff3cc0f295327676663236c6214b5736cb6a.
Branch: audit/f09-windows-kb06-current-ui-20261102.
Only these three new files, one commit/push, one windows-2022 job <=45 minutes,
no automatic retry. Product, SDK, original tests, original failure and ledger remain unchanged.

## Why this separate test exists
The old audit's import_book returns at missing import_edit before Space is sent
(tests/reader_a11y_windows/flows.py:127-140). phase_import still marks KB-06
failed from a missing focus_after_space (178-196). Thus that historical result
does not prove a product focus failure. It is retained, not rewritten or promoted.

The old criterion is that an activated command leaves keyboard focus defined,
or at most two Tabs restore it. This new test uses the current Import button
(Win32 control ID 102), not the removed path field. It uses real keyboard input:
Tab to the button, Space once, Escape to cancel; then Tab to the same command,
Space once, paste the original deterministic Extra-Book.epub and Enter once.
Both modal-return paths read GetGUIThreadInfo and UIA focus, require owned,
visible, enabled focus in the main product window, and allow at most two
recovery Tabs. No Invoke or SetFocus repairs focus; SetActive is initial setup only.
No other product actions, screen reader, old audit, or other platform suite is run.

## Build and identity
The unchanged tests/reader_f06_packages/build.py:windows recipe builds the
existing SDK 3.42.0 and complete compact host. OPDSHash is first built and installed
with EXREADER_OPDS_HASH_ONLY=ON, then provided by EXREADER_ORIGINAL_HASH_PREFIX,
as in the existing F09 workflow. Existing package checks remain in effect.
The original Windows fixture generator supplies Extra-Book.epub.
The observation binds source/run/attempt, actual running process image path
and SHA256, fixture hash, and before/after packaged EXE/DLL hashes.
Only the owned test process and a fresh build-directory data folder are used.

## Outcome boundaries
This candidate is not a result. If build, window, or button preconditions prevent
Space from being sent, status is not_executed and the job exits nonzero.
After a real activation, a failure remains fail; no rerun or replacement occurs.
A pass applies only to these two current-shell paths, not all F09 or accessibility.
Other Windows/GTK failures, mobile VoiceOver gaps, and the formal 98/108 ledger
remain unchanged. Historical G16 results are not touched.
