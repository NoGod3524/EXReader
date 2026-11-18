# Dense vector pages: fill+stroke compounds scanned the whole canvas

**Conclusion.** On vector-heavy-100's 35 dense vector pages (p66–100) at 1200 px, **84%** of render time was spent in `exr_composite_compound`. That is the fill+stroke (`B*`) composite, and it scanned all 1,080,000 canvas pixels for each of the page's 25 star polygons. It now scans only the fill and stroke coverage bounds. Those pages are **77.9% faster** in a same-process paired A/B. Against PDF.js 3.11.174 the cohort ratio went from **8.21× to 1.99×** at 1200 px. At 600 px it went from 3.07× to **0.80×**, so we are now faster there. Output is byte-identical on all **465,040,200** compared pixels. CTest passed **577/577**.

The hundred-page p95 and throughput targets are **not** met. The remaining tail comes from the gradient + soft-mask slides and the image-heavy multi-image pages, which this change does not touch (see Acceptance).

## Attribution (instrument first)

I used a temporary diagnostic build (`-DEXR_DIAG_TIMERS`, since removed). It had QueryPerformanceCounter scopes around every stage of `path_impl` and `clip_path` in `src/canvas.c`. Its untimed speed matched the production build (122.7 vs 123.2 ms/page, alternating runs). Measurements: vector-heavy-100 p66–100 at 1200 px, 3 warm rounds after one cold round. Values are per page:

| Stage | Before (ms/page) | Calls/page | After (ms/page) |
| --- | ---: | ---: | ---: |
| **compound fill+stroke composite** (`B*`) | **105.131** | 25 | **4.498** |
| fill into canvas (60 strokes + background) | 9.891 | 61 | 8.253 |
| fill into coverage masks (incl. even-odd stars, clip) | 6.994 | 51 | 5.391 |
| non-rectangular clip (`W n`) | 2.730 | 2 | 1.929 |
| stroke outline | 0.493 | 85 | 0.256 |
| new_mask (recycle + clear) | 0.487 | 50 | 0.121 |
| edge build | 0.161 | 112 | 0.076 |
| stroke flatten | 0.159 | 85 | 0.118 |
| **dash generation** | **0.142** | 20 | 0.105 |
| fill flatten | 0.071 | 26 | 0.010 |
| path_impl total | 121.047 | 86 | 16.979 |
| render total | 125.90 | — | 20.07 |

The three suspects from #250 were checked against these numbers:

- **The non-rectangular clip sends us down a per-pixel coverage-mask path.** False as the cause. Building the clip costs 2.7 ms per page, and masked fills into the canvas cost 9.9 ms in total.
- **Dash patterns are recomputed per segment.** False. Dashing all 20 dashed curves costs 0.14 ms per page.
- **Even-odd polygons do a per-pixel winding test.** False as the cause. The 25 even-odd star fills plus their stroke masks cost about 7 ms. The real cost was the step after rasterisation. `B*` paints fill and stroke as one transparency element (ISO 32000-1 11.6.2), and `exr_composite_compound` (`src/blend.c`) walked every canvas row and column in double precision, about 4.2 ms per call. Each star covers about 17k pixels of the 1.08 MP page.

## Change

- `exr_clip_mask` (`src/canvas_internal.h`) now records dirty columns (`dirty_left`/`dirty_right`) next to its existing dirty rows. `mask_fill` (`src/canvas.c`) sets them from the path's x-extent with the same one-pixel margin it already used for rows. Row tracking, and therefore mask recycling, is unchanged.
- `path_impl` passes the union of the fill and stroke masks' bounds to `exr_composite_compound` and `exr_composite_compound_cmyk` (`src/blend.c`). These scan only that rectangle.
- **Why the output cannot change.** The loop already `continue`s, before any read-modify-write, on every pixel where both coverages are zero. Every pixel outside the bounds is such a pixel, so skipping it changes nothing.
- **Work budget.** It is charged for skipped rows too (`width × skipped rows`), so the work budget limit trips on the same totals as before.

## Results

### Same-process paired A/B (the attribution-grade measurement)

- **A**: `845ec19fe` (main after #250), DLL sha256 `7ed884c3adc00f83c4c9961011748b34aff3101aa9313cb6f3d2bece4724833f`.
- **B**: this branch, sha256 `03a7da8bdf38b20c71aee46425c42375cbe515d2a1acf408e6861032cd09b461`.
- Both are Release MinGW GCC 16.2.0 `build/perf` builds with #248's option set.
- Both DLLs ran in one process, alternating AB/BA on every page render. Each page took the median of N pairs. The idle gate (≤15% system CPU) was checked before timing. Readings were 3.9–11.6%. Data: [`interleaved/`](interleaved/).

| Fixture @ width | Pages | Pairs | Σ p50 A (ms) | Σ p50 B (ms) | Paired Δ |
| --- | --- | ---: | ---: | ---: | ---: |
| vector-heavy-100 @ 1200 | **p66–100 (dense vector)** | 7 | 3410.8 | 761.3 | **−77.85%** |
| vector-heavy-100 @ 1200 | p11–65 | 7 | 267.9 | 264.4 | −0.87% |
| vector-heavy-100 @ 1200 | p1–10 (gradient slides) | 7 | 1548.0 | 1548.7 | +0.62% |
| vector-heavy-100 @ 1200 | all 100 | 7 | 5226.7 | 2574.4 | −50.66% |
| real-mixed-120 @ 1200 | all 120 | 5 | 5189.9 | 5208.6 | −0.63% |
| image-heavy-100 @ 1200 | all 100 | 5 | 9817.4 | 9904.8 | +0.28% |
| pptx-20 @ 600 | all 20 | 41 | 17.77 | 17.57 | −0.34% |
| pptx-20 @ 1200 | all 20 | 41 | 32.87 | 32.89 | +0.34% |
| deck @ 1200 | all 15 | 21 | 272.84 | 271.88 | −0.16% |
| word-5 @ 1200 | all 5 | 41 | 32.80 | 33.05 | +0.43% |

The pages my change does not touch stay within ±1% paired.

### Fresh-process paired A/B (`tools/bench_real_doc.py --library-a/--library-b`)

Each child is a fresh process. The order alternated AB/BA/AB/BA over 4 repeats × 5 warm rounds. Data: [`paired/`](paired/).

| Fixture @ width | p50 A → B (ms) | p95 A → B (ms) | Throughput A → B (pages/s) | First screen A → B (ms) |
| --- | --- | --- | --- | --- |
| vector-heavy-100 @ 1200 | 15.08 → 18.49 | 193.9 → 207.0 | **15.39 → 30.63 (+99%)** | 160.4 → 163.7 |
| real-mixed-120 @ 1200 | 8.79 → 8.43 | 198.9 → 200.3 | 24.17 → 24.00 | 158.2 → 155.7 |
| image-heavy-100 @ 1200 | 20.12 → 20.90 | 198.6 → 213.4 | 12.93 → 12.79 | 164.1 → 159.2 |
| pptx-20 @ 600 | 0.817 → 0.819 | 1.200 → 1.156 | 1157.6 → 1146.7 | 2.181 → 2.190 |
| pptx-20 @ 1200 | 1.654 → 1.641 | 2.182 → 2.217 | 586.4 → 589.2 | 3.481 → 3.400 |
| deck @ 1200 | 16.74 → 16.92 | 18.19 → 18.20 | 59.17 → 58.95 | 84.1 → 85.4 |
| word-5 @ 1200 | 6.031 → 6.223 | 6.886 → 6.971 | 163.8 → 161.2 | 14.86 → 15.25 |

Two notes on reading this table:

- **The vector-heavy p50 rises even though no page got slower.** The 35 dense pages fell from about 120 ms to about 27 ms, which puts them in the middle of the per-sample distribution. Σ p50 fell 49.3%.
- **Untouched content moved by about 2–6% in this run** (for example vector-heavy p1–65 +5%). The same-process run above shows ±1% on the same pages, so that movement is session drift between processes, not code.

### Against PDF.js 3.11.174 (hundred-page, same harness and command as #250)

`tools/bench_large_vs_pdfjs.py` ran with 3 repeats per cell, alternating EXReader/PDF.js in fresh processes, with the 15% idle gate before every child. Data: [`vs-pdfjs/`](vs-pdfjs/).

| Fixture @ width | EXReader p50 / p95 (ms) | PDF.js p50 / p95 (ms) | EXReader tput (#250 → now) | PDF.js tput (now) |
| --- | --- | --- | --- | --- |
| vector-heavy-100 @ 1200 | 14.23 / 181.1 | 10.66 / 33.3 | 19.43 → **34.64** | 89.14 |
| vector-heavy-100 @ 600 | 6.01 / 37.5 | 7.34 / 26.7 | 70.32 → **139.03** | 124.41 |
| real-mixed-120 @ 1200 | 8.19 / 191.4 | 7.21 / 35.9 | 26.15 → 25.29 | 78.18 |
| real-mixed-120 @ 600 | 2.71 / 53.9 | 6.26 / 33.6 | 97.09 → 80.62 | 85.89 |
| image-heavy-100 @ 1200 | 23.15 / 232.2 | 17.64 / 34.2 | 13.84 → 11.05 | 53.38 |
| image-heavy-100 @ 600 | 10.28 / 77.1 | 14.86 / 29.6 | 41.89 → 33.18 | 64.77 |

This session ran slower than #250's for both renderers on content this change does not touch. PDF.js image-heavy @ 1200 fell from 63.46 to 53.38 pages/s. The real-mixed and image-heavy changes from #250 are therefore session-to-session drift; the same-process A/B above puts them at −0.6% and +0.3%.

Cohorts at 1200 px (Σ per-page warm p50; [`cohorts.py`](cohorts.py) reproduces #250's tables exactly from its `results.json`):

| Fixture @ 1200 | Cohort | Pages | EXReader Σ p50 (ms) | PDF.js Σ p50 (ms) | Ratio #250 → now |
| --- | --- | ---: | ---: | ---: | ---: |
| vector-heavy-100 | **dense vector p66–100** | 35 | 844.1 | 423.4 | **8.21× → 1.99×** |
| vector-heavy-100 | all non-slide pages | 90 | 1125.2 | 768.3 | **4.90× → 1.46×** |
| vector-heavy-100 | gradient + soft-mask slides | 10 | 1825.6 | 340.3 | 4.77× → 5.36× |
| image-heavy-100 | multi-image p71–100 | 30 | 6106.5 | 905.2 | 6.68× → 6.75× |
| image-heavy-100 | gradient + soft-mask slides | 10 | 2019.6 | 330.9 | 5.76× → 6.10× |
| real-mixed-120 | gradient + soft-mask slides | 21 | 3876.1 | 729.4 | 5.04× → 5.31× |

At 600 px, dense vector p66–100 is 236.6 vs 295.0 ms (**0.80×**) and vector-heavy's non-slide pages are 0.70×. All cells are in [`vs-pdfjs/cohorts.json`](vs-pdfjs/cohorts.json).

## Pixel equivalence

[`verify_pixels.py`](verify_pixels.py) loads A and B in one process. It renders every page at each width and compares the active RGBA bytes directly. Every fixture and width matched: 465,040,200 pixels compared, 0 different. [`pixels.json`](pixels.json).

| Fixture | Widths (px) | Compared pixels | Different pixels |
| --- | --- | ---: | ---: |
| pptx-20 | 600, 1200, 2400 | 85,056,000 | 0 |
| deck | 600, 1200 | 15,192,000 | 0 |
| word-5 | 600, 1200 | 11,649,000 | 0 |
| real-mixed-120 | 1200 | 131,317,200 | 0 |
| image-heavy-100 | 1200 | 112,872,000 | 0 |
| vector-heavy-100 | 1200 | 108,954,000 | 0 |

Small fixtures total **111,897,000** and hundred-page fixtures total **353,143,200**. The fresh-process paired runs also matched page hashes on every fixture.

CTest passed **577/577** in 84.13 s (Release, `EXR_BUILD_TESTS=ON`). [`ctest.txt`](ctest.txt).

## Acceptance

| Criterion | Result |
| --- | --- |
| At least one cohort ratio ≤2× | **Met.** Dense vector p66–100 @ 1200: 8.21× → 1.99×. Vector-heavy non-slide pages: 4.90× → 1.46×. |
| Hundred-page p95 ≤80 ms | **Not met.** Vector-heavy p95 is 181 ms. Its 10 gradient + soft-mask slides (~180 ms each) are the slowest 10% of pages, so they set p95. Real-mixed and image-heavy are unchanged. |
| Hundred-page throughput ≥40 pages/s | **Not met.** Vector-heavy rose from 19.43 to 34.64 pages/s (#250 → this session), and the fresh-process A/B doubled it (+99%). Real-mixed (25) and image-heavy (11) are unchanged. |
| Small fixtures no regression (±3%) | **Met on paired deltas.** pptx@600 −0.34%, pptx@1200 +0.34%, deck@1200 −0.16%, word-5@1200 +0.43% (same-process). Absolute values: pptx@600 0.819 ≤ 0.943 and pptx@1200 1.641 ≤ 2.118 pass. deck@1200 (16.92 ms) and word-5@1200 (6.22 ms) are just over the 16.4 / 6.2 figures, but baseline A is also over them in this session (16.74 / 6.03 fresh-process). |
| Deck first screen no regression | **No regression versus A**: 84.1 → 85.4 ms (+1.5%, fresh-process, within run spread). The 18.09 ms figure is from #251, which is not in this branch's base (`845ec19fe`) and uses a different first-screen definition. It was not re-measured here. |
| Pixels: 111,897,000 + 353,143,200, zero difference | **Met.** |
| CTest 577/577 | **Met.** |

## What is left

1. **Gradient + soft-mask slides.** These run 5.3–6.1× PDF.js's time on all three fixtures, and on vector-heavy they now set the p95 and worst page. The cost is in the axial shading itself (see #248).
2. **image-heavy p71–100.** These are still 6.75× PDF.js's time. Not investigated here. The decode-count test from the task brief (does every warm round re-decode?) is the next step.

## Reproduce

From the repository root, with A and B DLLs:

```
python -X utf8 evidence/dense-vector-throughput-20261118/verify_pixels.py A.dll B.dll pixels.json
python -X utf8 evidence/dense-vector-throughput-20261118/interleaved_ab.py A.dll B.dll tests/fixtures/pdf-large/vector-heavy-100.pdf 1200 1 100 7 out.json
python -X utf8 tools/bench_real_doc.py --library-a A.dll --library-b B.dll --input tests/fixtures/pdf-large/vector-heavy-100.pdf --expect-pages 100 --widths 1200 --runs 5 --repeat 4 --out out.json
python -X utf8 tools/bench_large_vs_pdfjs.py --library B.dll --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2 \
    --case real-mixed-120=tests/fixtures/pdf-large/real-mixed-120.pdf:120 \
    --case image-heavy-100=tests/fixtures/pdf-large/image-heavy-100.pdf:100 \
    --case vector-heavy-100=tests/fixtures/pdf-large/vector-heavy-100.pdf:100 \
    --widths 600 1200 --runs 5 --repeat 3 --out results.json
python -X utf8 evidence/dense-vector-throughput-20261118/cohorts.py results.json cohorts.json
```

Windows 11 (10.0.26200), Intel Core Ultra 7 256V, MinGW GCC 16.2.0 Release, Python 3.14.7, Node v24.19.0, `pdfjs-dist` 3.11.174 legacy build with `canvas` 3.2.3.
