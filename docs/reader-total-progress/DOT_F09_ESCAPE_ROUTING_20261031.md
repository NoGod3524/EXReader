# F09 focused Escape routing package
Authorization Sentinel_522c6064c7548191a55c6b246a71916b: initial run plus at most
one targeted correction; new 0/2 before first push.
Base 5f69c1e7ecc518b1635e044faa64ea8eb863de7e; isolated
codex/dot-f09-escape-routing-20261031 branch.
Only product change: the reader page WM_GETDLGCODE specifically claims its own
WM_KEYDOWN VK_ESCAPE message. NULL queries and all other keys retain the old
WANTARROWS|WANTCHARS flags. No unconditional WANTALLKEYS or main dialog changes.
The prior Escape selection-change notification remains byte-for-byte unchanged.
No provider ownership, SDK/C01, original managed or native consumer changes.

Evidence: preceding native/managed comparison run 41159620416 A1 at fe66f3a61
showed both native clients read selected text (432 units) but timed out awaiting
Escape clear; both managed clients still failed selected-range GetText with AV.
The message loop calls IsDialogMessage before DispatchMessage, while old
WM_GETDLGCODE did not claim Escape. This is a focused candidate, not a proven
root cause until new observation. Managed AV remains a separate blocker.

Keep all four independently launched baseline/candidate x managed/native
observations, same SDK/compiled host per consumer pair and same diagnostic overlay.
Keep the existing GetText, Ctrl+A, selection-clear, event, same-text and focus
assertions and all timeouts. Frozen baseline may still fail clearing; managed
clients may still crash. Any failure leaves the overall run RED, never concealed
by a passing native candidate. No formal F09/screen-reader acceptance.
Source receipts pin original/compiled provider hashes and test-only macro.
Retain failed runs 41152293447, 41155749004, 41156727928, 41157569248,
41159097889 and 41159620416, with their original artifacts.
All builds and tests run only in Actions; no live account material or text dumps.

References:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-isdialogmessagew
https://learn.microsoft.com/en-us/windows/win32/dlgbox/wm-getdlgcode
https://learn.microsoft.com/en-us/windows/win32/dlgbox/dlgbox-programming-considerations
