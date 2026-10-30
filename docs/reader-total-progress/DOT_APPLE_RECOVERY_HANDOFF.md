# Current recovery checkpoint — 2026-10-30 05:18 UTC / 01:18 EDT

Prepared for the 05:22 UTC hourly report. This section supersedes all older current-state wording below; the prior checkpoint is retained as historical evidence, not as current execution instructions. This is a resumable snapshot, not acceptance or a transfer.

## Publication state and ownership

This update is LOCAL ONLY in /data/workspace/exreader-dot-apple-receipt-20261030, branch codex/dot-apple-receipt-20261030. Its parent is unpublished bb47a331cffb271816a78bb62a90a843a9197f06; preserve history without amend/rebase. Last successfully published snapshot is 97264a714b721b58fbfab659ace37b503fa1ef5a. The bb47 push was denied even after exact user confirmation; no further retry, alternate route, or claim that GitHub is updated is authorized by this checkpoint.
Sole Apple source/diagnostic/result writer remains /root/repair_verify_apple_mobile; this writer changes only this recovery document. Common/staged worktrees remain outside scope.

## Current full candidate, fresh writer status at 05:16 UTC

Source **c46f7036d81f88d8529871590f780b5430630e47**, branch codex/dot-apple-complete-20261029, worktree /data/workspace/exreader-dot-apple-complete-20261029.
[Full run 41005300066](https://github.com/NoGod3524/EXReader/actions/runs/41005300066) is in progress, not accepted:
- SDK: both success.
- Native iPad and iPhone running; macOS queued.
- Supplemental four success: font iPad/macOS, original macOS/iPhone.
- Organization iPad, original iPad and sync iPhone running; five other supplemental jobs queued.
- Twelve supplemental jobs total = four success + three running + five queued.
No cross-source pass transfer: a91 successes and c66 focused passes do not prove c46 full completion.

c46 differs by four files from failed a91. The macOS-only canTap correction addresses actual reader.more native geometry 19 x 4 rejected by the prior 12-pixel minimum. It is not evidence of runtime success yet.
The user explicitly authorized the narrow OriginalSave readiness exception at 04:49:18 UTC: the original iPad line-63 NewFolder versus overflow race is corrected within the existing 90-second readiness budget. This is a disclosed exception to the prior absolute test-body freeze, not blanket authority to alter old tests. Exact exception in existing if !newFolder.exists: the existing wait90 accepts either (newFolder.exists and newFolder.isHittable) OR (overflow.exists and overflow.isHittable); overflow.tap occurs only if New Folder is not already both existing and hittable. Identifiers are app.buttons[New Folder] and app.buttons[OverflowBarButtonItem]. Subsequent original NewFolder wait/tap, inlineRename/Done, folder/Open, exportstatus/filename assertions remain unchanged. Runner budgets 240/360, one original case per platform, and byte-equal source/saved EPUB readback are unchanged. Admission checks whole file against frozen 4a68 plus this exact single snippet replacement. No added wait or budget. All other cases, budgets, assertions and actual saved-byte/hash readbacks remain required. Static reviewers completed the candidate review; that review is not a passing CI verdict.

## Retained failed full source a91

[Run 41000723036](https://github.com/NoGod3524/EXReader/actions/runs/41000723036), source a91ef5f3726b0d2f6bb1136e19bbeeb74fb40d72:
- macOS native 34/39 FAILED.
- iPad native 38/39 FAILED solely annotation four-minute budget.
- iPhone native 39/39 SUCCESS on a91 only.
- Supplemental 11/12 passed; original iPad failed.
- Same-run authentication and full summary FAILED.
This source is not a full pass. Preserve all evidence; do not erase failures or splice successes into c46.

Writer is preparing Actions-only diagnosis of a91 iPad original ZIP: artifact 12955922033, 474548744 bytes, SHA256 ee15fc2eaa8b908c8a1b2037e6667be73710745d2f1dcd75c1110b08ccfd2852. Diagnostic source 6cb9a6e68ed1c01406d40fb76cd70a7eac68cb22, run 41007675693, queued at 05:18 UTC. The annotation timeout remains unresolved pending diagnosis; c46 does not change mobile code and is not claimed to fix it.

Completed earlier Actions diagnostics (diagnostic success only, not product acceptance):
- macOS run 41004057606, source defe56ab, job 123894807795, artifact 12954976626, 63444 bytes, SHA256 b0df49359d119adf5c0e954907f69d2df9d70147be9efe366f8a1466090b8b65. All five failures linked to actual reader.more 19 x 4 geometry.
- Original iPad run 41004266572, source 2424f562, job 123895461538, artifact 12954926815, 13306177 bytes, SHA256 887746cb7c93baec415647516d29ac9d6fd91d88eaee409fc11aa688198d72fd. Established readiness race; authorized narrow fix follows it.

## Next executable sequence and limits

1. Monitor existing c46 run 41005300066 to terminal; do not duplicate it.
2. Retain and complete exact a91 iPad ZIP diagnosis in Actions. If c46 fails, diagnose its own raw evidence before a justified authorized fix.
3. Require all 117 original native cases (39 x 3), all 12 supplemental groups, same-source program/SDK identities, and original same-run ZIP authentication/summary.
4. Independent 19-ZIP audit at review-only 089c997c7206030477bd9981497cc6a5162bfd38 has NOT executed and has stale a91 pins. Do NOT push its old authentication execution branch. Retarget metadata only to a future full-success producer with exact source/run/attempt/job/artifact/size/digest identities, retaining the unchanged strong checker and static review.
5. Complete independent 19-ZIP audit, then final result evidence. No final completion claim, common integration, default push, PR, release, or automatic next pack.
All builds/tests/syntax/ZIP work stay in Actions; no credential/security reads, no new VM, no autosuspend change, no new Codex/Claude agent.

## Count, personnel, estimates and handshake

Formal **95/108 = 87.96% unchanged**; candidate corrections and static review are not formal acceptance. No global P0 migration/conflict recovery or SDK3.42 six-platform same-source completion is established.
Main writer is active/test monitoring and preparing retained-failure diagnosis. Documentation writer is active for this checkpoint. Other reviewers completed or await new evidence; do not count six slots as six active implementations.
Remaining full-suite and independent-audit duration cannot be reliably estimated from this running/queued state.

Last verified handshake **2026-10-30 05:14:55 UTC = 01:14:55 America/New_York (EDT)**: running, runtime.ready true, pwd /data/home, exitCode 0, timedOut false; autosuspend 1800 unchanged. Existing automation 6ae40da897ac81918ae3e90d91ee79ea remains the unique 28-minute maintenance task. Healthy output remains quiet.

---

## Historical checkpoint retained below (04:19 UTC; superseded above)

# EXReader Apple recovery checkpoint (not acceptance or a transfer)

Snapshot updated: 2026-10-30 04:19 UTC / 2026-10-30 00:19 America/New_York (EDT), prepared for the 04:22 UTC hourly report.
Focused completion independently verified by coordinator; full-suite state independently read by coordinator at 04:18:51 UTC.
Purpose: hourly resumable evidence snapshot against context/quota interruption. Work continues; this is neither product completion nor an actual handoff.

## Ownership and resumable entry points

- Coordinator: /root. Sole Apple source/diagnostic/result writer: /root/repair_verify_apple_mobile.
- This file's exclusive documentation writer: /root/maintain_apple_recovery_handoff.
- Full authorized task: [DOT_APPLE_TASK_20261029.md at 1ba643b3](https://github.com/NoGod3524/EXReader/blob/1ba643b3/docs/reader-total-progress/DOT_APPLE_TASK_20261029.md). Read the complete task before implementing.
- Accepted receipt: [966f34930f07cfd251d5f4e85513e4b77128c403](https://github.com/NoGod3524/EXReader/blob/966f34930f07cfd251d5f4e85513e4b77128c403/docs/reader-total-progress/DOT_APPLE_RECEIPT_20261029.md).
- Source worktree: /data/workspace/exreader-apple-features-repair-20261029; branch codex/repair-apple-features-20261029.
- Diagnostic worktree: /data/workspace/exreader-dot-apple-diagnostic-20261030; branch codex/dot-apple-diagnostic-20261030.
- This doc-only worktree: /data/workspace/exreader-dot-apple-receipt-20261030; branch codex/dot-apple-receipt-20261030. Pre-snapshot HEAD 966f34930f07cfd251d5f4e85513e4b77128c403, clean.
- Original working conversation has stopped its development and monitoring. It will NOT automatically integrate or take back the task. Deliver results directly to the user through the current coordinator.

## Qualified focused candidate and pending full validation

Exact source: **c66b5590e42adcf708365ba4fa315a811e475aaa**, pushed; writer reports clean source worktree.
Helper blob: **44b701a3f28d61d91b3588bc0fccc69e5c70e9f1**.

[Focused original-five run 40998486779](https://github.com/NoGod3524/EXReader/actions/runs/40998486779), attempt 1:
- macOS SDK job 123877098804: success.
- simulator SDK job 123877098994: success.
- iPad native original-five job 123878247831: SUCCESS, original five 5/5 accepted. Annotation 155s / history 28s / share 68s / directory 23s / null 65s. Original ZIP artifact 12952708284, 76318562 bytes, SHA256 207e01d38763f4187b6fe2e7795a90063744295529327fd2147188b59daded99.
- iPhone native original-five job 123878247862: SUCCESS, original five 5/5 accepted. Annotation 220s / history 36s / share 131s / directory 20s / null 47s. Original ZIP artifact 12953245859, 71554152 bytes, SHA256 2923b1b35f20b9adc07be52c0287d39c8d3e7080675ddda5ace86985ad2436b1.
- All four jobs succeeded on exact c66 source, attempt 1; both program/SDK3.42 identities accepted. This unlocks full-suite preparation, NOT final acceptance. Full validation is now running on a91ef5f3726b0d2f6bb1136e19bbeeb74fb40d72: [run 41000723036](https://github.com/NoGod3524/EXReader/actions/runs/41000723036), attempt 1, in progress. No new full-suite product pass is claimed.

Changes from 55e9 are restricted to the shared UI helper, explicit admission transformation and repair evidence document. The helper latches slower controlled native correction after a real drag direction reversal; Files current-directory recognition accepts actual local-provider root plus EXReaderAnnotations navigation rather than requiring a folder cell while already inside it. Actual Open/content checks remain. Original five test bodies, setup/teardown, 90-second waits, 24-drag cap and 240-360-second budgets remain frozen. See source-pinned docs/reader-total-progress/repair-apple-features-20261029.md for exact implementation evidence.

## Authentic failure evidence retained

Latest failed producer source: 55e9c203fc58c5b94d3d951dad17c32d7f15a08f.
[Producer run 40992359608](https://github.com/NoGod3524/EXReader/actions/runs/40992359608), attempt 1:
- iPad job 123858647139: 4/5; annotation timeout. Artifact 12950219035, 180602163 bytes, SHA256 68e47e9213e87b1d95c65b100603863be279031c0abb2d4875931b2af7610538.
- iPhone job 123858647168: 3/5; annotation timeout and history failure. Artifact 12950483426, 235576166 bytes, SHA256 f410536fc8b2732cc75feef43f3d12d583da06f5699b26a0b532f91aad10650d.
- Both SDK jobs succeeded; the product gate failed.

[Diagnostic run 40997553440](https://github.com/NoGod3524/EXReader/actions/runs/40997553440), source af33f61284a9aa7357e0777fab19bb110dd104d7: both jobs succeeded. This authenticated and inspected the original failed ZIPs in Actions, including native trees and history timeline; it is NOT a passing product run.
- iPhone history: 24 fast corrections oscillated; a subsequent 90-second wait failed at 193.442 seconds. Back button remained above the viewport. This establishes a helper navigation failure, not a history-model failure.
- iPhone annotation: functional content/duplicate checks completed, but case total 253.033 seconds exceeded 240.
- iPad annotation: actual Files view was already inside EXReaderAnnotations, but helper waited for a nonexistent folder cell.
- Preserve raw ZIP provenance and failure receipts. Never replace these failures with diagnostic-green status.

Earlier failed/superseded evidence remains in the source-pinned repair documents: 40982450461, 40986067818, 40989249100; cancelled superseded runs 40985138048 and 40985492438 are not passes. Full runs 40946118946 and 40946894035 failed mobile gates despite macOS 39/39. SDK3.41 run 40958251556 is not SDK3.42 evidence; its iPad missing ZIP/BlobNotFound is an unresolved evidence limitation, not a fabricated test count. Organization-only success 40981500259 is valid only for its own source. Do not combine any of these into a same-source complete result.

## Exact next steps and admission sequence

1. DONE: 40998486779 / attempt 1 is terminal success, original-five 5/5 on both platforms. Do not dispatch a duplicate.
2. Preserve c66 passing producer identities and all historical failures. If a later gate fails, authenticate and diagnose that exact source ZIP in Actions before a minimal fix; never transfer passes across source SHAs.
3. DONE: qualified c66 was used for codex/dot-apple-complete-20261029, worktree /data/workspace/exreader-dot-apple-complete-20261029. Full source a91ef5f3726b0d2f6bb1136e19bbeeb74fb40d72 differs only by two added files: .github/workflows/dot-apple-complete-20261029.yml and tools/reader_composition/dot_apple_complete_admission_20261029.py. All runtime/helper content is identical to qualified c66.
4. RUNNING: existing run 41000723036 attempt 1 runs unchanged original **39 x 3 platforms (macOS, iPhone, iPad) + 12 supplemental groups**, same-source SDK/program checks and same-run ZIP authentication/full summary. Monitor this existing run; do not duplicate it.
5. Perform the independent **19 original ZIP** authentication/audit. Bind source, run, attempt, job, artifact, name, bytes and digest. CI job-green alone is not this audit.
6. Write docs/reader-total-progress/DOT_APPLE_RESULT_20261029.md on the independent branch with exact producer SHA separately from documentation SHA, source/blob identities, all runs/jobs/artifacts, failures, limits and uncompleted items.
7. Deliver directly to the user. Do not push/integrate the common branch or silently assume global acceptance.

Prepared full-suite workflow template: .github/workflows/apple-sdk342-full-handoff-20261029.yml, blob 09350a203f79749668087c056e303aaf826245a6. Its old helper pin f7a3ddefc25d7a901dc0ef810dc66d850b9cb20f must not be reused for c66. The separate full wrapper/admission is now added in a91; the focused seven-path guard itself remains unchanged.
- Actual full-source delta from qualified c66: only the two independent wrapper/admission additions; other frozen paths preserved.
- Original 39 = 5 + 13 + 13 + 4 + 4.
- Supplemental 12 = four groups on three platforms: font 1; original 1 plus real saved-byte/hash readback; organization 6; sync 3 plus separate 401 recovery (256 shards, pending 1, recovered outbox 0).
- Strong independent checker: tools/reader_composition/closure_apple_independent.py on audit branch, blob dd7f9bf6a5035c2e74791c46346e8efc06305a9d. Keep unchanged; add separate metadata orchestration after full-suite pass.
- Expected 19 identities: 2 SDK + 3 native + 12 supplemental + authentication + full summary.
- Do not launch the whole unfinished closure_final_independent workflow with PENDING pins/zero runs/unrelated packages.
- Mobile success does not prove macOS 39/39; shared helper changes require macOS validation too.

## Full-run checkpoint at 04:18:51 UTC

Run 41000723036 / attempt 1 / a91 source remains in progress, with no failures observed in this checkpoint. Seventeen jobs have materialized; two summary/authentication jobs have not yet materialized. This is not a passing full-suite verdict.
- Both SDK jobs succeeded: simulator 123884230320, macOS 123884230525.
- Native macOS 123885490913 and iPad 123885490853 running; native iPhone queued.
- Supplemental organization iPhone 123885490935, sync iPhone 123885490969 and sync iPad 123885490980 running; other nine supplemental jobs queued (12 total).
- Independent 19-ZIP audit prepared at 089c997c7206030477bd9981497cc6a5162bfd38. Static identity review found no blockers; this is NOT executed audit evidence. Published only to non-trigger codex/dot-apple-audit-review-20261030.
- Local execution branch codex/dot-apple-authenticate-20261030 at the same SHA is in /data/workspace/exreader-dot-apple-authenticate-20261030, not pushed. Only after full run completes SUCCESS may its push trigger the pinned independent 19-ZIP audit. If full run fails, diagnose exact failed ZIPs first; do not launch the success audit.

## Frozen invariants and safety boundaries

All execution uses the existing saved-login normal CLI through Desktop Commander lap25002 (d55d0477-84bb-4425-8708-5a3ecacce78b):
npx --yes instabox@0.8.52 exec m_agqxv2s72g5vwdtsifu5cnmml4 --json --cwd <authorized-worktree> -- <command>
VM identity remains agent-browser-mol0 / m_agqxv2s72g5vwdtsifu5cnmml4.
- Build, tests, syntax checks, fixtures and ZIP/xcresult parsing ONLY in GitHub Actions.
- No credential/config/security reads or changes, no new VM/restart/replacement, no autosuspend changes, no new Codex/Claude tasks.
- No default/common branch pushes, merge, PR, tags, release, force push, shared staging cleanup or takeover.
- Retain assertions, failures, old test bodies, owner and SDK. No hidden UI model calls, precreated export directory, fake hittability or timeout inflation.
- Checker tools/check_apple_product.py: ed7f62597e01d4e045f679369805d27abc20b7bc.
- Isolated owner: 937f61057b06c5c9de3b562046e52c91b5be62b9.
- Original-five suffix: 622b9558f79eda07211e15c51bffcd728da6c553.
- Old 34/runner freeze: 4a68d80fbaa524fc28f899d209d795248627080b.
- SDK3.42 content identity: 8357eafa28423a7ab93ba08b823af80f01ad1505 (src/include/cmake/CMakeLists.txt/bindings).

Common remote stays **343bb94eb6513beaf5b344e7828342f6602a3b7b**. Main worktree /data/workspace/exreader-resume-20261029 stays HEAD **9330be495bffdf3bf421bdc32b963e3fbfc4c9fe**, staged 27 paths versus HEAD / cumulative 89 versus 343, as reported in the user's latest closure message. These are preserved, not revalidated or taken over by this snapshot.
Also leave /data/workspace/exreader-composition/2f215f57 and dirty Windows C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader untouched.
Original closure document: codex/handoff-evidence-resume-20261029:docs/reader-total-progress/EXReader_closure_handoff_20261029.md. It is not complete-product acceptance.

## Acceptance count, activity and estimates

Formal catalog remains **95/108 = 87.96%** (foundation 12/12, host 82/84, final 1/12). No new accepted item is claimed. Candidate work is pending audit, separate from the formal count. Do not combine a different branch's 78-item catalog with 95 as a single same-source product.
F01-F05 / F07-F12 remain pending; F06 is only its previously limited package identity. This work does not establish physical-device, global P0 migration/conflict recovery or six-platform same-source completion.

Actual work status at snapshot:
- Apple writer: active / awaiting full run 41000723036, with independent 19-ZIP follow-through still required; retains implementation ownership.
- Recovery document writer: active documentation only.
- Helper freeze audit, supplemental matrix, source identity, runtime boundary and failure-retention audits: completed.
- Full-workflow and independent-audit static reviewers: review completed; waiting for a new candidate or resulting evidence, not active implementation.
- Coordinator handles integration of evidence, not shared-branch integration.
Six available lanes are not six currently executing agents. Completed auditors must not be counted as live implementation.

Focused validation is complete. Remaining duration still cannot be reliably estimated before full-suite and independent 19-ZIP evidence; no full-suite completion deadline is established.

## Existing 28-minute handshake

User independently confirmed enabled task **6ae40da897ac81918ae3e90d91ee79ea**, every 28 minutes, first scheduled 2026-10-29 23:51 America/New_York = 2026-10-30 03:51 UTC. User deleted old local instabox-28 to avoid duplicates.
Latest real periodic handshake completed 2026-10-30 04:18:45 UTC = Oct 30 00:18:45 EDT: get state running, runtime.ready true; pwd /data/home, exitCode 0, timedOut false. Coordinator verified actual execution time and result; autosuspend remains 1800.
autoSuspendAfterSeconds=1800 unchanged; Desktop Commander connection retained. The first periodic invocation is now confirmed by its actual result.
Normal success stays quiet; notify only actual offline/pause/failure/timeout/login/CLI failure with last success time. A package download error is not proof the VM is offline. Do not use handshake for builds/tests/artifact processing.

## Resume checklist

Read the full task, latest source-pinned repair evidence and this snapshot; obtain fresh run status before edits. Check uncertain remote command outcomes before retry. Preserve exact worktree ownership. Resume only the pending gate sequence above. This snapshot's later documentation commit is not the tested application source. Report blockers by exact action/target/reason and distinguish completed, denied, pending and uncertain.
