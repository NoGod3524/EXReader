# Dense vectors on pages 66–100

Pages 66–100 of vector-heavy-100 accounted for +438.89 ms of the +581.51 ms EXReader–PDF.js gap in the earlier twocells attribution. This lane keeps that denominator and runs new controls only for the isolated cohort. Main already contains #253, which measured and optimized these exact pages by bounding the compound compositor.

## Bilateral ablation

Both engines opened the original PDF and the same incrementally edited PDF. The identity control opened the original bytes in both arms. The timed cohort was pages 66–100 at 1200 px. Each row averages 15 matched warm sweeps across three fresh-process rounds. The driver alternated EXReader and PDF.js page by page, flipped the starting order each warm sweep, and balanced which input was rendered first. All accepted rounds passed the 15% CPU gate (2.34–14.94%). Gap reduction is the full gap minus the omission gap. The percentage uses the earlier +438.89 ms attribution denominator. The range uses the three round means. [Raw captures](ablation/)

| Omitted in both engines | Edits | EXReader full → omit, ms | PDF.js full → omit, ms | Gap full → omit, ms | Gap reduction, ms | Share of 438.89 ms | Round range, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All path paint | 3,010 | 753.39 → 128.91 | 411.38 → 108.31 | +342.01 → +20.60 | **+321.41** | +73.23% | +300.96 to +345.74 |
| All fills | 910 | 781.74 → 529.99 | 429.28 → 398.71 | +352.46 → +131.28 | +221.17 | +50.39% | +209.76 to +243.61 |
| All strokes | 2,975 | 746.28 → 226.90 | 410.92 → 131.33 | +335.36 → +95.57 | +239.79 | +54.64% | +234.22 to +246.03 |
| Polygon fill and stroke | 875 | 759.74 → 447.42 | 412.07 → 348.18 | +347.67 → +99.24 | **+248.43** | +56.60% | +228.22 to +271.71 |
| Polygon fill, keeping stroke | 875 | 784.40 → 555.10 | 437.08 → 404.88 | +347.31 → +150.23 | +197.09 | +44.91% | +187.47 to +215.47 |
| Polygon stroke, keeping fill | 875 | 753.70 → 523.80 | 415.64 → 365.42 | +338.06 → +158.38 | +179.68 | +40.94% | +172.86 to +184.87 |
| Cubic stroke | 2,100 | 753.88 → 466.65 | 418.26 → 182.83 | +335.62 → +283.81 | +51.81 | +11.80% | +32.91 to +61.56 |
| Background fill | 35 | 746.13 → 725.49 | 411.32 → 407.92 | +334.81 → +317.57 | +17.24 | +3.93% | +9.20 to +22.69 |
| Explicit polygon clip | 35 | 772.58 → 640.31 | 434.61 → 302.22 | +337.98 → +338.09 | -0.12 | -0.03% | -5.34 to +5.24 |
| Identity control for absent classes | 0 | 737.46 → 738.42 | 399.49 → 404.57 | +337.97 → +333.84 | +4.12 | +0.94% | +1.52 to +5.59 |

The parsed before/after audit verified every edit. Paint omissions retain path construction and terminate unpainted paths with `n`. Compound omissions of one paint retain the other as `S` or `f*`. The clip edit removes `W` while retaining the geometry and `n`. The paint omissions changed 35 of 35 page hashes in each engine. Clip omission changed 0 of 35 EXReader hashes and 35 of 35 PDF.js hashes. Its gap reduction crossed zero across rounds. The standalone cost of creating the clip is unmeasured by this ablation. The paint omissions overlap, so their reductions cannot be added. [Path and clip operator audit](operator-audit-paths.json) · [Fill and stroke operator audit](operator-audit-fill-stroke.json)

Glyphs, shadings, transparency groups, images, and soft masks were absent on all 35 pages. Page resources were empty, the pages had no `/Group`, and the parsed streams contained no operators for those classes. Their common identity control used the original PDF bytes and changed zero hashes in both engines. Their operator-level reduction is zero. The +4.12 ms row measures timing noise from two identical inputs. [Page audit](page-paths.json)

## Runtime path

At 1200 px, every page issued 60 cubic strokes, 25 even-odd fill+stroke paints, and one background fill. Compounds were 875 of 3,010 paints (29.07%). The parsed PDF path operators per page were 86 moves, 278 lines, 60 cubics, 26 closes, and one rectangle. The canvas received 460 path segments per page, including five for the implicit page clip and five for the explicit clip. The implicit clip hit the identity branch on all 35 pages. The polygon clip was rasterized once per page and was present for all compound and stroke draws. [PDF audit](page-paths.json) · [Per-page runtime counts](probe-counts.json)

All 875 compounds reached the #253 bounded RGB compositor with Normal blend mode, two opaque paints, and no composite state. Its bounds contained 12,760,620 pixels. Of those, 7,728,350 had zero coverage or zero clip, 4,063,030 were solid fill without stroke, 97,260 were solid stroke, and 871,980 needed the general blend. Solid fill and solid stroke accounted for 82.67% of the pixels that reached the blend.

The #245 scanline reuse path reused zero rows across 29,190 polygon-clip rows and 204,410 compound-mask rows. Only 3,446,800 of 69,888,000 edge tests found an active crossing on the standalone strokes (4.93%). The stage counters were collected in the warm sweep of a temporary probe, whose pixels matched the baseline on all 37,800,000 compared pixels. The probe sweep took 1,426.46 ms versus 715.09 ms for baseline. Its scope timings include probe overhead. [Probe patch](probe.patch) · [Compressed trace](probe-trace.txt.gz) · [Probe capture](probe-paired.json)

## Renderer change

On opaque Normal RGBA compounds with no composite state, the renderer stores runs of fully covered fill or stroke directly. Full stroke coverage replaces the fill. Full fill coverage with no stroke replaces the backdrop. Fractional coverage and partial clip bytes still use the compound blend. The optimization retains the existing paint order, cancellation checks, and work charges. A row uses the existing per-pixel path when the remaining budget cannot cover its worst case. The vector test compares a fast row with a budget-limited row across solid fill, solid stroke, partial coverage and clipped pixels.

The spans pilot saved a median 127.62 ms over seven warm sweeps, with a range of 119.57–146.84 ms and zero pixel differences. It added no coverage storage. An active-edge pilot sorted edge start events to avoid scanning most inactive edges but raised the median paired time by 21.90 ms over the spans-only build and was slower in six of seven rounds. The production change is the span path. [Span pilot](pilot-spans.json) · [Active-edge pilot](pilot-active-edges.json) · [Active-edge patch](pilot-active-edges.patch)

The explicit clip already serves every paint within a page. Its stream geometry repeats across pages. Cross-page cache benefits and gains from merging separate paints remain unmeasured.

## Production A/B

Pages 66–100 at 1200 px took **710.66 ms on main** and **587.34 ms with solid spans**, using the median of each arm's 11 warm sweep totals. Every sweep was faster. Median paired savings were **123.33 ms (17.35%)**, with a range of 114.28–131.61 ms. The idle gate opened at 1.99–8.11% CPU busy across the warmup and warm sweeps. [Isolated native A/B](dense-1200.json)

With PDF.js added as C, median sweep totals were 694.08 ms for main, 582.56 ms for solid spans, and 368.55 ms for PDF.js. The median of the per-sweep EXReader–PDF.js gap fell from **+326.33 ms** to **+209.72 ms**, a reduction of **116.61 ms (35.73%)**. The median of the matched A−B savings in that run was 117.62 ms. [Matched three-arm capture](dense-vs-pdfjs-1200.json)

The native runner alternated AB/BA per page, reversed the starting order each sweep, and required valid idle samples at or below 15% CPU before each sweep for the isolated two-arm run and before each three-sweep batch for the three-arm run. The initial render supplied the pixel comparison. The warm sweeps supply the timings.

### Other vector-heavy cohorts

| Cohort | Pages | Main median sweep, ms | Spans median sweep, ms | Median paired change |
| --- | ---: | ---: | ---: | ---: |
| Courseware slides | 1–10 | 422.82 | 420.50 | -0.29% |
| Excel | 11–25 | 168.02 | 170.69 | +1.59% |
| PPTX | 26–65 | 67.27 | 66.55 | -0.25% |

All three median paired changes are within ±3%. The cohort timings come from 11 warm sweeps of the full fixture. [Full fixture A/B](paired/vector-heavy-100-1200.json)

### Small fixture ceilings

| Fixture | Main p50, ms | Spans p50, ms | Change | Ceiling, ms |
| --- | ---: | ---: | ---: | ---: |
| PPTX @600 | 0.8300 | 0.8294 | -0.08% | 0.844 |
| PPTX @1200 | 1.6581 | 1.6652 | +0.43% | 1.729 |
| Deck @1200 | 12.4192 | 12.6147 | +1.57% | 15.4 |
| Word-5 @1200 | 5.7212 | 5.6973 | -0.42% | 5.75 |

All four pass the absolute ceilings. The p50 is the median across warm renders for each arm. [Small fixture captures](paired/)

### Pixel parity and CTest

The native comparison checked active RGBA bytes directly. Three large fixtures at 1200 px matched on all **353,143,200 pixels**. Seven small fixture and width combinations matched on all **111,897,000 pixels**. CTest passed **577/577** in 97.58 seconds. [Pixel comparison captures](paired/) · [CTest output](ctest.txt)

### Peak RSS

Each 1200 px fixture ran twice per fresh process, in AB, BA, AB order. The table uses the maximum Windows process peak working set for each arm. The largest increase within a matched process pair was **+0.47%**, within the 10% limit. [RSS captures](rss.json)

| Fixture | Main peak, bytes | Spans peak, bytes | Change |
| --- | ---: | ---: | ---: |
| image-heavy-100 | 153,743,360 | 153,804,800 | +0.04% |
| real-mixed-120 | 112,791,552 | 112,590,848 | -0.18% |
| vector-heavy-100 | 82,526,208 | 82,411,520 | -0.14% |

## Reproduction

Build main at `c01b82c2b` and the span change at `b5ba2f363` as Release DLLs. The final pair used the same local CMake tree and dependency cache with MinGW GCC 16.2.0, Ninja, `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF`, and `EXR_ENABLE_IMAGE_AVIF=OFF`. The ablation control and probe comparisons used the existing #264 Release DLL. Its renderer sources, headers, tests, and CMake inputs match `c01b82c2b`. Its SHA-256 is `8a34941d6a88bf1fd9530c6d9684e8459f9dc1f84bd295fbd64fed13148ddd3f`. PDF.js 3.11.174 used Node 24.19.0 and node-canvas 3.2.3. The Python tools used Python 3.14.7, pypdf 6.16.1, and psutil 7.2.2. The Windows power plan was Balanced.

Restore the following scripts to an empty `_work/` under this report. Use `ablate.py`, `variants.py`, `worker.py`, and `worker.cjs` from `evidence/twocells-attribution-20261118/` at `5a325a57e`. Use `paired_sweep.py` and `verify.py` from `evidence/slides-gradient-20261118/` on main. [Harness patch](harness.patch) applies the fixture-specific fill/stroke omissions, page selector, and output paths. The archived timing code and per-page alternation are reused.

```powershell
$d = 'evidence/dense-vector-439-20261118'
$pdf = 'tests/fixtures/pdf-large/vector-heavy-100.pdf'
git apply --ignore-space-change --directory="$d/_work" "$d/harness.patch"

# A and B are Release DLL paths. Use a fresh ablation output directory.
python -B "$d/_work/variants.py" vector-heavy-100 66 100 path polygon-paint polygon-fill polygon-stroke curve-stroke background clip fill stroke
Copy-Item $pdf "$d/_work/vector-heavy-100-absent.pdf"
python -B -u "$d/_work/ablate.py" $A vector-heavy-100 66 100 path polygon-paint polygon-fill polygon-stroke curve-stroke background clip absent
python -B -u "$d/_work/ablate.py" $A vector-heavy-100 66 100 fill stroke

python -B -u "$d/_work/paired_sweep.py" $A $B $pdf 1200 11 "$d/dense-1200.json" --first 66 --pages 100
python -B -u "$d/_work/paired_sweep.py" $A $B $pdf 1200 11 "$d/dense-vs-pdfjs-1200.json" --first 66 --pages 100 --pdfjs-root ../pdfjs-bench2
python -B -u "$d/_work/verify.py" paired $A $B
python -B -u "$d/_work/verify.py" rss $A $B
ctest --test-dir build/perf --parallel 4 --output-on-failure
```

For the trace, build a separate DLL from main with [the probe patch](probe.patch) applied. Pair that DLL against main in a single warm sweep over pages 66–100 at 1200 px with `--trace`. The raw native captures retain active-pixel hashes and the binary fingerprints.
