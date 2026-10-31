# F09 legacy C API consumer diagnostic
Authorization Sentinel_55ceae76d9e0819189c68274ef3c17ae.
One initial run and at most one targeted correction, new 0/2 before first push.
Base a8352f3623078e4d64b222c5af4dc7a2f2bfa379. Only four new test/workflow/doc
paths. No product, frozen SDK/C01, provider ownership, old managed/native
consumer changes. The denied routing result-doc mutation stays in its original
worktree and is not included here.

The legacy consumer uses UiaNodeFromHandle, UiaGetPatternProvider,
TextPattern_GetSelection, UiaHTextRangeFromVariant, TextRange_GetText and
TextRange_CompareEndpoints. Client SAFEARRAY element VARIANT conversion is not
the provider VT_UNKNOWN array contract. Array/variant temporaries are destroyed
before reading the resulting owning range; each node/pattern/range handle has
one scoped release. No raw pointer reinterpretation and no added provider refs.
COM is retained only for unchanged focus/readiness properties and event
subscription; text-range retrieval and comparisons use the legacy C functions.
This diagnostic targets the legacy text conversion path, not every legacy UIA API.
Native AV is not caught; a failure or missing report stays failed.

Each source host is built once in this run. Three independent consumer processes
(managed, typed COM, legacy C API) use the same host binary bytes/private profiles.
Old artifacts did not include EXEs: this does NOT claim binary reuse from an old
run. Original/compiled provider, overlay, host, and consumer hashes are recorded.
Record reference Framework/UIAutomation module versions and hashes separately
from the actual UIAutomationCore module path recorded by the legacy process.
All six observations retain GetText/selection/event/focus/text assertions and
120s/10s/5s budgets. Any failure keeps aggregate red; neither native nor legacy
success replaces managed failure. Formal F09 remains unaccepted.

Retain failures 41152293447,41155749004,41156727928,41157569248,41159097889,
41159620416,41160570582. Route candidate native passed in-Actions in the last run;
managed selected-range AV remains unresolved. All builds/tests only Actions.
No credentials, document body dumps, full memory dumps, private account data.

Official API references:
https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcoreapi/nf-uiautomationcoreapi-textpattern_getselection
https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcoreapi/nf-uiautomationcoreapi-uiahtextrangefromvariant
https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcoreapi/nf-uiautomationcoreapi-textrange_gettext
Public dotnet/wpf UiaCoreApi.cs is a conversion reference, not proven source for
the exact installed .NET Framework binary; runtime metadata must remain explicit.


## Initial legacy run and targeted collector correction

Initial run 41161587756 attempt 1 at 9bca0cf54d06cab69dc227dca0eaced898fdf46f failed before all six consumer observations. Both existing 26-check host suites and all three consumer compilations passed. The new PowerShell reference-module collector returned 1; its captured stderr was not persisted, so the specific failure is unknown, not a product or legacy API finding. Artifact 13027875669: 5046 bytes, SHA256 4eaa87408d300128bc196745fa7f791862e2740c1e4556ce5911abad28f997ae.

The sole targeted correction (batch 2/2) preserves the original six precise reference-module paths, retains raw collector stdout/stderr in lossless base64 plus decoded text and return code, and records individual file errors. EncodedCommand UTF-16LE avoids argument interpretation ambiguity; this does not assert that quoting caused the initial failure. Metadata must contain six unique complete file records, versions and hashes on a 64-bit process. Missing/invalid metadata remains an aggregate failure but no longer prevents the six independent consumer observations. No provider, product, consumer, original assertion or timeout changes. Initial failure retained; formal F09 remains unaccepted.
