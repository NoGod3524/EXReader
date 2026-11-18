# Width-1200 throughput attribution — 2026-11-18

**The crossover is explained by EXReader's larger resolution-sensitive paint cost. It does not require a superlinear whole-document cliff.** The unchanged #257 DLL reproduced warm-sweep growth of real-mixed-120 **2.601×**, image-heavy-100 **3.169×**, vector-heavy-100 **2.860×**. In #257, PDF.js's corresponding growth was much smaller, as the archived table below shows. Winning at 600 px therefore does not rule out a costly pixel-processing algorithm: that cost can overtake the other renderer when the output area increases.

**Measured causes:** RGB image painting dominates image-heavy's extra time; mixed adds substantial image and gradient/soft-mask work; vector-heavy adds clipped-path work as well as the shared gradient slides. In the image-heavy instrumented sweeps, the RGB image sink accounts for **2233.772 / 2702.278 ms (82.66%)** of the width increment. Measured allocation intervals do not show comparable growth. The decoded-image cache has exactly the same warm hit/miss/eviction counts at both widths.

**Unresolved physical split:** the paint intervals contain both computation and memory traffic. DRAM-bandwidth milliseconds, CPU-cache-miss cost, and their split from arithmetic were not measured. They are not assigned fabricated shares of the residual. [Available PMU sources](pmc-sources.txt) and [the current process token's privileges](token-privileges.txt) are retained; the token has no `SeSystemProfilePrivilege`. There are no hardware-counter samples in this evidence.

## Check the original crossover and denominator

This table is **archived #257 data**, not a fresh PDF.js comparison. [Exact archive](../p95-then-throughput-20261118/results.json) · [Original method](../p95-then-throughput-20261118/REPORT.md).

| Fixture | Pages on both sides/widths | EXReader 600 ms | EXReader 1200 ms | EXReader growth | PDF.js 600 ms | PDF.js 1200 ms | PDF.js growth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 120 | 616.82 | 1663.09 | 2.696× | 1092.50 | 1445.18 | 1.323× |
| image-heavy-100 | 100 | 1246.38 | 3944.51 | 3.165× | 1276.22 | 1608.62 | 1.260× |
| vector-heavy-100 | 100 | 525.77 | 1436.36 | 2.732× | 704.89 | 1016.45 | 1.442× |

Both sides rendered the same **120 / 100 / 100** pages at both widths. Throughput is `N × 1000 / median(sum of timed page-render ms in each warm sweep)`. The validation reconstructs that denominator from every saved per-page sample, checks page IDs and sample counts, and checks the reported pages/s. Open time, hashing and output-bitmap freeing are outside that sum. The throughput ratio convention in #257 is **PDF.js pages/s / EXReader pages/s**; above one means EXReader is slower.

The new original-DLL results below confirm the resolution response on the same renderer binary. They are not combined with archived PDF.js samples to claim a new same-session engine comparison.

## Where the extra time goes

These are differences of **mean instrumented warm sweeps**, over three fresh children × five warm sweeps each. They are separate from the original-DLL throughput medians.

| Fixture | Total extra ms | RGB image sink extra ms | Mask building extra ms | Source paint outside masks extra ms | Other incl. canvas creation extra ms |
| --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 1147.129 | 461.924 | 246.437 | 77.256 | 361.512 |
| image-heavy-100 | 2702.278 | 2233.772 | 116.391 | 37.859 | 314.256 |
| vector-heavy-100 | 959.221 | 156.391 | 114.283 | 36.271 | 652.275 |

The RGB image sink, mask construction, source painting outside masks and canvas creation outside masks are separate scopes. The probe suppresses child paint/create buckets during a mask build; every telemetry page has at most one mask build. `other_ms` is the timed-render residual after those scopes, and contains path/glyph/clip work, interpretation, decoding and remaining setup/probe work. It is not a bandwidth estimate.

Allocator and decode timers overlap the scopes above and must **not** be added as extra rows of that partition:

- real-mixed-120: allocator interval Δ **-0.152 ms**, decode Δ **+0.000 ms**
- image-heavy-100: allocator interval Δ **+2.288 ms**, decode Δ **+9.003 ms**
- vector-heavy-100: allocator interval Δ **-7.618 ms**, decode Δ **+0.000 ms**

Allocator intervals include the intercepted malloc/calloc/realloc/free calls and their timer/counter overhead. Counts cover link-visible calls from EXReader and linked static dependencies; CRT/DLL-internal calls are outside that scope. Output-bitmap freeing is outside the timed render and excluded from these metrics. The per-page table below gives the actual call counts and requested bytes.

## Decoded-image cache intervention

At 64 MiB, mixed records **341 hits / 0 misses / 0 evictions** per warm sweep at each width; vector records **20 / 0 / 0**. Image-heavy records **308 / 110 / 110** at **both** widths. Thus the measured 600→1200 increment is not accompanied by any extra decoded-image eviction events. This is distinct from CPU hardware-cache behavior, which was not measured.

For image-heavy, the existing byte-limit override was changed between **64 and 256 MiB**, with 64/256, 256/64, 64/256 process order at each width. The width-pair order also reverses on the middle repeat. The 128-entry limit stays unchanged. At 256 MiB the sequential warm traces have **418 hits / 0 misses / 0 evictions** at 600 and **418 / 0 / 0** at 1200. The resident decoded set is **161.532 MiB** at 600 and **161.532 MiB** at 1200. Decoded textures are loaded in source resolution, before the placement transform in [image_event](../../src/pdf_paint.c); output width does not quadruple their cached bytes.

Observed paired warm-sweep savings are **175.304 ms at 600** and **195.369 ms at 1200**. The three signed pair differences are **+167.297 / +289.971 / +175.304 ms** and **+195.369 / +67.324 / +266.243 ms**, respectively. Median paired differences need not equal the difference of separately reported medians. The larger cache removes scan re-decode at both widths, while the measured 256 MiB native sweep still grows **3.440×** with width. Cache capacity is an independent image-heavy cost; the counters do not support a resolution-triggered image-cache eviction cliff. Peak RSS for this intervention is included in its table.

## Memory interpretation and the 4× criterion

The RSS table decomposes Windows peak-working-set growth arithmetically into process start, opening, the cold-sweep peak, and any later warm peak. It uses means of three original-DLL processes so the components sum to the mean final peak. It does not relabel all working-set growth as live bitmap bytes.

The measured maximum retained PDF scratch-pool payload is **7.467 → 29.869 MiB**; the fixed-render pool is **3.582 → 14.319 MiB**. These observed page-boundary maxima are the same across the three fixtures. Their individual limits are 64 MiB, and neither observed retained maximum reaches its limit. They are separate from the decoded-image cache, whose byte occupancy is width-independent here. Pool maxima need not coincide with a Windows RSS peak and are not additive RSS components.

Full sweeps grow below 4×. Image-sink intervals grow below 4×; direct gradient/mask intervals are close to 4× and sometimes slightly above it. Canvas creation grows more than 4× but contributes only the small absolute increment shown in the timer tables. A ratio slightly over four, or a ratio of two noisy ablation differences, does not establish a cache-threshold mechanism. The nominal 4× comparison also differs slightly from the exact output-pixel ratio because bitmap heights are rounded; the active-pixel counts are reported below.

Class ablations are interventions, not additive standalone class CPU times. Each saving is the median of three within-repeat differences: full-child median warm sweep minus disabled-child median warm sweep. It need not equal the difference between the two displayed median-time columns. Their tables retain these signed differences. Negative group deltas are observed intervention results. Bypassing boundaries retains children but changes the conditions under which they are composited; these deltas are not pure group overhead. Small or negative path/glyph effects in some fixtures should be read with their three raw paired deltas in [summary.json](summary.json), rather than turned into a fixed/linear classification from the median ratio alone.

## Recommendations, not implemented

1. Profile sampling versus blending in `exr_vector_texture_blend` for image-heavy and mixed; separate coverage generation from blending in the clipped-path rasterizer for the vector cohort. The native cohort table and image/path ablations identify these independently of image-cache misses.
2. Profile the gradient/soft-mask pixel loops next. Their measured resolution scaling is near area scaling. The next experiment should distinguish arithmetic from memory stalls with hardware counters before choosing a bandwidth-specific rewrite. Canvas initialization is a smaller measured target.
3. Treat a larger or scan-aware decoded-image cache as a separate image-heavy tradeoff. The paired capacity trial measures its benefit and memory cost; it does not remove the resolution-sensitive paint work. The current traces do not justify an allocator-focused rewrite as the cause of this width crossover.

## Capture and validation

- Source snapshot: `d234e41a46b3f8986daef55d3c112d32325558eb` (#257 merge). Original DLL SHA-256: `2640521cb124a7533c808429391a93bfa8d4db75443f79cd92f765c158f2c5ee`, exactly #257's DLL. The existing Release MinGW `-O3 -DNDEBUG` objects were reused; all **214** source/header files matched this worktree. [Build cache](CMakeCache.txt) · [Provenance](provenance.json).
- No `src/`, `include/`, CMake or existing benchmark-tool edits. [probe.c](probe.c) relinks the existing objects with GNU linker wrapping, reusing [#252's probe](../p95-tail-20261118/probe.c). Its constructor honors `EXR_ATTRIBUTION_SKIP=path|glyph|image|shading|group`.
- [capture.py](capture.py) calls unchanged `bench_real_doc.run_child_gated` for full-document throughput and unchanged `bench_firstscreen.run_child` for fresh first-page controls. It reuses #252's document bindings for sequential telemetry. Each capture is a fresh process. Throughput and telemetry captures have one cold full sweep plus five warm full sweeps, three repeats. First-page controls open once and render page 1 once. The initial probe sanity capture uses one warm sweep. Class order rotates; width orders are **600/1200, 1200/600, 600/1200**.
- Path ablation preserves clips; glyph ablation preserves text clipping; image ablation skips before decode; shading ablation bypasses dispatch including graphics-state-mask shading; group ablation bypasses sink layer/group boundaries while retaining children and rasterizer root setup.
- Every accepted child passed the fail-closed **≤15%** pre-child system-CPU gate plus competing-benchmark checks before and after capture. **186 accepted children**, gate range **2.73–14.90%**. All repeats, including wide timing outliers, remain in the accepted data.
- Two initial mixed baseline samples taken before the competing-process check was added were excluded. A new external benchmark appeared during the last 256 MiB trace; its post-child check rejected that sample, and the preceding 600 px partner was withdrawn so the pair could be repeated together. [Excluded records](excluded-overlap/) · [Wait/process log](competition.jsonl). Excluded samples do not contribute to any table.
- [analyze.py](analyze.py) verifies counts, alternating width order, cache A/B order, throughput denominators and pixel hashes. It performed **8,218 matching page-hash comparisons** across original/full-probe/telemetry/cache/first-page controls. The six full-render fixture/width cells cover **640 distinct page/width combinations**. Class-disabled output is intentionally different. [Validated summary](summary.json).

## Reproduce

Use a matching configured MinGW Release build, target `exreader`. To avoid resuming the saved captures, copy `capture.py`, `probe.c`, `run_all.py`, `analyze.py`, `tables.py`, and `report.py` into a **new directory directly under `evidence/`**. Then run, substituting that directory for `evidence/width1200-retest`:

```powershell
python -X utf8 evidence/width1200-retest/capture.py build --build build/perf
python -X utf8 evidence/width1200-retest/run_all.py --library build/perf/libexreader.dll
python -X utf8 evidence/width1200-retest/analyze.py
python -X utf8 evidence/width1200-retest/report.py
```

The capture runner checkpoints accepted children and fails closed on CPU timeout or a competing workload. Run it again to resume only unaccepted samples. If interference splits a width pair, withdraw its accepted partner and repeat both members together, as done here. Raw child files, indices and their hashes are retained alongside the summary; compressed JSON can be loaded by `analyze.py`.

## Original-DLL throughput

| Fixture | Width | Pages | Active pixels/round | Warm round median (ms) | Three repeat medians (ms) | Pages/s |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 120 | 32,859,000 | 652.166 | 612.918 / 658.756 / 652.166 | 184.00 |
| real-mixed-120 | 1200 | 120 | 131,317,200 | 1696.526 | 1681.380 / 1696.526 / 1719.088 | 70.73 |
| image-heavy-100 | 600 | 100 | 28,236,000 | 1228.920 | 1228.920 / 1227.450 / 1285.221 | 81.37 |
| image-heavy-100 | 1200 | 100 | 112,872,000 | 3893.964 | 3893.964 / 3867.865 / 4469.274 | 25.68 |
| vector-heavy-100 | 600 | 100 | 27,255,000 | 511.619 | 527.895 / 503.830 / 511.619 | 195.46 |
| vector-heavy-100 | 1200 | 100 | 108,954,000 | 1463.064 | 1463.064 / 1488.402 / 1391.713 | 68.35 |

## Native per-page time by cohort (sum of cross-repeat page p50s)

| Fixture | Cohort | Pages | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | gradient + soft mask | 21 | 324.346 | 1031.120 | +706.774 | 3.179× |
| real-mixed-120 | other | 99 | 301.432 | 659.964 | +358.532 | 2.189× |
| image-heavy-100 | gradient + soft mask | 10 | 208.255 | 585.247 | +376.992 | 2.810× |
| image-heavy-100 | other | 60 | 270.682 | 645.229 | +374.547 | 2.384× |
| image-heavy-100 | synthetic multi-image | 30 | 752.228 | 2681.779 | +1929.550 | 3.565× |
| vector-heavy-100 | gradient + soft mask | 10 | 157.184 | 485.418 | +328.234 | 3.088× |
| vector-heavy-100 | other | 55 | 116.662 | 244.605 | +127.943 | 2.097× |
| vector-heavy-100 | synthetic dense vector | 35 | 234.850 | 707.247 | +472.398 | 3.011× |

## real-mixed-120: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 607.679 | 1656.224 | 2.725× | +0.000 | +0.000 | — | 0 / 0 |
| path | 575.366 | 1624.723 | 2.824× | +32.313 | +35.140 | 1.087× (<=4) | 120 / 120 |
| glyph | 492.065 | 1436.604 | 2.920× | +119.880 | +214.432 | 1.789× (<=4) | 119 / 119 |
| image | 400.925 | 1028.394 | 2.565× | +208.324 | +622.642 | 2.989× (<=4) | 76 / 76 |
| shading | 508.156 | 1249.192 | 2.458× | +103.789 | +402.105 | 3.874× (<=4) | 21 / 21 |
| group | 816.099 | 1800.221 | 2.206× | -204.154 | -143.997 | undefined (signed/noise) | 30 / 0 |

## image-heavy-100: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 1251.828 | 3849.117 | 3.075× | +0.000 | +0.000 | — | 0 / 0 |
| path | 1187.968 | 3755.968 | 3.162× | +60.038 | +59.746 | 0.995× (<=4) | 90 / 90 |
| glyph | 1178.424 | 3942.160 | 3.345× | +54.636 | -93.043 | undefined (signed/noise) | 58 / 58 |
| image | 272.806 | 699.564 | 2.564× | +979.022 | +3149.553 | 3.217× (<=4) | 100 / 100 |
| shading | 1202.867 | 3669.880 | 3.051× | +67.094 | +145.834 | 2.174× (<=4) | 10 / 10 |
| group | 1427.684 | 4004.058 | 2.805× | -164.575 | -188.344 | undefined (signed/noise) | 30 / 0 |

## vector-heavy-100: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 512.690 | 1424.681 | 2.779× | +0.000 | +0.000 | — | 0 / 0 |
| path | 303.531 | 896.570 | 2.954× | +209.159 | +607.295 | 2.904× (<=4) | 100 / 100 |
| glyph | 423.443 | 1231.158 | 2.907× | +99.765 | +170.215 | 1.706× (<=4) | 65 / 65 |
| image | 447.057 | 1197.736 | 2.679× | +65.633 | +226.945 | 3.458× (<=4) | 10 / 10 |
| shading | 461.380 | 1201.908 | 2.605× | +62.341 | +222.799 | 3.574× (<=4) | 10 / 10 |
| group | 526.205 | 1627.643 | 3.093× | -8.520 | +26.969 | undefined (signed/noise) | 0 / 0 |

## Image cache counters per complete sweep

| Fixture | Width | Sweep | Hits | Misses | Evictions | Decode ms | Maximum resident MiB | Maximum entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | cold | 322 | 19 | 0 | 65.894 | 35.238 | 19 |
| real-mixed-120 | 600 | warm | 341 | 0 | 0 | 0.000 | 35.238 | 19 |
| real-mixed-120 | 1200 | cold | 322 | 19 | 0 | 65.981 | 35.238 | 19 |
| real-mixed-120 | 1200 | warm | 341 | 0 | 0 | 0.000 | 35.238 | 19 |
| image-heavy-100 | 600 | cold | 308 | 110 | 63 | 178.871 | 63.918 | 49 |
| image-heavy-100 | 600 | warm | 308 | 110 | 110 | 175.455 | 63.995 | 49 |
| image-heavy-100 | 1200 | cold | 308 | 110 | 63 | 177.170 | 63.918 | 49 |
| image-heavy-100 | 1200 | warm | 308 | 110 | 110 | 184.458 | 63.995 | 49 |
| vector-heavy-100 | 600 | cold | 17 | 3 | 0 | 23.652 | 8.693 | 3 |
| vector-heavy-100 | 600 | warm | 20 | 0 | 0 | 0.000 | 8.693 | 3 |
| vector-heavy-100 | 1200 | cold | 17 | 3 | 0 | 23.605 | 8.693 | 3 |
| vector-heavy-100 | 1200 | warm | 20 | 0 | 0 | 0.000 | 8.693 | 3 |

## real-mixed-120: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 655.657 | 1802.785 | +1147.129 | 2.750× |
| allocator_ms | 68.402 | 68.249 | -0.152 | 0.998× |
| canvas_create_ms | 2.969 | 17.864 | +14.895 | 6.017× |
| canvas_image_ms | 225.695 | 687.619 | +461.924 | 3.047× |
| mask_ms | 79.468 | 325.905 | +246.437 | 4.101× |
| canvas_paint_ms | 24.440 | 101.696 | +77.256 | 4.161× |
| mask_canvas_paint_ms | 34.887 | 143.149 | +108.262 | 4.103× |
| decode_ms | 0.000 | 0.000 | +0.000 | — |
| other_ms | 323.085 | 669.702 | +346.617 | 2.073× |

## image-heavy-100: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 1296.657 | 3998.935 | +2702.278 | 3.084× |
| allocator_ms | 83.882 | 86.169 | +2.288 | 1.027× |
| canvas_create_ms | 2.505 | 14.924 | +12.419 | 5.959× |
| canvas_image_ms | 820.639 | 3054.411 | +2233.772 | 3.722× |
| mask_ms | 36.255 | 152.646 | +116.391 | 4.210× |
| canvas_paint_ms | 11.447 | 49.306 | +37.859 | 4.307× |
| mask_canvas_paint_ms | 16.170 | 66.936 | +50.766 | 4.139× |
| decode_ms | 175.455 | 184.458 | +9.003 | 1.051× |
| other_ms | 425.811 | 727.648 | +301.836 | 1.709× |

## vector-heavy-100: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 539.785 | 1499.006 | +959.221 | 2.777× |
| allocator_ms | 53.413 | 45.795 | -7.618 | 0.857× |
| canvas_create_ms | 2.441 | 13.996 | +11.555 | 5.734× |
| canvas_image_ms | 78.237 | 234.628 | +156.391 | 2.999× |
| mask_ms | 37.466 | 151.749 | +114.283 | 4.050× |
| canvas_paint_ms | 11.838 | 48.109 | +36.271 | 4.064× |
| mask_canvas_paint_ms | 16.555 | 65.651 | +49.096 | 3.966× |
| decode_ms | 0.000 | 0.000 | +0.000 | — |
| other_ms | 409.804 | 1050.524 | +640.720 | 2.563× |

## Link-visible allocation calls per warm page and observed retained pools

| Fixture | Width | malloc/page | calloc/page | realloc/page | free(non-null)/page | Requested MiB/page | Allocator ms/page | Max PDF pool MiB | Max fixed pool MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 470.17 | 193.55 | 797.66 | 1445.27 | 4.794 | 0.5700 | 7.467 | 3.582 |
| real-mixed-120 | 1200 | 458.17 | 191.65 | 821.29 | 1431.37 | 13.240 | 0.5687 | 29.869 | 14.319 |
| image-heavy-100 | 600 | 400.56 | 152.36 | 644.07 | 1170.44 | 8.181 | 0.8388 | 7.467 | 3.582 |
| image-heavy-100 | 1200 | 388.06 | 151.56 | 658.79 | 1157.14 | 15.180 | 0.8617 | 29.869 | 14.319 |
| vector-heavy-100 | 600 | 504.23 | 233.61 | 1051.14 | 1683.88 | 5.270 | 0.5341 | 7.467 | 3.582 |
| vector-heavy-100 | 1200 | 502.23 | 232.01 | 1096.90 | 1680.28 | 12.359 | 0.4579 | 29.869 | 14.319 |

## Peak working-set growth by phase (mean of three processes, MiB)

| Fixture | Width | Process-start RSS | Open growth | Cold-sweep peak growth | Further warm peak growth | Final peak |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 24.694 | 0.792 | 47.491 | 3.350 | 76.327 |
| real-mixed-120 | 1200 | 24.771 | 0.812 | 67.560 | 14.639 | 107.783 |
| image-heavy-100 | 600 | 24.616 | 0.845 | 82.777 | 8.572 | 116.810 |
| image-heavy-100 | 1200 | 24.758 | 0.794 | 97.490 | 24.056 | 147.098 |
| vector-heavy-100 | 600 | 24.542 | 0.749 | 19.398 | 2.850 | 47.539 |
| vector-heavy-100 | 1200 | 24.870 | 0.818 | 42.456 | 10.889 | 79.033 |

## Image-heavy: alternating 64/256 MiB cache intervention

| Width | Paired 64 MiB native ms | 256 MiB native ms | Observed reduction ms | 256 MiB pages/s | Warm hits | Warm misses | Warm evictions | Warm decode ms | Resident MiB | Native mean peak RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 600 | 1248.250 | 1072.946 | 175.304 | 93.20 | 418 | 0 | 0 | 0.000 | 161.532 | 205.212 |
| 1200 | 3866.008 | 3691.297 | 195.369 | 27.09 | 418 | 0 | 0 | 0.000 | 161.532 | 237.026 |

## Unified fresh first page (bench_firstscreen, three processes)

| Fixture | Width | Open median ms | Render median ms |
| --- | --- | --- | --- |
| real-mixed-120 | 600 | 0.766 | 31.981 |
| real-mixed-120 | 1200 | 0.835 | 62.230 |
| image-heavy-100 | 600 | 0.681 | 31.564 |
| image-heavy-100 | 1200 | 0.734 | 62.850 |
| vector-heavy-100 | 600 | 0.580 | 33.384 |
| vector-heavy-100 | 1200 | 0.659 | 67.600 |
