# Apple continuation checkpoint — 2026-10-29

Current accepted fixed-catalog audit: [40920714977](https://github.com/NoGod3524/EXReader/actions/runs/40920714977), source f406ab02de173e3431db548de1c30b24f7074788: **94/108 (87.0%)**, foundation 12/12, host 81/84, final 1/12. This Apple batch has closed 11 of its 14 host items. Independent SDK 3.41 host evidence is separate from SDK 3.42, physical devices and the final common-source product.

Completed:
- Font library, all three Apple hosts: original 40627627614; independent 40904394809.
- Original save, all three hosts: macOS original 40647623322; iPhone/iPad producer 40905868673 at 127cdb7c62772fd293c10cc032547c28904bd1c2; independent iOS audit 40910291131.
- iPhone/iPad organization: 40911140164 at b259db57103cd7661ed3f1c3fc6bd0c49c08981c passed both original six-case suites, including real tag/series member add/remove/restore/restart. Fixed audit 40915032673 reread exact logs, steps and member-restoration screenshots. Earlier narrower passes were not counted.
- Sync status, all three hosts: producer 40914421686 at 6c7d043d416c1ab1075016695ae510c7b23dd2e5; independent 40920468235 verified XCTest, actual HTTPS cancellation, 401 details, credential update/retry and failed-state outbox before 256-shard recovery. Fixed audit 40920714977 counts the three host items. Prior failed 40910671642 remains retained.

Still unaccepted:
- Annotation exchange, all three hosts. Original system-save run 40911433448 at d5327faa540d2e19978e5b76e387f99457a60936 failed. macOS did not expand the native export control; iPhone's original tree showed its parent identifier replacing JSONL/Markdown child identifiers, and its unchanged live-system-theme case failed. iPad also retained feature and base-layout failures. The macOS-only leading-click trial 40920156829 at d26b37aac808edaff426d34796ce9feb7564b945 failed its annotation case; its other native modes passed.
- Corrected common candidate: branch codex/apple-annotation-controls-resume-20261029, source 622b9558f79eda07211e15c51bffcd728da6c553, [40923468266](https://github.com/NoGod3524/EXReader/actions/runs/40923468266). Both SDK builds passed and all three native jobs are running. Native expansion is now an explicit 44-point button; child identifiers are distinct. The active theme sheet observes the actual OS scheme. Tests, old-source hashes, native picker assertions, pixel checks and budgets remain. Do not duplicate this run or count any annotation item before actual outcomes and independent review.

SDK 3.42 source staging is saved separately: codex/apple-sdk342-host-continuation-stage-20261029 at 4a68d80fbaa524fc28f899d209d795248627080b, based on 80da967f5411e0c76d25e8bb21ec23c5f2b22385. Exact parent/blob comparisons and context application preserve existing 3.42 worker/model/bridge changes; missing font review view identifiers are added. This staging commit intentionally skips CI and grants no acceptance. Candidate annotation changes must be updated if their current cloud result requires another repair.

All builds, syntax, fixtures, tests and artifact parsing are Actions-only. Local source and lightweight Git/status only. Old failures and frozen budgets remain. No default-branch merge, tag or Release has been made.
