# Apple continuation checkpoint — 2026-10-29

Current accepted fixed-catalog audit: [40920714977](https://github.com/NoGod3524/EXReader/actions/runs/40920714977), source `f406ab02de173e3431db548de1c30b24f7074788`: **94/108 (87.0%)**, foundation 12/12, host 81/84, final 1/12. Scoped independent SDK 3.41 host evidence does not establish SDK 3.42, physical devices or unified-source release.

Completed:
- Three Apple font host items: original 40627627614; independent 40904394809.
- Three original-save items: macOS original 40647623322; iPhone/iPad producer 40905868673 at 127cdb7c62772fd293c10cc032547c28904bd1c2; independent iOS audit 40910291131.
- iPhone/iPad organization: producer 40911140164 at b259db57103cd7661ed3f1c3fc6bd0c49c08981c passed both original six-case suites with actual tag/series member add/remove/restore/restart assertions. Fixed audit 40915032673 verified exact original logs, steps and extra member-restoration screenshots. Old narrower six-case successes alone were not counted.

- Sync UI: branch codex/apple-sync-details-resume-20261029, corrected source 6c7d043d416c1ab1075016695ae510c7b23dd2e5, run 40914421686. Adds live session detail sheet, fixed native reason/HTTP status/counters and retry label; tests inspect actual cancellation and 401 recovery. Prior run 40910671642 at c5b0a285f409010fe9a5ac832b4640007864a50d passed macOS; iPhone/iPad failed the final immediate book-row assertion. Source shows FINISHED precedes asynchronous shelf publication. The correction waits within the existing test budget for publication and the same imported row. Old failures remain. Corrected 40914421686 passed all three platforms; independent 40920468235 authenticated native XCTest, actual 401/cancellation/detail/retry evidence and the failed-state outbox before 256-shard recovery. Fixed audit 40920714977 now counts these three host outcomes.

Still running; do not duplicate:
- Annotation UI: branch codex/apple-annotation-system-save-resume-20261029, d5327faa540d2e19978e5b76e387f99457a60936, run 40911433448. Actual production JSONL/Markdown export controls choose a system folder; subsequent native import selects files in that folder. Review-only invalid-file staging uses the selected destination, not invisible private Documents. Original assertions and five retained native suites remain. macOS failed to expand the native export disclosure. Scoped correction d26b37aac808edaff426d34796ce9feb7564b945 is running as 40920156829 with unchanged five native suites and both original SDK inputs. iPhone/iPad original jobs remain active. No annotation item is accepted before actual results and independent archive review.

All builds, syntax, fixtures, tests and artifact parsing are Actions-only. Local source work and lightweight status only. Preserve old failures and frozen budgets. No tag/Release without separate user authorization. No default-branch merge has been done.
