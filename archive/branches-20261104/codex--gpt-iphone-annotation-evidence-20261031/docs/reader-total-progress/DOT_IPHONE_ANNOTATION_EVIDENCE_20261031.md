# iPhone annotation exchange: single original-evidence audit

Status: correction CI retains accepted=false. Its6/7 labels include a new exact screenshot-role convention, not the fixed acceptance clause. Existing import activity/preview evidence awaits parent review; formal95/108 unchanged. This audit can only assess H.iphone.annotation_exchange; it does not change catalog.json or grant all Apple/F01–F12.

Exclusive branchcodex/gpt-iphone-annotation-evidence-20261031. Baseline94fb236a4a2da87dfbaf4f1dd2a47885d615a230 is the actual original Apple tested source, selected so the native test/body and producer contract remain unchanged. Exactly three additive paths:

- .github/workflows/dot-iphone-annotation-evidence-20261031.yml
- tools/reader_composition/iphone_annotation_evidence_20261031.py
- docs/reader-total-progress/DOT_IPHONE_ANNOTATION_EVIDENCE_20261031.md

The fixed catalog blob is e0c52bf139da2374cf58dbce40ae6c093a59f39d at5d4ec0ebd94fa3fabbf19af016073aef2877ac20. The complete clause is: iPhone：宿主标注文件导入/导出、预览确认及错误拒绝. It is partial/zero points there; no physical-device addendum appears in that individual clause. Physical-device qualification and final combined product remain separate. Formal95/108 stays unchanged pending the acceptance owner's review.

## Fixed original identities

Original run41170540560/attempt1 at94fb236a4a2da87dfbaf4f1dd2a47885d615a230 remains failure. iPhone native job124448286008 is success. Authentication job124461696689 remains failure; its ordinary log identifies only the iPad failures and reports scoped_acceptedtrue for the target iPhone artifact. That scoped flag is context, not a substitute for this audit.

Artifact13031773957, team24-apple-native-iphone-41170540560-1:324049983 ZIP bytes, SHA2567f32490e8692af06650494bbcb1be6c267214f90db1001bbb5a7b016ca66f4e7. Wave3 actual program9636784 bytes, SHA256e6ed87bd05b870621bbeff7d9175d88adaaeee22b1f9277a5e823f849ed5fdd6. Destination is iPhone SE3 simulator/iOS26.2, not physical hardware.

Frozen source blobs:
- tests/reader_team24_apple/ui/FeaturesUITests.swift:7b1b9d6b3d8093cf34744f3776a5f3b7ce3a1738
- tests/reader_team24_apple/run_ui.py:f7f2e5b388cd0072e9b3379772a0fcc76e3f70c9
- tests/reader_team24_apple/verify.py:99edf12381eef7aaf1aa1a2524dddbe4144d3948
- tests/apple_host/collect_evidence.py:61743374a1ffa526eb4a463f36a0f5af98fced1c

The original load_results explicitly initializes each case steps=[] and step_count0. The native mark helper retains actual XCTest screenshots. Empty summary steps therefore do not establish absent original attachments. The new audit independently reads the raw xcresult test tree, target activities, attachment manifest and bytes, scoped native log and frozen source.

## Required operation mapping

| Operation | Frozen source/expected original checkpoints |
|---|---|
| Import | FeaturesUITests.swift431–432; actual Files selection of EXReader-annotations.jsonl, native preview return and valid-preview checkpoint |
| Export | helper253–336 and case426/448–450; native JSONL/Markdown folder saves and content-consistency checkpoint |
| Preview |431–435/446–447; preview status, summary and explicit enabled confirmation |
| Confirm |453–455; explicit confirm, imported:1 status, confirmation disabled |
| Cancel |451–452; preview discard and absent preview summary |
| Duplicate | exported own bookmark is imported again; confirmed-exact-duplicate checkpoint. Do not invent an independently recounted revision/cardinality assertion |
| Error refusal |436–445; direct invalid/native-picked invalid JSONL, disabled confirmation and unchanged revision identity |

Every row needs actual retained PNG evidence owned by the exact target case, a matching original xcresult activity, a recorded timestamp and the original operation/assertion mapping. Source stop-on-first-assertion-failure, post-assertion checkpoint execution and one Passed invocation establish the successful original assertions; success is not inferred from the method name or39 total tests. Missing per-operation evidence is rejected as insufficient.

The audit verifies the fixed original API/run/job/attempt, original ZIP size/digest, safe ZIP boundaries and every producer file inventory hash. It binds the actual and nested-packaged program bytes/Info.plist to the fixed source. It checks raw wave3 case status, aggregate xcresult failure fields, target log failure/timeout indicators and failure attachments. The original failed aggregate/iPad results are retained separately; scoped acceptance does not overwrite them.

## Execution boundary

One macOS Actions job,20-minute ceiling, one initial push-triggered attempt only. No build, product launch, test rerun, fixture creation or product modification. All ZIP/xcresult handling stays in Actions. Source/Git/docs use the approved native lap25002 -> saved official instabox@0.8.52 -> original VM route; no DC or credential changes. No Apple owner branch/test edits, no F02 extra CI, main/shared branch, PR/tag/release or formal-catalog change. Result sealing may change only this document with [skip ci]; no automatic correction or second run.


## Actual sole audit result

**Inconclusive for the host feature; audit job failed before xcresult inspection.** Tested audit sourcefed03d9f9662a4f0619beb48d086b97b75c539d5, original product/test source94fb236a4a2da87dfbaf4f1dd2a47885d615a230.

[Run41246886339/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41246886339), job124672059258, completed failure. Job interval2026-10-31T22:09:30Z–22:10:30Z,60 seconds/1.00 elapsed runner-minute. The source/syntax/environment steps completed; the audit step failed at22:10:09.796573Z.

Actual result: acceptedfalse, evidence_sufficientfalse, errors["exact_original_file_inventory"], stageinventory_program_bundle. Frames in the tested new script are main257 -> verify_and_extract131 -> need39. The fixed original run/job/artifact metadata and raw ZIP size/SHA256 gates returned before this stage. The failure occurred at the new equality between ZIP member names and producer files inventory plus the root result.json.

The gate precedes the per-member hash loop, actual/nested program verification, raw xcresult test tree/activities/attachments, scoped log and seven-operation mapping. Those checks were **not executed**. This is not a discovered iPhone annotation functional failure or evidence that the original bundle is corrupt. No import/export/preview/confirm/cancel/duplicate/error-refusal verdict can be granted from this run.

### Source-contract finding and unresolved difference

The frozen producer tests/reader_team24_apple/run_ui.py158–160 generates its declared files inventory using path.name != 'result.json' and then writes the top-level result.json. Its frozen verifier tests/reader_team24_apple/verify.py53–54 checks the size/hash of each declared member; it does not require the producer inventory to exhaust the ZIP.

This new audit added a stricter all-members equality not supplied by that old contract. It did not export the actual missing/extra-name difference before stopping, so the precise mismatching members remain unknown. Excluding result.json by basename can differ from excluding only the root path; no specific nested result.json is asserted to exist without original-byte inspection.

A further authorized Actions-only audit should first publish the actual safe member-set difference and verify the original declared inventory according to its contract, while retaining the fixed whole-ZIP hash, safe ZIP boundaries, source/program identity and all seven operation gates. No product/test change or speculative fix was performed here. This sole-round approval does not authorize correcting the audit and pushing another run.

### Retained audit artifact

[iphone-annotation-original-audit-41246886339-1](https://github.com/NoGod3524/EXReader/actions/runs/41246886339/artifacts/13059895344)
- ID: 13059895344
- ZIP bytes: 323644424
- SHA256: 5eb050abc39f7dff0d290745c377f57828d7d8cbe2669d70c5b60afa130861c1
- Expiry: 2027-01-29T22:09:27Z

API identity/bytes/digest match the ordinary upload log. The artifact preserves original.zip, summary.json, original-metadata.json, source-contract.json and parser-environment.json. The original324049983-byte ZIP remains preserved as bytes inside this separate audit artifact; no old artifact or failed run was deleted/overwritten. No raw xcresult or PNG mapping output is claimed to have been generated.

One of one20-minute audit slots is consumed; unused ceiling is not a second attempt. No automatic correction, rerun, dispatch, build, product launch or test rerun occurred. Only this document is sealed [skip ci] after the result. Source/Git/docs used the approved original VM/native CLI route, and all ZIP processing occurred in this macOS Actions job.

The original Apple run41170540560/A1 and iPad/aggregate failures remain failed. The earlier iPhone scoped_acceptedtrue statement remains its original limited producer/verifier result; this failed new audit neither upgrades it nor silently revokes it. H.iphone.annotation_exchange remains partial until a successful sufficient single-item audit and acceptance-owner review. Formal95/108 and catalog.json remain unchanged. F02 and external Apple/UI/F08/C02 owner scope are untouched.

Seal prepared 2026-10-31T22:14:45.207186+00:00 / 2026-10-31T18:14:45.207186-04:00.


## Explicitly approved inventory-contract correction

A separate single correction run was authorized after the initial audit defect. Its edit baseline is the prior document sealcb7ee5540979aea7ce8446d3b0c1302e4cd72916 on the same exclusive branch/tree. Only the audit script and this document may change. The workflow blob remainsbc4322cde078d602501105c13f0ee029bf866a90; original Apple product/tests/catalog remain frozen.

The invalid full-member equality is replaced with the original contract: every declared member must exist and retain its exact declared bytes/SHA256, and every declared member is still hashed. Before those checks, inventory-difference.json and the ordinary log enumerate the actual missing declarations and unlisted members, including each unlisted member's observed bytes/hash and whether its basename is result.json. The actual difference is measured in Actions, never guessed from producer source. Unlisted authentic members are covered by the unchanged fixed whole-ZIP digest and ZIP safety checks; they are not falsely represented as covered by the producer's declared inventory.

Static review of the rest of the audit found no other established all-members/exhaustive-inventory promise to impose. The explicit fixed-input source/job/attempt/device/program values remain fixed; the old producer's wave3 five-case/zero-exit contract remains; the seven operation checkpoints, case ownership, timestamps, raw failure/timeout checks and post-assertion screenshot requirements remain. The selected program and Info.plist must still be regular entries and match both original and nested packaged bytes/source. ZIP canonical paths, case-insensitive duplicates, encryption/type/size budgets and no symlink extraction remain unchanged. No acceptance condition is substituted by the old scoped flag or39-test total.

This static review does not certify an unobserved xcresult schema or prefill missing operation evidence. Actual parser outputs remain retained; missing data still rejects acceptance.

One additional macOS job,20-minute ceiling, initial attempt only; no automatic third run. No product build/launch or original-test rerun. The initial fed03d9f/run41246886339 defect failure, original input and audit artifact13059895344 remain intact. Formal95/108 stays unchanged pending successful scoped evidence and parent acceptance review.

Correction prepared 2026-10-31T22:20:29.029102+00:00.


## Actual approved correction result

The inventory-contract defect is corrected; **the single-item audit remains not accepted** because one import screenshot-role binding is unresolved. This is an evidence-mapping outcome, not a reproduced product failure.

Tested audit source45d737947a8958e36ebd49923c22812b0c619ed2, edit parentcb7ee5540979aea7ce8446d3b0c1302e4cd72916. Only the approved script and this document changed; workflowbc4322cde078d602501105c13f0ee029bf866a90 and all Apple product/original-test bytes stayed fixed.

[Run41247817895/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41247817895), job124674807831, completed failure at the evidence-sufficiency guard. Interval2026-10-31T22:21:28Z–22:22:25Z:57seconds,0.95 elapsed runner-minute. acceptedfalse/evidence_sufficientfalse/all_seven_completefalse/covered6/errors["missing_per_operation_original_evidence"]. The audit reached stagecomplete; it did not stop at a parser exception.

### Actual member difference and authentication

Original artifact13031773957 was read in Actions:324049983 bytes, SHA2567f32490e8692af06650494bbcb1be6c267214f90db1001bbb5a7b016ca66f4e7. **All763 declared members were verified**, with no missing declaration. The actual ZIP contains765 files. The measured unlisted set is exactly:

| Actual unlisted member | Bytes | SHA256 | Excluded by producer basename result.json rule |
|---|---:|---|---|
| result.json |215247|e98cf06efb9b7368374fbb01614c3bc271347840f3c290957bddab7ed8c0ea1e|true|
| sdk342-native-identity.json |1727|eaf0c0d2a1dc5fd4fb6b90de7501efa1489475cc1efe8be785ec8a983768c2a5|false|

This difference is actual data, not the previously untested nested-result.json hypothesis. Frozen source references for writing the SDK sidecar are tests/apple_features_repair_20261029/admission.py88 and tests/apple_sdk342_host/run_ui.py88. The original declared-member verifier did not promise an exhaustive ZIP-member inventory. Both unlisted byte strings remain authenticated by the pinned complete original ZIP; no declared-member check was skipped.

The actual wave3 program and nested packaged program were verified:9636784 bytes, SHA256e6ed87bd05b870621bbeff7d9175d88adaaeee22b1f9277a5e823f849ed5fdd6, Info.plist/source94fb236a4a2da87dfbaf4f1dd2a47885d615a230, org.exreader.host. Native test command exit0. Original destination is arm64 iPhone SE(3rd generation),iOS26.2 Simulator, not physical hardware.

### Raw test and seven operation mapping

Raw xcresult has the target at $.testNodes[0].children[0].children[0].children[2], nodeIdentifierFeaturesUITests/testNativeAnnotationPreviewConfirmCancelAndDuplicate(). Its result is Passed and duration189.3697990179062 seconds. There is one original target invocation. Raw wave3 summary is5 passed/0 failed/0 expected failures/0 skipped, testFailures[]. Target native log/attachments produced no hidden failure or execution-timeout finding.

Full per-checkpoint activity paths, original log lines, timestamps, screenshot bytes/hashes and frozen assertions are in seven-operations.json/summary.json. The table below summarizes the actual output; source lines refer to the frozen FeaturesUITests.swift blob7b1b9d6b3d8093cf34744f3776a5f3b7ce3a1738. All timestamps are from original2026-10-31 execution, not this audit's time.

| Operation | Audit mapping | Frozen source lines | Original checkpoints and evidence paths |
|---|---|---|---|
| Import | insufficient | 431–432 | native-picker-selected-file-EXReader-annotations.jsonl: original activity/log at76.96s and125.35s; no matching screenshot role; native-preview-no-revisions-write: 2026-10-31T05:31:20.125Z, attachments/5D8B700D-B05B-44F7-92BC-5EDB84F11714.png; native-picker-valid-preview: 2026-10-31T05:32:07.553Z, attachments/2C0DD3AA-9775-4311-9A5D-62986B221DE3.png |
| Export | mapped | 253–336 | native-jsonl-folder-save: 2026-10-31T05:30:56.933Z, attachments/C4234E12-F6E5-47B6-9268-9F54A40EB56D.png; native-markdown-folder-save: 2026-10-31T05:32:26.379Z, attachments/C0FDC31D-52D2-47EF-A34A-2EAFC5A65CDE.png; jsonl-markdown-content-verified: 2026-10-31T05:32:32.036Z, attachments/9DB4B72F-A210-435F-8E34-6D8F225B11E1.png |
| Preview | mapped | 431–435 | native-preview-no-revisions-write: 2026-10-31T05:31:20.125Z, attachments/5D8B700D-B05B-44F7-92BC-5EDB84F11714.png; native-picker-valid-preview: 2026-10-31T05:32:07.553Z, attachments/2C0DD3AA-9775-4311-9A5D-62986B221DE3.png |
| Confirm | mapped | 453–455 | confirmed-exact-duplicate: 2026-10-31T05:32:56.310Z, attachments/48DE2595-7509-4D16-8E12-DBF6B86BE7F8.png |
| Cancel | mapped | 451–452 | preview-cancel: 2026-10-31T05:32:41.065Z, attachments/D38BA2E7-7185-421A-9D81-BDC48571AEBB.png |
| Duplicate | mapped | 426–454 | jsonl-markdown-content-verified: 2026-10-31T05:32:32.036Z, attachments/9DB4B72F-A210-435F-8E34-6D8F225B11E1.png; confirmed-exact-duplicate: 2026-10-31T05:32:56.310Z, attachments/48DE2595-7509-4D16-8E12-DBF6B86BE7F8.png |
| Error refusal | mapped | 436–445 | invalid-annotation-rejected: 2026-10-31T05:31:33.259Z, attachments/6B18FA0B-16EA-4528-9015-1D79F926F169.png; native-picker-invalid-rejected: 2026-10-31T05:31:47.558Z, attachments/8056E0D4-0D2F-4797-9C74-2EDD063E7CC5.png; invalid-import-revision-identity-unchanged: 2026-10-31T05:31:55.742Z, attachments/747CC4AF-8C47-4B66-8642-63E19DC293BC.png |

Import is the only coveredfalse row. The marker native-picker-selected-file-EXReader-annotations.jsonl has4 activity hits representing two observations at original elapsed76.96s and125.35s. Relevant activity titles are $.testRuns[0].activities[136].title and $.testRuns[0].activities[224].title, startTime1793424677.06 and1793424725.449. Following valid-preview checkpoints have retained PNGs and timestamps. However, the current mapper found zero PNG records whose decoded role exactly matches that file-selection marker.

This result establishes an unresolved attachment-role/byte binding. It does **not** establish that the original source never created that screenshot, that the import operation failed, or that a screenshot is physically absent from the package. The retained attachment export/manifest and target-attachments.json must be inspected in Actions before distinguishing a missing payload from a naming/type interpretation issue. Do not delete the missing-image gate or accept a method name as replacement evidence. No third run or further mapper correction was performed.

The duplicate row is limited to the original explicit repeat-import/processed1/disabled-confirmation assertions; it does not claim a separately recomputed post-import revision/cardinality count.

### Retained correction evidence and budget

[iphone-annotation-original-audit-41247817895-1](https://github.com/NoGod3524/EXReader/actions/runs/41247817895/artifacts/13060060920)
- Artifact ID: 13060060920
- Outer audit ZIP bytes: 327591328
- Outer audit ZIP SHA256: 47ceb363986b21e5f1f90243641b5d1ceb35d1d01696703090fab6580f713200
- Expiry: 2027-01-29T22:21:26Z

Its API ID/bytes/digest match the ordinary upload log. Read summary.json, inventory-difference.json, seven-operations.json, target-attachments.json, target-activities.json, target-native-ui.log, attachments/manifest.json and the original kept screenshot files. It also preserves original.zip with the original input identity above. Outer audit ZIP and inner original ZIP identities are distinct.

The separately approved correction slot is1/1 consumed. Initial audit41246886339 remains failed and preserved with artifact13059895344; the two approved job intervals total117seconds/1.95 elapsed runner-minutes. Unused20-minute ceilings do not grant a third run. Only this document is sealed [skip ci] after terminal results.

No product build/launch, original-test rerun, new fixture, catalog change or external owner edit occurred. Original aggregate Apple/iPad failures remain unchanged. Scoped acceptance was not granted; H.iphone.annotation_exchange remains partial, formal95/108 unchanged, pending parent review and any newly authorized evidence work.

Correction seal prepared 2026-10-31T22:27:06.746421+00:00 / 2026-10-31T18:27:06.746421-04:00.


## Clarification: exact screenshot role is an audit convention

The literal role native-picker-selected-file-EXReader-annotations.jsonl plus a separately matched .png file is **not** stated in H.iphone.annotation_exchange or in the original producer/verifier acceptance contract. The fixed clause requires host annotation file import/export, preview/confirmation and error refusal. It names no screenshot role, export filename, extension or per-checkpoint image count.

The frozen test does call mark("native-picker-selected-file-" + name) before selecting the native Files item. That source behavior does not establish that xcresulttool must export a PNG under the exact role string parsed by this new audit. The new ROWS/import mapping and the conjunction role==marker and filename.endswith(".png") introduced that representation rule.

Accordingly, the retained covered6/acceptedfalse result describes the new mapper's decision. It is **not** a formal finding that only six required operations have original evidence, that the original package lacks an image, or that native import is defective.

Actual already-output import evidence includes:
- selected-file activities/log at76.96s and125.35s (activity136/224, startTime1793424677.06/1793424725.449);
- following actual kept preview PNGs at80.03s and127.45s:5D8B700D-B05B-44F7-92BC-5EDB84F11714.png and2C0DD3AA-9775-4311-9A5D-62986B221DE3.png, with recorded hashes;
- the frozen chooseAnnotationFile control flow performs the native file tap/return before the preview assertions; the one original case Passed with continueAfterFailurefalse and no raw failure/timeout finding.

This existing sequence is available for the parent acceptance owner's review against the original clause. The current output does not settle whether the unmatched dedicated marker payload was absent, renamed or represented differently by the exporter. No actual missing product behavior or missing original payload has been established by this marker mismatch alone.

The raw CI remains failed, its summary is not edited to passed, the script/row conditions are not changed after the run, and formal95/108 remains unchanged. Any parent scope decision should evaluate the existing operations/assertions/activity/preview evidence, not treat the newly invented role equality as part of the product contract. A further Actions payload-binding inspection is only needed if that review requires it; it is not automatically mandated by the6/7 mapper label. No third run or acceptance waiver is performed here.

Clarification prepared 2026-10-31T22:30:49.153627+00:00 / 2026-10-31T18:30:49.153627-04:00.
