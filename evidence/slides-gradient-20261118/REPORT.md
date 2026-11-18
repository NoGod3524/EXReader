# Slide gradients inside luminosity masks

The path probe confirms that all 20 axial draws on pages 1–10 at 1200 × 900 use the #248 row reuse path. Each draw has a clip. The ten draws inside the luminosity-mask groups and the ten page draws with the finished mask applied both enter the same aligned axial path in `exr_canvas_paint`. The former use the RGB group store and the latter use the masked page store from #254.

## Path and draw scopes

| Measured over the ten pages | Inside mask group | On page with mask applied |
| --- | ---: | ---: |
| Axial draws | 10 | 10 |
| Clipped draws | 10 | 10 |
| Rows on the axial path | 5,360 | 5,360 |
| Rows on the generic path | 0 | 0 |
| Covered pixels | 6,432,000 | 6,432,000 |
| Covered pixels using cached row samples | 6,271,200 (97.5%) | 6,271,200 (97.5%) |
| Covered pixels evaluated with the sampler | 160,800 | 160,800 |
| Covered pixels outside the pre-normalized range | 155,440 | 155,440 |
| Pixels in the fast stores' runs | 6,259,500 | 6,259,500 |
| Median paint time per draw, ms | 8.284 | 8.444 |
| Observed draw range, ms | 6.725–19.879 | 4.646–14.089 |

The only draws with no mask applied to their source are inside the mask groups. Each scope measures one canvas paint call. The mask-group scope runs during mask construction. The page-draw scope starts after the painter has built its mask. They include clip scanning, sampling, blending or group writes, and probe overhead. The 50 warm observations per scope come from five A/B sweeps against the original build. The instrumented and original arms produced identical RGBA bytes for 10,800,000 pixels. Their median ten-page totals were 592.71 and 614.00 ms for original and instrumented, respectively. [Probe patch](probe.patch) · [trace](probe-trace.txt) · [paired samples](probe-paired.json)

## Change

The aligned run now finds the exact rightmost in-scale column once per draw. Within that bound it consumes full clip coverage eight bytes at a time, charges the run's sample work together, and retains the per-pixel charge on the limit so it writes the same successful prefix. The clip scan uses the clip's recorded bounds and counts holes only within the covered interval. Both operations retain the original work accounting, quarter-pixel sample positions, clip fractions and color and blend operations.

The first pilot included the run change alone. Across 11 alternating native sweeps its median paired saving was 25.30 ms per ten pages, with 9 of 11 sweeps faster and zero pixel differences. The median totals were 657.64 ms for the original build and 627.88 ms for the pilot. [Pilot samples](pilot-run-only.json)


## Production A/B

On pages 1–10 alone, the original build's median ten-page sweep was **624.45 ms** and the candidate's was **602.38 ms**. The median of the paired savings was **30.80 ms**, ranging from a 5.32 ms slowdown to a 50.14 ms saving. The candidate was faster in 9 of 11 sweeps. The sum of each page's median was 643.61 ms for A and 615.57 ms for B. [Native p1–10 samples](slides-1200.json)

A is `9a4f3ba0c` and B is `f77d6712a`. PR #263 was open at capture, so A uses the version of main before #263. Both DLLs are MinGW GCC 16.2.0 Release builds with `-O3 -DNDEBUG`, on Windows 11 on an Intel Core Ultra 7 256V with the Balanced power plan. SHA-256 fingerprints are in each sample file.

The native runner alternates A/B and B/A by page and reverses the starting order on the next sweep. With PDF.js as C it uses ABC and CBA in the same pattern. One warmup sweep supplies the pixel comparison and the later sweeps supply render times. The 15% system CPU gate measures over half a second and retries after a closed window. The p1–10 native run and the 100-page cohort run gate each sweep. Other fixture sizes required only for pixel comparison use a single untimed pass. The PDF.js run gates every three sweeps. The small-fixture captures record their batch gates in the raw samples. [Capture runner](paired_sweep.py) · [matrix runner](verify.py)


### Current comparison with PDF.js

The same original PDF ran in all three arms, with PDF.js 3.11.174, node-canvas 3.2.3 and Node 24.19.0. Over 11 warm sweeps, the median ten-page totals were **600.92 ms for A**, **595.57 ms for B**, and **349.31 ms for PDF.js**. The median of the sweep-by-sweep gap was **255.82 ms for A** and **237.69 ms for B**, a reduction of **18.13 ms (7.1%)**. A/B alone within these sweeps showed a median paired saving of 24.57 ms, ranging from a 48.96 ms slowdown to a 172.94 ms saving, with 8 of 11 sweeps faster. The earlier 315.35 ms gap was measured in a separate session. [Matched full-render samples](slides-vs-pdfjs-1200.json)

### Other cohorts

| Pages | A sum of page medians (ms) | B sum of page medians (ms) | Change | Median paired sweep change |
| --- | ---: | ---: | ---: | ---: |
| 11–40, deck | 604.18 | 586.77 | −2.88% | −3.80% |
| 41–60, Word | 159.66 | 157.07 | −1.63% | −1.63% |
| 61–70, images | 92.93 | 94.06 | +1.22% | −0.25% |
| 71–100, multiple images | 1,360.37 | 1,387.33 | +1.98% | −0.02% |

The sum-of-page-medians changes all fall within ±3%. The paired sweep median for the deck cohort is a 3.80% improvement. [100-page samples](paired/image-heavy-100-1200.json)




### Small-fixture timing ceilings

| Fixture | A render p50 (ms) | B render p50 (ms) | Change | Ceiling (ms) |
| --- | ---: | ---: | ---: | ---: |
| PPTX @600 | 1.2301 | 1.2323 | +0.18% | 0.844 |
| PPTX @1200 | 2.3571 | 2.3593 | +0.09% | 1.729 |
| Deck @1200 | 18.9846 | 18.8328 | −0.80% | 15.4 |
| Word @1200 | 7.6004 | 7.4911 | −1.44% | 5.75 |

Each figure is the median across warm renders for that arm. Both builds exceed all four absolute ceilings in this run. The four relative p50 changes fall within ±3%. The PR is a draft because the absolute timing gates are unmet. [Small-fixture samples](paired/)

## Pixel parity, tests and RSS

- Three large PDFs at 1200 px matched on all **353,143,200** active RGBA pixels.
- Seven small fixture/width pairs matched on all **111,897,000** active RGBA pixels.
- CTest passed **577/577** in 99.30 seconds. [CTest output](ctest.txt)

The pixel check compares each active RGBA row byte-for-byte on the untimed sweep, with page hashes retained in the raw files. [Parity captures](paired/)

Working sets were measured in fresh processes, two passes per process, in AB, BA, AB order. The table uses the maximum of the three process peaks per build and fixture.

| Fixture @1200 | A peak bytes | B peak bytes | Change |
| --- | ---: | ---: | ---: |
| image-heavy-100 | 153,870,336 | 153,448,448 | −0.27% |
| real-mixed-120 | 113,217,536 | 112,414,720 | −0.71% |
| vector-heavy-100 | 82,808,832 | 82,386,944 | −0.51% |

The largest increase within any single process pair was 0.008%, within the 10% limit. [RSS captures](rss.json)

## Reproduce

Build A from `9a4f3ba0c` and B from `f77d6712a` with MinGW and Ninja. Use Release with `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF`, and `EXR_ENABLE_IMAGE_AVIF=OFF`. Copy the DLLs to the paths below. The probe DLL is a separate build from A with [probe.patch](probe.patch) applied.

```powershell
$d = 'evidence/slides-gradient-20261118'
$pdf = 'tests/fixtures/pdf-large/image-heavy-100.pdf'
$a = 'build/probe/baseline.dll'
$b = 'build/probe/candidate.dll'
ctest --test-dir build/perf --parallel 4 --output-on-failure
python "$d/paired_sweep.py" $a build/probe/instrumented.dll $pdf 1200 5 "$d/probe-paired.json" --pages 10 --trace 2> "$d/probe-trace.txt"
python "$d/paired_sweep.py" $a $b $pdf 1200 11 "$d/slides-1200.json" --pages 10
python "$d/paired_sweep.py" $a $b $pdf 1200 11 "$d/slides-vs-pdfjs-1200.json" --pages 10 --pdfjs-root ../pdfjs-bench2
python "$d/verify.py" paired $a $b
python "$d/verify.py" rss $a $b
```
