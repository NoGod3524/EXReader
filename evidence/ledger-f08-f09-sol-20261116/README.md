# F08 / F09 source-bound follow-up

Baseline: PR #225 head `f9b77d83aac82212aae6582328ad85abf1ddbaa7`.
Initial implementation: `c6451161`; GTK follow-ups through `8c30ac3c` on `codex/ledger-f08-f09-sol`; PR #226 targets main and must not be merged by this task.

## Final result

- F08: **verified**. Windows run **43829432891**, GTK run **43832477170**. Both fixed 2,202-book shelves and their budgets passed; GTK retained 2,804 real GDK frame records and all 768 scroll samples.
- F09: **verified**. Windows run **43829432891** passed all names/roles and keyboard reachability. Completed GTK audit **43831196406** accepted with zero blocking findings (31/32 checks); its sole truncated reader-Tab advisory is covered by the passing reader-cycle case and real 17-Tab trace in **43832477170**, on the **identical host binary SHA-256**. The latter run did not complete the later annotation phase and is not represented as a second full audit.
- Both GTK combined runs ended cancelled after the relevant evidence was uploaded; their separate F10 public TLS step failed. No F10 requirement record changed. Catalog: **105 verified / 1 partial / 2 pending**, denominator **108**; the other 106 requirement records are unchanged as parsed JSON to the handoff baseline.

Source-bound audit records: `docs/reader-total-progress/_audit/43829432891.json`, `43831196406.json`, `43832477170.json`. The records identify the exact scoped assertions and exclusions, artifact IDs/digests, source SHA and retained-file hashes.

## Changes and acceptance

F08 records opt-in per-frame `update` / `after-paint` signals from the real GTK host. Each JSONL record contains the GDK frame counter, GDK frame time, update timestamp, and after-paint timestamp. The summary checks consecutive counters and monotonic timestamps, then computes nearest-rank p50/p95 for update-to-after-paint duration and clock intervals. Missing, malformed, negative, or discontinuous samples cannot grant frame coverage. These are GDK phase durations, not input latency or GPU execution time.

The fixed GTK workload seeds 2,202 deterministic originals through the installed public SDK. Three AB/BA process pairs each start from the same seeded library, load the shelf, and deliver 128 real Down key events, including scrolling. Raw selections, frame traces, per-process RSS high-water marks, environment, corpus and binary hashes are retained. Relative budgets compare candidate and baseline cohort medians on the same runner: 2.5x for timings and 1.25x for RSS. Both cohorts use the same binary; this tests repeatability and does not establish a historical regression comparison. No absolute GTK millisecond budget is compared across machines.

Windows reuses the existing 2,202-book production shelf probe. The exporter validates exactly 256 grid and 128 list samples per fresh process, recomputes p50/p95 from raw samples, checks actual scrolling, and records load, first paint, first interactive, and PeakWorkingSetSize (RSS high-water mark). The established budgets remain 2,500 ms first interactive, 50/100 ms p50/p95, and 256 MiB peak.

runner 无物理显示器 vsync，以 GDK frame clock 时间戳替代。Windows EndDraw/GdiFlush observations likewise do not claim physical monitor vsync.

F09 retains all checks. Scroll containers now have distinct names ending in `scroll area`, so name-based AT-SPI lookup reaches the intended list/text child. The account audit expects the current Sync library / Receive books / Cancel / Retry controls. The baseline rerun also aborted inside the multi-threaded AT-SPI collector (`malloc(): unaligned fastbin chunk detected`). Event dispatch and proxy queries now share the audit thread. Status notifications are matched using `object:property-change:accessible-name`; AT-SPI detail1/detail2 are numeric fields and do not contain the property name.

## Validation

Local MSVC Release compilation of `EXReaderAudit` and `exreader-shell-selection-test`: exit 0. The initial MinGW build hit existing document-editor warnings promoted to errors; no unrelated editor source or warning policy was changed.

`python tests/ledger_f8910/test_f08_f09_contract.py`: 4 tests passed. Covers malformed/missing/discontinuous frame data, duplicate/missing/incorrect shelf metrics, zero scrolling, budget failures, the actual AT-SPI event shape, and reentrant dispatch without a background proxy reader.

`python tests/reader_perf_windows/render_budget.py --self-check`: passed.

`pwsh -File .../ops/prepush-check.ps1 -Worktree <this worktree>`: all checks passed.

`python tools/check_ci_hygiene.py`: violations=0.

Catalog denominator: 108. Only F08/F09 requirement entries may change; F10 and all other requirement records must match the handoff baseline exactly.

## CI evidence

Baseline reruns requested before fixes: Linux 43828822348; Windows 43828825452 (source f9b77d83).

Implementation runs: Linux 43829432896; Windows 43829432891 (source c6451161). Windows accepted: render/present/interactive budget, fixed shelf export, keyboard reachability, and name/role audit. CTest passed 602/602. The GTK attempt was cancelled after its artifact showed that dropping XAUTHORITY prevented the host from connecting to xvfb-run. Superseded runs 43830611662 and 43831074061 are not used as acceptance evidence. Corrected GTK run: 43831196406 / source 45c44b310898772a878f41d406297311238e9d8f.


### Windows shelf results (run 43829432891)

| Metric | p50 | p95 |
| --- | ---: | ---: |
| Shelf load, three fresh processes (ms) | 2.192 | 2.199 |
| First paint (ms) | 718.888 | 720.486 |
| First interactive (ms) | 728.190 | 730.304 |
| Peak working set (bytes) | 19,546,112 | 20,434,944 |
| Grid moves, 768 raw samples (ms) | 6.073700 | 6.487100 |
| List moves, 384 raw samples (ms) | 5.493250 | 6.393900 |

Load/paint/interactive/RSS percentiles use three process observations; move percentiles pool the raw samples. See `windows-budget/aggregate.json` and the unmodified exports for every input. Keyboard evidence records 740 SendInput events, all 11 surfaces, `name_role_passed=true`, no unnamed/unexplained controls, and `accepted=true`.

The GTK audit's historical `sdk` field identifies its frozen accessibility contract (3.40.0), while package `build.json`, runtime dependencies, binary hash and source identity bind the actual 3.42.0 build. The historical contract is not represented as a runtime version measurement.


### First accepted GTK evidence (run 43831196406, source 45c44b31)

F08: `accepted=true`, six fresh processes, 128 scroll samples each, complete consecutive GDK frame traces, actual geometry 1088x820 in every process. Candidate/baseline median ratios: load 0.946807, first interactive 0.956089, scroll p50 0.999975, scroll p95 1.014181, RSS 0.998205, update-to-after-paint p50 1.000000 / p95 1.024765, clock-interval p50/p95 1.000000. All relative budgets passed. GDK interval p50/p95 was 16.667/16.667 ms for every process. Clock phase p50 ranged 0.004–0.005 ms and p95 1.083–1.220 ms; these include continuous idle update cycles and are not page raster cost or physical display latency.

The GTK fixed shelf first-interactive median was 3,835.424 ms in the candidate cohort and 4,011.578 ms in the baseline cohort. GTK is gated by the documented same-run relative budgets, not by the Windows 2,500 ms absolute budget. All six raw process records, including the first baseline's larger RSS of 119,212 KiB, are retained without filtering.

F09: 32 checks / 13 phases, 31 passed, zero blocking findings, accessibility accepted. The sole advisory sampled only 14 Tabs and ended at the added Reading records button, before the comment entry. The follow-up collector now records a complete Tab cycle, bounded at 64 stops; the original assertion and severity remain. `linux-f09/result.json` preserves the earlier result.

The F08/F09 steps completed successfully before the run was superseded by the full-cycle audit change. The separate F10 public-PKI TLS step failed and is outside this task; its catalog entry is unchanged.


### Final GTK performance and supplementary reader evidence

Run **43832477170**, source **8c30ac3c59a369fac071de7d6b5da2b74b628fe5**: F08 passed all nine relative budgets. Candidate/baseline median ratios were load **1.583850**, first interactive **1.575459**, scroll p50 **0.965992**, scroll p95 **0.468250**, RSS **0.951957**, GDK phase p50 **1.000000** / p95 **0.930723**, and clock interval p50/p95 **1.000000**. All six processes completed; all 2,804 frame records and 768 scroll samples were independently recomputed locally with exact agreement to the CI summary. Candidate load p50/p95 was 7,412.466/9,143.493 ms; first interactive 7,479.401/9,209.624 ms. Baseline first-interactive median was 4,747.444 ms. These satisfy the stated relative GTK budgets and do not satisfy or claim the separate Windows 2,500 ms absolute budget.

`linux-f08-final/` contains the unmodified final performance JSON, corpus, environment and six host-generated frame traces. `linux-f08/` retains the earlier accepted performance observation. Windows original bytes are kept under `windows-budget/` and `windows-keyboard/`; `.gitattributes` prevents evidence newline conversion.

The cancelled run's original `linux-reader-cycle/audit.txt` records `reader_tab_order_reaches_panels PASS`. Its `keys.tsv` observations 82–98 show a complete cycle: Import F1 → toolbar → Selectable page text → Reading records → Annotation comment → Saved notes scroll area → Import F1. The cycle itself passed; the collector later stopped during annotation sampling. The completed prior audit's annotation checks passed. Host SHA-256 in both runs is **8f06c8409aebd28930b1824ba1e5213c95c7f4625251076eb47d4ba99dd8c458**. Only the reader-cycle case is credited from the incomplete rerun; no later-phase acceptance is inferred.

| Original GTK blocker | Evidence closing it |
| --- | --- |
| Unnamed Tab stop | Distinct named scroll containers; completed audit passes tab names |
| Collections dialog focus | Baseline focus handling confirmed by real AT-SPI focus inside the modal dialog |
| Shelf row names | Named row children selected correctly after removing the container-name collision |
| Annotation note names | Named note rows selected correctly; actual annotation phase passed |
| Status name notification | Actual `object:property-change:accessible-name` events captured and checked |
| Account Escape focus restoration | Baseline modality/focus behavior confirmed by real restored main-window focus |

The extra current-host mismatches (reader panel lookup and renamed account buttons) also pass. The full-cycle probe remains in the final source because its reader case was proven by the supplementary trace. The final source differs from tested **8c30ac3c** only by evidence, catalog and `.gitattributes` files; Windows host source is unchanged from tested **c6451161**.
