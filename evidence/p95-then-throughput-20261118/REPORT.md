# Hundred-page retest: current main vs PDF.js 3.11.174

**Result: three of six cells still lose on whole-document throughput, all at 1200 px.** Real-mixed is 1.15× behind (13.1% fewer pages/s), image-heavy 2.45× behind (59.2% fewer), and vector-heavy 1.41× behind (29.2% fewer). At 600 px, real-mixed and vector-heavy have clear throughput leads; image-heavy has a 2.4% median lead with overlapping repeat ranges, so it is a near-tie. By medians the split is three losses / three leads; accounting for spread it is three losses / two clear wins / one near-tie.

EXReader has lower p50 in five cells (the exception is vector-heavy @ 1200), lower p95 in two cells (mixed and vector @ 600), and lower peak RSS and faster first screen in all six. No render code or benchmark code changed.

## Setup and comparability

- **Measured source:** current `origin/main` at run start, `6e11e8c95b57beb77c56ffcc83a9331a1b50cbb2`, on branch `perf/p95-then-throughput`. Includes #248, #251, #253 and #254. Capture: 2026-11-18T05:24:05.4225030-05:00 to 2026-11-18T05:31:05.4481247-05:00.
- **Machine:** Windows 11 10.0.26200, Intel Core Ultra 7 256V, 8 cores / 8 logical processors; same machine as #250.
- **Build:** fresh Release MinGW GCC 16.2.0, Ninja, `-O3 -DNDEBUG`, target `exreader`. All `EXR_*:BOOL`, build-type and Release C flags match #250's saved `EXReader-pdfjs-large/build/perf/CMakeCache.txt`; AVIF is OFF, PDF/crypto/JPX/ICC/TIFF/WebP are ON. Source dependencies reuse the same local pinned cache. [Build configuration](CMakeCache.txt), [build log](build.log).
- **DLL SHA-256:** `2640521cb124a7533c808429391a93bfa8d4db75443f79cd92f765c158f2c5ee`.
- **PDF.js:** `pdfjs-dist` **3.11.174**, legacy build, in-process fake worker, Node **v24.19.0**, node-canvas **3.2.3**, from `C:/Users/Oscar/Documents/Codex/pdfjs-bench2`; `disableFontFace: true`, `useSystemFonts: false`. This uses v3 as #250 did. The task notes a 1.5× v3/v4 difference; this retest measures v3 only.
- **Harness:** reused `tools/bench_large_vs_pdfjs.py` from #250 unchanged. Its PDF.js child, EXReader child and CPU gate files also have an empty diff against #250 commit `213f242b4`. [Harness hashes](harness-sha256.json).
- **Reference:** [#250 report](../pdfjs-large-doc-20261118/REPORT.md) and [archived exact results](../pdfjs-large-doc-20261118/results.json); that DLL was #248 head `556ac0119`. The comparison below is against those archived results, not a newly rerun old DLL.

| Fixture | Pages | SHA-256 |
| --- | ---: | --- |
| real-mixed-120 | 120 | `cdfc1ee6952652613c15fe91288450c6e168994e3b1792e52bb56db14ab8a693` |
| image-heavy-100 | 100 | `c027e8e78346b159e08d3a8c5313b0bd240403873e1c58de0e1b2c3f11b87cb2` |
| vector-heavy-100 | 100 | `72e72440fb9fe01e8c4c0c9171e80356ca05b627690b578db8a9cf2030dab207` |

## Method

Exactly #250's settings: 3 repeats × 5 warm rounds per fixture/width. Each repeat starts fresh EXReader and PDF.js children in one session, ordered EXReader/PDF.js, PDF.js/EXReader, EXReader/PDF.js. Each child opens the document, renders one cold full-document round, then five warm full-document rounds. Both sides use the same `bench_real_doc.summarize_repeats`; reported metrics are medians of repeat-level summaries.

Before each of the 36 children, the unchanged fail-closed gate required ≤15% system CPU. All passed, observed **2.73–14.94%**; no timeout, retry or discarded capture. The gate applies before a child; `capture_cpu_percent` includes the benchmark itself and is not an idle reading. CPU readings are retained in `results.json` under each side's `repeats`.

- **p50 / p95:** pooled per-page warm-render samples within each child, then median across children.
- **Worst page:** page ID is the page with the highest cross-repeat median per-page warm p50. The displayed worst-page time is the median of each repeat's maximum page p50; the ID and time are selected separately by the unchanged summarizer. Worst single render is the median of repeat-level document maxima.
- **Throughput:** page count divided by median warm-round sum of timed page renders, then median across repeats.
- **First screen:** document open plus first cold render of page 1, fresh process.
- **Peak RSS:** Windows peak working set for the whole child; also show growth above process start.
- **PDF.js timing:** `getPage` + viewport + canvas allocation + `render()`, followed by page cleanup; same harness as #250. Node runs natural V8 GC inside the timed region, without forced GC. EXReader has no V8 runtime. GC share is reported below; it remains included in PDF.js time.

## Results (same columns as #250)

| Fixture @ width | Side | p50 (ms) | p95 (ms) | Worst page p50 (ms) | Worst single render (ms) | Throughput (pages/s) | Peak RSS (MiB) | Peak RSS over process start (MiB) | First screen (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 @ 600 | EXReader | 1.98 | 15.93 | 18.82 (p2) | 20.57 | 194.55 | 75.98 | 51.45 | 31.99 |
| real-mixed-120 @ 600 | PDF.js | 4.21 | 25.73 | 39.51 (p2) | 49.05 | 109.84 | 318.82 | 263.54 | 457.01 |
| real-mixed-120 @ 1200 | EXReader | 6.27 | 49.39 | 65.52 (p2) | 69.74 | 72.16 | 107.67 | 82.95 | 63.27 |
| real-mixed-120 @ 1200 | PDF.js | 6.87 | 34.78 | 47.81 (p2) | 76.42 | 83.03 | 293.71 | 238.50 | 420.89 |
| image-heavy-100 @ 600 | EXReader | 6.89 | 33.37 | 34.49 (p71) | 39.26 | 80.23 | 116.61 | 92.01 | 31.49 |
| image-heavy-100 @ 600 | PDF.js | 13.56 | 25.57 | 28.55 (p7) | 32.33 | 78.36 | 307.88 | 252.57 | 433.85 |
| image-heavy-100 @ 1200 | EXReader | 14.27 | 119.82 | 121.41 (p76) | 188.65 | 25.35 | 147.02 | 122.24 | 62.60 |
| image-heavy-100 @ 1200 | PDF.js | 14.47 | 29.09 | 33.26 (p7) | 74.59 | 62.17 | 301.57 | 246.20 | 417.27 |
| vector-heavy-100 @ 600 | EXReader | 5.86 | 15.86 | 17.89 (p2) | 18.72 | 190.20 | 47.28 | 22.77 | 34.70 |
| vector-heavy-100 @ 600 | PDF.js | 7.24 | 23.67 | 29.49 (p2) | 33.32 | 141.87 | 278.73 | 223.61 | 455.45 |
| vector-heavy-100 @ 1200 | EXReader | 12.18 | 48.52 | 53.10 (p2) | 55.27 | 69.62 | 79.02 | 54.16 | 68.59 |
| vector-heavy-100 @ 1200 | PDF.js | 10.43 | 29.66 | 37.69 (p1) | 53.87 | 98.38 | 267.24 | 211.91 | 471.88 |

Ratios use #250's convention: **above 1× means EXReader is worse**. Time and memory = EXReader / PDF.js; throughput = PDF.js / EXReader.

| Fixture @ width | p50 | p95 | Worst page | Throughput | Peak RSS | First screen | Throughput position |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| real-mixed-120 @ 600 | 0.47× | 0.62× | 0.48× | 0.56× | 0.24× | 0.07× | clear win: 77.1% more pages/s |
| real-mixed-120 @ 1200 | 0.91× | 1.42× | 1.37× | 1.15× | 0.37× | 0.15× | loss: 13.1% fewer pages/s |
| image-heavy-100 @ 600 | 0.51× | 1.31× | 1.21× | 0.98× | 0.38× | 0.07× | near-tie: 2.4% median lead |
| image-heavy-100 @ 1200 | 0.99× | 4.12× | 3.65× | 2.45× | 0.49× | 0.15× | loss: 59.2% fewer pages/s |
| vector-heavy-100 @ 600 | 0.81× | 0.67× | 0.61× | 0.75× | 0.17× | 0.08× | clear win: 34.1% more pages/s |
| vector-heavy-100 @ 1200 | 1.17× | 1.64× | 1.41× | 1.41× | 0.30× | 0.15× | loss: 29.2% fewer pages/s |

## Changes versus #250

EXReader throughput is **1.83–3.58×** its archived value and p95 falls **33.7–73.4%**. These are historical session-to-session changes after the merged PRs; they do not isolate individual PR effects. PDF.js throughput moved too, so the next table shows both the old and fresh relative gaps.

| Fixture @ width | EXReader throughput old → new (pages/s) | Change | PDF.js throughput change | Throughput gap old → new (PDF.js / EXReader) | EXReader p95 old → new (ms) | Change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 @ 600 | 97.09 → 194.55 | +100.4% | +9.3% | 1.03× → 0.56× | 43.30 → 15.93 | -63.2% |
| real-mixed-120 @ 1200 | 26.15 → 72.16 | +175.9% | +5.8% | 3.00× → 1.15× | 185.94 → 49.39 | -73.4% |
| image-heavy-100 @ 600 | 41.89 → 80.23 | +91.5% | -3.1% | 1.93× → 0.98× | 58.12 → 33.37 | -42.6% |
| image-heavy-100 @ 1200 | 13.84 → 25.35 | +83.2% | -2.0% | 4.59× → 2.45× | 180.67 → 119.82 | -33.7% |
| vector-heavy-100 @ 600 | 70.32 → 190.20 | +170.5% | +5.2% | 1.92× → 0.75× | 39.43 → 15.86 | -59.8% |
| vector-heavy-100 @ 1200 | 19.43 → 69.62 | +258.3% | +4.9% | 4.82× → 1.41× | 154.14 → 48.52 | -68.5% |

Other EXReader metric changes against #250 (percent; negative means a reduction):

| Fixture @ width | p50 | Worst page p50 | Worst single render | Peak RSS | First screen |
| --- | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 @ 600 | -15.1% | -59.8% | -68.7% | -0.2% | -44.9% |
| real-mixed-120 @ 1200 | -20.7% | -66.5% | -76.0% | -0.1% | -62.3% |
| image-heavy-100 @ 600 | -11.0% | -54.9% | -51.7% | -0.3% | -41.8% |
| image-heavy-100 @ 1200 | -20.5% | -39.1% | -11.2% | +0.6% | -61.2% |
| vector-heavy-100 @ 600 | -2.3% | -56.5% | -58.0% | -0.5% | -39.2% |
| vector-heavy-100 @ 1200 | -6.2% | -66.5% | -70.4% | +0.2% | -58.9% |

**Overtaken cells:** real-mixed @ 600 (1.77× PDF.js throughput) and vector-heavy @ 600 (1.34×), with non-overlapping three-repeat throughput ranges. Image-heavy @ 600 moved from 1.93× behind to 1.024× PDF.js throughput by the medians, but its ranges overlap. #250 described mixed @ 600 as on par and the other five cells as slower; this run leaves only the three 1200 px cells clearly slower.

## Repeat spread and Node GC

Throughput lists below are sorted repeat values, as stored by the shared summarizer, not chronological pair order. Ranges are descriptive; there is no significance test.

| Fixture @ width | EXReader throughput repeats (pages/s) | PDF.js throughput repeats (pages/s) | PDF.js median GC warm share |
| --- | --- | --- | ---: |
| real-mixed-120 @ 600 | 191.26 / 194.55 / 197.93 | 104.52 / 109.84 / 111.37 | 0.56% |
| real-mixed-120 @ 1200 | 68.30 / 72.16 / 72.46 | 81.42 / 83.03 / 90.29 | 0.82% |
| image-heavy-100 @ 600 | 75.80 / 80.23 / 80.41 | 75.20 / 78.36 / 79.05 | 1.11% |
| image-heavy-100 @ 1200 | 24.21 / 25.35 / 25.94 | 61.69 / 62.17 / 63.41 | 1.03% |
| vector-heavy-100 @ 600 | 173.09 / 190.20 / 198.44 | 133.17 / 141.87 / 143.77 | 0.56% |
| vector-heavy-100 @ 1200 | 58.94 / 69.62 / 71.96 | 84.90 / 98.38 / 100.93 | 0.50% |

Node/V8 GC scheduling and JIT warm-up differ from native EXReader. The existing harness records GC through `perf_hooks`, leaves it inside the measured time, and records render-only p50 separately. Median warm GC shares are small relative to the remaining 1200 px gaps. Individual GC events can still affect tail samples. PDF.js's cold first-page cost includes its runtime warm-up; first-screen results are fresh-process results.

## Reproduce and evidence

Build with the configuration above, then from the repository root:

```powershell
python -X utf8 tools/bench_large_vs_pdfjs.py --library build/perf/libexreader.dll --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2 --case real-mixed-120=tests/fixtures/pdf-large/real-mixed-120.pdf:120 --case image-heavy-100=tests/fixtures/pdf-large/image-heavy-100.pdf:100 --case vector-heavy-100=tests/fixtures/pdf-large/vector-heavy-100.pdf:100 --widths 600 1200 --runs 5 --repeat 3 --out evidence/p95-then-throughput-20261118/results.json
```

- [results.json](results.json): exact summaries, all per-page summaries, CPU gate/capture readings, versions and hashes.
- [.raw-results/](.raw-results/): 36 unchanged child JSON outputs with per-page samples.
- [run.log](run.log): complete successful capture console output.
- [CMakeCache.txt](CMakeCache.txt), [build.log](build.log), [source.txt](source.txt), [machine.json](machine.json), [harness-sha256.json](harness-sha256.json): build and source provenance.
- Validation: six case keys; 3 × 2 child captures per case; AB/BA/AB order; all pre-child CPU readings ≤15%; fixture hashes match #250; DLL hash matches results; all four harness files unchanged from #250. The PR adds measurement evidence only.
