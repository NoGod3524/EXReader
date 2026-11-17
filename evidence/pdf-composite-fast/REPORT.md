The normal RGBA layer compositor now batches full-coverage rows and removes per-pixel opacity rounding from the unit-opacity path. The 1200 px fresh-process first-render p50 meets the supplied 13 ms target. The 4 ms repaint target remains unmet.

`src/blend.c` admits only unit opacity, normal blend, four-channel source/target, no target precision buffer/soft mask/shape/knockout/gray/CMYK, and no source shape/CMYK or non-isolated precision semantics. A bitwise row reduction checks clip bytes and source alpha. Fully covered opaque rows use `memcpy`; mixed-alpha rows retain `exr_pixel` integer arithmetic, with direct copies for opaque pixels. Partially clipped rows retain the generic loop and use the known source alpha directly. An opaque source replaces any destination alpha exactly.

Work charges remain one scan unit per row pixel plus one blend unit per nontransparent source pixel. The fast row reserves the maximum blend charge and refunds transparent pixels. If that reservation would exceed the budget, the generic row preserves the exact failure point, partial writes, and work counter. Cancellation remains one entry poll plus one poll per row. CMYK, gray, knockout and soft-mask branch bodies are unchanged.

`src/vector.c` adds a fixed four-byte store loop for unmasked, fully covered, opaque colored rectangle spans. Four-byte `memcpy` stores permit unaligned bitmap rows without aliasing casts. Rectangle coverage calculations are unchanged. Production PDF parsing, fonts and images are unchanged.

Baseline is pinned to `b9f4d5c9b0aef7ed5798b594beaa8450969219c7`. During this session the branch history was rewritten externally from the initially observed `b86e8d8d9`; the canvas/blend/vector source hashes matched. The final baseline was rebuilt from the pinned HEAD source copies using the same Ninja compile/link commands and unchanged objects. The original DLL and capture remain locally in `build/pdf-composite-fast/baseline` and the ignored `before` directory. [Provenance](provenance.json) records source, DLL, input and script hashes.

Local native C measurements: Windows 11, Intel Core Ultra 7 256V, eight logical CPUs, Balanced power plan, MinGW GCC 16.2.0, Release, PDF and PDF editing enabled. [Machine record](machine.json). Builds, CTest and performance captures ran sequentially. Disk cache, processor frequency and unrelated background load were uncontrolled. The three tables below are separate workloads/captures; their timings are not interchangeable.

Input: the 20-page PowerPoint PDF [pptx-20.pdf](../../tests/fixtures/pdf-hybrid-real/pptx-20.pdf), SHA-256 `2bfb94aa6905f27915e309b3c820fef3ba13492dddedfb93d97a10e8d7679729`.

Fresh-process comparison uses 20 before/after pairs per width, alternating AB/BA order. Each process loads its DLL before timing, opens the document once, renders page 1 once, then repaints it eight times. First-render p50 has 20 samples per implementation/width; repaint p50 pools 160 samples. These are repeated page-1 renders, not UI page navigation. All raw samples and process order are in [fresh-process.json](fresh-process.json); collector: [benchmark_pdf_composite.py](../../tools/benchmark_pdf_composite.py).

| Width | HEAD first-render p50 ms | Optimized first-render p50 ms | HEAD repaint p50 ms | Optimized repaint p50 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1200 | 22.176700 | 10.932900 | 21.379550 | 10.124550 |
| 2400 | 64.139750 | 28.514350 | 63.880450 | 28.098400 |

The supplied PDF.js targets (13 ms first screen, 4 ms repaint) were not remeasured here. First-render p50 meets 13 ms; repaint remains above 4 ms. At 1200 px, open plus first render has an optimized p50 of 11.484850 ms.

Cold native open, after DLL loading, from those same fresh processes:

| Width | HEAD open p50 ms | Optimized open p50 ms | HEAD open p95 ms | Optimized open p95 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1200 | 0.615050 | 0.575650 | 1.067700 | 0.693300 |
| 2400 | 0.447000 | 0.451900 | 0.544600 | 0.567600 |

At 2400 px the measured cold-open p50 is 0.004900 ms higher, so the strict no-increase criterion is not established at that width.

The existing [benchmark_pdf_rect.py](../../tools/benchmark_pdf_rect.py) independently warms all 20 pages once, then measures nine full sequential rounds: 180 renders per width. Render timers include bitmap allocation and drawing, and exclude pixel copying/hashing, PNG encoding and bitmap freeing. p50 is the median; p95 uses nearest rank. [HEAD raw data](head-before/summary.json), [optimized raw data](after/summary.json).

| Width | HEAD render p50 ms | Optimized render p50 ms | HEAD render p95 ms | Optimized render p95 ms | p50 speedup |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1200 | 12.309200 | 5.457900 | 13.116900 | 6.224100 | 2.255x |
| 2400 | 56.135600 | 20.931650 | 67.141500 | 21.849300 | 2.682x |

Pixel identity against pinned HEAD: **81,000,000 active RGBA pixels, zero different pixels, maximum channel difference 0, RMSE 0** across all 20 pages at both widths. All 40 PNG pairs are byte-identical. Every captured render also matches its warmup hash. The compare command decompresses both snapshots, validates their hashes and compares every active pixel. [Pixel report](head-diff/diff.json), [output](pixel-head-diff.log).

A separate timing DLL instruments copies of canvas, blend, vector and fixed-page draw sources. QueryPerformanceCounter totals cover page 1 over nine draws (one first draw and eight repaints). The following values are measured totals divided by nine, in ms per render. The last two phase rows are timer differences: draw time outside the listed canvas functions, and render setup/finish outside canvas create/clip/draw.

| Phase, mean ms/render | HEAD 1200 | Optimized 1200 | HEAD 2400 | Optimized 2400 |
| --- | ---: | ---: | ---: | ---: |
| Layer composite | 8.392122 | 0.368833 | 33.456956 | 1.639467 |
| End-layer outside composite | 0.169500 | 0.136156 | 0.604667 | 0.505978 |
| Canvas allocation/background | 0.820944 | 0.796544 | 3.287800 | 2.928933 |
| Initial canvas clip | 0.235489 | 0.273433 | 0.993156 | 0.730678 |
| Begin group / clip scan / working buffer | 0.708167 | 0.715956 | 2.926944 | 2.697789 |
| Canvas paths | 2.618911 | 2.528344 | 9.001656 | 8.604322 |
| Canvas images | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Public clip-union add | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| Clip-union commit | 0.000222 | 0.000278 | 0.000367 | 0.000289 |
| Fixed-page draw outside profiled canvas calls | 2.050978 | 2.209178 | 4.858156 | 4.483344 |
| Other render setup/finish | 0.129278 | 0.104533 | 0.182822 | 0.149578 |
| Total native render | 15.125611 | 7.133256 | 55.312522 | 21.740378 |

Nested vector timers overlap the canvas path/clip timings above. Their totals over the same nine draws are:

| Vector category, total ms over nine renders | HEAD 1200 | Optimized 1200 | HEAD 2400 | Optimized 2400 |
| --- | ---: | ---: | ---: | ---: |
| Rectangle coverage masks | 1.018300 | 1.257000 | 39.382200 | 34.378100 |
| Rectangle RGBA fills | 11.519100 | 10.598800 | 47.469800 | 45.749200 |
| General vector RGBA fills | 11.322600 | 11.353400 | 32.468000 | 30.703900 |

The remaining measured costs are canvas path drawing, fixed-page draw work outside those canvas calls, allocation/background initialization and group setup.

[1200 HEAD profile](profile-head-before-1200.json), [1200 optimized profile](profile-after-1200.json), [2400 HEAD profile](profile-head-before-2400.json), [2400 optimized profile](profile-after-2400.json); [profiler source](profile_composite.py). These diagnostic runs are separate from the uninstrumented acceptance captures.

Final full CTest: **585/585 passed, zero failures, zero skipped**. [Final log](ctest-final.log), [JUnit](ctest-final.xml). Native vector executable: **38,707 checks passed**. The added compositor regression covers all source/destination alpha pairs, opaque/transparent/mixed rows, full/partial clips, padded and unaligned strides, offsets, isolated source bounds, alpha-source flags, non-unit opacity, cancellation polling and the exact budget-exhaustion prefix/work count. [Regression output](vector-regression.log).

The initial full run passed 584 tests and found only a stale SPDX checksum for `docs/READER-DISTRIBUTION-INVENTORY.md`. Regenerating the package SBOM updates that document digest and the aggregate verification code; the final complete run passes. [Initial run](ctest.log), [SBOM refresh](sbom-refresh.log).

Reproduce with the same configured Release Ninja build and dependencies:

```powershell
./evidence/pdf-composite-fast/reproduce.ps1
```

The [reproducer](reproduce.ps1) builds the native baseline/candidate, captures both widths and every page, runs the exhaustive pixel diff, alternates fresh-process measurements, captures phase timings and runs the complete CTest suite. The baseline relink is specific to this patch: its only production changes are `src/blend.c` and `src/vector.c`.

Branch: `perf/pdf-fast-rect`. Acceptance: exact pixels and 1200 px first-render p50 achieved; 4 ms repaint remains unmet; the 2400 px cold-open median is slightly higher in the paired sample.
