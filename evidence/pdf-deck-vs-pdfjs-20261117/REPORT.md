# PDF deck render performance

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
