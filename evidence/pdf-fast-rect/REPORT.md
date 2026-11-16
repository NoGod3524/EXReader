The rectangle fast path is implemented and pixel-identical on the 20-page PowerPoint fixture. The PDF.js timing targets remain unmet: page 1 at 1200 px has a warmed render p50 of 24.312 ms, above both supplied targets (13 ms first screen, 4 ms turn).

`src/vector.c` recognizes connected, alternating axis-aligned sides with `EPS = min(1e-6, 1e-9 * max(1, coordinate magnitude))`. Coordinates are not rounded to integers. Fully covered spans retain the integer rectangle bulk stores (including grayscale `memset`); edge/corner alpha is `floor(255 * intersection_width * intersection_height + 0.5)`. The existing clip multiplication and RGBA/CMYK/blend/state compositors are retained. Coverage uses scalar locals and allocates no crossings array, row coverage, or page mask. Persistent canvas clip masks remain in the existing canvas implementation.

Repeated coincident rectangle contours use the same analytic coverage, with nonzero winding and even-odd cancellation preserved. This keeps duplicate annotation appearances identical to a single appearance. Other polygons, curves, distinct rectangle compounds, PDF parsing, font and image code retain their existing paths.

Measurements were collected locally on 2026-11-16: Intel(R) Core(TM) Ultra 7 256V, 8 logical CPUs, Windows-11-10.0.26200-SP0, Balanced power plan; gcc (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r1) 16.2.0. Native build: Release, PDF and PDF editing enabled, default features retained. Disk cache, processor frequency and unrelated background activity were uncontrolled. Builds and CTest were not run concurrently with the performance captures.

Input: [`pptx-20.pdf`](../../tests/fixtures/pdf-hybrid-real/pptx-20.pdf), 60,423 bytes, 20 pages, Microsoft PowerPoint export; SHA-256 `2bfb94aa6905f27915e309b3c820fef3ba13492dddedfb93d97a10e8d7679729`. The fixture manifest records the same identity. Baseline was built before editing production sources at `48f46bea24198b24a2fa416aeaf7f4ad31e14184`, equal to `origin/main` at the start. Its DLL is preserved locally under `build/pdf-fast-rect-baseline/`. [Provenance](provenance.json) records both DLL hashes and final source hashes.

The standard-library Python collector calls the native C ABI through `ctypes`. Each width uses a fresh process. It times five structure opens, then warms every page once and measures five complete sequential rounds (100 measured renders per width). Render time includes native bitmap allocation and drawing; PNG encoding, pixel copying/hashing and bitmap freeing are outside the timer. p50 is the median; p95 uses nearest rank (the maximum for a five-sample page). The raw files contain every page and every timing.

| Width | Baseline open p50 ms | Optimized open p50 ms | Baseline render p50 ms | Optimized render p50 ms | Baseline render p95 ms | Optimized render p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1200 | 0.241600 | 0.236700 | 213.788550 | 27.409150 | 255.553000 | 32.702300 |
| 2400 | 0.575800 | 0.234600 | 820.323500 | 119.306050 | 977.917300 | 151.610900 |

Render percentiles above pool the 100 measured page draws at each width. The following table keeps the same-page comparison explicit; each entry is a median of five draws.

| Page | 1200 baseline p50 ms | 1200 optimized p50 ms | 2400 baseline p50 ms | 2400 optimized p50 ms |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 218.103300 | 24.312000 | 778.162300 | 120.972600 |
| 2 | 196.845500 | 24.738200 | 755.249600 | 122.311700 |
| 3 | 194.137100 | 27.765300 | 741.718300 | 129.379900 |
| 4 | 208.943300 | 27.491100 | 789.898100 | 112.839500 |
| 5 | 205.954500 | 22.934700 | 782.990200 | 113.193700 |
| 6 | 226.007400 | 26.772800 | 773.344100 | 115.715700 |
| 7 | 207.367800 | 25.929700 | 799.458500 | 120.517300 |
| 8 | 206.667900 | 27.994500 | 844.759300 | 110.939500 |
| 9 | 205.599800 | 28.152200 | 824.445000 | 117.425200 |
| 10 | 213.473900 | 27.968300 | 823.020700 | 113.924900 |
| 11 | 220.753300 | 23.480200 | 857.236200 | 121.147700 |
| 12 | 225.608900 | 20.763300 | 845.502000 | 125.537800 |
| 13 | 209.766500 | 22.525500 | 834.180700 | 115.583500 |
| 14 | 221.864300 | 27.125600 | 798.136400 | 118.433000 |
| 15 | 223.965900 | 28.853100 | 840.649200 | 119.481800 |
| 16 | 210.579500 | 29.142000 | 860.366900 | 123.589100 |
| 17 | 219.090200 | 28.201900 | 848.767700 | 113.315100 |
| 18 | 229.028600 | 28.488500 | 788.265800 | 125.251500 |
| 19 | 211.732300 | 30.981700 | 846.784100 | 117.441800 |
| 20 | 221.705600 | 28.038000 | 855.461700 | 122.596000 |

PDF.js reference from the handoff: **1200 px first screen 13 ms; turn 4 ms**. These were supplied comparison targets, not PDF.js measurements made in this run. The optimized first, unwarmed draw of page 1 was 24.428400 ms at 1200 px. Neither the first draw nor the warmed page-1 p50 meets the supplied targets.

Doubling width quadruples pixels (1200×675 to 2400×1350). The measured pooled p50 ratio was 3.837079× before and 4.352782× after. Measured p50 speedups are 7.799897× at 1200 px and 6.875791× at 2400 px. No timing is extrapolated.

[Before raw measurements](before/summary.json), [after raw measurements](after/summary.json). Individual width JSON files also retain the five structure-open samples, first-draw samples, per-page p50/p95, five full measured rounds and RGBA hashes.

**Pixel result:** 81,000,000 active RGBA pixels compared across all 20 pages at both widths; **zero different pixels, maximum channel delta 0, RMSE 0**. All 40 before/after PNG pairs are also byte-identical. Every measured round matches its warmup pixel hash. [Exhaustive comparison](diff/diff.json), [comparison output](pixel-diff.log), [baseline PNG example](before/1200-page-001.png), [optimized PNG example](after/1200-page-001.png). No baseline waiver or replacement was needed for this PDF.

**Correctness/build checks:** baseline and final `cmake --build build/perf --parallel 6` completed with exit 0; final full CTest passed **585/585, zero failures and zero skipped**. The vector executable passed **38,668 checks**. New tests use integer arithmetic on an eighth-pixel grid as an independent area oracle and cover negative/clipped coordinates, subpixel rectangles, both windings/fill rules, coincident contours, clip masks, transparent paint, grayscale/RGBA, all blend modes, soft-mask states, CMYK, near-integer edges and rejection of a slanted quadrilateral. Existing cancellation, work limits, degenerate and scanline equivalence checks remain. The first full CTest caught the coincident-annotation issue; it was fixed in rectangle recognition without changing the annotation test or PDF writer. [Final CTest](ctest.log), [JUnit](ctest.xml), [vector output](vector-final.log), [baseline build](build-baseline.log), [final build](build-after.log).

A separate DLL compiled from timing-instrumented source copies profiles page 1 over nine renders (one first draw plus eight repaints). Its timers use QueryPerformanceCounter. The instrumented runs are diagnostic measurements, separate from the uninstrumented acceptance captures. Vector and canvas timers are inclusive and overlap; their times must not be summed across layers.

| Instrumented page 1, nine renders | 1200 px total ms | 2400 px total ms |
| --- | ---: | ---: |
| Rectangle coverage masks | 5.643000 | 104.394900 |
| Rectangle RGBA fills | 39.785600 | 91.772600 |
| General vector RGBA fills | 32.463100 | 75.030000 |
| `exr_canvas_end_layer` | 191.918300 | 781.126100 |

The measured remaining hotspot is isolated-layer finalization (`src/canvas.c:613`). That function calls `exr_composite_frame` before releasing the layer. The next task is to time the inner compositor and add a proven bulk case for normal opaque layer composition, then rerun these exact pixel comparisons and timings. This change leaves production `canvas.c`, `blend.c`, PDF parsing, fonts and image code untouched. [1200 diagnostic output](profile-1200.txt), [2400 diagnostic output](profile-2400.txt), [reproducer](profile_vector.py).

The initial search also tested the separate 15-page `pdf-ppt/deck.pdf`: baseline 1200 px p50 2272.361000 ms; baseline 2400 px hit the existing `EXR_LIMIT` vector work budget. Those results are excluded from the 20-page tables. Its initial raw 1200 capture and PNGs remain locally in `before-proxy-15/`; [failure output](benchmark-proxy-15-before.log) is retained. The work budget was not raised.

To reproduce on this checkout, first build baseline commit `48f46bea24198b24a2fa416aeaf7f4ad31e14184` in a workspace-local checkout and preserve its DLL, then build this branch with identical flags/dependencies. The eight valid supplied dependency caches were reused. The supplied OpenJPEG cache contained object files rather than sources, so `FETCHCONTENT_SOURCE_DIR_OPENJPEG` was left empty and CMake fetched the pinned, hash-verified sources into `build/perf/_deps`. Other missing pinned dependencies were also fetched inside the build directory. CMake TLS used a workspace-local PEM bundle exported from Windows trusted certificates; certificate verification remained enabled.

```powershell
python -c "from pathlib import Path; import ssl; Path('build').mkdir(exist_ok=True); Path('build/pdf-fast-rect-ca.pem').write_text(''.join(ssl.DER_cert_to_PEM_cert(x) for x in ssl.create_default_context().get_ca_certs(binary_form=True)),encoding='ascii')"
$rectDeps = '<home>/exr-deps-cache'
$rectArgs = @('-S','.', '-B','build/perf','-G','Ninja','-DCMAKE_BUILD_TYPE=Release', '-DEXR_ENABLE_PDF=ON','-DEXR_ENABLE_PDF_EDIT=ON')
$rectArgs += "-DCMAKE_TLS_CAINFO=$((Resolve-Path -LiteralPath 'build/pdf-fast-rect-ca.pem').Path)"
foreach ($rectDep in @('freetype','mbedtls','zlib','expat','miniz','libwebp','libtiff','libavif')) {
  $rectArgs += "-DFETCHCONTENT_SOURCE_DIR_$($rectDep.ToUpper())=$rectDeps/$rectDep-src"
}
cmake @rectArgs -DFETCHCONTENT_SOURCE_DIR_OPENJPEG=
cmake --build build/perf --parallel 6
python tools/benchmark_pdf_rect.py capture --library build/pdf-fast-rect-baseline/libexreader.dll --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 --output evidence/pdf-fast-rect/before
python tools/benchmark_pdf_rect.py capture --library build/perf/libexreader.dll --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 --output evidence/pdf-fast-rect/after
python tools/benchmark_pdf_rect.py compare --before evidence/pdf-fast-rect/before --after evidence/pdf-fast-rect/after --output evidence/pdf-fast-rect/diff
ctest --test-dir build/perf --output-on-failure --parallel 6
python evidence/pdf-fast-rect/profile_vector.py
```

Files changed: `src/vector.c` (production rectangle rasterization), `tests/test_vector.c` (area/winding regression checks), `tools/benchmark_pdf_rect.py` (stdlib timing/pixel collector), and this evidence directory (raw measurements, PNGs, active RGBA snapshots, test results, profiler and report). Branch: `perf/pdf-fast-rect`; draft PR to `main`, with the performance acceptance target outstanding.
