# Masked interpolated image resampling

At 1200 px, fresh same-process p71–100 improved from **87.902 to 35.685 ms/page** (**59.40% less time**), meeting the ≤60 ms/page target. Fresh image-heavy peak RSS medians were **146.95 → 146.69 MiB**. The maximum process peaks across the four repeats were 147.32 → 146.88 MiB.

Continuation of `51d3f69c2`; production fix retained from `b515fe418`. The measurements below distinguish the committed diagnostic captures from the fresh continuation captures. Decode remains excluded by the prior cache-cap experiment; the cache limit is unchanged.

## Content difference

Image dictionaries and every drawn image/clip were enumerated without decoding image data ([script](content.py), [records](continuation/content.json)). The PDF SHA agrees with `../real-doc-throughput-20261118/page-content.json`; cohort boundaries follow `../pdfjs-large-doc-20261118/cohorts.json`.

| Property | p11–40 | p41–70 | p71–100 |
| --- | --- | --- | --- |
| Image draws/page | 9 | 1 | 3: background + two tiles |
| Distinct drawn image XObjects/page | 6 or 7 | 1 | 3 |
| Color source dimensions | 1342×757; four 190×160 + four 95×62 draws | 640×480 | background 960×720, 1200×675, 800×600, 1024×512, 720×540 (six pages each); tile 1: 320–416×240; tile 2: 256×192–256 |
| Color `/Interpolate` | false | false | true on all 90 draws |
| Soft mask | 9/page, matching dimensions, DeviceGray, nearest; `/Matte [0 0 0]` | none | background on 18/30 pages; tile 2 on all 30; matching dimensions, DeviceGray, nearest, no Matte |
| Clip operators/page | 57 even-odd | 2, 32 or 33 even-odd | two even-odd + one nonzero |
| Clip path complexity | 49 single-rectangle paths + eight 16-operator paths | single rectangles | all three single rectangles |

Thus this cohort does not interpolate the soft mask twice: it bilinearly samples color and nearest-samples its mask. An even-odd operator alone does not imply a complex path.

## Instrumented baseline and ablations

[build_probe.py](build_probe.py) restores baseline `653e44bde` sources and relinks diagnostic objects. QPC scopes surround background/tile texture blending and clip construction; counters record image calls, decodes, clip presence and eligibility. [compare.py](compare.py) alternates AB/BA per page, reverses the starting order each sweep, and retries a failed ≤15% CPU gate. These are the committed `raw/ablate-mode*.json` captures: one cache-filling sweep excluded, then the mean of per-page warm medians. Both arms use the same diagnostic DLL `1ae0bd5df0da24389e0662eff0ef37a45e9a8728ae565eed9f89f57b4fe66160` with different skip modes. Skip switches exist only in diagnostic builds.

| Disabled category | p11–70 full → disabled, ms/page | Δ removed | p71–100 full → disabled, ms/page | Δ removed |
| --- | ---: | ---: | ---: | ---: |
| All images | 10.728 → 7.247 | 3.481 | 87.065 → 1.992 | 85.073 |
| Soft masks | 10.721 → 16.109 | -5.388 | 88.465 → 31.093 | 57.373 |
| Clip | 10.302 → 8.082 | 2.220 | 94.619 → 86.775 | 7.844 |
| Both tiles | 10.709 → 11.556 | -0.847 | 92.817 → 72.267 | 20.550 |
| Tiles + soft masks | 10.346 → 14.650 | -4.304 | 88.118 → 23.384 | 64.734 |

The scopes in the full arm of the mask-ablation capture partition the render as follows (p71–100; texture blending includes sampling and destination blending, excludes decoding):

| Scoped stage | ms/page | Share of full render |
| --- | ---: | ---: |
| Background texture blend, including its soft mask | 60.440 | 68.32% |
| Both tile texture blends, including tile 2 mask | 21.810 | 24.65% |
| Clip construction | 0.302 | 0.34% |
| Outside those scopes | 5.913 | 6.68% |

Total 88.465 ms/page. Soft-mask ablation removes 57.373 ms/page (64.85%); this overlaps the background and tile scopes. Clip ablation also removes coverage checks during painting. Its delta is not just the clip construction time. The ablation deltas are not an additive partition.

The task’s historical 158 ms/page and 6.7× PDF.js ratio were not reproduced as a same-session baseline here. No exact fraction of that historical ratio can be assigned from these captures. The table above gives measured stage shares and the ablation table gives measured marginal costs, without double counting them.

The background is the largest scoped block. The baseline already has separable bilinear taps and converted-row reuse, but the `!source->mask` eligibility guard excludes these masked interpolated images. The fix extends that existing path to one-level masks: compute horizontal taps once per column, vertical taps once per row, and sample the mask at the same coordinate before adding each color sample. It preserves the generic arithmetic order. Matte reversal, nested masks, non-axis-aligned transforms and composite states retain their existing path. Fast helpers stay out of line to avoid the measured generic-loop regression recorded in the committed candidate experiments.

The probe records 1.0 background and 2.0 tile blend calls/page, and 1.0/2.0 background/tile decode calls/page. The tiles are image XObjects, not a tiling-pattern construction; all 90 drawn image XObject IDs in p71–100 are distinct. Their drawing cost is included above; there is no measured separate pattern rebuild stage. The fix targets the larger background sampler.

## Candidate A/B

Release MinGW build: removed `build/perf/libexreader.dll`, forced a relink, checked the new timestamp and hashes ([build log](build-continuation.txt), [PE section identities](continuation/build-identity.json)). The latter compares the executable code section to the preserved committed candidate; a relink may change the overall PE hash.

The tables below use the captures committed at `51d3f69c2`, in `interleaved/` and `paired/`. Accepted continuation captures follow separately below. Pixel and CTest checks are retained from the committed candidate whose code, constants, data and unwind sections match the relink. All committed same-process idle prechecks returned values below 15% CPU.

Same-process captures load both DLLs and alternate AB/BA on each page, reversing the starting order each sweep. One cold sweep is excluded. Paired Δ is the sum of per-page median (B−A) differences divided by the sum of A page medians; the separate A/B medians are a different aggregation.

| Fixture @ width | A mean page p50, ms | B mean page p50, ms | Median paired Δ / A |
| --- | ---: | ---: | ---: |
| deck @ 1200 | 13.551 | 13.530 | +0.07% |
| image-heavy-100 @ 1200 | 41.688 | 24.765 | -40.98% |
| pptx-20-1200 @ 1200 | 1.618 | 1.606 | -0.35% |
| pptx-20-600 @ 600 | 0.817 | 0.818 | -0.11% |
| real-mixed-120 @ 1200 | 14.311 | 14.296 | +0.01% |
| vector-heavy-100 @ 1200 | 14.020 | 13.978 | -0.65% |
| word-5 @ 1200 | 6.019 | 6.050 | +1.06% |

| Image-heavy cohort | A ms/page | B ms/page | Change |
| --- | ---: | ---: | ---: |
| p11–70 | 11.567 | 11.666 | +0.86% |
| p71–100 | 95.231 | 38.628 | -59.44% |

### Accepted continuation captures

The continuation runner retains only sweeps that passed the ≤15% CPU gate and the process-overlap monitor. Other jobs during idle waits do not invalidate already accepted sweeps. [Raw samples](continuation/).

| Fresh same-process fixture | A mean page p50, ms | B mean page p50, ms | Paired Δ / A |
| --- | ---: | ---: | ---: |
| deck @ 1200 | 13.515 | 13.518 | -0.00% |
| image-heavy @ 1200 | 38.517 | 22.791 | -41.10% |
| pptx-1200 @ 1200 | 1.641 | 1.627 | +0.15% |
| pptx-600 @ 600 | 0.841 | 0.845 | -0.01% |
| real-mixed @ 1200 | 14.036 | 14.044 | -0.37% |
| vector-heavy @ 1200 | 13.903 | 13.883 | -0.36% |
| word-5 @ 1200 | 6.096 | 6.067 | -0.80% |

| Fresh image-heavy cohort | A ms/page | B ms/page | Change |
| --- | ---: | ---: | ---: |
| p11–70 | 10.546 | 10.518 | -0.27% |
| p71–100 | 87.902 | 35.685 | -59.40% |

Fresh-process `tools/bench_real_doc.py` captures alternate AB/BA (four repeats on image-heavy and small fixtures; two on real-mixed/vector-heavy in the committed captures), five warm rounds per child after one cold round. RSS is the median of process peak working sets. These results use whole documents:

| Fixture / capture | p50 A → B, ms | p95 A → B, ms | Throughput A → B, pages/s | Peak RSS A → B, MiB | RSS change |
| --- | ---: | ---: | ---: | ---: | ---: |
| image-heavy-100 / continuation | 13.619 → 13.749 | 121.198 → 58.522 | 25.93 → 44.62 | 146.95 → 146.69 | -0.18% |
| real-mixed-120 / committed | 6.522 → 6.306 | 49.332 → 50.009 | 70.06 → 71.56 | 107.86 → 107.99 | +0.12% |
| vector-heavy-100 / committed | 11.736 → 11.752 | 47.235 → 48.711 | 71.51 → 69.96 | 78.91 → 79.01 | +0.12% |

Partial children in `continuation/.realdoc-paired-real-mixed-120/` came from a gate-aborted duplicate batch and are excluded from every table.


Small-fixture acceptance uses the all-page render p50 from the committed fresh-process paired captures (four repeats × five warm rounds). The relink code/data sections match that candidate:

| Fixture | A p50, ms | B p50, ms | Limit, ms |
| --- | ---: | ---: | ---: |
| pptx-20 @ 600 | 0.864 | 0.841 | 0.871 |
| pptx-20 @ 1200 | 1.639 | 1.617 | 1.768 |
| deck @ 1200 | 13.551 | 13.528 | 15.4 |
| word-5 @ 1200 | 6.094 | 6.038 | 6.5 |

## Correctness

Active-row byte comparison: **353,143,200 + 111,897,000 = 465,040,200 pixels**, **0 differing pixels** ([records](pixels.json)). The large split is 353,143,200; the small split is 111,897,000. The production test adds 144 cases comparing the fast path with a mathematically identical nested-mask generic reference: nearest/interpolated masks, differing source/mask dimensions, flipped/off-target placement, transparent texels, clip coverage, constant alpha, and both source-row conversion branches.

**CTest: 577/577 passed** ([log](ctest.txt)). No cache-cap increase, sampling reduction, interpolation switch-off or drawing omission is present in production.

## Reproduction

```powershell
Remove-Item -LiteralPath 'build/perf/libexreader.dll'
cmake --build build/perf --parallel 4
Get-Item build/perf/libexreader.dll
Get-FileHash build/perf/libexreader.dll
python -X utf8 evidence/resample-path-20261118/content.py
python -X utf8 evidence/resample-path-20261118/verify_continuation.py
python -X utf8 evidence/resample-path-20261118/report.py
```

The rebuilt diagnostic has the same executable `.text` hash as the committed probe, and its exported counter reset/read smoke check passed ([identity](continuation/probe-identity.json), [build log](continuation/probe-build.txt)).

The preserved A DLL is `../resample-dlls/main-653e44b.dll`. To reproduce diagnostics after building the candidate, `build_probe.py` explicitly restores the baseline `affine_image.c` as well as the instrumented canvas/PDF files.
