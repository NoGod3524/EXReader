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

## Final observed result (2/2 exhausted)
Source fe66f3a613c8e304043885633916672a05e1dd5b, run 41159620416 A1,
job 124414039121: FAILURE. Native consumer compiled; all four observations ran.
- baseline-managed and candidate-managed: two document reads of length 432,
  Ctrl+A selection event and GetSelection count 1, then native AccessViolation
  in managed RawTextRange_GetText. Neither reached Escape.
- baseline-native and candidate-native: document and selected-range GetText
  returned length 432; Ctrl+A positive control passed; real Escape was sent.
  Both then timed out at the unchanged 5-second selection-clear predicate.
  Provider ranges during those observations remained start 0/end 432.
  This is not a native pass and cannot override the managed failure.
- Same SDK/host source and diagnostic overlay were used for the consumer pair.
  The observation demonstrates a consumer-path difference, not proof that the
  provider or managed library is solely responsible for the AccessViolation.
Artifact 13026382940, 39686 bytes, SHA256
069678579d121fdba67b20c54b5b07ad7e0e19d8d683d3886fe89ed368aeaeba.
No full F09 or screen-reader acceptance; all prior failures remain retained.

Read-only source follow-up found page WM_GETDLGCODE returns WANTARROWS|WANTCHARS
(reader.c 3587), while the main loop calls IsDialogMessage before DispatchMessage
(line 6274). The existing page VK_ESCAPE handler is at line 3713.
Microsoft documents ESC dialog handling and conditional DLGC_WANTMESSAGE.
A narrowly scoped ESC routing candidate therefore warrants separate approval
and execution; it has NOT been applied in this package and is not proven fixed.
No unconditional WANTALLKEYS, no blind reference-count changes, no assertion loss.
Managed AV remains a separate unresolved blocker.
References:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-isdialogmessagew
https://learn.microsoft.com/en-us/windows/win32/dlgbox/wm-getdlgcode
https://learn.microsoft.com/en-us/windows/win32/dlgbox/dlgbox-programming-considerations
Result-only documentation commit uses [skip ci]; no third run is authorized.
