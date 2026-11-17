# PDF deck render performance

## 1200 px follow-up on `perf/pdf-deck-vs-pdfjs`

Deck p50 at 1200 px went from **45.882 to 28.357 ms/page** (-38.2%). The 22 ms gate remains unmet.

Baseline A is `fc6a0899a`. Candidate B uses the scanline changes in this commit. The host ran Windows build 26200 on an Intel Core Ultra 7 256V with the Balanced power plan, MinGW GCC 16.2.0 and Python 3.14.7. One process loaded both Release DLLs and alternated AB/BA on each page. Each repeat used separate documents, one warmup round and 20 measured rounds per side. The timer covers `exr_fixed_render` including bitmap allocation and drawing. CPU sampling used the repository’s 15% fail-closed idle gate before each repeat. Capture CPU includes the benchmark. During a Word idle wait, CTest ran separately. The timing runner then resumed with both DLLs in a fresh process for the remaining pairs. p50 and nearest-rank p95 are medians across the three repeats. Spread is the p50 range divided by the smallest repeat p50. [Timings, CPU readings, and DLL and fixture hashes](1200-timings.json).

### Render and open acceptance

| Case | p50 A → B (ms) | p95 A → B (ms) | Spread A / B | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | ---: | ---: | --- | --- |
| deck 1200 px (miss) | 45.882 → 28.357 | 47.820 → 29.802 | 1.0% / 2.0% | 11.72 / 7.03 / 12.55 | 30.16 / 30.34 / 26.48 |
| deck 600 px (pass) | 20.721 → 14.312 | 22.221 → 15.551 | 2.3% / 2.8% | 14.62 / 14.06 / 12.50 | 41.39 / 34.26 / 26.55 |
| pptx-20 1200 px (pass) | 3.079 → 2.657 | 3.557 → 3.109 | 1.0% / 0.9% | 13.67 / 8.95 / 8.30 | 38.61 / 42.00 / 23.07 |
| pptx-20 600 px (pass) | 1.733 → 1.527 | 2.376 → 2.159 | 1.1% / 2.7% | 8.59 / 11.02 / 11.07 | 19.22 / 19.81 / 21.97 |
| word-5 1200 px (miss) | 9.068 → 8.393 | 9.996 → 9.152 | 4.2% / 2.9% | 13.28 / 14.45 / 13.23 | 31.10 / 26.23 / 22.50 |
| word-5 600 px (miss) | 3.349 → 3.064 | 3.862 → 3.469 | 3.7% / 5.0% | 13.15 / 11.11 / 8.00 | 19.63 / 36.27 / 33.24 |

The deck 600 px gate allows +3% from the supplied 19.974 ms reference. The control render gates are 2.9 / 2.1 ms for PPTX and 7.3 / 2.6 ms for Word at 1200 / 600 px.
Both Word widths improved within their pairs and exceeded the specified ceilings on both builds.

The dedicated open benchmark used 50 warmups and 3,000 paired opens per repeat and fixture. The timer covers `exr_fixed_open`.

| Case | p50 A → B (ms) | p95 A → B (ms) | Spread A / B | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | ---: | ---: | --- | --- |
| deck open (miss) | 0.2374 → 0.2378 | 0.3965 → 0.3983 | 7.8% / 8.2% | 9.77 / 10.89 / 10.34 | 23.57 / 30.15 / 23.43 |
| pptx-20 open (miss) | 0.1679 → 0.1678 | 0.2873 → 0.2832 | 2.0% / 1.8% | 9.88 / 13.28 / 11.49 | 19.85 / 36.50 / 31.91 |
| word-5 open (miss) | 0.1012 → 0.1013 | 0.1841 → 0.1847 | 1.7% / 1.3% | 8.63 / 9.77 / 8.73 | 18.35 / 27.12 / 23.13 |

Open is checked against paired A and the supplied references of 0.16 ms for deck, 0.11 ms for PPTX and 0.06 ms for Word.
Both DLLs exceeded those references. The paired p50 changed by +0.0004 ms for deck, −0.0001 ms for PPTX, and +0.0001 ms for Word.

### Deck attribution at 1200 px

Class A ran the full painter. B ran a temporary DLL with one operation disabled. Path and glyph probes retained clipping. The group probe covered painter groups. A separate probe covered the root canvas commit. The class runs used 20 rounds. The extra clip, root and scoped timing runs used five rounds. The first attempt to run paths timed out at the idle gate, so the other class probes resumed from the saved image pairs.

| Case | p50 A → B (ms) | p95 A → B (ms) | Spread A / B | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | ---: | ---: | --- | --- |
| Image loading and paint off | 45.386 → 37.979 | 56.259 → 46.917 | 6.9% / 6.7% | 9.77 / 13.95 / 14.84 | 51.16 / 63.56 / 41.07 |
| Path paint off | 44.450 → 39.413 | 105.055 → 78.173 | 4.7% / 4.3% | 10.76 / 6.61 / 9.58 | 30.94 / 54.02 / 61.48 |
| Glyph paint off | 42.798 → 35.231 | 45.405 → 37.861 | 4.4% / 4.2% | 3.91 / 5.79 / 10.16 | 22.24 / 25.04 / 27.01 |
| Painter groups off | 43.255 → 42.889 | 48.051 → 47.938 | 78.1% / 79.4% | 5.43 / 2.75 / 14.34 | 35.29 / 30.72 / 88.50 |
| Content clip off | 45.091 → 27.937 | 48.743 → 30.195 | 147.7% / 116.3% | 13.95 / 10.59 / 5.79 | 87.40 / 26.98 / 25.42 |
| Content clip off, images off in A and B | 36.825 → 19.383 | 39.037 → 21.112 | 1.6% / 3.9% | 5.79 / 12.25 / 7.42 | 30.74 / 21.04 / 28.74 |
| Root group commit off | 44.916 → 44.545 | 83.012 → 72.845 | 79.8% / 73.1% | 5.47 / 11.16 / 7.06 | 37.71 / 84.62 / 27.25 |

Image removal saved a median of **7.407 ms** across the paired repeats. Content clip removal saved **17.396 ms** with images disabled on both sides. With all operations enabled, scoped clip filling averaged **16.863 ms** per page (median of repeat means). Crossing and span accumulation used **13.058 ms**, byte writes used 3.039 ms, and rectangle rasterization used 0.037 ms. Clip flattening and allocation used 0.065 and 0.550 ms. The crossing and write timers are nested inside clip fill. Pre-CPU for the scope pairs was 8.98 / 13.23 / 10.51%.

The two content-clip-off runs with the lowest capture CPU measured 27.587 and 27.937 ms p50 with images enabled. Content clipping changes the paint that follows it, so these are diagnostic times. The table retains all idle-admitted repeats, including capture CPU spikes.

### Scanline change and verification

The scanline rasterizer reuses rounded clip coverage while active edges stay vertical and no edge endpoint changes the crossing set. It still applies each row’s parent clip and source-over, preserves the four sample positions, and charges the original work. Near the work limit it steps through the original charges to preserve the exact failure point. Finite edge comparisons and the small crossing sort also reduce work in the same rasterizer. The temporary painter switches and timers were removed before the candidate build.

| Fixture | Page / width pairs | RGBA pixels | Different pixels | Max channel delta |
| --- | ---: | ---: | ---: | ---: |
| deck | 30 | 15,192,000 | 0 | 0 |
| pptx-20 | 60 | 85,056,000 | 0 | 0 |
| word-5 | 10 | 11,649,000 | 0 | 0 |

**111,897,000 identical pixels** by direct active RGBA byte comparison. PPTX includes 2400 px for the pixel gate. [Pixel comparison](1200-pixels.json).

**577/577 CTest tests passed.** The added vector case compares threshold and fractional edge behavior, exact work counts, and partial writes at the work limit. [CTest summary](1200-ctest.txt).

## Earlier PR #243 measurements

At 1200 px, deck p50 fell from **120.391 to 47.821 ms/page** (-60.3%). The 40 ms acceptance target and 20 ms ideal remain unmet.

Main was `51ce8814d`. Testing used Windows 11 build 26200, Intel Core Ultra 7 256V (8 logical CPUs), AC power, the Balanced power plan, MinGW GCC 16.2.0 Release and Python 3.14.7.

## Render and open benchmarks

The main checkout’s `tools/bench_engine.py` measured 20 rounds after one full warmup with three fresh-process repeats per width. The idle gate sampled system CPU before each capture and required 15% or less. Capture CPU is the system-wide mean including the benchmark. Builds, tests and pixel comparisons ran separately. The p50 and p95 columns are medians across repeats. Spread is (max − min) ÷ min of the three repeat p50s.

| Fixture | Width | Build | p50 (ms) | p95 (ms) | Repeat p50s (ms) | Spread | Pre-CPU (%) | Capture CPU (%) | Open p50 (ms) |
| --- | ---: | --- | ---: | ---: | --- | ---: | --- | --- | ---: |
| deck | 600 | baseline | 40.852 | 43.447 | 37.577 / 42.066 / 40.852 | 11.9% | 3.14 / 11.60 / 5.47 | 29.60 / 40.07 / 29.25 | 0.154 |
| deck | 600 | candidate | 22.111 | 24.834 | 21.444 / 22.111 / 22.247 | 3.7% | 6.54 / 5.02 / 11.33 | 35.79 / 29.94 / 31.62 | 0.145 |
| deck | 1200 | baseline | 120.391 | 127.606 | 124.166 / 120.391 / 119.377 | 4.0% | 8.11 / 12.84 / 5.86 | 39.49 / 32.99 / 36.35 | 0.160 |
| deck | 1200 | candidate | 47.821 | 51.637 | 47.713 / 47.821 / 47.994 | 0.6% | 7.03 / 8.40 / 5.49 | 29.83 / 27.67 / 24.20 | 0.155 |
| pptx-20 | 1200 | baseline | 3.421 | 4.602 | 3.739 / 3.421 / 3.386 | 10.4% | 10.89 / 12.89 / 7.03 | 34.91 / 26.05 / 29.09 | 0.115 |
| pptx-20 | 1200 | candidate | 3.560 | 4.785 | 3.471 / 3.560 / 3.684 | 6.1% | 4.23 / 9.80 / 11.20 | 27.23 / 28.85 / 18.62 | 0.102 |
| word-5 | 1200 | baseline | 17.388 | 19.498 | 17.388 / 18.149 / 17.353 | 4.6% | 7.81 / 9.38 / 7.91 | 36.28 / 42.03 / 23.35 | 0.063 |
| word-5 | 1200 | candidate | 17.584 | 19.547 | 17.871 / 17.584 / 16.937 | 5.5% | 13.28 / 7.42 / 5.12 | 31.98 / 24.66 / 33.80 | 0.065 |

Deck p50 changed **-45.9%** at 600 px and **-60.3%** at 1200 px. At 1200 px the controls changed **+4.1%** for PPTX and **+1.1%** for Word relative to this run’s main build. The measured main control timings already exceed the handoff’s historical values. [Per-repeat p95 and CPU measurements, fixture and DLL hashes](measurements.json).

## Paired open probe

Three repeats alternated baseline and candidate calls in the same process, with 3,000 opens per DLL and fixture after 50 warmups. CPU columns are in repeat order.

| Fixture | Open p50 before → after (ms) | Change | Spread before / after | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | ---: | --- | --- | --- |
| deck | 0.234200 → 0.235900 | +0.73% | 57.7% / 59.1% | 7.39 / 5.47 / 13.95 | 23.29 / 31.14 / 44.90 |
| pptx-20 | 0.168400 → 0.169300 | +0.53% | 2.8% / 2.8% | 5.86 / 10.94 / 12.40 | 17.03 / 25.44 / 20.19 |
| word-5 | 0.099300 → 0.100300 | +1.01% | 4.6% / 4.9% | 7.81 / 7.81 / 8.98 | 14.32 / 21.75 / 39.34 |

The strict open-time gate remains unmet in the paired medians.

## Paired control renders at 1200 px

A separate probe alternated DLL order on each page, with one warmup round followed by 12 measured rounds. The same CPU readings apply to both DLLs in each repeat.

| Fixture | p50 before → after (ms) | Change | p95 before → after (ms) | Spread before / after | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | ---: | ---: | --- | --- | --- |
| pptx-20 | 3.6522 → 3.7128 | +1.66% | 4.5337 → 4.8356 | 11.9% / 11.7% | 4.30 / 4.69 / 7.81 | 16.33 / 22.55 / 23.87 |
| word-5 | 23.7661 → 24.3193 | +2.33% | 25.6645 → 26.0127 | 4.3% / 3.0% | 5.04 / 10.55 / 12.99 | 19.62 / 21.50 / 30.55 |

Both controls meet the +3% limit in the paired runs.

## Attribution at 1200 px

The temporary DLL used the renderer from main with class switches in the painter. Each repeat opened a separate document per variant, warmed every page once, then measured four rounds of all 15 pages. The variant order rotated by page and round. The same CPU readings apply to every variant in a repeat. Pre-capture CPU was **11.46% / 13.28% / 8.20%** and capture CPU was **48.22% / 36.09% / 69.20%**. Treat these as paired diagnostics under variable system load.

| Enabled or disabled operations | p50 (ms) | p95 (ms) | Repeat p50s (ms) | Spread | First page, cold (ms) |
| --- | ---: | ---: | --- | ---: | ---: |
| All enabled | 126.131 | 169.316 | 126.131 / 122.203 / 129.672 | 6.1% | 162.938 |
| Bypass image drawing, keep image loading | 43.364 | 61.019 | 45.490 / 41.764 / 43.364 | 8.9% | 105.118 |
| Bypass image drawing and loading | 43.566 | 57.734 | 45.945 / 41.652 / 43.566 | 10.3% | 38.701 |
| Bypass path paint, keep clipping | 124.602 | 164.252 | 125.839 / 120.340 / 124.602 | 4.6% | 160.209 |
| Bypass glyph paint, keep text clipping | 116.823 | 167.078 | 116.996 / 113.242 / 116.823 | 3.3% | 154.505 |
| Bypass nested groups and graphics-state soft masks | 126.089 | 182.125 | 127.143 / 120.999 / 126.089 | 5.1% | 160.581 |
| Bypass images and content clipping | 23.954 | 37.993 | 25.749 / 22.214 / 23.954 | 15.9% | 21.758 |
| Bypass images, paths, glyphs, nested groups, masks and clipping | 7.329 | 10.278 | 7.716 / 6.953 / 7.329 | 11.0% | 5.747 |

Median paired p50 deltas were **80.641 ms** for image drawing, **19.612 ms** for clipping with images disabled, **9.135 ms** for glyph paint, and **1.862 ms** for path paint. The median paired delta was −0.201 ms for warm image loading and +1.204 ms for nested groups and masks. Both sets of deltas changed sign across repeats. Cold page-one image loading added **62.383 / 69.703 / 67.984 ms** in the three pairs. The residual includes content walking, viewport and canvas setup, and root compositing. Interactions between variants prevent adding the deltas. [Raw paired samples](ablation.json)

A separate untimed trace recorded **270 draws** over two deck rounds at 1200 px, with **15 distinct image/transform pairs**. The largest texture (1342 × 757) uses opaque black for all 1,015,894 source texels and the same transform for its 30 draws. Its decoded mask contains 986,540 texels with value 89. [Decoded texture and transform trace](image-trace.txt)

## Renderer change

The affine image renderer checks for an opaque, uniform RGB texture with a same-size, opaque nearest-neighbor soft mask in axis-aligned normal source-over. It computes the two horizontal tap indices once per destination column and the two vertical indices once per row. Each valid quarter-pixel tap contributes the exact gray-mask byte to the alpha sum. The four-tap average keeps the existing byte rounding, clip coverage, source-over operation and row work charge. The validation scan is bounded relative to the destination area.

The native differential test uses an opaque identity mask layer to exercise the generic reference sampler. It compares reflected axes, fractional boundaries, varied colors and mask values, and partial clip coverage. The diagnostic painter was restored before the final build.

## Verification

| Fixture | Page/width combinations | Active RGBA pixels | Different pixels | Maximum channel delta |
| --- | ---: | ---: | ---: | ---: |
| deck | 30 | 15,192,000 | 0 | 0 |
| pptx-20 | 60 | 85,056,000 | 0 | 0 |
| word-5 | 10 | 11,649,000 | 0 | 0 |

The comparator decompressed actual RGBA snapshots and checked the bytes across every page and width. [Pixel results and per-page hashes](pixels.json).

CTest passed **577/577**. [CTest summary](ctest-summary.txt).

## Word-5 regression follow-up

The follow-up compares the PR head `fa47cf9f3`, the GCC outlining fix, and main `8c603624f` where measured. The machine used an Intel Core Ultra 7 256V with eight logical CPUs, Windows 11, AC power, the Balanced plan, and MinGW GCC 16.2.0 Release. The handoff names three fixtures. `pptx-1` is the fourth timing control from the same fixture set.

### Reproduction and attribution

The handoff runner sampled 13.28% system CPU before the original Word run. It samples once for the full invocation. The measured p50s were 3.058 ms at 600 px (14.3% spread) and 7.423 ms at 1200 px (3.5% spread).

One trace rendered every page once at each width. Code 1 recorded a successful `nearest_axis` dispatch, 0 or 2 a mask-validation call, and 3 a successful solid-mask dispatch.

| Fixture | Width | Nearest-axis draws | Mask validation calls | Solid-mask draws |
| --- | ---: | ---: | ---: | ---: |
| word-5 | 600 | 5 | 0 | 0 |
| word-5 | 1200 | 5 | 0 | 0 |
| deck | 600 | 0 | 135 | 135 |
| deck | 1200 | 0 | 135 | 135 |

MinGW GCC inlined both fast paths into `exr_vector_texture_blend_inks`. Adding the masked path changed the emitted unmasked path. Disabling only the masked branch produced affine-object disassembly identical to main. Outlining `nearest_axis` gives GCC a separate function body and retains the solid-mask dispatch and its validation.

Paired Word diagnostics rotated DLL order on each page, with 3 warmup rounds followed by 20 measured rounds per repeat. CPU readings apply to every DLL in that repeat. Spread is (max − min) ÷ min across repeat p50s.

| Width | Build | Repeat p50s (ms) | Median p50 (ms) | Spread | Pre-CPU (%) | Capture CPU (%) |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 600 | before | 3.471 / 3.299 / 3.131 | 3.299 | 10.9% | 12.11 / 11.67 / 13.28 | 34.90 / 26.68 / 41.35 |
| 600 | main | 3.446 / 3.289 / 3.081 | 3.289 | 11.8% | 12.11 / 11.67 / 13.28 | 34.90 / 26.68 / 41.35 |
| 600 | no-solid | 3.412 / 3.253 / 3.143 | 3.253 | 8.6% | 12.11 / 11.67 / 13.28 | 34.90 / 26.68 / 41.35 |
| 600 | outline-solid | 3.456 / 3.260 / 3.179 | 3.260 | 8.7% | 12.11 / 11.67 / 13.28 | 34.90 / 26.68 / 41.35 |
| 600 | outline-nearest | 3.339 / 3.167 / 2.994 | 3.167 | 11.5% | 12.11 / 11.67 / 13.28 | 34.90 / 26.68 / 41.35 |

### Render acceptance

The repository runner uses 20 rounds after one warmup and three fresh processes per width. Each repeat requires system pre-CPU of 15% or less. Capture CPU includes the benchmark. The p50 is the median of repeat p50s.

| Fixture | Width | Build | p50 (ms) | Repeat p50s (ms) | Spread | Pre-CPU (%) | Capture CPU (%) |
| --- | ---: | --- | ---: | --- | ---: | --- | --- |

### Verification

| Fixture | Page/width combinations | Active RGBA pixels | Different pixels | Maximum channel delta |
| --- | ---: | ---: | ---: | ---: |
| word-5 | 10 | 11,649,000 | 0 | 0 |
| deck | 30 | 15,192,000 | 0 | 0 |
| pptx-20 | 60 | 85,056,000 | 0 | 0 |

Compared 111,897,000 active RGBA pixels between the original and final DLLs. CTest passed 577/577.

word-5 回退的原因是 GCC 把两条快路径内联到同一个函数后，改变了 word-5 所用无掩码近邻循环的机器码。
