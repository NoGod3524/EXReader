# F09 Microsoft RichEdit reference-host comparison

Authorized branch codex/dot-f09-reference-host-20261031; parent 15ea33d9e914e8b353f0d6ec5c31b021cfaa04a4. Exactly four new files: reference_host.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions.

## Question

Run41171939136 localized the anomaly to the array-to-legacy-handle route: on EXReader hosts the direct DocumentRange legacy handle passes four methods with S_OK, while the visible-array-converted handle fails all four and GetText crashes 0xC0000005. Does the same route also fail against a Microsoft text provider? If yes, the fault follows the Windows legacy client path, not EXReader. If no, it follows the EXReader provider.

## Method

run.py runs the byte-frozen handle-control driver unchanged: frozen eight observations, 26-check suites and assertions, six array-handle and eight direct-handle processes against the EXReader baseline/candidate hosts. Guard parent, new paths, frozen list (now including both handle-control files) and output directory are the only updates. Then a test-only reference host is built: a top-level window whose page (control ID 123) is a read-only multiline Microsoft RichEdit (Msftedit.dll, MSFTEDIT_CLASS) holding fixed non-book text. The same already-built consumer binaries drive it in eleven independent processes: managed, typed native COM, legacy selection and legacy visible (frozen consumers), the three array-handle variants and the four direct-handle controls. The frozen aggregate failure is re-raised at the end.

## Interpretation limits

Selection-event and Escape assertions are EXReader-specific; RichEdit failing them is expected and not a finding. The comparison metric is exit code (0xC0000005 versus not), the last stage reached and raw method values. Whether RichEdit's text pattern comes from its own provider or from a UIAutomationCore built-in proxy is not determined; either way it is Microsoft code. A RichEdit pass narrows responsibility toward EXReader's provider but still names no defect; a RichEdit crash on the same route points at the client path but still is not proof of a specific Windows defect. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures retained.

Initial status: source prepared, no run yet.

## Initial validation result (1/2), 2026-10-31 05:36 UTC

Source 6893064b407bb55411667a6629fef9c81ba2e35c; run41172958918 attempt1, job124454609343: overall failure (frozen aggregate assertion re-raised, as designed). Artifact13032042304, `f09-reference-host-41172958918-1`, 114767 bytes, SHA256 40e8b35045fa8c6018dfebaaf33d890a88ffdfda02fd6c9c3e8f9635c19dd354. Guard passed, both 26-check suites passed; all frozen EXReader observations reproduced exactly (frozen eight; array-handle compare/expand non-standard values, clone 0x80040201; direct-handle control all S_OK).

Same consumer binaries, same run, Microsoft RichEdit reference host:

| Consumer / route | EXReader baseline and candidate | Microsoft RichEdit reference |
|---|---|---|
| managed .NET selection GetText | 0xC0000005 | 0xC0000005, last stage `ctrl-a get-selection-after count=1` |
| legacy C API selection GetText | 0xC0000005 | 0xC0000005, last stage `legacy-get-text-before` |
| legacy C API visible-array GetText | 0xC0000005 | 0xC0000005, last stage `legacy-get-text-before` |
| array-handle CompareEndpoints | 0x7938BD91 | 0x7938BD91 |
| array-handle Clone | 0x80040201 | 0x80040201 |
| array-handle ExpandToEnclosingUnit | 0x7938BD8F | 0x7938BD8F |
| direct-handle compare/clone/expand/gettext | all S_OK | all S_OK |
| typed native COM selection-array GetText | passes (candidate all assertions) | GetText on selection range length 290 succeeds; later fails only the EXReader-specific Escape-clears-selection expectation (exit 1), as anticipated |

The array-handle values again changed between runs (now 0x7938BD91/0x7938BD8F) and are identical between EXReader and RichEdit within this run.

Result: every crash and anomaly on the array-to-legacy-handle route reproduces identically against a Microsoft RichEdit text provider, while direct legacy handles and typed COM array ranges work on both. The fault therefore does not follow the EXReader provider; it follows the legacy client route (UIAutomationCore legacy HUIATEXTRANGE from an array element via UiaHTextRangeFromVariant, also used by .NET UIAutomationClient) on this runner's Windows Server 2022 build (UIAutomationCore 7.2.20348.1). This is strong evidence that no EXReader provider change is warranted for these failures. It is not proof of a specific Windows defect or instruction, and whether RichEdit's text pattern is native or a UIAutomationCore proxy is not determined. No correction run needed or used. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; how F09 acceptance treats legacy/managed consumers is a user decision. All prior failures retained.

## Decision, 2026-10-31 (user delegated all decisions in the Claude conversation)

1. For the F09 access-violation question, the typed native COM consumer is the deciding consumer. On the candidate (product a835 Escape routing) it passes every original assertion in runs 41165411704, 41170051294, 41170867473, 41171939136 and 41172958918.
2. The managed .NET UIAutomationClient and legacy C API 0xC0000005 failures are recorded as a known Windows limitation of the legacy array-to-handle client route, with this package's RichEdit comparison as the evidence. They are not fixed in EXReader, and no workaround is added to the provider: no extra AddRef, no SAFEARRAY type change, no FTM or marshaler change.
3. Not changed by this decision: the frozen observations still run and stay red; no assertion, budget, test or acceptance count changes (formal progress stays 95/108); formal F09 acceptance and screen-reader verification stay false until the a835 routing fix is integrated and a real screen reader is verified.
4. The previously denied push of docs/reader-total-progress/DOT_F09_ESCAPE_ROUTING_20261031.md stays denied. This decision does not lift it or carry it.
