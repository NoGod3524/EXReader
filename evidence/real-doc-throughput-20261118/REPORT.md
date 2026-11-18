# PDF worst-page attribution

The slow pages are slides that paint large axial gradients, including a gradient inside a soft mask. The fixture generator put these slides at the start of all three large PDFs. The slow range follows the slides when they are extracted into a shorter document.

## Content and page position

Means per page at 1200 px for `real-mixed-120.pdf`. The render column uses the committed per-page p50s from `1693e2f56`. Image area is the sum of intrinsic image sizes or transformed image areas before clipping. Path paint and clip columns count PDF operators. The stream column counts decoded page `/Contents` bytes. [Per-page content inventory](page-content.json) · [Committed render baseline](baseline-real-mixed-120.json).

| Pages | Render (ms) | Stream (bytes) | Image draws | Source image pixels | Placed image area (pt²) | Path paints | Path clips | Axial shadings | Axial shadings in selected masks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1–21 | 583.958 | 3,361.95 | 2.19 | 2,113,050 | 456,053 | 3.33 | 22.00 | 1.05 | 1.00 |
| 81–120 | 3.272 | 1,008.05 | 0 | 0 | 0 | 5.55 | 3.90 | 0 | 0 |

The early cohort had 3.34× as many decoded stream bytes and took 178.44× as long. The image-heavy and vector-heavy fixtures each start with ten of the same slides. Each of those ten pages also selects a soft mask with an axial shading. [Fixture generator](../../tools/generate_real_doc_fixtures.py) · [Content inventory](page-content.json).

The same baseline DLL ran both arms of each position test. The runner alternated AB and BA in one session, starting a fresh process for each arm. For the standalone page and open probes, each arm rendered one page once and the table gives the median of five pairs. For the 21-page sweep, each arm ran two consecutive sweeps and the table gives the median of the three sweep means. The extracted pages have byte-identical decoded page streams. [Cold and extraction timings](cold-and-subset.json).

| Comparison | A (ms) | B (ms) |
| --- | ---: | ---: |
| Fresh render of page 1 vs page 81, full PDF | 409.273 | 3.129 |
| Fresh page 1 render, full PDF vs extract | 410.363 | 407.551 |
| Open, full PDF vs extract | 0.774 | 0.406 |
| First sweep of pages 1–21, full PDF vs extract | 526.948 | 533.598 |
| Second sweep of pages 1–21, full PDF vs extract | 588.070 | 581.459 |

## Page 1 and page 81 ablations

Both arms of each class comparison used copies of the same diagnostic DLL. They loaded in one process and alternated AB/BA on each render. Each case ran three repeats with one cold render and three warm renders per arm. The full row pools the four class controls. Each disabled row gives the p50 of its own full and disabled arms, plus the median of the individual paired savings. The idle gate required system CPU at or below 15% before each page batch. Observed readings were 6.64–12.50%. Path and glyph probes preserved clipping. The group probe covered the painter's paired begin and end callbacks. [Paired renders and scoped timings](page-ablation-paired.json).

### Page 1 at 1200 px

| Disabled class | Full warm p50 (ms) | Disabled warm p50 (ms) | Paired saving (ms) |
| --- | ---: | ---: | ---: |
| Full | 572.739 | — | — |
| Images | 552.494 | 440.470 | 108.851 |
| Paths | 581.331 | 568.545 | 7.727 |
| Text | 568.895 | 577.920 | −15.104 |
| Groups | 585.053 | 567.995 | 23.700 |

### Page 81 at 1200 px

| Disabled class | Full warm p50 (ms) | Disabled warm p50 (ms) | Paired saving (ms) |
| --- | ---: | ---: | ---: |
| Full | 2.158 | — | — |
| Images | 2.216 | 2.214 | −0.140 |
| Paths | 2.099 | 1.739 | 0.331 |
| Text | 2.273 | 1.815 | 0.455 |
| Groups | 2.108 | 2.380 | −0.107 |

Disabling the `sh` operator reduced page 1 from 570.476 to 139.052 ms, with a median paired saving of 432.115 ms. Page 81 went from 2.243 to 2.205 ms and issued zero shading samples. The page 1 ablation removed both gradient paints and changed the soft mask used in later compositing.

## First screen and the rendering hotspot

The committed **402.654 ms first screen** came from page 1's render (401.885 ms p50, with 0.797 ms to open). In the cold scoped pair closest to that baseline, the production and diagnostic renders took 410.992 and 422.783 ms. The diagnostic took **262.204 ms in two gradient paint calls** that evaluated **5,145,600 axial samples**. One gradient ran inside the graphics-state soft mask. The mask build took 178.198 ms including its gradient. Image callbacks took 121.332 ms including 17.044 ms of decoding. These scopes can overlap. [Committed component timings](baseline-real-mixed-120.json) · [Cold scoped pair](page-ablation-paired.json).

On the warm scoped renders, the two axial passes still used 372.569 ms at the median, with two decoded-image cache hits and 0.000 ms of image decoding. The retained cache has a default 64 MiB cap. Peak process RSS in the committed runs was 106.33 MiB for mixed, 145.54 MiB for image-heavy and 78.43 MiB for vector-heavy. [Image cache implementation](../../src/pdf_image.c) · [Warm scoped timings](page-ablation-paired.json).

## Change

The procedural axial sampler precomputes the normalized origin and direction when the shading coordinates determine the normalization scale. Outside that range it recomputes the projection with the original sample-dependent scale. Every sample uses the original positions, projection arithmetic, interpolation and work charge. The hot interpolation clamps use comparisons with the existing endpoints. [Sampler](../../src/pdf_shading.c).

## Paired production verification

A is the preserved DLL from the committed baseline. B is the Release DLL built with `cmake --build build/perf --parallel 6` after removing the diagnostic switches. Both loaded into one process, each with its own document. The runner alternated AB/BA on each page and reversed the starting order on alternate sweeps. It checked the 15% system CPU idle gate before each large sweep and each batch of five small-fixture sweeps. Observed prechecks ranged from 3.52% to 14.73%. Windows 11, Intel Core Ultra 7 256V, Balanced power plan, MinGW GCC 16.2.0. [Per-page samples, pair order, CPU readings and DLL hashes](final-paired.json).

Large-fixture timings use three timed sweeps after one pixel comparison sweep at 1200 px. Throughput uses the median sum of render-call times per sweep and excludes pixel comparison. The worst-page figure is the highest per-page p50 across the timed sweeps.

| Fixture | p50 A → B (ms) | p95 A → B (ms) | Worst page p50 A → B (ms) | Throughput A → B (pages/s) |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 8.775 → 8.573 | 594.293 → 474.677 | 614.599 (p2) → 491.914 (p2) | 8.98 → 10.96 |
| image-heavy-100 | 29.213 → 29.281 | 585.611 → 476.532 | 645.927 (p5) → 513.867 (p2) | 7.36 → 7.95 |
| vector-heavy-100 | 16.300 → 16.262 | 568.522 → 457.950 | 585.352 (p2) → 470.148 (p2) | 9.70 → 10.83 |

### Small-fixture timing guards

All four paired changes were within 3%. **Both builds exceeded all four absolute ceilings**, including the 3% allowance. The handoff references were recorded for main `453b1dcb3`. The preserved A/B baseline comes from `1693e2f56`. Each timing case used 15 measured sweeps after one warmup, with p50 calculated across the measured renders. [Per-page samples](final-paired.json).

| Fixture | A p50 (ms) | B p50 (ms) | Change | Handoff reference (ms) | Ceiling with +3% (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| pptx-20 @ 600 | 1.5077 | 1.5114 | +0.25% | 0.824 | 0.84872 |
| pptx-20 @ 1200 | 2.6619 | 2.6684 | +0.24% | 1.699 | 1.74997 |
| deck @ 1200 | 28.0290 | 28.0071 | −0.08% | 16.884 | 17.39052 |
| word-5 @ 1200 | 8.1259 | 8.1396 | +0.17% | 6.553 | 6.74959 |

### Pixel equivalence

The runner compared active RGBA bytes directly on every page at each listed width. All **111,897,000** small-fixture pixels and all **353,143,200** large-fixture pixels matched. [Per-page pixel counts](final-paired.json).

| Fixture | Widths (px) | Compared pixels | Different pixels |
| --- | --- | ---: | ---: |
| pptx-20 | 600, 1200, 2400 | 85,056,000 | 0 |
| deck | 600, 1200 | 15,192,000 | 0 |
| word-5 | 600, 1200 | 11,649,000 | 0 |
| real-mixed-120 | 1200 | 131,317,200 | 0 |
| image-heavy-100 | 1200 | 112,872,000 | 0 |
| vector-heavy-100 | 1200 | 108,954,000 | 0 |

CTest passed **577/577** in 76.40 seconds. [CTest summary](ctest.txt).
