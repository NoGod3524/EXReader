# Shading / soft-mask follow-up after PR #254

Base: `6e11e8c95` (current main at capture; includes #254 and #253). Branch: `perf/shading-in-softmask`.

The largest measured component on real-mixed p2 is image painting: **42.868 ms**. A one-axis shear prevents the largest individual image call from using the existing axis-aligned row cache. Reusing converted source rows for that shear reduces its scoped paint from **21.217 to 10.267 ms**. Final production p2 p50 is **64.213 → 53.697 ms**.

**The strict no-p95-increase requirement is not fully met:** mixed-120 p95 is **47.314 → 47.851 ms (+1.13%)**. The two 100-page fixtures decrease. This PR is left as a draft, unmerged.

## Measurement discipline

- Production A: DLL SHA-256 `497f91a3111de6fd0abe1743b9cc6ed2f48fb09fb01f5a42e5920cadc3a47eb5`.
- Production B: DLL SHA-256 `fc06363ab39e1c51a275c4c9681d4fbaf11183ffbb7494595603c6d6f1e7258c`.
- Windows 11, MinGW GCC 16.2.0, Release `-O3 -DNDEBUG`, Balanced power plan. [Environment](environment.json) · [forced relink timestamps and hashes](final-build.json) · [build output](build-logs.json).
- Final native runs load both DLLs in one process and alternate AB/BA on every page; starting order reverses on successive sweeps. Seven measured large-fixture sweeps and 41 small-fixture sweeps follow one pixel/hash warmup. p50/p95 use all measured render calls; p95 is nearest rank. Throughput is pages divided by the median sweep sum. No samples are discarded.
- The ≤15% system CPU idle gate fails closed and retries the same batch. It runs before each large sweep and each five-sweep small batch. Final native prechecks: 2.335–14.453%. Builds and CTest ran before these captures.
- [Native runner](run_paired.py) · [per-page alternating harness](paired_sweep.py) · [raw samples](paired/) reuse `tools/bench_real_doc.py` bitmap definitions, geometry, hashes and idle gate. Cohorts use the committed `page-content.json` and `cohorts.json` definitions.
- The earlier fresh-process pilot is preserved under [pilot-fresh-process/](pilot-fresh-process/). Its B DLL is `350212ce…`, before the success-error reset was restored. It is not the final production DLL. [Initial p2 pilot](candidate-p2.json).

## Post-#254 p2 ablations at 1200 px

Both diagnostic arms have the same lightweight instrumentation. Each case alternates nine AB/BA pairs and discards its first pair; the remaining eight supply the medians. The full arm remains enabled in every pair.

| Disabled class | Full control (ms) | Disabled/full result (ms) | Median paired saving (ms) |
| --- | ---: | ---: | ---: |
| Full | 64.169 | 64.042 | +0.144 |
| Shading (`sh`, including inside masks) | 63.706 | 43.852 | +19.741 |
| Graphics-state soft mask | 64.150 | 77.171 | -12.774 |
| Shading + soft mask | 65.419 | 44.943 | +20.525 |
| Images (before decode) | 63.895 | 22.794 | +40.944 |

Skipping the soft mask changes later painting and is slower here. These interventions overlap and are not an additive time partition. [Raw ablation pairs](ablation-light.json) · [capture harness](page2.py).

### Scoped attribution

| Lightweight scope | Median ms | Calls/p2 |
| --- | ---: | ---: |
| Image painting | 42.868 | 3 |
| Warm image load | 0.002 | 3 |
| Soft-mask build (inclusive) | 14.176 | 1 |
| Mask raster (inside build) | 12.745 | 1 |
| Gradient paint inside mask (inside raster) | 6.230 | 1 |
| Mask group commit (inside raster) | 3.342 | 1 |
| Mask conversion / transfer | 1.329 | 1 |
| Page gradient paint | 4.267 | 1 |
| Build gradient tables | 0.041 | 2 |

The colour-stop-search hypothesis does not describe this code: `pdf_shading.c` already builds 512-entry tables and directly indexes/interpolates adjacent entries. Two tables are constructed on p2; their combined construction scope is 0.041 ms. There is no per-pixel walk over colour stops.

The separate call-by-call timer build records **128,640 source samples**, **126,496 colour-table lookups** and **124,352 out-of-scale normalizations**. Its median lookup scope is **2.868 ms**, normalization is **3.025 ms**, and inclusive source sampling is **12.471 ms**. These include timer overhead: that diagnostic changes full p2 from **65.855 to 78.762 ms** in its alternating control. They are instrumented upper bounds, not extrapolated production costs. [Detailed timer pairs](ablation.json).

Mask compositing is visible separately in the 3.342 ms mask group commit; mask conversion costs 1.329 ms. Both are smaller than the 42.868 ms image-paint component. Inclusive scopes overlap. A production percentage split of the former “5×” into lookup/mask/other is not supported by these timers; the current end-to-end ratios are measured below.

Temporary attribution code is preserved as [a patch](diagnostic.patch.gz), [timer source](diagnostic.c), and [header](diagnostic.h). To reproduce on the base commit, decompress the patch, apply it with `git apply --ignore-space-change`, copy the source/header to `src/exr_diag.c` and `src/exr_diag.h`, then build. `exr_diag_sample` returning 1 enables the detailed timers; returning 0 gives the lightweight scopes. These files and switches are absent from production.

## Largest remaining image call and change

Image-call scopes use seven alternating fresh-process A/B pairs, two warm renders per child, and a gate before each pair. [Probe builder](image_probe.py) · [capture runner](image_trace.py) · [raw scopes](image-scopes.json).

| Image | A warm paint (ms) | B warm paint (ms) |
| --- | ---: | ---: |
| 1500×1125 background | 19.599 | 19.327 |
| 1920×154 footer | 2.679 | 2.662 |
| 1073×789 sheared illustration | 21.217 | 10.267 |

Median of the three-image paint total per warm render: **43.817 → 32.523 ms**.

The illustration matrix has `m[1] = 0.0000508333333`, `m[2] = 0`. The existing bilinear-axis path rejects that nonzero shear. The new helper precomputes horizontal taps and reuses the existing converted-row/SSE2 sampler when both vertical taps stay on the same source rows across a destination row. It handled **473 cached rows and 2 scalar crossing rows** on p2. It preserves the original coordinate expressions, weights, tap/supersample addition order, rounding, clipping, cancellation and work charges. Allocation failure and unsupported transforms retain the generic path.

No shading precision or sampling density changes. No pptx/Word source changes. The instrumented new renderer processed **zero rows** on every page of pptx-20, deck and word-5 at 1200 px. [Small-path trace](small-paths.json) · [trace runner](check_small_paths.py).

## Final production A/B

| Fixture @1200 | p50 A → B (ms) | p95 A → B (ms) | p95 Δ | Throughput A → B (pages/s) |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 6.266 → 6.194 | 47.314 → 47.851 | +1.13% | 73.72 → 74.36 |
| image-heavy-100 | 13.576 → 13.631 | 116.731 → 116.715 | -0.01% | 26.27 → 26.31 |
| vector-heavy-100 | 11.801 → 11.824 | 47.032 → 46.854 | -0.38% | 69.75 → 70.48 |

| Gradient + soft-mask cohort | Pages | A Σ page p50 (ms) | B Σ page p50 (ms) |
| --- | ---: | ---: | ---: |
| real-mixed-120 | 21 | 983.375 | 972.697 |
| image-heavy-100 | 10 | 564.242 | 543.395 |
| vector-heavy-100 | 10 | 475.046 | 471.170 |

### Fresh current PDF.js comparison

PDF.js 3.11.174 / node-canvas 3.2.3. `tools/bench_large_vs_pdfjs.py` alternates EXReader/PDF.js, PDF.js/EXReader, EXReader/PDF.js, each arm idle-gated and in a fresh process, with five warm sweeps after a cold sweep. Cohorts sum the per-page p50 medians across the three repeats. These are contemporary measurements, separate from the native A/B above. [Runner](pdfjs_ab.py) · [summary and metadata](pdfjs-current.json) · [raw repeats](.raw-pdfjs-current/).

| Gradient + soft-mask cohort @1200 | Pages | EXReader Σ p50 (ms) | PDF.js Σ p50 (ms) | Ratio |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 21 | 977.840 | 634.677 | 1.541× |
| image-heavy-100 | 10 | 598.338 | 284.123 | 2.106× |
| vector-heavy-100 | 10 | 485.307 | 307.294 | 1.579× |

| Whole document @1200 | EXReader p95 (ms) | PDF.js p95 (ms) | EXReader pages/s | PDF.js pages/s |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 47.961 | 33.809 | 73.46 | 88.87 |
| image-heavy-100 | 132.860 | 29.396 | 24.45 | 64.55 |
| vector-heavy-100 | 48.380 | 29.946 | 70.64 | 102.06 |

Fresh-process p95 is the median of the three repeat-level pooled p95s. Its definition and process/session conditions differ from the native per-page alternating experiment; both experiments are retained.

### Small-fixture guards

| Fixture | A p50 (ms) | B p50 (ms) | Δ | Reference +3% ceiling (ms) |
| --- | ---: | ---: | ---: | ---: |
| pptx-20-600 | 0.824 | 0.821 | -0.39% | 0.971 |
| pptx-20-1200 | 1.643 | 1.645 | +0.12% | 2.182 |
| deck-1200 | 13.695 | 13.705 | +0.07% | 16.892 |
| word-5-1200 | 6.016 | 5.988 | -0.46% | 6.386 |

All four p50 changes are within ±3% and below their absolute ceilings. The remaining 600/2400 px captures are retained in [paired/](paired/) and [summary.json](summary.json).

## Pixel and native checks

- Large PDFs: **353,143,200** active RGBA pixels compared, zero mismatched pages.
- Small fixtures: **111,897,000** active RGBA pixels compared, zero mismatched pages.
- Total: **465,040,200** pixels, zero differences by per-page active-RGBA SHA-256.
- Existing `native-pdf-image` now adds 96 sheared placements/opacity/clip/colour combinations against an opaque-unit-mask generic sampler. It also checks success clears a prior error.
- **CTest 577/577**, 195.81 seconds. [Full output](ctest.txt).
- `git diff --check` passed.

## Acceptance

- Five-row post-#254 p2 ablation and scoped attribution: recorded above.
- Three current gradient cohort ratios ≤2.5×: see contemporary comparison above.
- Strict p95 nonregression: **not fully met**; mixed-120 increases 0.537 ms / 1.13%. Both 100-page fixture p95 values decrease.
- Small p50 guards, exhaustive pixel equality and 577 native tests: passed.
- PR remains draft and unmerged.

## Reproduce final captures

```powershell
cmake --build build/test --parallel 6
ctest --test-dir build/test --output-on-failure
python evidence/shading-in-softmask-20261118/image_probe.py
python evidence/shading-in-softmask-20261118/image_trace.py
python evidence/shading-in-softmask-20261118/check_small_paths.py
python evidence/shading-in-softmask-20261118/run_paired.py
python -X utf8 evidence/shading-in-softmask-20261118/pdfjs_ab.py --library out/shading-final/libexreader.dll --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2 --case real-mixed-120=tests/fixtures/pdf-large/real-mixed-120.pdf:120 --case image-heavy-100=tests/fixtures/pdf-large/image-heavy-100.pdf:100 --case vector-heavy-100=tests/fixtures/pdf-large/vector-heavy-100.pdf:100 --widths 1200 --runs 5 --repeat 3 --idle-timeout 45 --out evidence/shading-in-softmask-20261118/pdfjs-current.json
python evidence/shading-in-softmask-20261118/summarize.py
python evidence/shading-in-softmask-20261118/write_report.py
```

Keep the baseline A DLL in `out/shading-base/libexreader.dll`. `image_probe.py` temporarily instruments the baseline and current source, restores the current source in `finally`, deletes the production DLL, rebuilds it, and saves the result as `out/shading-final/libexreader.dll`. Run builds, tests and timing phases sequentially.
