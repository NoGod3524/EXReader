# F09 independent managed/native consumer comparison
Authorization: Sentinel_51525348b41481918e9792737a99d633.
New package: one initial Actions run plus at most one targeted correction (0/2 before push).
Parent source ba1dd10ea2f2da5b553099ad70a3fd309d15a31c.
Isolated branch codex/dot-f09-consumer-compare-20261031. No new production change.
Preserve failure runs 41152293447, 41155749004, 41156727928, 41157569248.

The unchanged .NET Framework64 probe and a new C++ IUIAutomation consumer each
launch a separate real host and private profile against baseline and candidate.
The two consumers use the same two compiled host binaries and the exact same
test-only provider diagnostic overlay inherited from the parent.
Receipts identify original/compiled provider bytes, overlay macro, host and
consumer binary hashes. These are diagnostic host builds, not untouched binaries.
The SDK, provider ownership, original .NET source and original tests are frozen.

Both consumers keep GetText(-1), Ctrl+A event and nonempty selection positive
controls, Escape degenerate selection at document start, unchanged full page text,
keyboard focus and expected baseline-absent/candidate-present event assertions.
Timeouts remain 120s native page, 120s ready, 10s focus, 5s selection/event windows;
the old 90-minute job cap and 26 existing package checks remain.
Native uses MTA, no cached patterns, real SendInput, process-bound window discovery,
and IUIAutomationTextRangeArray instead of managed TextPatternRange wrappers.
HRESULT or native AV is failure, never skipped or converted to success.
Four observations run independently; any failure keeps the overall verdict red.
A native pass cannot replace a managed failure or establish formal F09 acceptance.
No body text, credentials, memory dumps or private account data is logged.
No source/build/test execution occurs outside GitHub Actions.

References:
- https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nn-uiautomationclient-iuiautomationtextpattern
- https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomation-addautomationeventhandler
