# F09 legacy handle-method differential

Authorized branch codex/dot-f09-handle-diff-20261031; parent 570b320a3b6b80dc8019dbbfa6b8dde6c373d599. Exactly four new files: handle_probe.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions. Option A of the read-only proposal; options B (in-process exception location) and C (starting WerSvc on the runner) are not implemented.

## Question

Run41165411704 and run41170051294 show the visible-array-converted legacy handle crashes the consumer with 0xC0000005 on TextRange_GetText, while direct DocumentRange GetText passes and the provider trace shows no GetText entry for array ranges. Is the converted handle unusable for any legacy method, or does only GetText fail?

## Method

run.py runs the byte-frozen av-stack driver (frozen visible-range driver plus the verified event collector) with only guard parent, new paths, frozen list and output directory updated. The eight observations, both 26-check suites, assertions and timeouts are unchanged. Only if the frozen run reaches its final aggregate assertion (verdict written) do six extra independent processes run against the same two host binaries: variants compare (TextRange_CompareEndpoints start versus DocumentRange start, expect 0), clone (TextRange_Clone, expect non-null) and expand (TextRange_ExpandToEnclosingUnit Document, expect S_OK), each per baseline/candidate. Each process uses the frozen visible conversion route, calls exactly one method on the converted handle and never GetText on it, then re-checks document text and focus. The frozen aggregate failure is re-raised after the differential, so the job stays red.

## Interpretation

All three variants crash: the converted handle itself is unusable, pointing at the array-to-legacy-handle conversion. All pass: the failure is specific to GetText on that handle. Mixed: method-specific. The provider overlay traces only GetText, QI, AddRef/Release, creation and array publication, so only clone can show provider entry (a created line); absence of provider lines for compare and expand is not evidence. No location, root cause or responsibility claim follows from this alone. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures, including run41170051294, remain retained.

Initial status: source prepared, no run yet.
