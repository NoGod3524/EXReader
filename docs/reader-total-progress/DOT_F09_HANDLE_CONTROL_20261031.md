# F09 direct legacy handle control

Authorized branch codex/dot-f09-handle-control-20261031; parent 6f519876e6ee3bdb1bdd25952f6733ffba994aa6. Exactly four new files: control_probe.cpp, run.py, workflow, this document. One initial Actions run and at most one correction limited to defects of this package; the job keeps the 90min cap. All execution only GitHub Actions.

## Question

Run41170867473 found that on the visible-array-converted legacy handle Clone returns 0x80040201 and CompareEndpoints/ExpandToEnclosingUnit return non-standard values 0x52E1BD91/0x52E1BD8F, while GetText crashes in earlier runs. Without a control it is unknown what the same probe on this runner reports for a known-good handle. This package supplies that control in the same run and against the same host binaries.

## Method

run.py runs the byte-frozen handle-diff driver unchanged: frozen eight observations, 26-check suites and assertions, then its six array-handle processes with their original SUCCEEDED criterion and raw values. Only guard parent, new paths, frozen list (now including both handle-diff files) and output directory are updated. Then eight control processes run: compare, clone, expand and gettext on a direct TextPattern_get_DocumentRange legacy handle, each per baseline/candidate. Control criteria are strict: hr must equal S_OK; compare must give 0 against a second DocumentRange; clone non-null; gettext must equal the earlier document text. Raw hr is logged as hex. No array conversion, no selection input, no book text logged. The frozen aggregate failure is re-raised at the end, so the job stays red.

## Interpretation

Control all S_OK while array-handle values stay abnormal in the same run: the converted handle behaves differently from a direct one in the same process type, localizing the anomaly to the array-to-legacy-handle conversion. Control also showing the non-standard values: the probe's or runner's legacy return reporting is itself unreliable and the earlier differential cannot be read as handle failure. No location, root cause or responsibility claim. No product, provider or consumer change. Formal F09 acceptance and screen-reader verification remain false; all prior failures, including run41170051294 and run41170867473, remain retained.

Initial status: source prepared, no run yet.

## Initial validation result (1/2), 2026-10-31 05:24 UTC

Source 5081a5468d8d2f34a69f2c0c65c1d81fa0c3c924; run41171939136 attempt1, job124451560082: overall failure (frozen aggregate assertion re-raised, as designed). Artifact13031398551, `f09-handle-control-41171939136-1`, 89781 bytes, SHA256 1692341f35645c61a9673015872922af53d95e06d714efd7fc3e7ca030929da1. Guard passed, both 26-check suites passed, frozen eight reproduced exactly (managed, legacy, visible 0xC0000005 both sources; typed COM baseline 1, candidate 0). Host hashes in this run: baseline a910113c6a3e…, candidate 4257072813ac… (full values in artifact; again different from earlier runs).

Same run, same host binaries, same process type:

| Method | Direct DocumentRange handle (control, strict) | Visible-array-converted handle (frozen differential) |
|---|---|---|
| CompareEndpoints | S_OK, value 0, both sources pass | 0xC0FABD91, value 0, both fail |
| Clone | S_OK, non-null, both pass | 0x80040201, null, both fail |
| ExpandToEnclosingUnit Document | S_OK, both pass | 0xC0FABD8F, both fail |
| GetText | S_OK, length 432 equal to document text, both pass | 0xC0000005 crash (frozen visible consumer) |

The array-handle compare and expand values changed from run41170867473 (0x52E1BD91/0x52E1BD8F) to 0xC0FABD91/0xC0FABD8F: upper 16 bits differ between runs, lower 16 bits and the difference of 2 are identical, and baseline equals candidate within a run. They are not stable HRESULTs. Clone 0x80040201 is identical across both runs.

Result: the control removes the earlier caveat. On this runner the probe reports S_OK correctly for a known-good legacy handle, while all four methods misbehave only on the handle produced by TextPattern_GetVisibleRanges → VT_I8 element → UiaHTextRangeFromVariant. This localizes the anomaly to the array-to-legacy-handle conversion in the client path, identically for baseline and candidate hosts. It does not identify a module, instruction or responsible party, and does not show whether the provider's VT_UNKNOWN array contents or the client conversion is at fault; the typed COM client reading the same provider array still passes. No correction run needed or used. No product, provider or consumer change. Formal F09 remains false; all prior failures retained.
