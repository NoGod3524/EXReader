# Where the remaining @1200 throughput gap comes from

## Method

- All three fixtures ran at 1200 px on current main `ad85474161eb6b59600149b7a1e8300758e8dd57`. The benchmark uses a fresh MinGW GCC 16.2.0 Release build (`-O3 -DNDEBUG`) on the Intel Core Ultra 7 256V. PDF.js uses the same legacy 3.11.174 build and node-canvas 3.2.3 as #257. [#257 report](../p95-then-throughput-20261118/REPORT.md).
- Each fixture uses three repeats with five warm full-document sweeps per arm after one cold sweep. EXReader and PDF.js run A/B, B/A, A/B in fresh processes. The two ablation arms also reverse order relative to full. The existing fail-closed CPU gate requires at most 15% system CPU before each of the 36 children. Only the three @1200 cells were run.
- Throughput uses the median of the three repeat-level throughputs. Each repeat divides the page count by the median of its five sums of timed page renders. The p50 uses the median of the three repeat-level p50s over all warm page renders. The total-time ratio uses the sum of all timed renders across all repeats and warm sweeps.
- To locate the gap, take each page's mean over its 15 warm timings in each engine and subtract PDF.js from EXReader for that page. Rank the positive differences and report the share from the top 10% of fixture pages. Replacing those EXReader times with their matched PDF.js times shows how much of the signed gap remains. Cohort labels use the fixture generator and the page-content inventory. [Fixture generator](../../tools/generate_real_doc_fixtures.py) · [Page inventory](../real-doc-throughput-20261118/page-content.json).
- Each ablation disables one class throughout the document. `image-paint` keeps decode and bypasses the image draw. `image-decode` substitutes placeholder textures. `path` keeps clips and bypasses path fills and strokes. `shading` bypasses shading dispatch, including in soft masks. An ablation can change downstream work, so savings are intervention results and can overlap. The two modes per fixture target the classes implicated by prior measurements. [Prior attribution](../width1200-attribution-20261118/REPORT.md).

## Reproduce

```powershell
python -X utf8 evidence/throughput-gap-20261118/measure.py --library build/perf/libexreader.dll --pdfjs-root ../pdfjs-bench2
python -X utf8 evidence/throughput-gap-20261118/measure.py
```

The capture retains the warm page timings, CPU gate readings, input hashes, DLL hash and runtime versions. The summary command reads the retained capture. [Timings](timings.json.gz) · [Harness](measure.py).
