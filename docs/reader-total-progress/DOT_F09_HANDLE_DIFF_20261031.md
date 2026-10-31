# F09 legacy handle-method differential

Authorized branch codex/dot-f09-handle-diff-20261031; parent 570b320a3b6b80dc8019dbbfa6b8dde6c373d599. Exactly four new files: handle_probe.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions. Option A of the read-only proposal; options B (in-process exception location) and C (starting WerSvc on the runner) are not implemented.

## Question

Run41165411704 and run41170051294 show the visible-array-converted legacy handle crashes the consumer with 0xC0000005 on TextRange_GetText, while direct DocumentRange GetText passes and the provider trace shows no GetText entry for array ranges. Is the converted handle unusable for any legacy method, or does only GetText fail?

## Method

run.py runs the byte-frozen av-stack driver (frozen visible-range driver plus the verified event collector) with only guard parent, new paths, frozen list and output directory updated. The eight observations, both 26-check suites, assertions and timeouts are unchanged. Only if the frozen run reaches its final aggregate assertion (verdict written) do six extra independent processes run against the same two host binaries: variants compare (TextRange_CompareEndpoints start versus DocumentRange start, expect 0), clone (TextRange_Clone, expect non-null) and expand (TextRange_ExpandToEnclosingUnit Document, expect S_OK), each per baseline/candidate. Each process uses the frozen visible conversion route, calls exactly one method on the converted handle and never GetText on it, then re-checks document text and focus. The frozen aggregate failure is re-raised after the differential, so the job stays red.

## Interpretation

All three variants crash: the converted handle itself is unusable, pointing at the array-to-legacy-handle conversion. All pass: the failure is specific to GetText on that handle. Mixed: method-specific. The provider overlay traces only GetText, QI, AddRef/Release, creation and array publication, so only clone can show provider entry (a created line); absence of provider lines for compare and expand is not evidence. No location, root cause or responsibility claim follows from this alone. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures, including run41170051294, remain retained.

Initial status: source prepared, no run yet.

## Initial validation result (1/2), 2026-10-31 05:09 UTC

Source 0a41bf5d6c70dab419976e54703e03fb71832c5d; run41170867473 attempt1, job124448340930: overall failure (frozen aggregate assertion re-raised, as designed). Artifact13030813623, `f09-handle-diff-41170867473-1`, 65672 bytes, SHA256 297468c6e4bb393b9c1d813a3ad4fbd39cb6b0a7dcff54da113042e9173c4062. Guard passed, both 26-check suites passed, frozen eight reproduced exactly: managed, legacy and visible 0xC0000005 on both sources; typed native COM baseline 1, candidate 0. Host hashes within the run: baseline b42736a8aa761c012ed309b94a7d8939cf671b3066651774ef012918292f06ac, candidate 97eda45d3c251e485499730002e9d73c13efda73d89e2a77317333725fa6dffa (again different from earlier runs; compare by source).

All six extra processes reached visible-array-converted (array VT12 dim1 0..0, element VT20) and returned from their single method. None crashed:

| Variant on converted handle | Baseline | Candidate | Raw method return |
|---|---|---|---|
| CompareEndpoints start vs DocumentRange | exit0 | exit0 | 0x52E1BD91, value 0 |
| Clone | exit1 | exit1 | 0x80040201, null clone |
| ExpandToEnclosingUnit Document | exit0 | exit0 | 0x52E1BD8F |

Package defect: the probe accepted SUCCEEDED(hr), not hr==S_OK. 0x52E1BD91 and 0x52E1BD8F have the failure bit clear but are not S_OK or any standard success code, and are identical across processes and sources. The compare and expand "passes" are therefore not valid evidence of normal success; the raw values above are the evidence. Clone failed with 0x80040201; the provider trace in that process shows no new range creation after the array range, so the provider-side Clone was not observed (the overlay does trace creation). Compare and expand are not traced by the overlay, so provider entry for them is unknown.

Reading: on the visible-array-converted legacy handle, GetText crashes (earlier runs) and three other legacy methods return a failure or a non-standard value; none of four methods behaved normally. This is consistent with the handle itself being unusable after conversion, rather than a GetText-only fault. It is not proof: the same three methods were not run on a direct DocumentRange legacy handle in this package, so how this probe and runner report a known-good handle's return values is not established. No location, root cause or responsibility claim. The correction run is not used: fixing the S_OK criterion adds no information because raw values are already recorded, and adding a direct-handle control would be a new diagnostic, not a defect fix. Formal F09 remains false; all prior failures retained.
