# Hundred-page PDFs: EXReader vs PDF.js

**Conclusion.** EXReader is faster on first screen and uses less memory on all three hundred-page fixtures at both widths. It also has the faster median page at 600 px. On whole-document throughput it is **slower** in five of six cells. The only near-tie is real-mixed-120 @ 600 (97.1 vs 100.5 pages/s). At 1200 px PDF.js has **3.0× to 4.8×** our throughput. The gap comes from our slow pages: p95 is 4.9× to 5.8× PDF.js's at 1200 px. Typical pages are not the problem; at 1200 px our p50 is 1.08× to 1.24× PDF.js's.

First screen here means opening the document and rendering page 1 once in a fresh process. On the gradient-plus-soft-mask slides that open these fixtures, PDF.js's paged throughput is far ahead of ours. Neither side was checked on reflow, text, or other document types.

## Setup

- **Machine.** Windows 11 (10.0.26200), Intel Core Ultra 7 256V (Family 6 Model 189), the same session for both sides.
- **EXReader.** `perf/real-doc-throughput` (#248) head `556ac0119`, built for this run as a Release MinGW GCC 16.2.0 `build/perf` with the same option set as the #248 perf build. DLL sha256 `193972af80e40986ae6d9c21332e6f91dcdc62cb6cb541b3e2aba3a978c1a452`.
- **PDF.js.** `pdfjs-dist` **3.11.174**, legacy build, in-process fake worker. It runs on Node **v24.19.0** with `canvas` (node-canvas, cairo) **3.2.3** from `C:\Users\Oscar\Documents\Codex\pdfjs-bench2`, using `disableFontFace: true, useSystemFonts: false`. **This is v3. PDF.js v4 and v5 can differ by up to 1.5×, so these numbers say nothing about them.** PDF.js also renders through node-canvas/cairo here; a browser with Skia and GPU canvas would give different numbers again.
- **Fixtures.** From #248 (`tests/fixtures/pdf-large/`):

| Fixture | Pages | sha256 |
| --- | ---: | --- |
| real-mixed-120.pdf | 120 | `cdfc1ee6952652613c15fe91288450c6e168994e3b1792e52bb56db14ab8a693` |
| image-heavy-100.pdf | 100 | `c027e8e78346b159e08d3a8c5313b0bd240403873e1c58de0e1b2c3f11b87cb2` |
| vector-heavy-100.pdf | 100 | `72e72440fb9fe01e8c4c0c9171e80356ca05b627690b578db8a9cf2030dab207` |

## Method

`tools/bench_large_vs_pdfjs.py` runs each fixture at each width with 3 repeats. Each repeat starts one **fresh** EXReader process (the `tools/bench_real_doc.py` child) and one **fresh** PDF.js process (`tools/bench_pdfjs_large.cjs`). The order alternates exreader/pdfjs, pdfjs/exreader, exreader/pdfjs in one session. Before every child the fail-closed CPU idle gate from `bench_engine.py` (≤15% system CPU) has to pass. Pre-child readings were 1.57–14.84%. No gate timed out.

Each child does the same thing:

- It opens the document.
- It runs one **cold round**, which renders every page once. Page 1 of this round gives the first screen: open plus that first render.
- It runs **5 warm rounds** over every page. All warm per-page times give p50 and p95.
- **Worst page** is the page with the highest per-page warm p50. The column after it is the slowest single warm render.
- **Throughput** is pages divided by the median warm-round sum.
- **Peak RSS** is the process `PeakWorkingSetSize`. The engine reads it with `GetProcessMemoryInfo`. Node reads it with `process.resourceUsage().maxRSS`, which libuv fills from the same counter on Windows.

Both children write one JSON schema. Both are summarized by the same `bench_real_doc.summarize_repeats`. Every value is the median of the 3 repeats.

For PDF.js, per-page time covers `getPage` + viewport + canvas allocation + `render()`, then `page.cleanup()`. That is page index in, finished bitmap out, which matches `exr_fixed_render` (it allocates its own bitmap). The `render()`-only p50 is recorded too and differs by less than 0.1 ms (see `results.json`, `render_only_p50_ms_median`).

## Results

| Fixture @ width | Side | p50 (ms) | p95 (ms) | Worst page p50 (ms) | Worst single render (ms) | Throughput (pages/s) | Peak RSS (MiB) | Peak RSS over process start (MiB) | First screen (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 @ 600 | EXReader | 2.34 | 43.3 | 46.8 (p2) | 65.8 | 97.09 | 76.1 | 51.4 | 58.1 |
| real-mixed-120 @ 600 | PDF.js | 4.99 | 28.5 | 42.3 (p2) | 47.6 | 100.45 | 335.5 | 275.7 | 476.0 |
| real-mixed-120 @ 1200 | EXReader | 7.92 | 185.9 | 195.4 (p12) | 290.8 | 26.15 | 107.8 | 82.9 | 167.7 |
| real-mixed-120 @ 1200 | PDF.js | 7.31 | 35.6 | 49.9 (p2) | 57.8 | 78.49 | 303.1 | 243.3 | 445.5 |
| image-heavy-100 @ 600 | EXReader | 7.74 | 58.1 | 76.5 (p5) | 81.4 | 41.89 | 117.0 | 92.1 | 54.1 |
| image-heavy-100 @ 600 | PDF.js | 13.43 | 24.3 | 28.5 (p2) | 31.0 | 80.90 | 310.7 | 250.9 | 406.2 |
| image-heavy-100 @ 1200 | EXReader | 17.95 | 180.7 | 199.3 (p5) | 212.5 | 13.84 | 146.1 | 121.7 | 161.6 |
| image-heavy-100 @ 1200 | PDF.js | 14.49 | 31.0 | 34.5 (p7) | 40.6 | 63.46 | 301.8 | 241.9 | 425.3 |
| vector-heavy-100 @ 600 | EXReader | 5.99 | 39.4 | 41.2 (p4) | 44.5 | 70.32 | 47.5 | 22.8 | 57.0 |
| vector-heavy-100 @ 600 | PDF.js | 7.78 | 26.4 | 30.9 (p1) | 51.4 | 134.83 | 261.1 | 201.1 | 431.6 |
| vector-heavy-100 @ 1200 | EXReader | 12.97 | 154.1 | 158.4 (p5) | 186.6 | 19.43 | 78.8 | 53.9 | 166.8 |
| vector-heavy-100 @ 1200 | PDF.js | 11.35 | 31.4 | 39.6 (p1) | 46.0 | 93.74 | 259.7 | 199.8 | 436.0 |

The ratios below follow one rule: **above 1× means EXReader is worse.** Time and memory columns are EXReader ÷ PDF.js. Throughput is PDF.js ÷ EXReader.

| Fixture @ width | p50 | p95 | Worst page | Throughput | Peak RSS | First screen | Our position |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| real-mixed-120 @ 600 | 0.47× | 1.52× | 1.11× | 1.03× | 0.23× | 0.12× | throughput on par; faster median; worse tail |
| real-mixed-120 @ 1200 | 1.08× | 5.22× | 3.91× | 3.00× | 0.36× | 0.38× | **slower** |
| image-heavy-100 @ 600 | 0.58× | 2.39× | 2.69× | 1.93× | 0.38× | 0.13× | **slower** (faster median) |
| image-heavy-100 @ 1200 | 1.24× | 5.82× | 5.77× | 4.59× | 0.48× | 0.38× | **slower** |
| vector-heavy-100 @ 600 | 0.77× | 1.49× | 1.33× | 1.92× | 0.18× | 0.13× | **slower** (faster median) |
| vector-heavy-100 @ 1200 | 1.14× | 4.91× | 4.00× | 4.82× | 0.30× | 0.38× | **slower** |

**Spread.** The 600 px cells used the throughput medians shown. For real-mixed @ 600 the repeats were EXReader 92.11 / 97.09 / 102.02 and PDF.js 82.09 / 100.45 / 101.31. Those ranges overlap, so "on par" is the honest reading. In every other cell the throughput repeats of the two sides do not overlap. The p50 spread across repeats was 2.1–12.9% for EXReader and 2.4–23.9% for PDF.js (`spread_percent` in `results.json`).

**Our advantages are not close.** First screen is 2.7× to 8.2× faster. PDF.js spends 10–14 ms in `getDocument` and 395–461 ms on its first page render. Its warm renders of the same page 1 take 21–40 ms, so most of that is probably first-run cost in the fresh process (JIT, worker-code warm-up), not page complexity. This was not profiled. Peak RSS is 2.1× to 5.5× lower. Node's baseline accounts for about 60 MiB of the PDF.js figure, but PDF.js stays 2.0× to 8.8× higher even on peak growth above process start.

## Where the time goes (cohorts at 1200 px)

Each fixture's pages are split by content using #248's `page-content.json`. The table sums per-page warm p50 for each cohort (`cohorts.txt` / `cohorts.json`; 600 px is there too).

| Fixture @ 1200 | Cohort | Pages | EXReader Σ p50 (ms) | PDF.js Σ p50 (ms) | EXReader ÷ PDF.js |
| --- | --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | gradient + soft-mask slides (p1–21) | 21 | 3624.2 | 718.7 | 5.04× |
| real-mixed-120 | image pages without gradient | 55 | 772.3 | 655.3 | 1.18× |
| real-mixed-120 | other | 44 | 109.6 | 132.2 | 0.83× |
| image-heavy-100 | gradient + soft-mask slides (p1–10) | 10 | 1680.4 | 291.8 | 5.76× |
| image-heavy-100 | image pages without gradient | 90 | 5565.2 | 1292.8 | 4.30× |
| vector-heavy-100 | gradient + soft-mask slides (p1–10) | 10 | 1542.9 | 323.4 | 4.77× |
| vector-heavy-100 | other (vector pages) | 90 | 3614.0 | 737.3 | 4.90× |

There are three hotspots:

1. **Axial gradients inside soft masks.** These are the slides #248 already identified. #248 roughly halved them, and they still take us about 5× as long as PDF.js at 1200 px.
2. **The 30 synthetic multi-image pages in image-heavy (p71–100).** Mean per page is 158 ms for us against 24 ms for PDF.js, about 6.7×. Pages 11–70 are within about 1.0×–1.9×.
3. **The 35 synthetic dense-vector pages in vector-heavy (p66–100).** Mean per page is about 96 ms for us against 12 ms for PDF.js, about 8×. Pages 26–55 are slightly faster for us (1.8 vs 2.2 ms).

On real-mixed-120 without the slides (99 pages), we are roughly level: 882 ms against 788 ms Σ p50.

### Attribution guesses (unverified; nothing here was profiled)

- **Gradients.** PDF.js v3 turns an axial `sh` into a canvas `createLinearGradient` with a precomputed colour-stop table, and cairo/pixman fills it per pixel. We evaluate the shading with four subpixel samples per pixel; #248 only reuses them along axis-aligned scanlines. Cost scales with area, which fits the jump from about 1.5× at 600 px to about 5× at 1200 px. PDF.js's soft-mask composition (`genericComposeSMask`, a per-pixel JS loop over `getImageData`) is not free either, so the gap is probably in the shading fill, not the mask.
- **Synthetic image pages.** Each page draws a 0.4–0.9 MP `/Interpolate true` image with a soft mask under an even-odd (`W*`) clip, plus two tiles. Three possible causes:
  - Our interpolated, soft-masked resample path is slower per output pixel than pixman's bilinear.
  - Over 30 distinct large images, our decoded-image cache (64 MiB cap) may evict and re-decode every warm round, while PDF.js recompiles each page's operator list after `cleanup()` anyway. This would show up as warm ≈ cold for those pages on our side.
  - The even-odd clip may push us onto a per-pixel coverage-mask path.
- **Synthetic vector pages.** Each page has 60 stroked cubic curves (20 dashed) and 25 even-odd star polygons, all inside a non-rectangular polygon clip. Possible causes are curve flattening or dash generation in our stroker, and per-span clip-mask intersection under a non-rectangular clip. Cairo's tessellating rasterizer with a clip region might handle this kind of content better. The ablation setup from #248 can confirm or rule out any of these.
- **Node GC is not the explanation.** V8 GC pauses measured with `perf_hooks` `gc` entries took 0.5–1.0% of PDF.js warm-round time. PDF.js's speed here is not hiding GC cost, and its slower first screen is not GC either. Node's GC still differs from our malloc/free model in when memory is released. That shows up in peak RSS, which includes heap PDF.js has not yet collected, so the RSS comparison flatters us a little.

## Output equivalence check

PDF.js could look fast by skipping content. To rule that out, both renderers drew the same page from each hotspot cohort at 1200 px: real-mixed p2 (gradient + soft mask), image-heavy p90 and vector-heavy p90. The images are in `visual/` and look the same by eye: shading, soft-masked images, clips, dashes and even-odd fills are all present. This was not a pixel diff. PDF.js printed one `Warning: TT: undefined function: 21`, a TrueType hinting warning that does not affect output.

## Reproduce

From the repository root, with the fixtures from #248 and a `build/perf/libexreader.dll`:

```
python -X utf8 tools/bench_large_vs_pdfjs.py --library build/perf/libexreader.dll \
    --pdfjs-root C:/Users/Oscar/Documents/Codex/pdfjs-bench2 \
    --case real-mixed-120=tests/fixtures/pdf-large/real-mixed-120.pdf:120 \
    --case image-heavy-100=tests/fixtures/pdf-large/image-heavy-100.pdf:100 \
    --case vector-heavy-100=tests/fixtures/pdf-large/vector-heavy-100.pdf:100 \
    --widths 600 1200 --runs 5 --repeat 3 --out evidence/pdfjs-large-doc-20261118/results.json
```

`pdfjs-bench2` contains only `npm i pdfjs-dist@3.11.174 canvas@3.2.3`. To render the comparison pages, run `python -X utf8 evidence/pdfjs-large-doc-20261118/visual/dump_engine.py <dll> <pdf> <page> <width> <png>` and `node evidence/pdfjs-large-doc-20261118/visual/dump_pdfjs.cjs <pdfjs-root> <pdf> <page> <width> <png>`, both from the repository root.

## Files

- `results.json`: per-case summaries for both sides (per-page p50/p95/max, repeats, CPU gate readings, versions, hashes)
- `raw/`: each child's full JSON, with per-page samples for every repeat
- `cohorts.txt`, `cohorts.json`: the cohort breakdown above, at both widths
- `run.log`: console output of the run
- `visual/`: the equivalence-check renders and the scripts that made them
