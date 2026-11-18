# EXReader and PDF.js memory and first screen

## Peak RSS and first screen

EXReader passed the 1.5× peak RSS target in all 10 workload/width pairs. Its highest ratio was 0.344× on word-5 at 1200 px. Its largest absolute peak was 80.59 MiB on long-100 at 1200 px. EXReader reached the first screen sooner on every pair.

Each paired cell lists EXReader / PDF.js. Peak RSS covers the full run through the last reopen cycle. Per-page RSS is the first full-pass resident RSS minus opened RSS, divided by page count. It is an average for the workload and includes document-level allocations made during rendering.

| Fixture @ px | Pages | Peak RSS (MiB) | Peak ratio | RSS added/page (MiB) | First render (ms) | Open + first render (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| deck @ 600 | 15 | 41.68 / 180.96 | 0.230× | 0.730 / 4.939 | 75.606 / 399.984 | 75.971 / 409.271 |
| deck @ 1200 | 15 | 46.81 / 185.43 | 0.252× | 0.887 / 4.935 | 88.674 / 400.409 | 89.085 / 409.440 |
| pptx-20 @ 600 | 20 | 27.22 / 115.11 | 0.236× | 0.070 / 1.996 | 2.156 / 328.882 | 2.438 / 336.164 |
| pptx-20 @ 1200 | 20 | 31.93 / 127.79 | 0.250× | 0.196 / 2.030 | 2.865 / 338.412 | 3.222 / 346.472 |
| word-5 @ 600 | 5 | 32.20 / 131.53 | 0.245× | 0.702 / 8.754 | 10.008 / 378.990 | 10.315 / 385.737 |
| word-5 @ 1200 | 5 | 47.07 / 136.85 | 0.344× | 1.782 / 8.542 | 15.344 / 361.389 | 15.663 / 370.470 |

### Stress cases

| Fixture @ px | Pages | Peak RSS (MiB) | Peak ratio | RSS added/page (MiB) | First render (ms) | Open + first render (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| long-100 @ 600 | 100 | 66.10 / 325.34 | 0.203× | 0.351 / 1.101 | 74.887 / 391.479 | 75.580 / 401.145 |
| long-100 @ 1200 | 100 | 80.59 / 329.04 | 0.245× | 0.437 / 1.125 | 86.417 / 428.585 | 87.118 / 438.284 |
| three-docs @ 600 | 15+20+5 | 45.11 / 202.16 | 0.223× | 0.382 / 1.911 | 74.694 / 398.302 | 75.007 / 408.433 |
| three-docs @ 1200 | 15+20+5 | 64.33 / 198.69 | 0.324× | 0.623 / 1.917 | 89.253 / 394.629 | 89.647 / 405.124 |

## Resident RSS by stage

All values are medians in MiB. “First pass” follows one draw of every page. “Repeat passes” follows the additional cache-warming draws. PDF.js cycle readings follow a forced GC at the end of each cycle.

| Fixture @ px | Renderer | Loaded | Opened | Page 1 | First pass | Repeat passes | Closed | Closed + GC | Cycle 1 | Cycle 2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deck @ 600 | EXReader | 24.16 | 24.69 | 35.57 | 35.64 | 35.62 | 24.95 | — | 25.04 | 25.01 |
| deck @ 600 | PDF.js | 60.93 | 65.71 | 114.42 | 139.79 | 163.42 | 163.46 | 152.19 | 158.24 | 164.28 |
| deck @ 1200 | EXReader | 24.30 | 24.86 | 38.04 | 38.17 | 38.21 | 25.52 | — | 25.51 | 25.59 |
| deck @ 1200 | PDF.js | 60.79 | 66.06 | 112.64 | 140.09 | 156.95 | 157.08 | 144.40 | 158.84 | 159.16 |
| pptx-20 @ 600 | EXReader | 24.09 | 24.48 | 25.83 | 25.88 | 25.89 | 24.93 | — | 24.93 | 24.81 |
| pptx-20 @ 600 | PDF.js | 60.71 | 63.02 | 99.23 | 102.93 | 106.46 | 106.68 | 105.66 | 110.30 | 115.05 |
| pptx-20 @ 1200 | EXReader | 24.40 | 24.82 | 28.70 | 28.75 | 28.75 | 25.60 | — | 25.65 | 25.68 |
| pptx-20 @ 1200 | PDF.js | 60.80 | 63.00 | 100.52 | 103.59 | 119.59 | 119.93 | 120.12 | 122.75 | 122.94 |
| word-5 @ 600 | EXReader | 24.18 | 24.58 | 28.52 | 28.09 | 28.22 | 25.15 | — | 25.10 | 25.14 |
| word-5 @ 600 | PDF.js | 60.78 | 62.36 | 104.25 | 106.13 | 109.35 | 109.43 | 106.94 | 115.42 | 122.97 |
| word-5 @ 1200 | EXReader | 24.37 | 24.77 | 33.68 | 33.68 | 33.68 | 25.37 | — | 25.38 | 25.37 |
| word-5 @ 1200 | PDF.js | 60.92 | 62.70 | 104.01 | 105.41 | 107.98 | 108.04 | 106.23 | 122.62 | 123.51 |
| long-100 @ 600 | EXReader | 24.12 | 24.93 | 35.77 | 60.02 | 60.34 | 25.19 | — | 25.34 | 25.21 |
| long-100 @ 600 | PDF.js | 60.79 | 69.25 | 112.77 | 179.33 | 238.39 | 236.75 | 211.96 | 247.46 | 274.70 |
| long-100 @ 1200 | EXReader | 24.36 | 25.20 | 38.23 | 68.90 | 68.89 | 26.03 | — | 25.68 | 25.97 |
| long-100 @ 1200 | PDF.js | 60.81 | 69.27 | 113.62 | 181.72 | 243.05 | 243.13 | 212.33 | 243.16 | 272.83 |
| three-docs @ 600 | EXReader | 24.08 | 24.59 | 35.59 | 39.86 | 40.37 | 25.30 | — | 25.26 | 25.28 |
| three-docs @ 600 | PDF.js | 60.73 | 67.01 | 112.74 | 143.43 | 171.00 | 171.07 | 157.30 | 171.57 | 187.84 |
| three-docs @ 1200 | EXReader | 24.41 | 25.07 | 38.21 | 49.98 | 50.07 | 25.88 | — | 25.63 | 25.64 |
| three-docs @ 1200 | PDF.js | 60.85 | 66.94 | 112.34 | 143.61 | 170.46 | 170.47 | 156.92 | 166.73 | 180.77 |

EXReader’s closed RSS was 0.79 to 1.67 MiB above its loaded baseline. Closed private bytes changed by −0.28 to +1.14 MiB relative to baseline. After the second reopen cycle, RSS was 0.72 to 1.61 MiB above baseline, with changes of −0.13 to +0.29 MiB from cycle 1 to cycle 2. The return toward baseline shows that EXReader released resident memory on close. The two reopen cycles provide a short-run retention check.

## Decision

Keep the current image and font caches. The default image cache evicts least-recently-used entries within 64 MiB and 128 entries per document. Font-stream retention is capped at 16 MiB per PDF. The handoff commit included experimental pixel memoization. This benchmark and the final branch use the renderer source from `main`. The four warm-throughput guards apply when the renderer is optimized.

## Pixel and test verification

`tools/benchmark_pdf_rect.py` captured the measured DLL and compared active RGBA bytes against the approved #244 captures. The reference DLL hash matches the candidate listed in the #244 manifest. [Reference evidence](../pdf-pptx-600-20261117/manifest.json)

| Fixture | Widths (px) | Pixels compared | Different pixels | Maximum channel delta |
| --- | --- | ---: | ---: | ---: |
| deck | 600, 1200 | 15,192,000 | 0 | 0 |
| pptx-20 | 600, 1200, 2400 | 85,056,000 | 0 | 0 |
| word-5 | 600, 1200 | 11,649,000 | 0 | 0 |
| **Total** | | **111,897,000** | **0** | **0** |

[Deck pixel comparison](pixels-deck.json) · [PPTX pixel comparison](pixels-pptx.json) · [Word pixel comparison](pixels-word.json)

CTest passed 577/577 in 83.46 seconds. The Release build used `EXR_BUILD_TOOLS=OFF` to match the #244 test configuration. The DLL SHA-256 matched the memory benchmark. [CTest output](ctest.txt)

## Method

Windows 11 build 26200 on an Intel Core Ultra 7 256V, MinGW-w64 GCC 16.2.0 Release, Python 3.14.7, and Node v24.19.0 with `pdfjs-dist` 3.11.174 and `canvas` 3.2.3. The EXReader build uses the renderer from `main` at `e595a2662`.

The existing `tools/bench_memory.py` and `tools/bench_memory_pdfjs.cjs` ran three fresh processes per renderer, fixture, and width. The order alternated EXReader/PDF.js, PDF.js/EXReader, EXReader/PDF.js. The system CPU idle gate was 15%, with pre-pair samples of 5.41% to 14.84%. Windows `GetProcessMemoryInfo` supplied working set (RSS), peak working set, and private bytes for both processes. Each process opened the input, drew page 1, finished a pass through the document, did three additional full passes, closed, and repeated the open/render/close sequence twice. [Raw samples, medians, DLL and fixture hashes](memory.json)

First screen is the median of each run’s measured open time plus its first page render. Both timers start after the renderer modules load. Operating-system file caches are shared across the fresh processes. EXReader times `exr_fixed_open` and `exr_fixed_render`, with page geometry enumeration between the timers. PDF.js times file read and `getDocument`, then `getPage(1)`, viewport and canvas creation, and `page.render`. For the three-document case the first-screen time uses the first document’s open and render timers. The inputs are opened together before drawing.

The 100-page PDF is a generated concatenation of the three fixtures with distinct PDF objects for each copy. The three-document workload holds the three original PDFs open together.

Process RSS includes the Python or Node runtime, renderer dependencies, and allocator behavior. Node can collect garbage during rendering. The PDF.js harness also samples after document cleanup and again after two forced GC calls. The EXReader harness samples immediately after `exr_fixed_free`. These figures compare the two runnable configurations and include runtime and GC effects.

## Reproduce

From the repository root, use a Windows Release build with shared-library support, Python with `pypdf` 6.16.1 for the long fixture, and the `pdfjs-bench2` Node environment.

```powershell
cmake --build build/perf --parallel 6
python -X utf8 tools/make_memory_fixture.py --out out/memory-firstscreen/long-100.pdf
python -X utf8 tools/bench_memory.py run `
  --side engine=engine:build/perf/libexreader.dll `
  --side pdfjs=pdfjs:C:/Users/Oscar/Documents/Codex/pdfjs-bench2 `
  --case deck=tests/fixtures/pdf-ppt/deck.pdf `
  --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf `
  --case word-5=tests/fixtures/pdf-hybrid-real/word-5.pdf `
  --case long-100=out/memory-firstscreen/long-100.pdf `
  --case 'three-docs=tests/fixtures/pdf-ppt/deck.pdf+tests/fixtures/pdf-hybrid-real/pptx-20.pdf+tests/fixtures/pdf-hybrid-real/word-5.pdf' `
  --widths 600 1200 --runs 3 --rounds 3 --cycles 2 --idle-threshold 15 `
  --out evidence/memory-firstscreen-20261118/memory.json
```
