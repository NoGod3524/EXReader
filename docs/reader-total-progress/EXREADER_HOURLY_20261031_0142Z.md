# EXReader hourly continuity snapshot — 2026-10-31 01:42Z

Snapshot assembled 01:43Z (America/New_York: 2026-10-30 21:43 EDT).
This is a quota/disconnection continuity backup only, NOT a stop, completion, or acceptance declaration.

## Ledger and scope
Formal acceptance remains **95/108 = 87.96%**: 95 verified, 2 partial, 11 pending. Candidate CI passes are separate and do not add formal credit. Fixed denominator 108; no combining different source/run/attempt evidence.
Receipt worktree: /data/workspace/exreader-dot-apple-receipt-20261030
Receipt branch: codex/dot-apple-receipt-20261030
Receipt base before this document: dfd44687ba5b7ea976ed59de74da875f9ba4253c.
Existing dirty docs/reader-total-progress/DOT_APPLE_RECOVERY_HANDOFF.md is deliberately untouched and excluded from this commit.

## Newly verified candidate evidence
Read-only gh run metadata fetched through lap25002 Desktop Commander -> saved-login InstaBox CLI at 01:43Z:
- F08 source cfdaf6a4531548be63b4dd0c2bccd6b050a93124: [41155753132](https://github.com/NoGod3524/EXReader/actions/runs/41155753132) completed SUCCESS. Earlier running snapshot is superseded. Candidate only; detailed ledger audit remains.
- F11 source c957fa56fb15a8e5a536f94dda2a546af7a5e76b: [41156570278](https://github.com/NoGod3524/EXReader/actions/runs/41156570278) A1 completed SUCCESS. Job124404557392. Writer evidence: accepted=true; 37 actual files, EXReader and three SDK dylibs have correct Mach-O kind/platform7 (simulator). Artifact13025700596,27024935 bytes,SHA256 ff60d885b6e6099c2bded6dce12b0abe3f24a9e6ec33dfdc989c52f9dc787742.
  Independent source review verified producer4971c75f9037bb9e95498435efe5d179b87dcea6 uses SDK3.42 + wave3 + selector; historical build page_theme=false, identity field absent. At that source page-theme true was restricted to SDK3.41. Gate9b5d0d6914671c99fc20b8cc7361f700b83ca778 source/hash/inventory/Mach-O assertions unchanged.
  Original fixed producer run40655659565/artifact12805245231,27011224 bytes,SHA256 a14b0825e0b1db8204e394a99af4d46417cb4052e8678bc493e82d60b2c49af5.
  Preserve failed audit bf6af40c2f228de9a8f8d78d9e1aff665aecfc90/[41156000885](https://github.com/NoGod3524/EXReader/actions/runs/41156000885): wrong later-schema profile assumption; do not erase it. Corrected real-package audit is identity evidence, not device deployment acceptance.

## Remaining failures and bounded next steps
- F09 bd33476166f33a671fae9de16b83982d1f4c77fc: [41155749004](https://github.com/NoGod3524/EXReader/actions/runs/41155749004) completed FAILURE. Test diagnostic overlay under implementation/review; newly approved maximum two rounds. No claim of repair yet.
- F10 036717d9796e40b69cb48352c797695b76e17ae7: [41155648866](https://github.com/NoGod3524/EXReader/actions/runs/41155648866) completed FAILURE. Linux green; macOS archive byte-equality assertion failed. Operations6/6 and parser1/4 assertions passed per owner report; preserve original quantity and failure. New maximum two rounds of archive evidence preparation; first diagnostic workflow/doc reviewed and awaiting submission at this snapshot.
- Apple source a9a22319825d97b9d94b4d2f11e7ca0a5635a673, branch codex/dot-apple-fresh-focused-20261031, tree /data/workspace/exreader-dot-apple-fresh-focused-20261031: [41151397700](https://github.com/NoGod3524/EXReader/actions/runs/41151397700) A1 failed both original-five jobs; SDK2/font2 passed. iPhone job124389731494, iPad124389731206. Do not launch full19.
  iPhone rawartifact13024245737,169012046 bytes,SHA256 72e311c7547497e5426d5a3d93941daffc75325b576b87bdf81108e56689896a.
  iPad rawartifact13023154061,144183535 bytes,SHA256 7284a7c4bbbb9f16e28b46ca2a19a0aa8786a5d40a08ff7ff9eba566eb0b2761.
  Diagnostic dc66d5a56d60dbd782badec208ac38d3f2d270e7, branch codex/dot-apple-fresh-diagnose-20261031: [41155577811](https://github.com/NoGod3524/EXReader/actions/runs/41155577811) A1 SUCCESS; artifact13024948078,26188996 bytes,SHA256 013f7d86642bbe8a17717dea3129196986d771523f46436cdb1a21ec97f912a6.
  Raw ZIP identities verified within Actions. iPhone annotation reached final reader.location at232.26s, teardown232.43s/terminate232.65s then total240s timeout. Three fresh frames equalled old frames; not proven misclick. iPad all five fail app.launch background-assertion acquisition, not snapshot helper.
  No reliable next product/helper fix currently established; no new product run authorized by this snapshot. Do not increase240/360, remove teardown, repeat already-optimized typed queries, or splice earlier passes.
- P0 migration safety/conflict recovery and six-platform same-source SDK3.42 remain incomplete. C02 attachment/Git handoff delivered to external agent; do not reclaim its ownership. Frozen failure evidence and owned-path separation remain mandatory.
- WebDAV POSIX read-only finding: linkat success followed by ignored unlinkat failure can leave a temp hardlink. NOT tested. Must preserve published=true/OK fact; simple IO return would strand callers. Production/API changes require separate scope approval; no implementation/CI started.

## Actual six child lanes (not CI job count)
As parent assigned at01:43Z:
1. diagnose_ipad_font_failure: F09 diagnostic overlay implementation/review preparation.
2. review_native_journal_contract: F10 archive evidence workflow/doc, reviewed, preparing submission.
3. diagnose_iphone_annotation_failure: independent F09/F10 review.
4. map_remaining_acceptance_work: F08 result follow-up (now success), plus F03 category/series read-only source audit.
5. review_restart_crash_gaps: F11 real-package result completed, evidence sealing/next assignment.
6. check_apple_run_status: this documentation snapshot; not implementation.
Six actual workers were enumerated; only two implementation/pre-submission lanes. Waiting and documentation are not implementation.

## Connectivity, authorization, estimates
Network restored around01:22Z; parent reports three existing automations restored. Last successful handshake01:22:36Z (2026-10-30 21:22:36 EDT); not independently re-run here to avoid duplicate handshake. Existing machine m_agqxv2s72g5vwdtsifu5cnmml4, device d55d0477-84bb-4425-8708-5a3ecacce78b. No credentials retained.
All source/Git/docs only through authorized Desktop Commander -> official InstaBox CLI. All builds/syntax/tests/fixtures/benchmarks/ZIP operations only Actions. Preserve original assertions, budgets, counts, and failures. Different exclusive files/worktrees may proceed in parallel; same file one owner. No default/common branch pushes, PR/tags/releases, new Codex/Claude teams.
This commit is docs-only [skip ci]. No product run or artifact download is initiated by it.
Current-round and total remaining completion ETA: **not estimable with defensible confidence**. CI timeout limits are not completion ETAs; unresolved platform launch, performance and acceptance audits prevent a credible range. Confidence high in linked terminal metadata; root causes not established must remain unknown.
