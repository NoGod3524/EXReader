# EXReader hourly continuity snapshot: 2026-10-30 21:22 UTC

Prepared 21:25 UTC / America/New_York 17:25 EDT. This is a backup against quota interruptions, not a stop or completion notice. Formal acceptance remains 95/108 (87.96%): 95 verified, 2 partial iPhone/iPad annotation_exchange, 11 pending; foundation12/12, host82/84, final1/12. New candidate passes do not add acceptance without catalog evidence.

## Newly verified progress
All repository/status reads below were performed 21:23-21:25 UTC through lap25002 Desktop Commander and official saved-login instabox@0.8.52, machine m_agqxv2s72g5vwdtsifu5cnmml4. No artifacts were downloaded or parsed by this snapshot task.

Restart branch codex/p0-win-restart-reader-20261030:
- tested source 6db7c3dc1005c7fd22f91b02a150bfdd671f723c
- document HEAD 638976413692412fd7cc15d7e508d0382d1faffd, clean
- run41130069225 attempt1/job124318418607 success, completed21:21:26Z
- https://github.com/NoGod3524/EXReader/actions/runs/41130069225
- artifact13011924675,507992 bytes,SHA256 5c4801d1cf5ff20851a7bb725dc0a64bb6921cb09de04856ef083916276245e5
Independent source review at21:24: compared with0d575448 production implementation is unchanged; probe/run.py/docs add a 26th case. window-drift injects generation5/PENDING0, verifies shared BUSY while the refused object holds custody, kills it, records post-kill shared outcome, and verifies an old generation0 reader refuses. This records a residual, not crash-durable isolation. Recovery write/flush failure, real nonzero-generation recovery, and provenance of restored snapshots remain unproved. Preserve earlier25-case run41105493390 and prior failures.

C02 branch codex/windows-coordinator-hardening-20261030:
- local/remote source b830486c21bfa82cf69a1d816b424fe2fc53d29b, clean
- run41128388018 success: ubuntu job124312694334 and Windows job124312694439
- https://github.com/NoGod3524/EXReader/actions/runs/41128388018
- actual test path tests/migration/windows_coordinator_hardening_20261030/wh_test.c
The older missing-file check used tests/windows_coordinator_hardening_20261030 without the migration level; do not repeat the claim that no test exists. Tests, commit, push and CI now exist. This establishes progress on those actions, not a global approval-system guarantee.
- Windows artifact13012126284,662 bytes,SHA256 372ed26ded7d3e6cb296de6d0766fa0ca8de7f391c8cfb9efab2c8b1ec19c6fd
- Ubuntu artifact13010509925,655 bytes,SHA256 cc1a09dd613d18cb70210665c1517bf11d0b3c59ea4b5b5c157a8821eeb13247
- preserve failed runs41128027528(source415ccc0e6dbef3b426078bb7fe517b61bb7b62e0),41127711029(sourceec88b8e0141f6d8c3134450995e35b2d659a4fdc).
Independent review of the new implementation, real sink/lease/journal behavior and original three C02 draft defects remains required; a dual-platform unit pass is not full lifecycle admission.

## Unchanged candidates and Apple failure
Bridge audit remains39f30d8488362d0c35796e75de34a8342eca7b02/run41104382055 completed success.
https://github.com/NoGod3524/EXReader/actions/runs/41104382055
Earlier review established22 negative controls and retained original ZIP rehash. No newer bridge run appeared in this query. Preserve failed924bcd63/run41100882880 and the negative-construction corrections.

Apple branch codex/dot-apple-complete-20261029 remains b2f4e6e1363d0ee20fcb87a6acef548e0624318a; latest run41093873914 completed failure.
https://github.com/NoGod3524/EXReader/actions/runs/41093873914
Prior complete identity review:19jobs,15success/4failure(native iPhone annotation,font iPad,authenticate,full-host-summary). No new run/source observed21:23. Keep exact source/run/attempt identity; never combine different runs.
Original native iPhone artifact13000480037,429525947 bytes,SHA256 6df5cee057d608ae96f3cf14193ed546606cba78c7f362362c8af5691e7f5cae.
Original font iPad artifact12998390637,117806346 bytes,SHA256 c91eb0db5e0b63c2e1f17711d69a0e45bf06ca128b5ebcdacd8f535314e45c4e.
Next: diagnose original failure evidence in a bounded GitHub Actions package, then authorized source repair and unchanged-budget verification. Exit65 alone is not a root cause. Retain oldc46/run41011360858 failures and avoid the stale55b32042 audit binding.

## Remaining work, people and timing
SDK3.42 fixed8357eafa28423a7ab93ba08b823af80f01ad1505; six-platform same-source installed-owner evidence and formal audit remain incomplete.
P0 migration safety/conflict recovery still require real C01 lease/gen/PENDING authority, C02 five-gate journal binding and atomic sink checks, compatible publisher/engine/restart custody, and failure/crash isolation.
At21:24 the coordinator reported two actual workers: one documentation snapshot and one independent restart review; zero implementation workers. CI job counts are separate. Other completed or blocked lanes are not active workers.
This hour produced a new restart26-case candidate and C02 two-platform candidate. Neither full remaining work nor the next repair cycle has a defensible numerical ETA; confidence in numerical estimates would be low pending independent review, fault coverage and Apple diagnosis.

## Boundaries and continuity
Source/Git/docs only via lap25002 device d55d0477-84bb-4425-8708-5a3ecacce78b and the existing InstaBox. Exclusive worktrees under/data/workspace. Source single-writer; confirm current ownership before changes.
Builds, syntax checks, tests,fixtures,benchmarks and originalZIP unpack/parse only GitHub Actions. Claude raw-download allowance does not authorize VM unpacking/testing. No credentials,shared/default branch pushes,PRs,tags,releases,new Codex/Claude tasks or repeated schedules in this snapshot.
Dedicated handshake latest parent-confirmed success21:08:59UTC/17:08:59EDT; running/ready and pwd. Keep existing connection and autoSuspend1800 unchanged.
Receipt worktree /data/workspace/exreader-dot-apple-receipt-20261030; branch codex/dot-apple-receipt-20261030; previous snapshot ffae0a07743e54f29fa58aeeadccc36d13be8b69.
Older modified DOT_APPLE_RECOVERY_HANDOFF.md is preserved and excluded. Only this timestamped document is committed with skip-ci. This snapshot is resumable evidence backup, not completion.
