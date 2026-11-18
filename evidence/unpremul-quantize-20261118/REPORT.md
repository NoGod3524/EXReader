# Un-premultiply + quantize: SIMD / reciprocal rewrite (negative result)

**Conclusion: no candidate is faster, and none ships. `src/` is unchanged from `main`.**
Five bit-exact rewrites of the RGB sink's `image_byte(sums[k]/sums[3])` loop were
timed with in-process interleaved A/B tests. Each one was either neutral or slower on
the headline fixtures. The 153.98 / 382.67 ms that sink2 attributed to this stage is
not divide cost that a bit-exact rewrite can recover (see "Why the attribution
overstated it").

## The code

`src/affine_image.c` has five copies of the per-pixel loop
`for(k<3) color|=image_byte(sums[k]/sums[3])<<(24-8*k)`: in `nearest_axis`,
`axis_store`, `bilinear_shear`, `bilinear_axis` and `exr_vector_texture_blend_inks`
(object and composite branches). `sums` holds the premultiplied double sums from 2×2
supersampling of the bilinear taps. There is no 8-bit premultiplied source here.
`sums[3]` is a sum of weighted alphas, so an opaque image does not make the
quotient an identity. The task's options B and C (a constant alpha=255 path, or a
256×256 integer table) therefore do not apply bit-exactly. Only reducing or
packing the divides is left.

Counter build (`count.json`, `build.py count`), @1200: 59.2 M pixels through the
loop on image-heavy-100, 29.2 M on real-mixed-120, 12.0 M on vector-heavy-100,
0.56 M on word-5, and 0 on deck and pptx-20.

## Candidates

| Build | `image_rgb` form | Source sha256 (prefix) |
| --- | --- | --- |
| A / Afresh | `main` (three scalar quotients) | `eac17340` |
| B | one reciprocal `1/sums[3]`, three multiplies, boundary guard with quotient fallback; not force-inlined | `5218b573` |
| C | intermediate, source not preserved (only its hash was recorded) | `930460da` |
| D | SSE2 `divpd` on R,G plus `divsd` on B, saturating packs, sign-mask guard; not force-inlined | `8f8c0090` |
| E | D with `always_inline`/`__forceinline` and `loadh/load_sd` | `9e1e709d` |
| F | B's reciprocal and guard, plus E's forced inline | `8872796e` |

## Equivalence (hard constraint)

- `equivalence.py` cuts `image_byte` and `image_rgb` verbatim from the source and
  compares them with the quotient form on 88,663,368 sums. The inputs are random
  bilinear sums, exact `k+.5` boundaries with neighbouring doubles, 2×/3×/4× weights,
  integer nearest sums, tiny and huge alpha, and non-finite or out-of-domain lanes.
  The variants are `-O3`, `-ffp-contract=fast -mfma -mavx2`, and no-SSE2.
  - E: 0 mismatches in all three. The unguarded control has 47,952 mismatches
    (`equivalence.json`).
  - F: 0 mismatches in all three. The unguarded control has 4,996,215 mismatches
    (`equivalence-F.json`).
- Full-render pixel check for B's algorithm, which is the same function as F
  (`pixels.json`): 353,143,200 large-fixture pixels + 111,897,000 small-fixture
  pixels, **0 different**.

Correctness was never the obstacle. Speed was.

## Timing (interleaved A/B, both DLLs in one process, AB/BA alternating per page)

Paired delta = median of per-page (B−A) differences, as % of A. Positive means
the candidate is slower. Noise floor: A against an identical copy of A on word-5
gave +0.51% (`null-AA-word-1200.json`). Swapping arm order (C as A) reproduced the
word-5 gap with the sign flipped, −12.5% (`swap-CA-word-1200.json`), so the
gap is not caused by arm position.

| @1200, paired Δ | B | C | D | E | F |
| --- | ---: | ---: | ---: | ---: | ---: |
| image-heavy-100 (x9) | +5.02% | +3.64% | +3.24% | +1.09% | +4.40% |
| real-mixed-120 (x9) | +3.24% | +1.98% | +3.63% | +1.39% | +4.63% |
| vector-heavy-100 (x9) | +0.34% | — | −0.24% | −0.27% | stopped |
| word-5 (x60) | +12.57% | +16.09% | +16.86% | −0.25% | stopped |
| pptx-20 (x40) | −0.17% | −0.20% | — | −0.14% | stopped |

Minimum-time deltas have the same sign (logs: `interleaved*.log`). The E and F runs
were taken with the machine 44–70% busy from other lanes, so their absolute times
are about 2× the B–D runs. The paired deltas are still valid because each pair
shares the same load. F was stopped after the two headline fixtures because it
was already rejected on both.

Findings:

1. **The word-5 +12–17% regression (B, C, D) came from inlining, not arithmetic.**
   word-5 sends only 0.56 M pixels through the loop. An out-of-line `image_rgb` call
   inside `exr_vector_texture_blend_inks` blocked optimization of the surrounding
   composite loop. Forcing inline (E) brought word-5 back to the noise floor.
2. **Packing the divides into `divpd` (E) is neutral.** On this core, two scalar
   `divsd` overlap with the surrounding sampling work about as well as one packed
   `divpd`, and the pack/shuffle costs the rest.
3. **One reciprocal and multiplies (B, F) is slower by 3–5%.** The boundary guard
   (two compares per lane, a convert-back and subtract, a movemask branch) costs
   more than the two divides it removes, even with 99.7% of pixels on the fast path.

## Why the attribution overstated it

The sink2 probe (`EXReader-sink2/evidence/rgb-sink-arithmetic-20261118/make_replica.py:84`,
`REPLICA_UNPREMULTIPLY`) replaced the three quotients with a **constant colour**.
That removes the divides, and it also removes every use of `sums[0..2]`. The
compiler is then free to drop the R/G/B multiply-accumulates of the interpolation
feeding them, and the divide latency left the critical path. The 153.98 ms
(real-mixed) and 382.67 ms (image-heavy) are an upper bound on "everything that
depends on RGB", not the cost of the division and quantization. A rewrite that must
keep the exact quotient cannot recover that.

## Checklist status

```
☑ located: 5 call sites, src/affine_image.c (list above)
☑ alternating A/B: image-heavy-100 @1200, real-mixed-120 @1200 (and vector, word, pptx)
☑ pixel equivalence: 353,143,200 + 111,897,000, 0 different (B/F algorithm); 88.66 M-case harness, 0 mismatches (E, F)
– ctest 577/577: not run. src/ is unchanged from main, so nothing new to test
– small-fixture gates / RSS: not applicable (no code change)
```

## Recommendation

Drop this lane. To make the RGB sink faster, change the amount of work per pixel
rather than how the divide is done. One option is to skip the 2×2 supersample when
the four taps fall on the same texel pair. Another is to share the bilinear
weights across the supersample. Before choosing, re-run the sink2 decomposition
with a probe that keeps the quotient's data dependency, for example by feeding
`sums[0]^sums[1]^sums[2]` into a volatile sink, so each stage's cost is
measured without dead-code elimination.

## Files

- `build.py`: builds the tagged DLLs (`build-*.json` records DLL and source hashes)
- `count.py`, `count.json`: per-fixture pixel counts through the loop
- `equivalence.py`, `equivalence.json` (E), `equivalence-F.json`: bit-exactness harness
- `pixels.json`: full-render byte equality, A vs B
- `interleaved_ab.py`, `interleaved*-*.json`, `interleaved*.log`: interleaved A/B
- `null-AA-word-1200.json`, `swap-CA-word-1200.json`: noise floor and arm-order control
- `run_timing.py`, `timing-*-ab.json`, `timing.log`: earlier `bench_real_doc` paired runs (A vs B)
