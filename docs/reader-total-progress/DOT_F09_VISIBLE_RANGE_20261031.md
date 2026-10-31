# F09 visible-range array diagnostic

Authorized branch codex/dot-f09-visible-range-20261031; base506402b25797d40831755254ce29a94e6ef91623. Exactly four new files: visible_probe.cpp, run.py, workflow, this document. One initial Actions validation and at most one targeted correction; each job retains90min. All execution only GitHub Actions. No product/provider/old-consumer edits and no transfer of denied routing documentation.

## Question and controls

Existing run41162331946 shows document-range text passes but selected range converted through the deprecated legacy C API fails. Later authenticated evidence run41163507048 confirms legacy and managed exit0xC0000005; typed COM candidate passes. This package tests whether a visible-range array fails without selection input.

The same SDK3.42 and same baseline/candidate host binaries are built once per source with the unchanged identical test-only provider diagnostics overlay. All six old observations remain byte-frozen consumers with original assertions and timeouts. Two additional independent process/host pairs use the new visible consumer. It sends no Ctrl+A or Escape, retains document GetText as positive control, obtains TextPattern_GetVisibleRanges, verifies the client VT_VARIANT array and converts its single element through UiaHTextRangeFromVariant. After array/VARIANT lifetime ends, the owning range is read and compared against complete document text and endpoints; focus is retained. No plaintext book content is logged. /EHsc does not swallow native access violations. One observation failure cannot prevent subsequent independent observations; any of eight failures or metadata failure keeps aggregate red. A passing visible result cannot override the old managed/legacy failures.

## Runtime identity correction

Only the new driver replaces unavailable Get-FileHash with System.Security.Cryptography.SHA256 over the exact same six reference DLL paths. Both version strings, file sizes, exact normalized path set and64hex SHA256 remain mandatory. Raw collector stdout/stderr/return code and per-file failures are retained; process success alone is not metadata success. Existing driver stays frozen. Reference DLLs are not claimed to be all actual loaded modules; native legacy/visible process loaded-uia-module.txt is retained. Each process exit code is printed in decimal/hex with binary hash.

## Interpretation

Visible array failure with direct document success narrows the fault to a common array-to-legacy-handle route, not proven provider premature release or Windows defect. Visible success with selection failure instead points toward the selection-specific route. Exact root cause still needs evidence; no extra AddRef, SAFEARRAY type change, custom marshaler or production workaround is introduced. Formal F09 acceptance and screen-reader verification remain false.

Known limitations preserved: original baseline Escape behavior fails its clear-selection assertion; managed and legacy failures remain independent. COM calls have no new per-call timeout beyond the original90min job cap. Provider diagnostic logging can perturb timing. Existing C02/Claude files and SDK/C01 are untouched.

Initial status: source prepared, independent review pending, no new run yet.


## Initial validation result (1/2), 2026-10-31 03:47 UTC

Source fb3e95aca4dae83ca7773eb261af09b0af9ec652; run41165411704 attempt1, job124431799228: overall failure. Artifact13028741859, 43883 bytes, SHA256 9b1fb0e83152ceb8eda449b24e7f805532860894a3eea4ddaea1b85c702d6cd7. Both preserved26-check suites passed. All eight process observations executed:

| Consumer | Baseline exit | Candidate exit |
|---|---|---|
| managed selection | 0xC0000005 | 0xC0000005 |
| typed native COM | 1 (original Escape clear failure) | 0, all original assertions pass |
| legacy selection | 0xC0000005 | 0xC0000005 |
| new legacy visible array | 0xC0000005 | 0xC0000005 |

Visible PID6880/6988 each completed direct document GetText length432 twice, then direct-document-positive-control, visible array VT12, element VT20, conversion success, visible-array-converted, and selected legacy-get-text-before without return. Neither sent selection keys. This is not an independent proof that the current selection is empty; the experiment specifically removes selection input. All four consumers per source shared exact host hashes: baseline1fe82f3f292cc94e18b538948b3baf24179f3229888906fd5a6d3b02af64b80a and candidate632a60c88e93645d482f58a2fc1fc884b89f2e549f659d760caa8ad0e0029dde.

Runtime metadata correction succeeded: collector rc0,64bit, all six exact paths exist with complete versions/sizes/SHA256, no per-module errors. UIAutomationCore file7.2.20348.1/product10.0.20348.1, SHA2562B1EA113EBE23C8FDA36926F912891A85CAB28632CAFE5D255905BF66CB149C8. UIAutomationClient, UIAutomationTypes, WindowsBase, clr and mscorlib all report4.8.9363.0. Raw metadata and hashes are retained in artifact. These are reference-module identities; no unverified full process-module claim.

Independent reviewer review_restart_crash_gaps verified original logs, eight exits, same-binary hashes and artifact metadata. The problem is not purely managed/.NET and not restricted to selection input. A common array-to-legacy-handle boundary remains the narrowed hypothesis, not proof of responsibility, incorrect reference count, or exact native crash address. No production change or extra reference was applied. The one permitted targeted correction has not been consumed: no evidence-backed correction yet warrants another run. Formal F09 remains false; all prior failures remain retained.
