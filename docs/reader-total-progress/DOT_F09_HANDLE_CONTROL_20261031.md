# F09 direct legacy handle control

Authorized branch codex/dot-f09-handle-control-20261031; parent 6f519876e6ee3bdb1bdd25952f6733ffba994aa6. Exactly four new files: control_probe.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions.

## Question

Run41170867473 found that on the visible-array-converted legacy handle Clone returns 0x80040201 and CompareEndpoints/ExpandToEnclosingUnit return non-standard values 0x52E1BD91/0x52E1BD8F, while GetText crashes in earlier runs. Without a control it is unknown what the same probe on this runner reports for a known-good handle. This package supplies that control in the same run and against the same host binaries.

## Method

run.py runs the byte-frozen handle-diff driver unchanged: frozen eight observations, 26-check suites and assertions, then its six array-handle processes with their original SUCCEEDED criterion and raw values. Only guard parent, new paths, frozen list (now including both handle-diff files) and output directory are updated. Then eight control processes run: compare, clone, expand and gettext on a direct TextPattern_get_DocumentRange legacy handle, each per baseline/candidate. Control criteria are strict: hr must equal S_OK; compare must give 0 against a second DocumentRange; clone non-null; gettext must equal the earlier document text. Raw hr is logged as hex. No array conversion, no selection input, no book text logged. The frozen aggregate failure is re-raised at the end, so the job stays red.

## Interpretation

Control all S_OK while array-handle values stay abnormal in the same run: the converted handle behaves differently from a direct one in the same process type, localizing the anomaly to the array-to-legacy-handle conversion. Control also showing the non-standard values: the probe's or runner's legacy return reporting is itself unreliable and the earlier differential cannot be read as handle failure. No location, root cause or responsibility claim. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures, including run41170051294 and run41170867473, remain retained.

Initial status: source prepared, no run yet.
