# PDF masked image drawing measurements

Base: `baf348d2d`, branch `perf/pdf-matte-image`. Windows x64, GCC 16.2.0,
Release `-O3 -DNDEBUG`, PDF/PDF editing/tests enabled, AVIF disabled.

The retained change reduces loop cost by 17.3%. A matched three-repeat check
reduces deck 1200px p50 by 5.8%, to 225.56 ms/page. The 150 ms target remains
unmet; this is a draft performance improvement rather than full acceptance.

## Instrumentation first

Before changing rendering behavior, timers were inserted inside the existing
affine drawing loop and `texture_sample`. One in 256 clip-covered destination
pixels was sampled, including all four original quarter-pixel samples. The
canonical `bench_engine.py` ran 12 measured rounds plus a warmup, twice, at
600 and 1200 pixels. No compilation or tests ran during measurements.

| Four measured sub-steps | 600px | 1200px |
|---|---:|---:|
| Source sampling | 32.26% | 32.09% |
| Soft-mask sampling | 36.75% | 36.81% |
| Mask/matte application | 15.34% | 14.79% |
| Color packing and background composite | 15.66% | 16.30% |

Percentages subtract the calibrated mean cost of an empty clock pair (13.96 ns
at 600px, 14.62 ns at 1200px). Raw percentages are also retained in
`profile-before.json`: 1200px = 31.35%, 33.41%, 23.79%, 11.46%.
Each width includes 3,510 image draws (15 pages × 13 rounds × 2 repeats × 9
images). The 1200px run samples 1,259,310 destination pixels.

Fine-grained timers perturb optimization and execution: the corrected sampled
stage durations sum to 146.86 ns/pixel, while the stage-instrumented entire loop
measures 87.70 ns/pixel. These percentages describe the instrumented sub-steps;
they are not an additive decomposition of uninstrumented render time. A second
instrumentation mode times only the entire drawing loop, with all per-pixel
timing, depth counters and sample counters compiled out. Its pixel denominator
is counted after the timed loop. Use that mode for the before/after ns/pixel.

All recorded images use nearest-neighbor source and mask sampling, matching
dimensions, no nested image mask, normal blending and no composite state. Sizes
are 1342×757, 190×160 and 95×62. All reach drawing with `has_matte == 0`:
`pdf_image.c` already reverses PDF Matte during decode. The third measured stage
is therefore mask multiplication, not runtime Matte reversal.

The baseline whole-loop measurement gives 77.97 ns/pixel at 600px and
77.75 ns/pixel at 1200px. At 1200px, per-render loop time has median 63.29 ms;
subtracting each render's loop time from that same render gives median
175.95 ms outside this loop. At 600px these medians are 15.99 ms and 102.84 ms.
The ≤150 ms/page target cannot be reached by optimizing this loop alone on this
fixture/build: even removing the entire loop leaves approximately 176 ms/page.

## Change

For a nearest-neighbor image and an unnested nearest-neighbor mask of identical
dimensions, calculate the texel address once. Read the source RGBA and just the
mask components needed for opacity, avoiding the recursive general sampler and
its duplicate coordinate calculation. Keep the original two mask divisions,
source products, accumulation order and shape flags. Other textures retain the
general sampler, including interpolated, mismatched, nested, native CMYK and
runtime Matte cases.

Channel packing also uses nonnegative integer truncation after adding 0.5,
with saturation at 255, replacing equivalent `floor`/`fmin` calls. Valid sampled
channel values are finite, nonnegative and bounded by 255.

The differential native test forces the reference recursive sampler with an
opaque tail mask. It covers 64 cases with padded/different strides, partial
source and mask alpha, transparent/opaque extremes, clip holes, rotations,
reflections, both mask modes, source alpha/shape flags, object alpha, shape
tracking and normal/multiply blending.

## Measured result

The retained kernel's initial canonical runs use 12 rounds and two repeats,
with per-pixel instrumentation disabled. The rebuilt retained DLL has exactly
the same `.text`, `.rdata` and `.data` bytes as this benchmarked candidate; see
`retained-binary-sections.json`.

| Metric | Before | After | Change |
|---|---:|---:|---:|
| deck 600px render p50 | 117.630 ms | 113.710 ms | −3.33% |
| deck 1200px render p50 | 240.610 ms | 225.276 ms | −6.37% |
| 600px drawing loop | 77.9705 ns/pixel | 64.4346 ns/pixel | −17.36% |
| 1200px drawing loop | 77.7497 ns/pixel | 64.2884 ns/pixel | −17.31% |
| pptx-20 600px render p50 | 1.979 ms | 2.012 ms | +1.67% |
| pptx-20 1200px render p50 | 3.520 ms | 3.396 ms | −3.52% |
| pptx-20 2400px render p50 | 11.285 ms | 11.273 ms | −0.11% |

The 1200px deck repeat spread is 2.1% before and 0.3% after; 600px spread is
0.1% and 2.0%. Whole-loop ns/pixel is total loop time divided by total
clip-covered destination candidates, including warmup. This denominator counts
each destination pixel once per image, not once per quarter-pixel sample.

The ≤150 ms/page target is **not met**. Whole-loop improvement is proportional
at both widths, but total render time improves less at 600px because the loop
is a smaller portion of the total there.

An additional coordinate-reuse experiment was removed: its loop measurements
were 64.4461 ns/pixel at 600px and 63.5856 ns/pixel at 1200px, versus
64.4346/64.2884 for the smaller retained change. The negligible 600px result and
1.1% 1200px benefit did not justify the added per-pixel arrays and branches.
Its raw results remain in the `coordinate-*` evidence.

The retained implementation passes all 577 CTests (75.12 seconds) and 4,172
native PDF image checks, including the expanded differential cases.

### Matched verification of render and open timings

An initial two-repeat deck open measurement was 0.150 → 0.158 ms; the discarded
coordinate experiment also produced outlying open/pptx repeats. A matched
before/after check of the retained implementation used the same canonical tool,
12 rounds and **three repeats**, at 1200px:

| Metric | Before | After |
|---|---:|---:|
| deck render p50 | 239.547 ms | 225.562 ms (−5.84%) |
| deck open p50 | 0.152 ms | 0.149 ms |
| pptx-20 render p50 | 3.394 ms | 3.346 ms (−1.41%) |
| pptx-20 open p50 | 0.110 ms | 0.105 ms |

Deck repeat p50 values are 235.574/239.547/241.275 ms before and
223.342/225.562/231.539 ms after (spread 2.4%/3.7%). pptx-20 after-repeat p50
values are 3.308/3.346/3.508 ms (6.1% spread); every repeat remains within the
task's +3% ceiling relative to 3.49 ms. The open increase in the initial deck
run does not repeat in this matched check. `verify-*.json` preserves all four
reports. Initial two-repeat reports are preserved separately, not replaced.

### Exhaustive pixel comparison

The canonical `benchmark_pdf_rect.py compare` command compared every active
RGBA pixel from the retained candidate's snapshots against the baseline. Its
code, constant-data and writable-data sections match the delivered rebuild.

| Fixture | Page/width combinations | Compared RGBA pixels | Different pixels | Maximum channel difference |
|---|---:|---:|---:|---:|
| deck, 15 pages × 600/1200 | 30 | 15,192,000 | 0 | 0 |
| pptx-20, 20 pages × 600/1200/2400 | 60 | 85,056,000 | 0 | 0 |

Per-page counts and before/after RGBA SHA-256 values are in `pixels-deck.json`
and `pixels-pptx.json`. The render target is the remaining acceptance failure;
total-render gains at 600px also do not match the 1200px percentage, although
the drawing kernel itself improves by the same proportion at both widths.

## Reproduction

Use the configure/build flags and dependency overrides from
`TASK-PDF-MATTE-IMAGE.md`. Production builds leave `EXR_PROFILE_IMAGE` undefined.
For diagnostics on Windows, compile `src/affine_image.c` with
`EXR_PROFILE_IMAGE=1` (sampled stages) or `EXR_PROFILE_IMAGE=2` (whole loop only),
and set `EXR_PROFILE_IMAGE_OUT` to an absolute CSV path. Profiling is deliberately
single-threaded and intended only for the serial benchmark. The macro is absent
from the delivered build.

`instrumentation-only.patch` applies to the base commit's `affine_image.c` and
adds just the timers, counters and CSV output, without either kernel change.
Use that source for before-profile reproduction; use this branch's source for
after-profile reproduction. Summarize either CSV with the included tool.

```powershell
python -X utf8 C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\projects\exreader-handoff\tools\bench_engine.py `
  --library build/perf/libexreader.dll --input tests/fixtures/pdf-ppt/deck.pdf `
  --expect-pages 15 --widths 600 1200 --runs 12 --repeat 2 --idle-threshold 15 `
  --repo . --out build/matte-evidence/after-deck/bench.json
python tools/summarize_image_profile.py build/matte-evidence/profile-before.csv build/matte-evidence/profile-before.json
```

Use the same benchmark for pptx-20 with widths 600, 1200 and 2400. Pixel snapshots
are the canonical harness's active RGBA captures; comparisons use its `compare`
command on each width's `.repeat-0/<width>` directories.

Raw captures, DLLs and full logs are under `build/matte-evidence/` locally.
Compact benchmark, profile and comparison evidence accompanies this report.
