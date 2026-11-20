# P600fix: pptx-20 at 600 px

**Candidate verified for the primary speed target.** PPTX-20 measured **0.891× PDF.js** (0.756000 vs 0.848450 ms/page, 11/12 round-sum wins). This is uncommitted work on `perf/pptx600-clip-identity`, not a merge. The exact prior 577-test suite passed in guarded shards; deck changed in the faster direction, not literally unchanged.

## Attribution summary

The prior published baseline was **1.002 ms/page vs 0.813 ms/page** for PDF.js (**1.232×**, 1/12 round-sum wins). That is historical, not a same-session native baseline for this run. Its attribution rerun identified five near-full axis-aligned masks per page, including the 600 × 337.5 viewport on a 600 × 338 backing bitmap. The four stream clips and viewport retained fractional last-row/corner coverage. Source: `b7d98274e:evidence/pptx600-attribution-20261120/REPORT.md`.

## Verification targets

| Gate | Result |
| --- | --- |
| pptx-20@600 vs PDF.js ≤1.00× | **0.891037×**, 11/12 round-sum and per-round median wins. [Capture](raw-dot-rule/pdfjs-600.json) |
| word-5@600 vs PDF.js ≤0.70× | **0.536240×**, 12/12 round-sum and per-round median wins. [Capture](raw-dot-rule/pdfjs-600.json) |
| deck@600 unchanged inside native null floor | **0.842843× candidate/base**, 5.515100 vs 6.543450 ms/page (15.72% faster); 12/12 wins. Same-DLL null max round drift 7.89%. No regression, but not literally unchanged. [Capture](raw-dot-rule/deck-600.json) |
| Small-fixture pixels | **111,897,000 compared / 0 differences**; PPTX 600/1200/2400, deck and word 600/1200. [Logs](raw-dot-rule/pixels.log) |
| Output backgrounds and fractional edge | **200 page comparisons / 0 mismatches**, white, transparent, tinted RGBA and grayscale, at 600/1200 on pptx-20 and word-5. Active pixel and last-row SHA-256 agree on all pages. [Capture](raw-dot-rule/backgrounds.json) |
| CTest matching prior suite | **577/577 distinct tests passed**, 24 guarded CTest shards on the corrected binary. The current build registers 586; nine extra release/CLI/corpus/benchmark checks are outside the prior exact suite. One extra execution of a fixture prerequisite was deduplicated. [Aggregate](raw-dot-rule/ctest-aggregate.json), [canvas regression](raw-dot-rule/ctest-canvas.txt). |
| Peak RSS (≤+10%) | **Pass** for all three 600 px cells; worst of any matched pair was **+2.25%** (word-5). [Raw peaks](raw-dot-rule/rss-summary.json) |

## Design & Change

Recovered an existing seven-file candidate in the assigned worktree and corrected a validation regression: the new rectangular fast path now requires a valid fill rule. An invalid rule on the fractional rectangle is routed to legacy validation and returns EXR_ARGUMENT, as tested. The code represents an axis-aligned full-span clip by an opaque interior and exact fringe/corner coverages rather than materializing the dense A8 mask up front. A clip covering the actual full pixel extent can be identity; the 337.5-row geometry is **not** treated as full bitmap identity. Only the 255-coverage interior gets unmasked writes. Intersections multiply coverage with the original integer formula; fallback consumers can materialize when needed. Group commit preserves fringe coverage. The added `fractional_full_span_clip` test checks 255 interior, 127/128 corner/fringe, nested multiplication, save/restore, no widening on full clip, and group output alpha 63/64. The new shortcut reduces the number of raster-row work charges and cancellation polls; the path flattening step remains in both routes. Those are synthetic per-operation assertions; full fixture output comparison separately verifies the final row, not an instrumented trace of each original clip.

## Measurement rules

- `harness/build.ps1 -Target all -Holder codex-P600f` acquired the shared build slot. On the first attempt DLL replacement hit a transient sharing violation with the older test shard. Guarded targeted DLL and canvas relinks succeeded once that shard exited, and guarded `-Target all` completed the remaining relinks. [DLL build](raw-dot-rule/build-exreader.txt), [canvas build](raw-dot-rule/build-canvas-test.txt), [all targets](raw-dot-rule/build-all.txt).
- Native baseline and its distinct byte-identical copy: SHA-256 `06ca9f0e0f9d079ae80754af4a1d10c457d1f07e544b02e349a963f386a9d261`. Candidate and distinct null copy: `931948aca8638cfe32db972ce06c36456d7e29991b64ee70f9093cb99c65ab67`.
- Same-session PDF.js comparison: `EXR_IDLE_GATE=off`, `ops/bench-lock.ps1 -Holder codex-P600f`, zero occupied build slots at acquisition, 12 mirrored order rounds (all retained; pre-CPU recorded, not filtered), installed `../pdfjs-bench2/node_modules/pdfjs-dist`. Run from `EXReader-slides`: `python -B ../EXReader-openperf/tools/render_vs_pdfjs.py --library build/p600-dlls/rule.dll --null-library build/p600-dlls/rule-null.dll --pdfjs-root ../pdfjs-bench2/node_modules/pdfjs-dist --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf --case word-5=tests/fixtures/pdf-hybrid-real/word-5.pdf --width 600 --rounds 12 --out evidence/pptx600-fix-20261120/raw-dot-rule/pdfjs-600.json`.
- Deck uses `harness/validate-dot-rule.py deck` with baseline, byte-identical baseline null, candidate, mirrored order, 12 rounds with pre-CPU, and all-arm hash checks; final capture is the isolated rerun. Previous uncorrected DLL captures in `raw-dot/` are retained for provenance, not used for corrected acceptance. Pixel parity and memory are separate checks. RSS uses three AB/BA/AB pairs of fresh native processes per fixture. [Lock log](raw-dot-rule/lock.txt).

## Results

| Fixture @600 | Candidate p50 | PDF.js p50 | Candidate/PDF.js | Candidate / candidate-null p50 | Null median/max absolute paired round-sum drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| pptx-20 | 0.756000 ms | 0.848450 ms | 0.891037× | 0.991736× | 3.17% / 15.48% |
| word-5 | 2.527300 ms | 4.713000 ms | 0.536240× | 1.013413× | 5.55% / 26.53% |

The PPTX p50 margin is larger than the median null drift but not the largest single-round null deviation; eleven wins out of twelve and the pooled p50 meet the prescribed gate in this run. For deck the same-DLL baseline/null p50 ratio was 1.064348× and median/max absolute round-sum null drift 2.79%/7.89%.

| Fixture @600 | Maximum baseline peak (B) | Maximum candidate peak (B) | Peak change (max vs max) | Largest paired change |
| --- | ---: | ---: | ---: | ---: |
| pptx-20 | 29,765,632 | 29,044,736 | −2.42% | −1.07% |
| deck | 44,376,064 | 44,142,592 | −0.53% | +0.45% |
| word-5 | 35,672,064 | 34,963,456 | −1.99% | +2.25% |

## Verdict

PPTX and Word speed thresholds, small fixture and multi-background output parity, and 600 px RSS thresholds met. Deck is reproducibly faster, not unchanged. All 577 required named CTests passed. No commit, push, merge, or Closeout edit.

