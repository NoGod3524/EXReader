Items 1 and 3 are implemented with pixel identity. The 1200px render target remains unmet: **9.251300 ms p50**, versus 9.889550 ms for the baseline and the requested 4.00 ms limit. This is a draft performance change.

`src/vector.c` writes opaque RGBA spans with SSE2/NEON stores. `src/blend.c` blends eight pixels per iteration using exact integer division/rounding; transparent destinations retain the original straight-alpha denominator. Scalar fallback remains available. Constant clip runs share the span kernels.

Clip objects cache exact nonzero bounds and whether the enclosed mask is solid 255. Vector fills, affine images, procedural paint, compound paths and group commits intersect their drawing bounds with that region before pixel loops. Empty intersections return immediately; solid rectangles need no per-pixel mask reads. Saved clips share the cached metadata. Group creation reuses it instead of rescanning the page.

`src/fonts.c` and `src/font_outline.c` are unchanged. Item 2 (glyph atlas) is outside this branch; no atlas contribution is claimed.

Measurements below use the unchanged capture timing boundaries in `tools/benchmark_pdf_rect.py`: one warmup round and five measured rounds over all 20 pages, giving 100 render samples per width. Every measurement process uses logical CPU 0 (affinity mask 1) and High priority. Other builds and processor frequency remain uncontrolled. Two earlier series without process controls are retained in [initial captures](initial-captures-with-background-ctest.json) and [repeat captures](uncontrolled-repeat-captures.json); they showed large scheduling/load variation, including a 2400px regression.

| Width | Baseline p50 ms | SIMD only | Regions only | Combined | Combined open p50 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 600 | 3.741450 | 3.602000 | 3.506200 | 3.725450 | 0.244100 |
| 1200 | 9.889550 | 9.285450 | 7.178400 | 9.251300 | 0.235800 |
| 2400 | 33.690600 | 31.698100 | 30.866100 | 31.682900 | 0.286500 |

Raw samples, page hashes, PNGs and compressed RGBA: [baseline](baseline/summary.json), [SIMD only](simd/summary.json), [regions only](region/summary.json), [combined](all/summary.json). The three ablations recompile the four graphics implementation files with identical current private headers and remaining objects. Baseline implementations come from `2b24c3ea8`; their pixels also match the original DLL built before edits ([comparison](diff-baseline-original/diff.json)).

At 1200px, isolated SIMD saves 0.604100 ms and isolated regions save 2.711150 ms. Combined savings are 0.638250 ms; combined is 2.072900 ms above the regions-only median. These sequential captures do not demonstrate additive gains. Width reductions are 600px: 0.428%, 1200px: 6.454%, 2400px: 5.959%. The 600px result does not establish the requested proportional improvement.

1200px open p50 is 0.229000 -> 0.235800 ms, below the 0.70 ms limit. This is the harness open measurement, with disk cache uncontrolled.

**Pixel result:** 85,056,000 active RGBA pixels across 60 page/width pairs; **0 differing pixels, maximum channel delta 0, RMSE 0**. This includes the required 81,000,000 pixels at 1200/2400px plus 600px. SIMD-only and regions-only comparisons also have zero differences. [Combined diff](diff-all/diff.json), [SIMD diff](diff-simd/diff.json), [regions diff](diff-region/diff.json).

**Validation:** CTest 586/586, zero failures and skips ([JUnit](ctest.xml), [log](ctest.log)). SSE2 and forced scalar fallback each pass 1,087,457 vector checks, including all paint-alpha/coverage pairs, sixteen byte alignments, transparent destinations, tails, blend modes and region comparisons. [SSE2](vector-sse2.txt), [scalar](vector-scalar.txt). The procedural-paint test now expects two 4x4 region scans instead of a full-page scan; all 283 checks pass ([output](paint-source.txt)). NEON execution was not tested on this x86 machine.

The diagnostic DLLs time source copies without changing production objects. The following values are **exclusive ns per final output pixel** at 1200px, summed across 100 measured renders. Nested timers are subtracted; allocation/clear/free and other uninstrumented work remain visible. Instrumentation overhead is included, so these totals are separate from acceptance p50 timings.

| Path | Baseline ns/pixel | Combined ns/pixel |
| --- | ---: | ---: |
| Opaque rectangle spans | 0.289122 | 2.039411 |
| Alpha/edge rectangle spans | 0.000000 | 0.001679 |
| Masked rectangle spans | 2.287956 | 0.000000 |
| Vector work outside rectangle spans | 3.893107 | 3.730277 |
| Group commit | 0.566038 | 0.461902 |
| Canvas allocation/clear | 1.596543 | 1.529960 |
| Group creation outside nested timers | 1.425620 | 0.012279 |
| Group end outside commit | 0.246712 | 0.241505 |
| Clip bounds lookup/computation | 0.000000 | 0.406506 |
| Remaining work and timer overhead | 4.096105 | 3.929838 |
| Total | 14.401204 | 12.353358 |

The largest remaining measured buckets are vector work outside rectangle spans, remaining work, opaque spans and canvas allocation/clear. The image, sampled-paint and complex-rectangle buckets had zero calls. [Baseline profile](profile-baseline.json), [combined profile](profile-all.json).

A separate hot-cache benchmark invokes the actual `rectangle_span` implementations: 1200 pixels, 20,000 repetitions, seven samples. It covers alpha 128 even though the PDF baseline has no unmasked alpha-span calls. Values are p50 **ns per visited span pixel**.

| Kernel | Baseline | Combined |
| --- | ---: | ---: |
| Opaque colour | 0.056829 | 0.056671 |
| Alpha 128 over opaque | 1.769379 | 0.413212 |
| Alpha 128, clip 128 | 3.195158 | 0.695625 |

[Kernel raw samples](kernels.json). Opaque stores are already fast in the baseline; the demonstrated kernel gain is in normal alpha blending and constant masked spans.

Run [reproduce.ps1](reproduce.ps1) from this checkout to configure/build, run CTest, construct the ablations, capture/compare all widths, profile both implementations, benchmark kernels and regenerate [results.json](results.json) and this report. It uses valid local dependency caches and workspace-local pinned downloads. [Provenance and tested platforms](provenance.json), [machine](machine.json). No parsing, font-file semantics or antialiasing quality changed.
