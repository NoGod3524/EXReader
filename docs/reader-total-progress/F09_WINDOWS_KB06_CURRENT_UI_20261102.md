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


## R2: canonical installed hash prefix
Parent: b62ef60e8830f7b515c1fb6234dc4187c429954e. Product baseline remains
5a57ff3cc0f295327676663236c6214b5736cb6a. Only these three audit files change.
The first run 41521295042 failed product configuration with the unchanged
canonical-prefix assertion. Space activations were zero; the case was not executed.
R2 obtains the prefix from the same CMake REAL_PATH operation used by the
product, verifies directory identity and rejects symlinks/junctions. No case-folding
or relaxed comparison replaces the original guard. Before rebuilding the SDK,
a configure-only admission invokes the original exact OPDSHash 0.1.0 package
validator, including imported target, archive, header and ownership checks.
The canonical environment selector is inherited by all original F06 subprocesses.
The installed package byte inventory is checked again after the original build.
F06 source, SDK, product, all module flags/targets and original package checks
remain unchanged. This adds no device cases: exactly the original cancel/import
Space paths run once after a successful same-run build. One new Windows job
at most 45 minutes, no automatic retry; all previous failures remain preserved.
