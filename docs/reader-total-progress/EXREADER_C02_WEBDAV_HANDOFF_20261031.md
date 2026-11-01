# EXReader continuation snapshot — 2026-11-01 00:22 UTC
Actual preparation observation: **2026-11-01T00:21:48Z / 2026-10-31 20:21:48 America/New_York (EDT)**.

Continuity backup only, not completion or suspension. Formal catalog remains **96/108 (88.89%): 96 verified / 1 partial / 11 pending**, pinned at `5db41cb19673fb75bb0b498c677d770931ac33e8`. This update changes only this document on the independent documentation branch; no catalog/source/test/workflow change or CI.

## Latest approval and execution boundary

User at **00:20:51Z** approved both the previously specified A and B batches (message `Sentinel_65b3db377d1c81918a134c3f56b3d706`); coordinator confirmed at00:20:59. This supersedes the immediately preceding “waiting for A/B approval” status. At this observation **neither new batch has a reported implementation commit or run**. Do not invent a new source SHA or treat a queued instruction as a passed test.

- **A:11 paths / one200 runner-minute cap** (GTK60 + Android120 + audit20), genuine GTK-author → Android shared candidate, no automatic retry. Reuse/parameterize the existing `.github/workflows/dot-f03-same-source-20261031.yml`, not an extra workflow. Canonical branch planned `dot/reader-suite-20261101`, from product `94fb236a4a2da87dfbaf4f1dd2a47885d615a230`. F03 alone creates it and writes9 package files; F07 alone writes workflow and scope.json and is sole trigger. Exact9 package files: scope.json, identity.py, build.py, fixtures.py, gtk.py, android.py, verify.py, android/OrganizationInteropTest.java, README.md under tests/dot_f03_same_source_20261031, with scope.json assigned to F07; remaining document is docs/reader-total-progress/DOT_F03_SAME_SOURCE_20261031.md assigned to F03. No Apple production delta or Windows driver is included. F04/F05 are explicitly not-run, not passed.
- A keeps original Android native owner17, typed-kill2, functional112, gate87, altered-owner19 and original organization/UI/recovery evidence; same actual APK and fixture CA, new instrumentation separately identified. Old ordinary owner builder has no sync, whereas the prior wave3 recipe lacks full owner evidence; the new adapter must preserve original producer/checker output while enabling existing sync on the same APK. No original assertion removal.
- New candidate admission separates product94fb from frozen SDK `8357eafa28423a7ab93ba08b823af80f01ad1505`. SDK paths are src/include/cmake/CMakeLists.txt/bindings. Original tests/fixtures and production remain unchanged from94fb; exact11-path allowlist. Existing checker candidate env uses94fb/94fb and preserves its actual report fields; `historical_owner_guard_reexecuted=false` with historical evidence reference. Empty historical review range is not represented as a new historical owner audit. The outer admission separately proves SDK object identity against8357.
- **B:13 paths / one60 runner-minute cap** (Linux45 + audit15), continuing `dot/f10-stale-owner-20261031` from the b5e7 family. Five production paths: extras/webdav/include/exr_webdav.h, extras/webdav/src/webdav.cpp, extras/webdav/include/exr_webdav_managed.h, extras/webdav/src/webdav_managed_posix.inc, apps/reader/sync/src/sync.cpp. Six existing scoped CMake/run/verify/manifest/workflow/doc files plus two new sync_probe.cpp/https_fixture.py; original probe.c stays unchanged. New bounded callback upload and managed sync snapshot integration, not all-platform acceptance.
- B explicitly includes approved persistent registry v1→v2 purpose labeling: a single total16-root budget,64 lifetime slots per root, no slot reuse; old download roots keep their purpose and recovery behavior. Old binaries reject v2; no automatic downgrade. This compatibility/migration change was disclosed in the approved proposal, not hidden as an implementation detail. Preserve original33 cases/258 assertions/8 negative controls, old failures and prior limits. No path-borrow shortcut that could upload replaced bytes; callbacks read the held descriptor and preserve cancellation, 412 verification and acknowledgment rules.

At23:58:15 the user required **test design before each new batch**, independent review of proof/counterexamples and precise failure reasons, and convergence toward a parameterized suite. No arbitrary replacement of original acceptance criteria. One implementation stream plus independent verification per module family; no redundant implementation branches. F03/F07 share one canonical candidate with disjoint writer paths, not competing candidates. Historical branches remain sealed, not deleted.

## Fixed deliverables and package state

| Package | Last fixed branch / HEAD | Evidence and present state |
|---|---|---|
| F03 | dot/f03-same-source-20261031 / 0fa23868a585c6a7698e05ea25a835f279063c8a | Old preparation sealed;0CI. Apple organization production delta b3ef06e169b6c0f56ea3d76246351018b0ef37e1 remains on this old line, uncompiled/unaccepted, not included in A. New A preparation authorized, no new commit/run observed. |
| F04 | dot/f04-reading-sync-20261031 / 0ab2d3e4a792d9d2f274cf085f3c1e44f4fea5ea |12 added files;0CI. Hash dependency ordering reviewed, real graph/retained producer integration incomplete; blocked/deferred, not part of A. |
| F05 | dot/f05-client-recovery-20261031 / ce34586d0f45e1fa6856e7eb760c8446eaeb38a5 | Last observed fixed preparation;9 files, no workflow or CI. Real host driver preparation remains partial, delete-conflict UI detail and exact suite/aggregate mapping unresolved. Original265-minute allowance unused and not transferred to A. |
| F06 | Formal source8f8acf3234cba747165f001c0c96efe1b911e6ad / run40678657371 | Already verified six-package identity; no rerun. This agent now performs independent review and documentation, not active F06 implementation. |
| F07 | dot/f07-link-evidence-20261031 / 697448abd8188580304806163ba9b543e76ba9ba | Diagnostic run41251856370 A1 succeeded; provider proof remains ambiguous and F07accepted=false. Old line sealed. New A workflow/scope preparation authorized, no new run observed. |
| F10 | dot/f10-stale-owner-20261031 / API seal659ef67bb6d408bb5653cedd03efe06e9d7dd6f9 | Additive API independently verified as below; fullF10false. Old safety/diagnostic lines sealed. New B preparation authorized, no new commit/run observed. |

Actual six native-dot assignments at this observation: **3 authorized implementation-preparation assignments** (F03 canonical package, F07 disjoint workflow/scope, F10 B), **1 independent review/documentation assignment** (F06 agent), **2 blocked/deferred packages** (F04/F05). Active CI/testing-wait:0. Completed sealed results are evidence, not additional active implementation slots. No Codex/Claude task or extra team started.

## Independently checked F10 delivery evidence

1. No-replace cache publication: [run41253596892 A1](https://github.com/NoGod3524/EXReader/actions/runs/41253596892), source `123e1852335ab16e3bc1863e050eb0a298b01cca`; Linux124691995530 success, audit124692312679 overall failure because the original cleanup gaps remained. `no_replace_passed=true`, evidence_consistent=true/errors[], four publication cases and six exact semantic negatives passed. Seal `e3fac494afdb6b24a1448e8eeb665860f98f4d27`. Producer13062596391 /953269bytes /SHA256 a9e75b56dd5d59f0c235e15797306f442920f9c055b06e2b004dff6a9bc7d9e2; audit13062501822 /1530bytes /SHA256 8308a569f156774ff92d6a4d1ca10047823e957e4d775c6dd8dc143bf2d199d4. This is a valid partial repair, not full acceptance; EACCES and kill snapshot residue remained red.
2. Additive cleanup API: [run41254709863 A1](https://github.com/NoGod3524/EXReader/actions/runs/41254709863), source `1dd213236ccd77899cb58c7d7ec58d5d3bca4448`; Linux124695313603 and audit124695358391 success. Ordinary audit log independently checked: api_accepted=true/errors[],33 cases/258 assertions,29 installed-consumer cases +4 explicitly labeled existing-hook real-SIGKILL boundary cases,8 exact negative controls rejected; **full_f10_complete=false**. Producer13061754329 /101625bytes /SHA256 bd79ea75b8475caea784b0f519f70d9d5073ddb67326b32df17e7c3d179da5e8; audit13062403971 /711bytes /SHA256 9ce612a724d9559498c28c7659c0c340481fc4bad239ce9c93697f4c34603862. APIs/ordinary logs agree; no local ZIP parsing.
3. API scope is POSIX Linux/cooperative private namespace, not high-level sync wiring, six-host SDK acceptance, malicious same-UID resistance, or hardware power-loss proof. B must demonstrate the actual sync cleanup loop separately.

## P0, integration and continuation

P0 migration safety is not fully accepted by C02/F10 component results. Concurrent heads/tombstones must be preserved and native conflict presented; existing explicit restore/resolve must cover all competing parents, but universal automatic single-head resolution was never required. F05 partial UI results do not count as complete recovery. SDK3.42 same-label artifacts from b5e7/SDK7271829a829bfa6aaa47b73077c493f71af27ad3 are not silently equivalent to A's8357 SDK; no automatic merge across these baselines.

The user explicitly transferred only F03's HostCatalog.swift/HostModel.swift and F10's two cleanup API files at23:45:47; B now separately authorizes the five listed WebDAV/sync production paths. Other Apple/UI/F08/F09/H/J/K ownership boundaries remain; external UI is not taken over. Old C02/WebDAV and Apple diagnostic run41179353708 remain sealed and are not rerun.

GitHub direct source/Git route is explicitly authorized; the earlier Desktop Commander quota failure is not worked around by retries. No machine handshake was performed by this snapshot, so no new running/ready/pwd or last-success time is asserted. No credentials read/exported. All builds, syntax, tests, fixtures and archive parsing remain Actions-only.

Next: finish the exact A adapter/guard/manifest and B approved implementation, independent static admission, then each sole explicitly authorized run; preserve failures and request new authority for any additional scope/run. **No reliable wall-clock completion range for either first execution or all remaining11 items**:200/60 are upper resource caps, not ETA; Android original suite plus six receive phases may exceed the allocated job and must fail honestly rather than lose checks. Full remaining completion confidence is insufficient to estimate.

---

## Previous immutable observation text (retained for continuity)

# EXReader continuation snapshot — 2026-10-31 23:20 UTC / 19:20 America/New_York

This is a continuity backup, not a stop/completion declaration. Formal count remains **96/108 (88.89%), 96 verified / 1 partial / 11 pending**. Catalog remains pinned at 5db41cb19673fb75bb0b498c677d770931ac33e8; no catalog, product, SDK, old test or workflow is modified by this document update.

## Current authorized native-dot work

At 23:08:06 UTC the user approved connected GitHub direct source/Git access for the six native dot agents, superseding the earlier source-route-only restriction for these scoped packages. No Codex/Claude task or extra team was started. Desktop Commander remains unused after its quota denial. InstaBox handshake was not rechecked in this work; no new last-success time is claimed.

At 23:13:25 UTC the user approved the first scoped batch: F03 13 new files, F04 10 new files (both implementation only, zero CI); F05 10 new files/one 265 runner-minute cap; F07 4 new files/one 15-minute diagnostic; F10 8 new files/one 60-minute cap. Total allowance:45 new files and340 runner-minutes, not permission for automatic repeats. Preparation commits use skip-ci. Current branches and actual stable identities:

| Package | Actual source/seal at snapshot | Current state and budget |
|---|---|---|
| F03 | dot/f03-same-source-20261031 / 514526d3c0373d6e86087e78074be50f03eec053 |13 new files remotely present; preparation only, six-host wire/receipt connection incomplete, static review underway;0 CI. Reviewer requested preparation-only verdict and no newly invented screenshot/author-round rule. |
| F04 | dot/f04-reading-sync-20261031 / a7c0adba3f940d916a19545ebf9901a606744686 |10 new files remotely present; initial Apple/Android real-driver preparation, not complete six-target evidence;0 CI and no syntax/build/test execution. |
| F05 | dot/f05-client-recovery-20261031 / dc142dd9558a8ce7b9a3b072d5483e86d81d20cd |6 of10 permitted new files present; Windows two-host/HTTPS fault driver preparation, remaining host/receive-cancel/tombstone coverage incomplete; no workflow,0/1 run used. |
| F06 | original accepted source8f8acf3234cba747165f001c0c96efe1b911e6ad; catalog5db41cb |Already verified; native dot rechecked original12/12 jobs and six identities. No repeat build. Agent now performs cross-package static review and this single-document continuity update. |
| F07 | dot/f07-link-evidence-20261031 / seal697448abd8188580304806163ba9b543e76ba9ba; tested triggerf33eb38571fd551f78555b89ab7ae553889f5cc4 |One approved diagnostic completed, not F07 acceptance;1/1 run used. |
| F10 | dot/f10-safety-20261031 / tested a650340012ef112731b03388a0c4367621e9b82a |8 new files; bounded installed raw-module experiment, no host/SDK acceptance. Run41252143789/attempt1 queued at23:21 UTC (agent-reported);1/1 approved run started, no repeat. |

Implementation, diagnostic and review are distinct: F03/F04/F05 preparing implementations; F10 waiting on its single bounded Actions experiment; F07 completed its diagnostic; F06 reviewing. Completed or waiting slots are not active implementation. No external team's current activity is inferred.

## Common source, owner and acceptance boundaries

Five-package preparation product source is94fb236a4a2da87dfbaf4f1dd2a47885d615a230; frozen SDK8357eafa28423a7ab93ba08b823af80f01ad1505. This is a shared preparation baseline, not a finally integrated six-host acceptance. GitHub compare confirms94fb descends from original F06 source8f8acf by42 commits. Original F06 success is not transferred to the new source or behavioral cases.

Linux C02/WebDAV joint b5e7fea87174f5e0baabfad97cf5cf7082f2d85e and94fb diverge3/1 commits fromc44a9cf211fffa4ed6f2720ffa49a186c3b4d196. Its manifest locks SDK7271829a829bfa6aaa47b73077c493f71af27ad3 and covers Linux admission/managed transport plus Windows/macOS legacy compatibility. SDK727 and8357 differ in library implementation/header/version metadata; same version labels are not equivalence. No joint delta or Android98d254 production delta was automatically merged.

C02/WebDAV sealed deliverables remain fixed; C02 is not reassigned. Existing Apple/UI/F08/F09 and other production owners retain their scopes. F05 does not write sync.cpp; any F10 production fix or shared composition requires explicit single-writer scope. Apple iPad organization issue remains with its existing owner. No in-flight UI/Apple delta is imported.

F05 contract interpretation is fixed to the original clauses: real competing-head preservation, visible deletion conflict, stale put must not resurrect a tombstone, illegal projection pauses, native explicit conflict UI, offline reconnect/cancel/crash recovery. Where an existing user resolve/restore is exercised, its parents must cover competing heads/tombstones. No invented requirement forces every host and every case to become a single head. Offline cases are not required to perform online wire requests. The initial blanket production blocker was corrected; this does not grant F05 acceptance.

F03 review similarly must not reject original semantic evidence merely because a new exact screenshot role or exhaustive author-round shape is absent. New stronger test plans are separate from the unchanged fixed criterion.

F10 reviews distinguish a real installed raw sync/session module from a real host. Negative-control rejection now requires the mutation's expected reason, not an unrelated baseline error. Residual files are recorded as observations; their existence alone is not proof that every retained file is unsafe. Full F10 remains false.

## Actual run and preserved evidence

F10 [41252143789/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41252143789), source a650340012ef112731b03388a0c4367621e9b82a, has been queued; no result or artifact is asserted. One60-minute capped run authorized and started. This update records actual activation, not a second run.


F07 [41251856370/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/41251856370), diagnostic job124686859052, completed success (GitHub jobs rechecked). It read the exact original Windows artifact without rebuilding. Agent reports retained full host-build.log5469 bytes/11 lines/SHA256351fbd1917835bae4dcee349303f609533aff49db7b583ba270133e9675248a6, with no Searching/Loaded rows; original parser/evaluator still refuse provider_loaded_ambiguous. Diagnostic completion is not provider acceptance; F07 remains false. Output artifact13061358143,32453178 bytes,SHA25686a22d48bbb319bd0be40b9a08ae84b4ebcb82fbdd9ddd3728c9a31c69d4d3c2 (agent-reported; ZIP not downloaded here). New provider capture would require separate scope/budget; no repeat is authorized.

F06 [40678657371/attempt1](https://github.com/NoGod3524/EXReader/actions/runs/40678657371):12/12 jobs success; original F06 job122788662924 and aggregate122788746787 accepted=true/failures=[]; all six original artifact IDs/digests/source identities match pinned handoff and remain unexpired. Only development-package extraction/install/program identity is accepted; no full behavioral, provider, physical-device or release credit.

## Next continuation

Finish the approved independent new drivers, statically review exact write sets and original contracts, then use only the already-approved single runs where their producers are ready. Retain every failure, actual source/run/attempt/artifact identity and original assertion. Do not spend a full six-host budget on an incomplete producer merely to obtain red status. No reliable end-to-end ETA is established; remaining work includes real six-host interaction and external-owner capabilities.

The historical independently accepted iPhone entry and its original failed audit history are preserved below.

---

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
