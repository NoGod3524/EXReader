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

## Initial result and targeted correction (round 2/2)
Run 41159097889 A1 at c75fcd84e696f0967d34c477ac5f3da6a49f3fef failed.
Both host packages and their existing checks built; the new native consumer
failed compilation before any of the four observations ran. This is a new
fixture header-dependency defect, not evidence of a new host product failure.
Windows SDK 10.0.26100.0 UIAutomationCore.h line 49 reported C4430/C2146 at
the first interface forward declaration, followed by cascading errors.
With WIN32_LEAN_AND_MEAN retained, explicitly include objbase.h and oleauto.h
before UIAutomation.h, plus initguid.h as required for UIA GUID definitions.
No assertions, runtime steps, SDK, provider, or original managed probe changed.
Retain artifact 13026641067, 5049 bytes, SHA256
f0bb2e395f5573fe233386d9ebbc57916e5c97a630e49cda5d37e7267da03aa7.
This uses the only targeted correction; no further automatic round is authorized.
Reference: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview
