# EXReader Apple recovery checkpoint (not acceptance or a transfer)

Snapshot written: 2026-10-30 03:47 UTC / 2026-10-29 23:47 America/New_York (EDT).
Source/run state confirmed by the sole implementation writer at 03:43 UTC.
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

## Current candidate and pending verdict

Exact source: **c66b5590e42adcf708365ba4fa315a811e475aaa**, pushed; writer reports clean source worktree.
Helper blob: **44b701a3f28d61d91b3588bc0fccc69e5c70e9f1**.

[Focused original-five run 40998486779](https://github.com/NoGod3524/EXReader/actions/runs/40998486779), attempt 1:
- macOS SDK job 123877098804: success.
- simulator SDK job 123877098994: success.
- iPad native original-five job 123878247831: in progress at 03:43 UTC.
- iPhone native original-five job 123878247862: in progress at 03:43 UTC.
- Neither UI gate is accepted yet. SDK success is not UI success. No full-suite admission until both original-five gates pass on this exact source.

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

1. Poll existing 40998486779 / attempt 1 to terminal; do not dispatch a duplicate.
2. If either original-five gate fails, authenticate and diagnose that exact candidate's original ZIPs in GitHub Actions, preserve the failures, then make only a justified minimal fix. Do not transfer passes across source SHAs.
3. Only after BOTH original-five gates pass on the same candidate, create codex/dot-apple-complete-20261029 from that qualified source.
4. Run unchanged original **39 x 3 platforms (macOS, iPhone, iPad) + 12 supplemental groups**, using the same admitted source and SDK/program identities.
5. Perform the independent **19 original ZIP** authentication/audit. Bind source, run, attempt, job, artifact, name, bytes and digest. CI job-green alone is not this audit.
6. Write docs/reader-total-progress/DOT_APPLE_RESULT_20261029.md on the independent branch with exact producer SHA separately from documentation SHA, source/blob identities, all runs/jobs/artifacts, failures, limits and uncompleted items.
7. Deliver directly to the user. Do not push/integrate the common branch or silently assume global acceptance.

Prepared full-suite workflow template: .github/workflows/apple-sdk342-full-handoff-20261029.yml, blob 09350a203f79749668087c056e303aaf826245a6. Its old helper pin f7a3ddefc25d7a901dc0ef810dc66d850b9cb20f must not be reused for c66. A separate wrapper/admission is needed; the focused seven-path guard cannot admit the full wrapper.
- Planned full-source delta from qualified c66: only the two independent wrapper/admission additions; preserve other frozen paths.
- Original 39 = 5 + 13 + 13 + 4 + 4.
- Supplemental 12 = four groups on three platforms: font 1; original 1 plus real saved-byte/hash readback; organization 6; sync 3 plus separate 401 recovery (256 shards, pending 1, recovered outbox 0).
- Strong independent checker: tools/reader_composition/closure_apple_independent.py on audit branch, blob dd7f9bf6a5035c2e74791c46346e8efc06305a9d. Keep unchanged; add separate metadata orchestration after full-suite pass.
- Expected 19 identities: 2 SDK + 3 native + 12 supplemental + authentication + full summary.
- Do not launch the whole unfinished closure_final_independent workflow with PENDING pins/zero runs/unrelated packages.
- Mobile success does not prove macOS 39/39; shared helper changes require macOS validation too.

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
- Apple writer: active, waiting for native CI verdict, retaining implementation ownership.
- Recovery document writer: active documentation only.
- Helper freeze audit, supplemental matrix, source identity, runtime boundary and failure-retention audits: completed.
- Full-workflow reviewer: preparation completed; waiting for qualified candidate.
- Coordinator handles integration of evidence, not shared-branch integration.
Six available lanes are not six currently executing agents. Completed auditors must not be counted as live implementation.

Remaining duration cannot be reliably estimated before the focused verdict and full-suite/19-ZIP evidence. Current native jobs have no verified finish time. Do not promise a completion deadline from queued/running status.

## Existing 28-minute handshake

User independently confirmed enabled task **6ae40da897ac81918ae3e90d91ee79ea**, every 28 minutes, first scheduled 2026-10-29 23:51 America/New_York = 2026-10-30 03:51 UTC. User deleted old local instabox-28 to avoid duplicates.
Latest real periodic handshake completed 2026-10-30 03:50:35 UTC = Oct 29 23:50:35 EDT: get state running, runtime.ready true; pwd /data/home, exitCode 0, timedOut false. Coordinator verified this result; the scheduled 03:51 invocation arrived slightly early, so actual execution time is recorded separately.
autoSuspendAfterSeconds=1800 unchanged; Desktop Commander connection retained. The first periodic invocation is now confirmed by its actual result.
Normal success stays quiet; notify only actual offline/pause/failure/timeout/login/CLI failure with last success time. A package download error is not proof the VM is offline. Do not use handshake for builds/tests/artifact processing.

## Resume checklist

Read the full task, latest source-pinned repair evidence and this snapshot; obtain fresh run status before edits. Check uncertain remote command outcomes before retry. Preserve exact worktree ownership. Resume only the pending gate sequence above. This snapshot's later documentation commit is not the tested application source. Report blockers by exact action/target/reason and distinguish completed, denied, pending and uncertain.
