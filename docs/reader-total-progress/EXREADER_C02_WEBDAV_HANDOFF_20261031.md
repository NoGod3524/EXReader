# EXReader continuation: independently accepted iPhone annotation exchange

Formal ledger: **96/108 = 88.89%**. Static catalog counts are **96 verified,1 partial,11 pending,total108**. This records the parent's independent scoped acceptance and the user's approved single-item ledger update; no new Actions audit is represented as passed.

## Fixed ledger baseline and exact change

Branchcodex/gpt-iphone-acceptance-96-20261031 starts at formal95-item commit5d4ec0ebd94fa3fabbf19af016073aef2877ac20, catalog blob e0c52bf139da2374cf58dbce40ae6c093a59f39d. No catalog data is copied from the older handoff branch.

Only H.iphone.annotation_exchange changes from partial to verified, with one evidence reference and its related scope note. All other107 requirement records, including the existing95 verified items, iPad annotation and every F item, remain identical to the fixed formal source. The only new catalog evidence record uses the existing generic named-case schema and explicitly records expected_conclusionfailure for the original run.

The second path is this new continuation document. No product,SDK,test,workflow,validator,main/shared branch,PR,tag or release change. Static text/Git review only; no local/VM validation script,syntax check,build,test or ZIP processing was run.

## Accepted fixed clause and independent review

Requirement: H.iphone.annotation_exchange.
Original complete clause: iPhone：宿主标注文件导入/导出、预览确认及错误拒绝.

The parent dot independent reviewer accepted the seven operation/assertion chains against that original clause. The user approved this single-item ledger entry. The entry is not based on changing a failed CI result to green.

Original tested product/test source:
94fb236a4a2da87dfbaf4f1dd2a47885d615a230.
[Original run41170540560/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41170540560), iPhone native job124448286008success. The complete original run and iPad/aggregate failures remain failed.

Original artifact13031773957:
324049983 bytes/SHA2567f32490e8692af06650494bbcb1be6c267214f90db1001bbb5a7b016ca66f4e7.
Actual wave3 program:
9636784 bytes/SHA256e6ed87bd05b870621bbeff7d9175d88adaaeee22b1f9277a5e823f849ed5fdd6.
Destination: arm64 iPhone SE(3rd generation),iOS26.2 Simulator; physical_devicefalse.

The frozen target case testNativeAnnotationPreviewConfirmCancelAndDuplicate() Passed189.3697990179062 seconds, with continueAfterFailurefalse and one original invocation. Raw wave3 xcresult is5 passed/0 failed/0 expected failures/0 skipped; no hidden failure or execution-timeout finding.

| Operation | Original evidence reviewed |
|---|---|
| Native import | Files selection activities at76.96s and125.35s; frozen chooseAnnotationFile performs the native file tap/return, followed by actual preview/status/summary and enabled-confirmation evidence at80.03s and127.45s |
| Export | Native JSONL folder save56.83s, Markdown save146.28s, and content-consistency assertion151.94s |
| Preview | Actual retained preview PNGs, summary and enabled-confirmation assertions at80.03s/127.45s |
| Confirmation | Explicit confirm, imported:1 status and disabled confirmation at176.21s |
| Cancellation | Explicit preview discard and absent summary at160.97s |
| Repeat import | The original exported record is explicitly imported again; processed1/disabled-confirmation assertions. No independent revision/cardinality recount is claimed |
| Error refusal | Direct invalid/native-picked invalid JSONL disable confirmation; retained revision identity remains unchanged at93.16s,107.46s and115.64s |

The fixed clause and original producer/verifier do not require a separately exported PNG with role native-picker-selected-file-EXReader-annotations.jsonl. That exact role/extension equality was introduced by the new audit mapper. Its mismatch does not erase the already-observed native selection and following preview/assertion chain, and cannot by itself establish absent original evidence.

[Full audit-rule clarification, sealed15682faeedec11c196f6a6232ae55a01eb00ea17](https://github.com/NoGod3524/EXReader/blob/15682faeedec11c196f6a6232ae55a01eb00ea17/docs/reader-total-progress/DOT_IPHONE_ANNOTATION_EVIDENCE_20261031.md).

## Original failures and machine-audit scope retained

Initial new auditfed03d9f9662a4f0619beb48d086b97b75c539d5/run41246886339/A1 failed at an incorrectly exhaustive inventory equality. It remains failed and preserved.

[Corrected audit41247817895/A1](https://github.com/NoGod3524/EXReader/actions/runs/41247817895), source45d737947a8958e36ebd49923c22812b0c619ed2, authenticated the pinned original ZIP, all763 declared file hashes, actual/nested program identity and raw xcresult. Actual ZIP765 files; unlisted members are result.json and sdk342-native-identity.json, both covered by the complete fixed ZIP hash.

That corrected run remains failed with acceptedfalse and6/7 mapper labels solely because of the additional exact selected-file screenshot-role gate. The parent independent review uses the original clause and actual operation/assertion evidence, not that added representation rule. No CI status,summary or failed artifact was rewritten.

[Correction evidence artifact13060060920](https://github.com/NoGod3524/EXReader/actions/runs/41247817895/artifacts/13060060920):
327591328 bytes/SHA25647ceb363986b21e5f1f90243641b5d1ceb35d1d01696703090fab6580f713200.
It retains the original ZIP and full inventory,activity,attachment,source/assertion and log mapping. Outer audit ZIP and inner original ZIP identities differ.

## Remaining scope and continuation

Only this one host outcome is added. iPad annotation remains partial; F01–F05 andF07–F12 remain pending. No physical-device,whole-Apple,six-target,full-F02 or final combined-product acceptance is granted.

Apple product/UI/F08/C02 and all existing owners remain unchanged. F02 same-source run41244498593 still fails at Windows native_transfer PermissionError; no new F02 execution is authorized here. C02/WebDAV and previous handoffs remain available on their original sealed branches; this document does not merge those implementations.

Both iPhone audit budgets are consumed (one initial and one separately approved correction); no third run or product/test rerun. This ledger publication is docs-only [skip ci], with no new CI.

Source/Git/docs use only approved native lap25002 -> saved official instabox@0.8.52 -> original m_agqxv2s72g5vwdtsifu5cnmml4. All project execution/ZIP handling remains Actions-only. DC remains unused; no new VM,credentials or recovery changes.

Ledger prepared 2026-10-31T22:43:27.251462+00:00 / 2026-10-31T18:43:27.251462-04:00.
