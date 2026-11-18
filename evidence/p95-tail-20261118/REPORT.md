# 1200 px PDF p95 tail attribution

The 1200 px tail is primarily paint work on gradient-and-soft-mask slides. Those slides account for 15 of the 16 slowest ranked pages and 93.7% of their archived render time. Warm ablations put image draws first and shading second. The 120-page mixed fixture has zero warm image misses and zero evictions. The 100-page image-heavy fixture has an additional LRU capacity problem that materially slows some ranked pages.

## Archived page ranking

PR #250 reports EXReader versus PDF.js p95 of **185.9 vs 35.6 ms** for real-mixed, **180.7 vs 31.0 ms** for image-heavy and **154.1 vs 31.4 ms** for vector-heavy. Those are the median of three repeat-level p95s over pooled warm render samples. To identify consistently slow pages, the ranking takes the median of each page's three archived warm p50s and applies the nearest-rank p95 to those page values. The strict page cutoff produces the requested 6/5/5 pages. The final column gives the literal comparison against the exact, unrounded pooled p95 from the raw repeat files. [PR #250 report](../pdfjs-large-doc-20261118/REPORT.md) · [Ranked archive of all 320 pages](ranked-pages.json)

| Fixture | Pooled p95 (ms) | Page p95 (ms) | Strictly above page p95 | Tail Σ page p50 (ms) | Document Σ page p50 (ms) | Tail share | Page p50 strictly above pooled p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| real-mixed-120 | 185.9417 | 173.0093 | 6 | 1,090.86 | 4,506.12 | 24.21% | 12, 2 |
| image-heavy-100 | 180.6666 | 171.0727 | 5 | 908.85 | 7,245.67 | 12.54% | 5, 4 |
| vector-heavy-100 | 154.1424 | 153.6244 | 5 | 779.54 | 5,156.90 | 15.12% | 5, 2, 8, 7 |

An inclusive page-p95 cutoff also includes mixed p15 (173.01 ms, gradient + soft mask), image-heavy p71 (171.07 ms, synthetic multi-image) and vector-heavy p10 (153.62 ms, gradient + soft mask). Their ablations appear with the comparison pages below. Vector-heavy p9 equals the exact pooled cutoff.

Page numbers are one-based. Time shares use the sum of every archived page p50 in the same fixture as the denominator. Cohort labels use the recorded content operators and the synthetic page ranges in the fixture generator. [Page inventory](../real-doc-throughput-20261118/page-content.json) · [Original cohorts](../pdfjs-large-doc-20261118/cohorts.json) · [Fixture generator](../../tools/generate_real_doc_fixtures.py)

| Fixture | Rank | Page | Archived warm p50 (ms) | Cohort | Document share |
| --- | ---: | ---: | ---: | --- | ---: |
| real-mixed-120 | 1 | 12 | 195.44 | Gradient + soft mask | 4.34% |
| real-mixed-120 | 2 | 2 | 191.01 | Gradient + soft mask | 4.24% |
| real-mixed-120 | 3 | 11 | 177.06 | Gradient + soft mask | 3.93% |
| real-mixed-120 | 4 | 14 | 176.60 | Gradient + soft mask | 3.92% |
| real-mixed-120 | 5 | 16 | 176.22 | Gradient + soft mask | 3.91% |
| real-mixed-120 | 6 | 17 | 174.53 | Gradient + soft mask | 3.87% |
| image-heavy-100 | 1 | 5 | 199.31 | Gradient + soft mask | 2.75% |
| image-heavy-100 | 2 | 4 | 182.69 | Gradient + soft mask | 2.52% |
| image-heavy-100 | 3 | 2 | 178.13 | Gradient + soft mask | 2.46% |
| image-heavy-100 | 4 | 86 | 174.63 | Synthetic multi-image | 2.41% |
| image-heavy-100 | 5 | 7 | 174.09 | Gradient + soft mask | 2.40% |
| vector-heavy-100 | 1 | 5 | 157.34 | Gradient + soft mask | 3.05% |
| vector-heavy-100 | 2 | 2 | 156.69 | Gradient + soft mask | 3.04% |
| vector-heavy-100 | 3 | 8 | 156.37 | Gradient + soft mask | 3.03% |
| vector-heavy-100 | 4 | 7 | 155.00 | Gradient + soft mask | 3.01% |
| vector-heavy-100 | 5 | 9 | 154.14 | Gradient + soft mask | 2.99% |

| Fixture | Cohort | Pages | Document Σ page p50 (ms) | Document share | Tail pages | Tail Σ page p50 (ms) | Tail portion of document | Samples above their repeat's pooled p95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 | Gradient + soft mask | 21 | 3,624.2 | 80.43% | 6 | 1,090.9 | 24.21% | 90 |
| real-mixed-120 | Image, no gradient | 55 | 772.3 | 17.14% | 0 | 0.0 | 0.00% | 0 |
| real-mixed-120 | Other | 44 | 109.6 | 2.43% | 0 | 0.0 | 0.00% | 0 |
| image-heavy-100 | Gradient + soft mask | 10 | 1,680.4 | 23.19% | 4 | 734.2 | 10.13% | 45 |
| image-heavy-100 | Synthetic multi-image | 30 | 4,749.5 | 65.55% | 1 | 174.6 | 2.41% | 30 |
| image-heavy-100 | Other image | 60 | 815.8 | 11.26% | 0 | 0.0 | 0.00% | 0 |
| vector-heavy-100 | Gradient + soft mask | 10 | 1,542.9 | 29.92% | 5 | 779.5 | 15.12% | 74 |
| vector-heavy-100 | Synthetic dense vector | 35 | 3,356.1 | 65.08% | 0 | 0.0 | 0.00% | 1 |
| vector-heavy-100 | Other | 55 | 257.9 | 5.00% | 0 | 0.0 | 0.00% | 0 |

Across the three fixtures, gradients with soft masks account for **15/16 ranked tail pages and 2,604.63 of 2,779.25 ms (93.72%)** of their summed page p50. The remaining 174.63 ms (6.28%) comes from image-heavy p86. The raw sample view also captures variation across repeats. Image-heavy's multi-image cohort produced 30 of its 75 samples above the corresponding repeat's pooled threshold. The synthetic image and vector cohorts each account for about 65% of their fixture's summed page times, which makes them throughput priorities even though the ranked p95 tail is dominated by slides.

## Per-page ablations

The probe uses the same MinGW Release objects as the archived DLL (SHA-256 `193972af80e40986ae6d9c21332e6f91dcdc62cb6cb541b3e2aba3a978c1a452`). GNU linker wrapping attaches a diagnostic consumer and reads existing image-cache counters. Every timed call enters through `exr_fixed_render`. The probe reuses the benchmark's ctypes definitions, viewport scaling, pixel hash and fail-closed 15% CPU idle gate. One full warm-up per target primes that page's image keys. Seven rounds run the full and six disabled modes in seeded shuffled order on the same document. The ablation columns report the median of the seven within-round full-minus-disabled differences in milliseconds. [Capture harness](capture.py) · [Linker shim](probe.c)

| Disabled | Diagnostic scope |
| --- | --- |
| Images | Skip image events before decode, including any image-owned mask and resampling. |
| Paths | Drop path fill and stroke, preserve their clip events. |
| Text | Suppress glyph painting, preserve text clips and upstream text interpretation. |
| Groups | Bypass canvas sink group and layer boundaries while drawing the group's children. The soft-mask rasterizer's direct root setup is retained. |
| Shading | Bypass shading dispatch, including `sh` inside graphics-state soft masks. |
| Clip | Bypass content clip callbacks and keep the fixed viewport and mask-form raster boundaries. |

Each ablation can change the amount of work done by subsequent operators. Shading can change the mask supplied to image/path compositing, and removing a clip can increase the painted area. The columns are individual interventions and overlap. Small signed differences near the within-page spread have limited diagnostic value.

| Fixture | Page | Diagnostic full p50 (ms) | Images Δ ms | Paths Δ ms | Text Δ ms | Groups Δ ms | Shading Δ ms | Clip Δ ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 | 12 | 179.9 | +128.5 | +2.7 | +3.2 | -5.6 | +45.8 | -14.5 |
| real-mixed-120 | 2 | 196.4 | +142.0 | -7.4 | -14.9 | -9.4 | +47.2 | -14.1 |
| real-mixed-120 | 11 | 168.5 | +110.4 | -7.8 | +4.6 | -3.6 | +51.8 | -15.6 |
| real-mixed-120 | 14 | 189.1 | +133.5 | +4.3 | +8.5 | -1.8 | +54.2 | -19.3 |
| real-mixed-120 | 16 | 164.1 | +109.7 | +1.7 | -0.1 | -8.9 | +48.0 | -18.3 |
| real-mixed-120 | 17 | 191.9 | +131.5 | -0.1 | -3.1 | -6.8 | +49.1 | -12.1 |
| image-heavy-100 | 5 | 157.0 | +111.7 | -0.3 | +0.3 | -5.9 | +45.5 | -11.4 |
| image-heavy-100 | 4 | 169.7 | +119.1 | -0.1 | +1.9 | -7.8 | +44.5 | -16.8 |
| image-heavy-100 | 2 | 175.2 | +130.4 | +1.0 | +1.7 | -2.1 | +43.8 | -10.2 |
| image-heavy-100 | 86 | 144.2 | +142.2 | +3.3 | +0.0 | +3.8 | -2.7 | +0.5 |
| image-heavy-100 | 7 | 179.5 | +134.4 | +2.1 | +4.3 | -9.0 | +42.1 | -12.4 |
| vector-heavy-100 | 5 | 149.1 | +101.4 | +0.2 | +3.6 | -1.4 | +43.0 | -11.8 |
| vector-heavy-100 | 2 | 168.8 | +110.2 | +0.2 | +9.7 | -5.3 | +45.2 | -72.5 |
| vector-heavy-100 | 8 | 150.3 | +99.8 | +0.6 | +4.5 | -6.1 | +41.0 | -12.2 |
| vector-heavy-100 | 7 | 147.1 | +99.2 | -0.4 | +2.8 | -4.3 | +40.5 | -11.7 |
| vector-heavy-100 | 9 | 158.4 | +104.4 | +2.5 | +5.0 | -0.8 | +44.2 | -10.4 |


The comparison pages include the three cutoff boundary pages, duplicate slides and samples from the synthetic throughput cohorts.

| Fixture | Page | Diagnostic full p50 (ms) | Images Δ ms | Paths Δ ms | Text Δ ms | Groups Δ ms | Shading Δ ms | Clip Δ ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 | 1 | 147.5 | +102.2 | +1.1 | +2.9 | -0.3 | +45.3 | -11.3 |
| real-mixed-120 | 5 | 187.8 | +129.6 | +4.6 | +18.1 | +5.5 | +54.3 | -8.2 |
| real-mixed-120 | 10 | 208.7 | +123.4 | -3.1 | +7.7 | -2.2 | +56.6 | -13.4 |
| real-mixed-120 | 15 | 149.7 | +102.1 | -0.9 | +2.9 | -3.8 | +43.7 | -8.8 |
| image-heavy-100 | 1 | 147.0 | +101.9 | +1.3 | +0.9 | -2.8 | +42.5 | -8.1 |
| image-heavy-100 | 10 | 199.2 | +142.0 | +1.4 | -0.2 | -5.7 | +49.3 | -12.1 |
| image-heavy-100 | 71 | 150.1 | +147.6 | +4.9 | +0.8 | +2.6 | +1.3 | +1.3 |
| image-heavy-100 | 90 | 144.5 | +142.3 | +0.3 | +1.0 | +0.8 | -1.2 | -1.2 |
| image-heavy-100 | 100 | 147.0 | +144.6 | +1.2 | -1.2 | +1.0 | -0.1 | +0.4 |
| vector-heavy-100 | 1 | 150.2 | +100.0 | +2.0 | +3.5 | -5.0 | +43.1 | -8.4 |
| vector-heavy-100 | 10 | 150.6 | +102.4 | +1.5 | +4.1 | -1.0 | +46.7 | -10.0 |
| vector-heavy-100 | 66 | 93.0 | -0.2 | +88.5 | -2.5 | +1.3 | -0.6 | +26.6 |
| vector-heavy-100 | 90 | 93.2 | -1.1 | +89.9 | +0.0 | +0.9 | -1.0 | +26.1 |
| vector-heavy-100 | 100 | 92.0 | +0.1 | +88.9 | -1.6 | +0.0 | -1.8 | +25.5 |

Positive deltas are savings. For the 15 ranked gradient slides, image removal saves **99.2–142.0 ms** (median **111.7 ms**, or **68.5%** of diagnostic full p50). Shading removal saves **40.5–54.2 ms** (median **45.2 ms**, or **27.3%**). Ratios use the median of the per-page percentages. The image draw path is the largest measured intervention on every one of these slides. The shading intervention also removes the shading used to generate the graphics-state mask and can affect later image compositing. The clip intervention makes all 15 slides slower, consistent with expanding the domains of other paint operations. Group, path and glyph ablations yield much smaller effects on the ranked slides. [Mixed ablations](real-mixed-120-ablation.json) · [Image-heavy ablations](image-heavy-100-ablation.json) · [Vector-heavy ablations](vector-heavy-100-ablation.json)

On synthetic image p86, the same-page warm image ablation saves **142.2 of 144.2 ms**. Image-heavy p71, p90 and p100 show the same pattern. The p86 clip intervention is near zero in this experiment. On dense-vector p66, p90 and p100, path removal saves **88.5–89.9 ms** and clip removal saves **25.5–26.6 ms**. Both affect the clipped path paint and their savings overlap. These dense-vector pages contribute strongly to total render time and sit below the ranked cut. [Synthetic fixture generation](../../tools/generate_real_doc_fixtures.py) · [Per-mode raw samples](vector-heavy-100-ablation.json)

## Whole-document cache trace

The counter pass walks the original page order with a single open document, one cold sweep and five warm sweeps, matching PR #250's access sequence. It records cache events and scoped decode/mask-build time at page boundaries. The published p95 values come entirely from the archive. Every page in the first sweep was checked against its archived full-output RGBA hash. The image cache has a 64 MiB byte limit and 128-entry limit. Hits, misses and LRU evictions are deltas of the renderer's counters. Image-owned alpha masks belong to their decoded textures. Graphics-state soft masks are tracked separately. [Image cache policy](../../src/pdf_image.c) · [Counter capture](capture.py)

### Mixed 120-page trace

| Sweep | Image hits | Image misses | Image evictions | Decode (ms) | Font-stream hits | Font-stream misses | Font-stream evictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 322 | 19 | 0 | 159.15 | 304 | 27 | 0 |
| Warm 1–5, each | 341 | 0 | 0 | 0.00 | 331 | 0 | 0 |
| Cold + five warm | 2,027 | 19 | 0 | 159.15 | 1,959 | 27 | 0 |

Cold image misses were confined to p1–3, p7, p12, p17, p22–23 and p52. Occupancy reached **19 entries / 35.24 MiB** at p52 and stayed there. Even warm p12 and p2, the two pages whose p50 exceeds the published pooled threshold, incurred zero image misses and evictions in every sweep. Font-stream occupancy reached **27 streams / 1.98 MiB** against a 16 MiB retention budget. The probe saw **247 font object opens and 247 paint-face opens per sweep**. These short-lived objects are scoped to the content reader and painter and are rebuilt when the render runs again. The decoded font streams are retained across page renders. [Mixed page-by-page counters](real-mixed-120-cache-64mib.json.gz) · [Font-stream retention](../../src/pdf_objects.c) · [Reader and paint-face lifetimes](../../src/pdf_content.c)

| Mixed probe, per 120-page sweep | Count | Lifetime |
| --- | ---: | --- |
| Clip callbacks | 3,326 | Content and direct viewport/mask-form boundary clips. |
| Clip callbacks creating a new coverage buffer | 172 | Within a canvas. |
| Clip callbacks reusing a spare buffer | 1,330 | The retrieved buffer is cleared and the coverage rasterized again. |
| Clip callbacks with no new buffer | 1,824 | Includes fast returns and in-place accumulation. |
| Graphics-state soft-mask builds | 21 | One on every page p1–21 on every sweep. |

The clip spare list is canvas-local and is released at canvas destruction. Cross-page coverage hits and capacity evictions are zero by design. A graphics-state soft mask is built on demand and released after the corresponding paint. It has zero rendered-mask cache hits and capacity evictions, with 21 uncached builds per sweep and a median of **640.51 ms** spent building masks per warm sweep. That scope includes the mask-form rendering and gives a sense of scale for the repeated work. There was no periodic rebuild of a document-level cache in the 120-page trace. The short lifecycle is per paint for the soft mask and per canvas or content walk for clip buffers and font objects. [Clip buffer lifecycle](../../src/canvas.c) · [Soft-mask build and release](../../src/pdf_paint.c) · [Mixed sweep trace](real-mixed-120-cache-64mib.json.gz)


### Image-heavy and vector-heavy cache contrast

| Fixture / image budget | Sweep | Image hits | Image misses | Image evictions | Decode time (ms) | Peak resident cache |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| image-heavy / 64 MiB | Cold | 308 | 110 | 63 | 723.09 | 63.92 MiB, up to 49 entries |
| image-heavy / 64 MiB | Warm 1–5, each | 308 | 110 | 110 | 731.12 median | 64.00 MiB, up to 49 entries |
| image-heavy / 64 MiB | Cold + five warm | 1,848 | 660 | 613 | 4,404.69 | 64.00 MiB, up to 49 entries |
| vector-heavy / 64 MiB | Cold | 17 | 3 | 0 | 24.80 | 8.69 MiB, 3 entries |
| vector-heavy / 64 MiB | Warm 1–5, each | 20 | 0 | 0 | 0.00 | 8.69 MiB, 3 entries |
| vector-heavy / 64 MiB | Cold + five warm | 117 | 3 | 0 | 24.80 | 8.69 MiB, 3 entries |

Image-heavy first evicts at p77 in the cold sweep. Repeated scans evict again at the start of the next sweep and through most of p71–100. Every synthetic page p71–100 misses all three image lookups on each warm sweep. Those 90 misses take a median **556.78 ms** per warm sweep, about **11.7%** of that cohort's archived 4,749.5 ms summed p50. Measured warm decode across all 100 pages is about **10.1%** of the archived document total. These percentages compare scoped time to archived page totals for scale. The 49-entry peak and nearly full byte occupancy identify byte pressure. The three fixtures recorded zero image bypasses. [64 MiB image-heavy counters](image-heavy-100-cache-64mib.json.gz) · [Vector-heavy counters](vector-heavy-100-cache-64mib.json.gz)

For image-heavy tail p86, decode uses **22.75 ms** per warm visit (median of five). Each visit misses three images and evicts two entries. Decode is about **13%** of its archived 174.63 ms p50. The isolated warm image ablation still saves **142.2 ms** after priming that page's image keys. The raster/composite work keeps the page expensive with the images resident.

Image-heavy deliberately repeats the same slides five pages later. Each pair below has identical output pixels. The first copy takes longer in each of the three archived repeats. The cache trace shows an early miss followed by a hit on the duplicate. The archived p5–p10 gap is **38.05 ms** and the median p5 decode is **40.48 ms**, which implicates eviction in that within-cohort spread. The isolated ablation controls prime each page first and are sensitive to host timing variation, including a reversal for p5/p10. The cache-state comparison uses the sequential traces and archived page times. [Archived per-page repeats and hashes](ranked-pages.json) · [Image-heavy trace](image-heavy-100-cache-64mib.json.gz)

| Identical pages | Archived p50s (ms) | Gap (ms) | Warm image misses | Warm decode median (ms) |
| --- | --- | ---: | --- | --- |
| p1 / p6 | 164.66 / 149.13 | 15.53 | 2 / 0 | 18.64 / 0.00 |
| p2 / p7 | 178.13 / 174.09 | 4.03 | 1 / 0 | 6.72 / 0.00 |
| p4 / p9 | 182.69 / 164.92 | 17.77 | 3 / 0 | 15.44 / 0.00 |
| p5 / p10 | 199.31 / 161.26 | 38.05 | 1 / 0 | 40.48 / 0.00 |

For comparison, mixed p14 and vector-heavy p7 also hash identically. Their archived p50s are 176.60 and 155.00 ms, with no warm image decode on either page. Timing spread can persist with resident image entries. The font-stream caches also show zero evictions in both 100-page fixtures, with 15 cold misses and 196 hits per warm sweep for image-heavy, and 18 cold misses and 115 hits per warm sweep for vector-heavy. Each of those fixtures builds 10 graphics-state masks per sweep, on p1–10. [Archived ranks](ranked-pages.json) · [Vector-heavy trace](vector-heavy-100-cache-64mib.json.gz)
### Capacity and priority

| Image-heavy budget | Cold evictions | First warm hits | First warm misses | First warm evictions | First warm decode (ms) | Peak bytes / entries |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 64 MiB | 63 | 308 | 110 | 110 | 731.12 | 67,103,268 / 49 |
| 128 MiB | 13 | 308 | 110 | 110 | 741.76 | 134,090,752 / 97 |
| 162 MiB | 0 | 418 | 0 | 0 | 0.00 | 169,378,688 / 110 |
| 192 MiB | 0 | 418 | 0 | 0 | 0.00 | 169,378,688 / 110 |

The 192 MiB pass measured a full resident set of **169,378,688 bytes (161.53 MiB) across 110 entries**. Setting the existing byte override to **162 MiB (169,869,312 bytes)** held the same set and eliminated warm re-decode, within the existing 128-entry limit. With 128 MiB, 13 cold evictions start a cascade. The repeated sequential access order drives all 110 first-touch keys to miss again despite the higher occupancy. The 64 MiB default already fits the mixed and vector fixtures. For repeated scans of a document with the image-heavy fixture's reuse pattern and available memory, 162 MiB is the smallest whole-MiB cap that fits this measured set. It raises peak image-cache occupancy by about 97.5 MiB over the 64 MiB run. A memory-constrained alternative worth testing is retaining frequently reused early-page textures ahead of scan-only admissions. The cap trials report counters and scoped decode, so the estimate of avoided decode is about 0.73 s per warm image-heavy sweep. [128 MiB trace](image-heavy-100-cache-128mib.json.gz) · [162 MiB trace](image-heavy-100-cache-162mib.json.gz) · [192 MiB trace](image-heavy-100-cache-192mib.json.gz)

For the p95 gap, prioritize warm image paint and the shading/mask path on the slides. The image-heavy ranked pages spend a combined **85.38 ms** in median warm decode against **908.85 ms** of archived page time, about **9.4%**. Cache pressure explains some page-to-page spread and can affect which image-heavy pages cross the cut. Mixed and vector-heavy incur zero warm decode across their ranked pages. For total throughput, prioritize synthetic image resampling/compositing and clipped path painting in their respective fixtures. The ablations measure EXReader's own render cost. Assigning component shares of the EXReader–PDF.js gap would require the corresponding PDF.js interventions.

## Reproduce

The captures ran on Windows 11 build 26200, Intel Core Ultra 7 256V and MinGW GCC 16.2.0. Use a configured MinGW/Ninja Release build matching PR #250. The original `EXReader-pdfjs-large/build/perf` objects were already available here, so the shim relink reused those files. To build equivalent objects in a configured worktree, use `cmake --build build/perf --parallel 6`. Run these commands from the repository root.

```powershell
$probe = 'evidence/p95-tail-20261118/capture.py'
$dll = 'build/perf/tail-probe.dll'
python -X utf8 $probe --mode rank
python -X utf8 $probe --mode ablate --build build/perf
python -X utf8 $probe --mode ablate --dll $dll --case real-mixed-120 --page 15 --out build/perf/boundary
python -X utf8 $probe --mode cache --dll $dll
foreach ($cap in 128, 162, 192) {
    python -X utf8 $probe --mode cache --dll $dll --case image-heavy-100 --cache-mib $cap --rounds 2
}
```

The boundary probe's p15 row is included in the mixed ablation JSON. Cache traces are gzip-compressed JSON containing cumulative image counters, page-local counters and the initial CPU gate reading for each document. Difference adjacent image counters across page and sweep boundaries to recover events for individual pages. Full-output controls use the archived page hashes. The reports and probe are contained in this evidence directory, and the production render source and build configuration are unchanged.
