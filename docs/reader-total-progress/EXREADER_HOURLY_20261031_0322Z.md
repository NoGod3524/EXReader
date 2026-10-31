# EXReader hourly handoff — 2026-10-31 03:22Z

This is a continuity backup against quota/context interruption, not a stop or completion notice. Evidence cutoff actually checked: 2026-10-31 03:22:48 UTC (America/New_York: 2026-10-30 23:22:48 EDT). Scheduled report slot: 03:22Z. Root/owners supplied current source and CI facts; the receipt writer additionally read F03 metadata and receipt Git status. No tests or artifacts were executed/parsed on the VM.

## Formal acceptance

**95/108 = 87.96%**, unchanged. 95 verified, 2 partial (iPhone/iPad annotation_exchange), 11 pending. Foundation 12/12, host 82/84, final 1/12. Candidate successes below do not add formal points. No full-target completion claim, no automation shutdown.

## This interval: completed evidence and remaining blockers

| Package | Actual tested source | Run / attempt | Result and scope |
|---|---|---|---|
| F03 GTK selection | 3de7d45dc21f034916d5e9aa6a89a3d3126ef806 | [41160082299](https://github.com/NoGod3524/EXReader/actions/runs/41160082299) / 1 | success; new 15 plus original 27+29 checks; candidate only; result doc prefix ada6 reported by root |
| F08 evidence analysis | 1f9540c7e362c0a75d0bb863d385aaf25e62e084 | [41161801430](https://github.com/NoGod3524/EXReader/actions/runs/41161801430) / 1; job124420751243 | success of analysis, not performance acceptance; result doc4137f9fa88102f4330065883265e909ff520094d |
| WebDAV temporary cleanup | ef83932406f8160547ebc3b73751f807a8486561 | [41161210906](https://github.com/NoGod3524/EXReader/actions/runs/41161210906) / 1 | success; both platforms original import47 + TLS77; Linux new7; doc666d0d81730ac3cf7caea52b05ca1f01b1d183b1 |
| F09 Escape routing | a8352f3623078e4d64b222c5af4dc7a2f2bfa379 | [41160570582](https://github.com/NoGod3524/EXReader/actions/runs/41160570582) / 1 | overall failure; native COM candidate passed selection/event/text/focus assertions, managed still fails; results doc commit was denied and remains dirty in its own tree |
| F09 legacy consumers | 9ab7076114a0213bd0513921b77152dd9014c9ce | [41162331946](https://github.com/NoGod3524/EXReader/actions/runs/41162331946) / 1; job124422399406 | overall failure; six observations executed; source package 2/2 exhausted; doc506402b25797d40831755254ce29a94e6ef91623 pushed |
| Apple focused c44 | c44a9cf211fffa4ed6f2720ffa49a186c3b4d196 | [41161011007](https://github.com/NoGod3524/EXReader/actions/runs/41161011007) / 1 | 5/6 jobs success; iPad original5/5, font2 and SDK2 success; iPhone original4/5, annotation 4-minute failure |
| Combined read-only evidence diagnostic | 2feb8ceccb0abecc876c9e8a47d26dafc8856cd8 | [41163507048](https://github.com/NoGod3524/EXReader/actions/runs/41163507048) / 1; job124426006790 | success, errors[]; verifies existing evidence, no product build or new acceptance |

F08: phase p95 main 4.123ms / interaction 3.951ms, but interaction interval p95 652.456ms, presentation samples 0, and 44/760 coverage. These are not full frame/presentation performance acceptance.

WebDAV: transient EIO/EINTR cleanup is verified. Persistent EIO/EACCES can leave residue; crash interruption remains unverified. Retain these limitations.

Apple: original timeline still executes annotation roundtrip at 239.33s; 240s timeout occurs before body finishes. Reader location appears 262.68s and teardown 263.35s. It is not merely teardown consuming time. ps sampling still times out (15s), complete=false. Small positive-observation deduplication has insufficient evidence to recover roughly24s. No blind new product run; full19 has not been pushed.

F09: the later combined artifact audit confirms both managed and both legacy consumers exit 0xC0000005; native baseline1, candidate0/pass. This supersedes the earlier legacy doc's explicit unknown exit-code limitation, not its failure preservation. Legacy document-range GetText432 passes; selection array VT12/elementVT20 converts, then selected GetText fails. Not a .NET-only issue; no proof of provider premature Release. Metadata collection still fails because Get-FileHash is unavailable although all six DLL paths exist. No reference-count or production workaround applied.

## Immutable artifact identities

All identities are metadata or existing Actions evidence, not locally downloaded ZIPs.

| Package | Artifact | Bytes | SHA256 |
|---|---:|---:|---|
| F03 |13026418563|897668|3b2dc81542655d344ab83ffbe8deb31a10bd150591ecc0de5581bcc8bac89a78|
| F08 analysis |13026904647|3081191|1891e213aa47d71b732942b4fc875dc14b7113e0d40db3fcdb46dc0b32237276|
| WebDAV Linux |13027740149|12586665|367d2ead206d5d5d4f006b7f57b55c47402177990d97694375d99e3c082cc4bd|
| WebDAV macOS |13027720393|10776106|14dccf0a6aae333b551e66b0a8226424d9f2c0e1c8f60de7311e3adc5a7bc01f|
| F09 legacy |13027487617|37960|967c46e2e7f00286d7df8c1b26b76c400d7d81dcdc7daa2c565fca14c2b8009e|
| Apple iPhone original ZIP |13028001843|181108941|42b1ce664a7e2a37c1e66bd35876ce7e35c4ddfaf3a457a6b8f6ae55957289f9|
| Apple observation |13027627711|14382|ac30db434949c44a5b440915ed25b356be46f00a3aa0cccc1f2a2621883be240|
| Combined diagnostic |13028132808|5338535|eab6e079b51a489e65dc7989f48dba5764fe58f7f2e92840f27fe018841fdb3b|

## Active next package and actual team activity

F02 Windows -> GTK same-source transfer:
- tree /data/workspace/exreader-dot-f02-win-gtk-transfer-20261031
- branch codex/dot-f02-win-gtk-transfer-20261031
- base cfdaf6a4531548be63b4dd0c2bccd6b050a93124
- exactly seven new paths: tests/reader_f02_win_gtk_20261031/{dav_store.py,windows_send.py,gtk_receive.py,authenticate.py,source_lock.json}; .github/workflows/dot-f02-win-gtk-transfer-20261031.yml; docs/reader-total-progress/DOT_F02_WIN_GTK_TRANSFER_20261031.md
- five files written, workflow/source lock not yet stable at owner snapshot. No commit, push, CI run or artifact.
- User approved one round with 240/150/20 budgets. Preserve them.
- Review HOLD: same-name compact import recursion, reversed GTK projection_status success condition, secret-scan failure vs always-upload safety gate, error-message sanitization and failed Store initialization cleanup. Writer is fixing; no premature GO.

Six registered child lanes, not six simultaneous developers. Four active actions at the latest03:22:48 snapshot (one implementation, two reviews, one document task); two completed lanes available:
1. map_remaining_acceptance_work — implementation: sole F02 source writer.
2. review_native_journal_contract — active security/transport review of F02; waiting for remaining stable files; no GO.
3. review_restart_crash_gaps — active Windows/GTK driver review of F02; concrete defects reported; no GO.
4. check_apple_run_status — completed evidence/document sealing after combined diagnostic; available, not active.
5. diagnose_ipad_font_failure — this receipt document and completed F09 read-only contract review; no product write.
6. diagnose_iphone_annotation_failure — completed independent Apple timeline review; no current execution/PID, available, not counted as an active implementer.

Root coordinates. CI jobs are not agents. Our listed package runs are terminal; F02 has not started CI. External C02 has one in-progress run, detailed below. Do not launch duplicate existing work or unapproved replacement runs.

## P0 / six-platform mainline

P0 migration safety, conflict recovery and SDK3.42 six-platform same-source acceptance remain open at formal level. C02/restart/bridge candidate successes do not prove real lifecycle integration or all host acceptance. Restart's detected-and-refused acquisition-window behavior is not a claim to prevent every external write; crash residue/isolation limits remain. H02/Claude owner files are outside these lanes and are not silently taken over. F02 same-source Windows/GTK transfer is the current bounded implementation step; Apple annotation blocks complete Apple evidence, and full19/six-platform unified evidence cannot be synthesized from different SHAs or runs.

This interval's remaining duration and the total remaining duration cannot be estimated with a defensible range. Confidence in any completion-time estimate is low: Apple root cause remains unresolved and F02 has not passed review or CI. Historical run duration is not a completion promise.

## Access, ownership, and restart-safe continuation

Authorized route: lap25002 Desktop Commander device d55d0477-84bb-4425-8708-5a3ecacce78b -> official saved-login instabox@0.8.52 -> existing machine m_agqxv2s72g5vwdtsifu5cnmml4.
Last root handshake: 2026-10-31 03:10:41 UTC (2026-10-30 23:10:41 EDT), running/ready and pwd succeeded. This receipt did not create a second handshake job. Latest actual source-read warning at03:21Z: /data bytes82.5%, inodes93.0%; no further cleanup, resize, restart or machine replacement performed.

Receipt tree /data/workspace/exreader-dot-apple-receipt-20261030, branch codex/dot-apple-receipt-20261030. Pre-write HEAD equals remote5640f69cfe263c8e9a0e672d0408adf05f492102. Index was empty. Existing dirty docs/reader-total-progress/DOT_APPLE_RECOVERY_HANDOFF.md is preserved and must not be staged. Only this new hourly file is committed. Denied routing-results doc remains untouched in its own tree; do not move it to bypass denial.

Source/Git/docs use the authorized machine route. Builds, syntax checks, tests, fixtures, benchmark and ZIP inspection only Actions. Preserve all original assertions, budgets and failures. No default/shared branch, PR, tag or release. No new Codex/Claude tasks or extra Terra team. Never read/export credentials; redact private authentication material. Unknown async operations must be collected using original PID. A denied action is recorded, not rerouted. This backup is not a stop or completion declaration.


## Latest root-verified update, 03:22:48 UTC

Apple diagnostic result document eda2a398fab706486be9446f1ca6738b668224ef was pushed doc-only [skip ci]. Apple writer and independent reviewer have completed their work and are available, not waiting on CI.

External C02 at source4d6655d3d9e45e86983037c4179989ad33b828d6: root API check03:22:12 UTC found run41163872509 registry_and_product in progress, run41163872431 persistent_gate success, run41163872424 native_evidence Windows and Ubuntu failed at the step named Preserve original ABI2 81 checks and raw six contract failures; original_zip_audit skipped. This is API step status only, not freshly read assertion counts. No full C02 success claim and no takeover of its external owner.
