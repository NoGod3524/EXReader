# RECT clipping: measured result

The RECT/NONE implementation passes pixel identity and CTest. **The requested deck.pdf ≤40 ms/page target is not met.** This is a draft PR; performance acceptance remains incomplete.

## Timings

Baseline: `baf348d2d`, preserved DLL. Release MinGW GCC 16.2.0, offline dependency cache, 12 measured rounds after one warmup, two repeats, idle gate 15%. Values below are the benchmark tool's reported p50 (upper middle repeat); all individual samples and repeat p50 values are retained in [samples.json](samples.json).

| Fixture | Width | Before ms/page | After ms/page | Change |
| --- | ---: | ---: | ---: | ---: |
| deck | 1200 | 233.255 | 237.511 | +1.8% |
| pptx | 600 | 1.991 | 2.985 | +49.9% |
| pptx | 1200 | 3.410 | 3.539 | +3.8% |
| pptx | 2400 | 11.265 | 11.369 | +0.9% |

The initial 1200px pptx result exceeded the ±3% allowance. Following the task's noise/rerun rule, code stayed unchanged and baseline/final were repeated back-to-back with a stricter 5% idle gate: **3.506 → 3.429 ms/page**, -2.2%. This rerun passes the 1200px allowance. Both runs are retained, including the original red result, in the paired JSON reports and [paired-samples.json](paired-samples.json).

Open p50:

| Run | Before ms | After ms |
| --- | ---: | ---: |
| deck, 1200px | 0.202 | 0.155 |
| pptx, 1200px initial | 0.113 | 0.117 |
| pptx, 1200px paired rerun | 0.102 | 0.107 |

The strict open no-slowdown condition is not demonstrated by the pptx measurements (+0.005 ms in the paired rerun). The 600px render regression is also recorded above; the task's render performance gate specifies 1200px.

## Pixel proof and tests

- pptx-20, widths 600/1200/2400: **60 combinations, 85,056,000 active RGBA pixels**, zero differing pixels, maximum channel difference **0**.
- deck, width 1200: **15 pages, 12,150,000 active RGBA pixels**, zero differing pixels, maximum channel difference **0**.
- Both fixtures use the same preserved baseline DLL. [identity.json](identity.json) contains every page's hashes, pixel count and exact comparison result. [metadata.json](metadata.json) records DLL and fixture hashes. Captures also verify hash stability in every render round.
- **CTest 577/577 passed**, 76.68 s: [full output](ctest.txt). Added checks cover repeated fractional intersections, save/restore, collinear/closing vertices, union clipping, images, compound draws, groups and a one-byte mask budget that proves empty compound draws bypass mask allocation.

## Clip counts and the missed target

One render of every page at 1200px; logging runs are separate from timing runs. Counts describe successful `clip_path` results, with the unrestricted NULL state separated from stored kinds:

| Fixture | NONE | stored RECT | MASK | identity/NULL | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| deck, 15 pages | 0 | 135 | 120 | 615 | 870 |
| pptx, 20 pages | 0 | 0 | 0 | 100 | 100 |

Baseline deck already elides 615 full-canvas clips and builds 255 clip masks. Final deck builds 120: **135 rectangle clip mask allocations removed across the document**. The remaining 120 clips each contain two contours and stay on MASK. The rectangular branch has 750 hits including its 615 identity results. Baseline pptx has 100 identity results.

These measurements differ from the task's stated 860 full-page mask allocations *per page*. Here deck has 58 canvas clips/page: 41 identity, 9 stored RECT, 8 MASK. Neither fixture exercises NONE at 1200px. Consequently these changes do not produce the requested deck speedup. See [clip-counts.json](clip-counts.json) for all per-page counters.

## Implementation

`exr_clip_state` stores NONE/RECT/MASK with reference ownership inherited by save/restore and groups. RECT has half-open pixel bounds and nine quantized edge/interior coverage values. Rectangle intersection multiplies those values using the original mask rounding, preserving fractional edges and repeated-clip coverage. Four-edge recognition uses the existing rasterizer's roundoff cap in addition to the requested canvas-relative tolerance; other near-axis polygons retain MASK to preserve exact scanline coverage. Collinear vertices use the existing four-sample scanline quantization.

Draws clamp to RECT bounds and can use the unmasked path when their entire extent is opaque. Empty intersections and newly built all-zero masks become NONE; paint entrypoints return before pixel loops, and NONE propagates through nested groups. Union construction retains mask coverage semantics.

## Reproduction

The provided external `bench_engine.py` adds idle time to total CPU time even though Windows kernel time already includes idle. It reported 52.075% during the initial idle check, preventing the requested 15% gate from opening. [tools/bench_engine.py](../../tools/bench_engine.py) is a copy with the CPU calculation corrected to `(kernel + user - idle) / (kernel + user)`. No contended timeout measurements are used.

From the repository root, using the task's Release build configuration:

```powershell
python -X utf8 tools/bench_engine.py --library build/cliprect/final/libexreader.dll --input tests/fixtures/pdf-ppt/deck.pdf --expect-pages 15 --widths 1200 --runs 12 --repeat 2 --idle-threshold 15 --repo . --out build/cliprect/recheck-deck/bench.json
python -X utf8 tools/bench_engine.py --library build/cliprect/final/libexreader.dll --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 --widths 600 1200 2400 --runs 12 --repeat 2 --idle-threshold 15 --repo . --out build/cliprect/recheck-pptx/bench.json
python -X utf8 tools/benchmark_pdf_rect.py compare --before build/cliprect/before-deck/.repeat-0/1200 --after build/cliprect/verified-deck/.repeat-0/1200 --output build/cliprect/diff-deck-1200
python -X utf8 evidence/pdf-clip-rect/profile_clips.py --out build/cliprect/counts-after
python -X utf8 evidence/pdf-clip-rect/profile_clips.py --baseline --out build/cliprect/counts-before
ctest --test-dir build/perf --output-on-failure -j 6
```

The pixel comparison command is also run for each pptx width. Counter scripts temporarily instrument canvas.c and restore it in `finally`; their elapsed times are not benchmarks. The preserved baseline/final DLLs and compressed RGBA snapshots remain under `build/cliprect/` in this checkout.
