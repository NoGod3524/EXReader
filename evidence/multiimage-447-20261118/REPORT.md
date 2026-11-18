# Multi-image PDF pages at 1200 px

The candidate reduces the sum of p71–100 page medians from **2,716.97 to 1,482.25 ms** in the machine-wide idle-gated run and from **2,135.55 to 1,315.62 ms** on the pinned CPU. It wins all seven paired sweeps in each run. Direct comparison found **zero differing pixels across 465,040,200 pixels**, and CTest passed **577/577**. Both builds exceed the four absolute small-fixture ceilings in the machine-wide idle-gated captures.

## Attribution of the historical 447.54 ms

The handoff records **+447.54 ms** for EXReader versus PDF.js on p71–100. Its bilateral image omission moved the gap from +344.38 to −5.67 ms in a separate set of runs. The image-mask omission narrowed the gap by **172.99 ms**, or **49.4%** of that set's 350.05 ms image-omission effect. These values come from the handoff.

| Component | Historical contribution to +447.54 ms | Live evidence from the pinned run |
| --- | ---: | --- |
| Image soft masks | 172.99 ms marginal effect in the earlier bilateral omission | 48 masked draws. Their EXReader callbacks take 1,237.76 ms inclusive. The sampled mask interval, including application of the result to all four color/alpha sums, totals 38.19 ms across 702,768 observed subsamples. |
| Interpolation and 2×2 supersampling | Unmeasured | All 90 draws use the separable bilinear path. The sampled color interpolation intervals total 34.23 ms on masked draws and 24.29 ms on unmasked draws across 1,228,560 observed subsamples. |
| Clip | Unmeasured within image rendering | Building 90 coverage masks takes 17.77 ms inside EXReader clip callbacks. Their per-pixel consumption remains inside the image draw. |
| Texture preparation and channel/row conversion | Unmeasured | Axis setup takes 0.90 ms on masked draws and 0.50 ms on unmasked draws. Row taps and RGBA-to-double conversion together take 37.58 and 34.70 ms, respectively. |
| Other drawing work | Unmeasured | The sampled resolve and destination blend intervals total 11.10 ms for masked draws and 8.15 ms for unmasked draws across 307,980 observed destination pixels. |

The historical mask omission is the largest isolated cross-engine effect available. **274.55 ms** is the arithmetic remainder after subtracting it from 447.54 ms. The measurements come from separate sessions, so that remainder cannot be assigned to the other rows. The largest measured inclusive EXReader block is the masked image draw. Sampling and applying masks within the inner loop accounts for the largest sampled block on those draws.

The scope DLL keeps the original painting operations and instruments their inputs and results as they flow into the bitmap. The coarse measurement records one interval per RGB image callback and PDF clip callback, plus each row's preparation. The inner-loop probe samples one covered x position per 128 columns with a row-dependent phase. It records the actual elapsed time for those samples, including timer cost. Probe builds add median paired render overhead of **5.25%** for the scoped mode and **15.50%** for the sampled mode. Sample totals are shown at the observed sample counts. [EXReader scopes](core-3/diagnostic-scopes.json.gz) · [sampled scopes](core-3/diagnostic-sampled.json.gz) · [probe builder](build_probe.py)

### PDF.js observable intervals

PDF.js 3.11.174 with node-canvas 3.2.3 runs the same pages. The probe times image preparation, scaling and draw calls while forwarding the same image data. The canvas call includes native interpolation, clipping and destination blending. PDF.js may perform clip work inside that call.

| Median ms per p71–100 sweep | Masked | Unmasked |
| --- | ---: | ---: |
| PDF.js image callback | 598.42 | 489.76 |
| PDF.js scratch canvas, upload and transfer | 77.93 | 105.15 |
| PDF.js scaling helper | 13.02 | 1.02 |
| PDF.js native canvas draw | 510.30 | 382.37 |
| EXReader image callback | 1,237.76 | 659.69 |

The PDF.js clip callback totals 1.84 ms. EXReader image loading, including any cache misses and decode, is timed outside its callback at 266.88 ms in this particular pinned run. Each row in the table is a median of whole-sweep scope sums. [PDF.js scopes](core-3/diagnostic-pdfjs.json.gz) · [scope summaries](core-3/summary.json)

The machine-wide gated scopes show the same ordering under different CPU load. EXReader spends 1,845.36 ms in masked image callbacks and 933.42 ms in unmasked callbacks. PDF.js spends 706.98 and 535.31 ms. EXReader clip construction takes 18.02 ms, and row preparation totals 40.44 and 33.84 ms for masked and unmasked draws. The EXReader scope and sampled probes increase the median paired render time by 11.10% and 19.05% in this run. [EXReader scope capture](diagnostic-scopes.json.gz) · [sampled capture](diagnostic-sampled.json.gz) · [PDF.js scope capture](diagnostic-pdfjs.json.gz)

## Structural findings and change

- The 90 draws reference **90 distinct XObjects**. All use axis-aligned bilinear color sampling. The 48 image masks use nearest-neighbor sampling, have no matte, and are sampled in the same output loop as their color textures.
- There are **three rectangular clip recipes** repeated on every page, with 90 clip masks constructed across the sweep. EXReader already reuses released clip storage within a canvas. The canvas also uses the existing buffer pool for eligible internal bitmap allocations, and transfers the final bitmap to the render caller. The clip construction time above bounds the measured scope of reusing the same clip geometry across pages. [Fixture and renderer census](census.json.gz)
- The images and background are separate ordered paints, and their destination regions overlap. A merged sweep would have to preserve that order, coverage, and source-over operations. This change targets repeated sampling inside the current draw.

The axis path finds spans whose full color footprint contains identical opaque texels. With a same-size nearest-neighbor luminosity mask, the span also requires equal opaque mask texels. All four quarter-pixel samples then resolve to the same quantized straight RGBA pixel. The renderer reuses that pixel over the span and still applies each destination pixel's actual coverage and source-over blend. Mixed footprints and partial sample footprints use the ordinary bilinear path. The change adds no heap allocation.

In a separate five-sweep diagnostic A/B, both builds use the same image callback timer. The largest measured reduction occurs on masked images. Both arms render the same pixels on all 30 pages.

| Image callback | A median (ms) | B median (ms) | Median paired saving (ms) |
| --- | ---: | ---: | ---: |
| 48 masked draws | 1,189.24 | 542.62 | 632.78 |
| 42 unmasked draws | 572.52 | 407.87 | 163.31 |

The masked saving includes avoided color interpolation and mask application on the same spans. [Matched image callbacks](core-3/diagnostic-flat.json.gz)

## Alternating production A/B

Both arms use Release GCC 16.2.0 DLLs. Each sweep alternates AB/BA per page and reverses the starting order on the next sweep. One parity warmup precedes seven measured 100-page sweeps and 15 measured sweeps per small fixture. The package-wide gate continues to require ≤15% CPU over 0.5 seconds. In the separate CPU 3 run, the same threshold applies to the pinned CPU before each batch and to its estimated background use during the batch. Batches over the cutoff are retried. On the accepted 100-page measurements, total system CPU was **44.05–72.91%**, and pinned-CPU background utilization was **8.42–12.07%**. [Build fingerprints](build-info.json) · [capture harness](capture.py) · [production samples](core-3/)

| 100-page cohort | A sum of page p50s (ms) | B sum of page p50s (ms) | Median paired sweep change | Paired sweep range |
| --- | ---: | ---: | ---: | ---: |
| p1–10 slides | 1,212.54 | 1,202.36 | +0.17% | −7.02% to +6.32% |
| p11–40 deck | 830.22 | 835.52 | +0.19% | −2.98% to +3.87% |
| p41–60 Word | 254.86 | 253.29 | −0.33% | −14.24% to +2.58% |
| p61–70 image-only | 158.37 | 158.76 | −0.31% | −2.17% to +8.24% |
| **p71–100 multi-image** | **2,135.55** | **1,315.62** | **−37.98%** | **−40.95% to −34.49%** |
| p1–100 | 4,591.55 | 3,765.55 | −17.99% | −20.08% to −13.89% |

| Small fixture | A render p50 (ms) | B render p50 (ms) | Ceiling (ms) | Median paired sweep change |
| --- | ---: | ---: | ---: | ---: |
| PPTX @600 | 1.857 | 1.866 | 0.844 | +0.53% |
| PPTX @1200 | 3.751 | 3.750 | 1.729 | +0.85% |
| Deck @1200 | 27.365 | 27.211 | 15.4 | −0.69% |
| Word @1200 | 12.437 | 12.465 | 5.75 | +0.33% |

Across slides, deck, Word, and the two PPTX widths the pinned paired changes straddle zero.

### Machine-wide idle gate

This run starts each large sweep and small-fixture batch only after a 0.5-second package CPU measurement of ≤15%. Warm CPU during the large sweeps varied from 22.33% to 55.97%, including rendering. The p71–100 median paired sweep reduction is **45.09%**, ranging from **44.79% to 46.75%**. [Large-document samples](production-heavy-1200.json.gz)

| 100-page cohort | A sum of page p50s (ms) | B sum of page p50s (ms) | Median paired sweep change |
| --- | ---: | ---: | ---: |
| p1–10 slides | 1,330.14 | 1,337.15 | +0.92% |
| p11–40 deck | 1,122.09 | 1,081.94 | −2.92% |
| p41–60 Word | 256.99 | 258.27 | +1.78% |
| p61–70 image-only | 165.25 | 167.95 | +0.34% |
| **p71–100 multi-image** | **2,716.97** | **1,482.25** | **−45.09%** |
| p1–100 | 5,591.43 | 4,327.56 | −22.53% |

Slides and Word have small positive median paired changes, with ranges of −2.39% to +7.09% and −8.11% to +11.77%. The observed ranges leave the strict no-regression checks inconclusive.

Warm CPU during the small-fixture batches varied from 15.05% to 52.73%, including rendering. All 15 warm sweeps per case are included.

| Small fixture | A render p50 (ms) | B render p50 (ms) | Ceiling (ms) | Median paired sweep change |
| --- | ---: | ---: | ---: | ---: |
| PPTX @600 | 2.005 | 2.029 | 0.844 | −2.44% |
| PPTX @1200 | 3.142 | 3.055 | 1.729 | −3.89% |
| Deck @1200 | 37.660 | 36.328 | 15.4 | −2.45% |
| Word @1200 | 13.693 | 13.507 | 5.75 | −2.16% |

The candidate wins 10/15, 12/15, 10/15, and 11/15 paired sweep totals, respectively. PPTX @600 has a 0.024 ms higher pooled per-render p50 on B while its median paired sweep total decreases. Every observed pooled p50 exceeds its absolute ceiling, including those of the baseline. [PPTX @600](production-pptx-600.json.gz) · [PPTX @1200](production-pptx-1200.json.gz) · [Deck](production-deck-1200.json.gz) · [Word](production-word-1200.json.gz)

The repository's fresh-process runner repeats the ceiling check with AB/BA/AB process pairs and 20 warm sweeps per process. Startup CPU ranges from 1.95% to 14.84%. The candidate reduces the median process p50 on all four cases. Both arms still exceed every ceiling. [Fresh-process results](fresh-process.json.gz)

| Small fixture | A p50 (ms) | B p50 (ms) | Ceiling (ms) |
| --- | ---: | ---: | ---: |
| PPTX @600 | 1.786 | 1.773 | 0.844 |
| PPTX @1200 | 3.039 | 2.957 | 1.729 |
| Deck @1200 | 36.214 | 35.097 | 15.4 |
| Word @1200 | 12.402 | 12.308 | 5.75 |

## Pixel, test and memory acceptance

- **Pixel comparison:** 353,143,200 large-fixture pixels and 111,897,000 small-fixture pixels with zero differences in active RGBA. [Direct comparison](pixels-B.json)
- **CTest:** 577/577 on the candidate build. [CTest output](ctest-B.log.gz)
- **Peak RSS:** Fresh-process Windows peak working sets, maximum of three alternating pairs for each large fixture at 1200 px. The largest increase is **0.42%** among the large fixtures and **0.45%** across all fixtures, within the 10% budget. The RSS harness records large-fixture working sets independently of wall-clock timing. [Raw large-fixture peaks](rss.json) · [small-fixture peaks](fresh-process.json.gz)

| Fixture | A peak bytes | B peak bytes | Change |
| --- | ---: | ---: | ---: |
| image-heavy-100 | 149,643,264 | 150,274,048 | +0.42% |
| real-mixed-120 | 109,342,720 | 109,146,112 | −0.18% |
| vector-heavy-100 | 79,024,128 | 79,036,416 | +0.02% |

## Reproduction

Preserve the baseline Release DLL from `ad8547416` and build the candidate with the same options. On this run the baseline DLL was open in another process, so CMake linked the candidate under `build/multiimage/tests` using `CMAKE_RUNTIME_OUTPUT_DIRECTORY`.

```powershell
$d = 'evidence/multiimage-447-20261118'
python "$d/build_probe.py"
python "$d/run_matrix.py" build/multiimage/A/libexreader.dll build/multiimage/tests/libexreader.dll --probe build/multiimage/probe/libexreader.dll --pdfjs-deps ../pdfjs-bench2
python "$d/run_matrix.py" build/multiimage/A/libexreader.dll build/multiimage/tests/libexreader.dll --probe build/multiimage/probe/libexreader.dll --pdfjs-deps ../pdfjs-bench2 --core 3
python "$d/summarize.py" "$d/core-3"
```
