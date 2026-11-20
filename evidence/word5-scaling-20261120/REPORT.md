# word-5 rendering scale at 600, 1200, and 2400 px

**Page-sized clip masks are the main scaling cost.** At 1200 px, direct clipping takes 1.80 ms/page and contributes 1.27 ms of the growth from 600. Group commit and image paint are close behind. At 2400 px, direct clipping takes 8.86–10.71 ms/page across the two probe modes, growing 5.07–5.94× on 4.00× as many page pixels. The number of clips stays fixed. Clearing reused masks grows 8.38× for 3.99× as many bytes. Glyph time grows about 2.1×.

## Renderer scaling

The 2026-11-19 run measured all five pages over 12 rounds at each width. The table uses the pooled p50 of 60 renders per arm. EXReader time covers `exr_fixed_render` and PDF.js time covers `page.render(...).promise` in Node. Both exclude document open, page lookup, RGBA readback and hashing. The native source matches this checkout under `src/` (`a35fed391` vs `052d2b3b2`). [Source report](../../../EXReader-openperf/evidence/tools-summary-20261119/REPORT.md)

| Width | Canvas | EXReader p50 ms/page | Same-DLL null p50 ms/page | PDF.js p50 ms/page | EXReader / PDF.js | Rounds won |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 600 × 777 | 2.11425 | 2.09810 | 3.59075 | 0.589× | 12/12 |
| 1200 | 1200 × 1553 | 6.62980 | 6.46855 | 6.00310 | 1.104× | 2/12 |
| 2400 | 2400 × 3106 | 31.87330 | 31.67305 | 18.56465 | 1.717× | 0/12 |

| Width step | Canvas pixel growth | EXReader time growth | EXReader width exponent | PDF.js time growth | PDF.js width exponent |
| --- | ---: | ---: | ---: | ---: | ---: |
| 600 → 1200 | 3.997× | 3.136× | 1.649 | 1.672× | 0.741 |
| 1200 → 2400 | 4.000× | 4.808× | 2.265 | 3.093× | 1.629 |

The width exponent is log₂ of the timing ratio for each doubling. Across 600 → 2400, it is 1.957 for EXReader and 1.185 for PDF.js. The null arm grows 3.083× and 4.896×, reproducing the jump past pixel growth at the second doubling. [600 px raw](../../../EXReader-openperf/evidence/tools-first-data-20261119/raw/run2/small-600.json) · [1200 px raw](../../../EXReader-openperf/evidence/tools-first-data-20261119/raw/run2/small-1200.json) · [2400 px raw](../../../EXReader-openperf/evidence/tools-first-data-20261119/raw/run2/small-2400.json)

Each width passed every null RGBA hash check and all three arms produced the same canvas dimensions. The byte-identical native DLL arms differed by +0.77%, +2.49%, and +0.63% in pooled p50. The median and maximum absolute round-sum differences were 5.82%/12.62%, 3.54%/13.67%, and 2.32%/17.03%. At 1200, the 10.4% p50 gap exceeds the median round-sum drift and falls within the largest single-round drift. EXReader lost 10 of 11 warm rounds at that width.

Pre-round system CPU was sampled for 0.2 s and all rounds were retained under the original bench lock with `EXR_IDLE_GATE=off`. [Lock record](../../../EXReader-openperf/evidence/tools-first-data-20261119/run2a-lock.log)

| Width | Pre-round CPU % (rounds 1–12) |
| ---: | --- |
| 600 | 20.4, 26.0, 18.8, 44.2, 23.5, 14.1, 16.3, 4.0, 7.2, 18.4, 23.5, 56.7 |
| 1200 | 21.2, 16.0, 28.8, 16.7, 27.9, 21.8, 21.2, 35.8, 29.8, 36.7, 40.4, 49.0 |
| 2400 | 47.6, 54.8, 43.3, 73.1, 55.8, 42.3, 37.1, 40.2, 16.7, 51.9, 9.6, 5.1 |

The comparator uses PDF.js 3.11.174 and node-canvas 3.2.3. The Node default sets `disableFontFace`, so ordinary outline fills use the cached glyph path generator and canvas `ctx.fill()`. The Node harness allocates the canvas before its timer. EXReader initializes its output canvas inside the timed call. [Comparator worker](../../../EXReader-openperf/tools/render_vs_pdfjs_worker.cjs#L15) · [Node default](../../../pdfjs-bench2/node_modules/pdfjs-dist/legacy/build/pdf.js#L3482) · [Glyph path paint](../../../pdfjs-bench2/node_modules/pdfjs-dist/legacy/build/pdf.js#L12223)

### Locked repeat on 2026-11-20

The fresh comparison reproduced the crossover and the 2400 px gap. Each p50 pools 60 renders, and round wins compare sums across the five pages. [600 px raw](raw/paired-600.json) · [1200 px raw](raw/paired-1200.json) · [2400 px raw](raw/paired-2400.json)

| Width | EXReader ms/page | Same-DLL null ms/page | PDF.js ms/page | EXReader / PDF.js | Rounds won |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 2.86430 | 2.86755 | 4.84240 | 0.592× | 12/12 |
| 1200 | 8.86690 | 8.80615 | 8.25195 | 1.075× | 2/12 |
| 2400 | 31.17350 | 31.28850 | 18.20620 | 1.712× | 1/12 |

| Width step | EXReader growth | EXReader width exponent | PDF.js growth | PDF.js width exponent |
| --- | ---: | ---: | ---: | ---: |
| 600 → 1200 | 3.096× | 1.630 | 1.704× | 0.769 |
| 1200 → 2400 | 3.516× | 1.814 | 2.206× | 1.142 |

The above-area whole-render jump at the second doubling is session-dependent. It was 4.81× in the original comparison, 3.52× in the fresh comparison, and 4.27× on the production DLL in the fresh attribution sweep (2.139 → 6.520 → 27.861 ms/page). The accompanying null grew 4.16× in the attribution sweep. EXReader scaled worse than PDF.js on both doublings in both paired comparisons.

## Stage attribution

This fixture has 22–23 text-show operations, 44 path fills, 32–33 clip operations, and one 640 × 480 image per page. The clips include 27 table-cell clips and four or five near-full-page clips. The renderer adds a viewport clip and an isolated RGB root group. [Fixture](../../tests/fixtures/pdf-hybrid-real/word-5.pdf) · [Root group](../../src/pdf_annotation_paint.c#L225)

Stage times below are means over all 60 renders in mode M1, which takes coarse timestamps and counts work. Means let the stages be added. The residual is the difference between the timed render and the listed stages. The comparison above uses p50s. [Per-page timings and counters](raw/attribution.json)

| Stage | 600 ms/page | 1200 ms/page | 2400 ms/page | 600 → 1200 | 1200 → 2400 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Viewport clip | 0.080 | 0.420 | 1.998 | **5.25×** | **4.75×** |
| Content clips | 0.451 | 1.383 | 8.709 | 3.07× | **6.30×** |
| Root-group commit | 0.409 | 1.584 | 7.537 | 3.88× | 4.76× |
| Image callback | 0.395 | 1.356 | 6.216 | 3.44× | 4.59× |
| Canvas creation | 0.099 | 0.401 | 1.783 | 4.03× | 4.45× |
| Glyph callback | 0.436 | 0.774 | 1.608 | 1.78× | 2.08× |
| Non-text path paint | 0.075 | 0.251 | 0.915 | 3.32× | 3.65× |
| Canvas teardown | 0.091 | 0.231 | 0.868 | 2.53× | 3.76× |
| Group setup | 0.010 | 0.017 | 0.039 | 1.61× | 2.30× |
| Residual | 0.253 | 0.275 | 0.363 | 1.09× | 1.32× |
| **Total render** | **2.299** | **6.692** | **30.036** | **2.91×** | **4.49×** |

- **At 1200 px**, the viewport clip is the clear above-area stage among the coarse timers. Direct clipping as a whole grows 3.40× and contributes 1.27 ms of the 4.39 ms increase. Root-group commit adds 1.18 ms and image paint adds 0.96 ms. Together those three account for 78% of the increase. Glyph work adds 0.34 ms.
- **At 2400 px**, direct clipping contributes 8.90 ms of the 23.34 ms increase. At 4× its 1200 cost, it would take 7.21 ms/page. It takes 10.71 ms/page, an excess of 3.49 ms, versus 1.20 ms for group commit and 0.79 ms for image paint. The median of 12 round-level clip means grows 4.92× in M1 and 5.26× in M2. M1's all-sample mean includes larger 2400 px tails, and the median and deep probe both retain the above-area clip growth.

### Counter evidence and sub-stages

M2 adds inner-scope timers. These rows are nested inside the coarse stages. Work counts are per page and consistent across both modes. Clip fill footprints are the probe's conservative bounds. [Probe data](raw/attribution.json)

| M2 sub-stage | 600 ms/page | 1200 ms/page | 2400 ms/page | 600 → 1200 | 1200 → 2400 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Viewport mask allocation and fill | 0.071 | 0.399 | 2.056 | 5.66× | 5.15× |
| Content mask reuse clearing | 0.041 | 0.180 | 1.512 | 4.35× | **8.38×** |
| Content mask fill without a parent clip | 0.108 | 0.877 | 4.196 | 8.14× | 4.79× |
| Content mask fill with a parent clip | 0.073 | 0.258 | 1.038 | 3.54× | 4.03× |
| Group source-alpha scan | 0.292 | 1.212 | 5.250 | 4.15× | 4.33× |
| Image paint | 0.353 | 1.316 | 5.816 | 3.73× | 4.42× |
| Glyph outline | 0.070 | 0.074 | 0.111 | 1.06× | 1.50× |
| Glyph flatten, edges, raster allocation and row buckets | 0.148 | 0.183 | 0.302 | 1.24× | 1.65× |
| Glyph scan and coverage generation | 0.139 | 0.279 | 0.613 | 2.01× | 2.20× |
| Glyph coverage application | 0.048 | 0.172 | 0.584 | 3.63× | 3.39× |

- **Clip work** stays at 32.8 rectangular content masks/page with two fresh allocations and 30.8 reuses at every width. Reuse clears 2.86 → 11.32 → 45.12 MB/page. The second-step cost per cleared byte grows 2.10×. Unparented mask fill covers 2.32 → 9.27 → 37.07 million pixels/page. Content mask alloc plus unparented fill grows 2.69× and 4.75×, so the first-step fill-only ratio is sensitive to where fresh-buffer work is timed.
- **Glyph work** stays at 86.8 callbacks and 61.0 nonempty outlines/page. Scan rows increase 491 → 953 → 1,855 and bounding-box pixels increase 3,020 → 10,761 → 40,362. Between 1200 and 2400 the latter grow 3.75× and coverage application grows 3.39×. The sibling's zero path-cache hits leave repeated outline work, whose growth is small here.
- **Group and image** keep the same paths. Root commit handles 777 → 1,553 → 3,106 rows, with one row taking the generic path at each width. About 93% of its 2400 px source pixels are transparent, yet the alpha scan reads the full layer. The same nearest-axis image path runs once per page, with 29,156 → 115,935 → 462,365 active output pixels. The image load takes about 0.03 ms/page at 1200 and 2400.

## Source mechanism and fix

`exr_fixed_render` rounds up the output size, then clips to the fractional viewport. The exact page bottoms are 776.471, 1552.941, and 3105.882. The full-canvas test compares against the rounded height, so the viewport clip allocates a mask to preserve partial coverage of the last row. Content clips make another mask for each intersection. The canvas sizes these at page width × height and zeroes entire dirty row bands on reuse, including for narrow table cells. The rectangle rasterizer still writes the coverage into the mask. At 2400 px, one mask is 7.45 MB and one RGBA surface is 29.82 MB. The root group then traverses its surface again for clip, alpha, and compositing. The work counts stay near area scaling. The larger clears and fills cost more per byte at 2400. The timings resolve where the extra time lands. Hardware cache and memory stalls were outside the scope of the probe. [Viewport clip, src/fixed.c:215–223](../../src/fixed.c#L215) · [Full-canvas check and intersections, src/canvas.c:335–375](../../src/canvas.c#L335) · [Mask allocation and clearing, src/canvas.c:43–55](../../src/canvas.c#L43) · [Rectangle spans, src/vector.c:132–162 and :201–221](../../src/vector.c#L132) · [Group commit, src/blend.c:376–407](../../src/blend.c#L376)

**Proposed fix.** Represent axis-aligned clips as bounds with opaque spans and byte coverage on fractional boundary pixels. Intersect rectangles over those spans and multiply rounded coverage bytes at shared boundaries. This retains the fractional viewport row and nested clip rounding while removing the repeated dense mask fills and clears. Keep dense masks for general paths. A smaller first change is to use the existing dirty-column bounds when clearing only part of a reused mask. That target leaves the near-full-page mask writes for the compact representation to address. Check byte-identical output on fractional and repeated nested clips, then repeat the width sweep. [Dirty bounds, src/canvas.c:117–136](../../src/canvas.c#L117)

## Fresh measurement record

Built the two-mode DLL from scratch copies of eight renderer translation units and the existing production objects using the Openperf Release flags. Both worktrees' `src/` trees were unchanged. Every completed sweep ran under bench holder `agy-W5` with zero build slots, a heartbeat before the sweep, and `EXR_IDLE_GATE=off`. The compile took and released the `agy-W5` build slot. The first attempt stopped at the signature check because it used a list as a set key. The retry used a tuple and completed all 12 rounds for every width and arm. [Bench lock log](raw/bench-lock.log) · [Build gate log](raw/build-gate.log) · [Build output](raw/build.log) · [First attempt](raw/attribution-first-attempt.console.log) · [Scratch build](../../../w5-scaling-scratch/build_probe.py) · [Scratch capture runner](../../../w5-scaling-scratch/measure.ps1)

The production and null DLLs are distinct byte-identical copies (SHA-256 `89ee7f81953459f0633aa66fb6e8f8bd65cd80bb8870963414283a625ef2b0db`). All native arms matched dimensions and RGBA SHA-256 on every completed page, including both probe modes. PDF.js matched dimensions. Relative to the attribution production p50, M1 changes were +3.29%, +1.92%, −0.40% at 600/1200/2400 and M2 changes were +9.31%, +4.21%, +2.02%. M2 is used to resolve sub-stages.

| Sweep | Width | A/A0 pooled p50 | Median / max absolute null round-sum drift | Pre-round CPU %, rounds 1–12 |
| --- | ---: | ---: | ---: | --- |
| Attribution | 600 | 0.9984 | 4.57% / 10.89% | 36.54, 6.00, 22.92, 12.12, 25.00, 8.65, 8.74, 30.39, 14.14, 17.65, 9.80, 23.58 |
| Attribution | 1200 | 0.9865 | 4.30% / 15.32% | 17.82, 34.62, 28.43, 21.00, 19.23, 16.49, 35.00, 24.04, 19.23, 30.77, 32.69, 24.00 |
| Attribution | 2400 | 1.0134 | 1.46% / 23.65% | 39.80, 19.23, 42.72, 64.08, 30.39, 33.65, 34.02, 25.71, 34.34, 17.31, 30.77, 12.50 |
| EXReader / PDF.js | 600 | 0.9989 | 3.89% / 10.25% | 37.50, 29.81, 42.31, 34.62, 47.12, 28.12, 36.54, 48.96, 36.11, 20.59, 23.08, 22.12 |
| EXReader / PDF.js | 1200 | 1.0069 | 1.84% / 15.05% | 46.88, 48.08, 36.63, 46.94, 52.88, 40.38, 51.92, 67.57, 9.62, 62.50, 67.31, 38.46 |
| EXReader / PDF.js | 2400 | 0.9963 | 1.24% / 23.16% | 71.15, 43.14, 21.15, 24.04, 46.53, 11.46, 29.81, 76.92, 77.88, 56.73, 56.73, 49.04 |
