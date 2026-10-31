# F09 Microsoft RichEdit reference-host comparison

Authorized branch codex/dot-f09-reference-host-20261031; parent 15ea33d9e914e8b353f0d6ec5c31b021cfaa04a4. Exactly four new files: reference_host.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions.

## Question

Run41171939136 localized the anomaly to the array-to-legacy-handle route: on EXReader hosts the direct DocumentRange legacy handle passes four methods with S_OK, while the visible-array-converted handle fails all four and GetText crashes 0xC0000005. Does the same route also fail against a Microsoft text provider? If yes, the fault follows the Windows legacy client path, not EXReader. If no, it follows the EXReader provider.

## Method

run.py runs the byte-frozen handle-control driver unchanged: frozen eight observations, 26-check suites and assertions, six array-handle and eight direct-handle processes against the EXReader baseline/candidate hosts. Guard parent, new paths, frozen list (now including both handle-control files) and output directory are the only updates. Then a test-only reference host is built: a top-level window whose page (control ID 123) is a read-only multiline Microsoft RichEdit (Msftedit.dll, MSFTEDIT_CLASS) holding fixed non-book text. The same already-built consumer binaries drive it in eleven independent processes: managed, typed native COM, legacy selection and legacy visible (frozen consumers), the three array-handle variants and the four direct-handle controls. The frozen aggregate failure is re-raised at the end.

## Interpretation limits

Selection-event and Escape assertions are EXReader-specific; RichEdit failing them is expected and not a finding. The comparison metric is exit code (0xC0000005 versus not), the last stage reached and raw method values. Whether RichEdit's text pattern comes from its own provider or from a UIAutomationCore built-in proxy is not determined; either way it is Microsoft code. A RichEdit pass narrows responsibility toward EXReader's provider but still names no defect; a RichEdit crash on the same route points at the client path but still is not proof of a specific Windows defect. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures retained.

Initial status: source prepared, no run yet.
