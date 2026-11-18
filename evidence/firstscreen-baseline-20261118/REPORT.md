# First screen: one definition, and where the 2 ms / 75 ms / 402 ms gap comes from

## Conclusion

The three first-screen numbers come from **one definition**. The 35× and 5× gaps come from what page 1 of each fixture contains. The tools did not cause them.

- **pptx-20, 2.2 ms.** Page 1 draws no images. Skipping images leaves its pixels unchanged, and the cache shows zero image decodes.
- **deck, 75 ms.** Page 1 decodes seven images on the first draw. One 1342×757 RGB image with a soft mask takes **56–58 ms** of that. Skipping images saves **66–67 ms**. A warm re-render of the same page takes 7.8 ms at 600 px and 16.8 ms at 1200 px.
- **long-100, 75 ms.** `make_memory_fixture.py` starts the document with deck, so its page 1 is deck page 1. Page count plays no part.
- **real-mixed-120, 402 ms.** Its page 1 is a slide that paints axial gradients through a soft mask, as the real-doc lane attributed. Page count plays no part here either.

**Correction to the "first screen beats PDF.js everywhere" claim:** on real-mixed-120 at 1200 px, EXReader's first render takes **395.9 ms** and PDF.js's takes **384.2 ms**, a ratio of **1.03×**. EXReader is not faster on that page. It is faster on every other fixture and width measured here. PDF.js's first render stays between 314 and 385 ms on every fixture, even pptx-20, which PDF.js renders warm in 0.87–2.78 ms. That makes PDF.js's first screen mostly a fixed first-call cost. EXReader leads where page 1 is cheap, and that lead says little about raster speed.

## 1. What each tool times

Every tool runs the renderer in a new child process. Process start-up and renderer module load are outside every timer. Every render timer brackets one `exr_fixed_render` call with `time.perf_counter_ns`. Bitmap allocation happens inside that call. Pixel copy, hashing, PNG encoding and `exr_bitmap_free` happen after the timer stops.

| Tool | First-render start | First-render end | Open before render | Other differences |
| --- | --- | --- | --- | --- |
| `bench_engine.py` → `benchmark_pdf_rect.py capture --child` | right before `exr_fixed_render(page 0)` in warm-up round 0 | right after the call returns; copy, hash, PNG and free come later (PNG is written in round 1) | `exr_fixed_open` is called `--runs` times (20 under `bench_engine`) and only the last handle is kept; `open_ms` is the median of those opens | it reports no open+first sum |
| `bench_memory.py engine-child` | right before `exr_fixed_render(page 0)` | right after the call returns; free comes later | one timed `exr_fixed_open`, then page enumeration, then a `STAGE opened` handshake while the parent samples memory | `first_screen_ms` = median(open + first) |
| `bench_real_doc.py` (branch `perf/real-doc-throughput`) | right before `exr_fixed_render(page 0)` in round 0 | right after the call returns; RSS sampling, hashing and free come later | one timed `exr_fixed_open`, then page enumeration | `first_screen_ms` = open + first |
| `bench_firstscreen.py child` (new) | right before `exr_fixed_render(page 0)` | right after the call returns; hashing and free come later | one timed `exr_fixed_open`, then page enumeration | `first_screen_ms` = open + first |
| PDF.js (`bench_memory_pdfjs.cjs`) | before `getPage(1)` | after `page.render().promise` resolves | `readFileSync` + `getDocument` | the render timer includes `getPage(1)`, the viewport and canvas creation |

The one real difference is how `benchmark_pdf_rect.py` opens: 20 opens of the same file. That makes its `open_ms` warm, 0.10–0.15 ms against 0.30–0.48 ms for a single open. It does not change the first render, because each document gets its own image cache and the cache is freed with the handle.

## 2. Same DLL and fixture, all four tools

DLL SHA-256 `769ff1cf589dc6033116a00b0329199a8f653011b5d59282584734e3105a5527`, built from `cc9d966e4` (current `main`).

There were three runs per cell. Each run started only after system CPU fell to 15% or lower; readings were 3.88–14.96%. Each run then executed all four tools in an order that rotated from run to run. Each cell gives the median first render in ms, followed by the spread, (max − min) / min. [Raw samples, orders, CPU readings](tools.json) · [real-mixed-120](tools-real-mixed.json)

| Fixture @ px | bench_engine / benchmark_pdf_rect | bench_memory | bench_real_doc | bench_firstscreen | Max/min of medians |
| --- | ---: | ---: | ---: | ---: | ---: |
| **deck @ 1200** | **85.957** (2.4%) | **84.092** (1.6%) | **85.069** (4.3%) | **84.584** (3.9%) | 1.022 |
| deck @ 600 | 74.174 (3.8%) | 75.028 (0.6%) | 75.927 (0.2%) | 75.755 (6.5%) | 1.024 |
| pptx-20 @ 1200 | 2.904 (4.3%) | 2.858 (6.6%) | 2.876 (4.6%) | 3.525 (15.0%) | 1.233 |
| pptx-20 @ 600 | 1.724 (8.1%) | 1.744 (20.8%) | 1.685 (10.1%) | 1.723 (8.6%) | 1.035 |
| real-mixed-120 @ 1200 | 424.911 (12.8%) | 408.107 (31.5%) | 434.933 (25.2%) | 418.251 (8.6%) | 1.066 |

On deck @ 1200 the four tools agree within 2.2%. The pptx-20 @ 1200 outlier, `bench_firstscreen` at 3.525 ms, is within that cell's 15% run-to-run spread. The same child code measured 2.812 ms (2.5% spread) in the unified run in section 4. On real-mixed-120 all four tools land on the same ~400 ms. **The tools measure the same thing.**

## 3. Why deck page 1 costs 75 ms: per-class disabling

The diagnostic DLL is a scratch build of the same commit with [`diagnostic.diff`](diagnostic.diff) applied. That patch is the real-doc lane's `instrument.py` plus a one-line trace of each image decode. With `EXR_ATTRIBUTION_SKIP=<class>` the DLL skips that class: images, filled or stroked paths (clipping is kept), glyph painting (clipping is kept), transparency groups, or `sh` shadings. The patch is not in `src/`.

There were three runs per case. Each run started only after CPU fell to 15% or lower; readings were 6.25–14.84%. The six arms ran in an order that rotated from run to run, each in a new process. Each process drew one cold render followed by three warm renders. "Saving" is the median of the per-run differences, full minus disabled. "Pixels changed" shows whether the class exists on the page. [Raw arms, traces, per-image decodes](ablation.json)

### deck page 1

| Class disabled | @600 cold (ms) | @600 cold saving | @1200 cold (ms) | @1200 cold saving | Pixels changed |
| --- | ---: | ---: | ---: | ---: | --- |
| none (full) | 75.502 | — | 82.410 | — | — |
| **images** | 9.324 | **66.234** | 15.557 | **67.287** | yes |
| paths | 71.743 | 3.758 | 79.222 | 3.428 | yes |
| glyphs | 71.220 | 5.663 | 79.441 | 2.921 | yes |
| groups | 72.718 | 2.784 | 83.243 | 0.198 | no (no groups) |
| shadings | 73.764 | 1.713 | 84.376 | −2.015 | no (no shadings) |

| deck page 1 | @600 | @1200 |
| --- | ---: | ---: |
| Cold render (ms) | 75.502 | 82.410 |
| Warm render, same page and process (ms) | 7.780 | 16.771 |
| **One-time cost, cold − warm (ms)** | **67.7** | **65.6** |
| Image callbacks on the cold render (ms) | 64.53 | 66.63 |
| Image decoding on the cold render (ms; 7 misses, 2 hits) | 62.44 | 60.69 |
| ↳ 1342×757 RGB + soft mask, Flate | **57.68** | **56.06** |
| ↳ 2 × 190×160 RGB + soft mask | 3.48 | 3.20 |
| ↳ 4 × 95×62 RGB + soft mask | 1.27 | 1.21 |

The one-time cost of 65.6–67.7 ms equals the saving from skipping images. Nearly all of it is decoding the image set, and 85–90% of it is the single 1342×757 image with a soft mask. Paths, glyphs, groups and shadings together cost about 10 ms or less.

All 15 deck pages use the same image objects. A one-off exploratory probe (one run, no idle gate) rendered each page first in a new process at 1200 px. Every page cost 83.6–90.3 ms cold and 16.5–19.8 ms warm. When one process renders pages 1–15 in order, only page 1 (7 misses) and page 2 (3 misses, 1.07 ms of decoding) decode anything. Pages 3–15 hit the cache.

### pptx-20 and word-5 page 1, for comparison

| Page 1 | Cold (ms) | Warm (ms) | Cold − warm | Image saving | Image decodes |
| --- | ---: | ---: | ---: | ---: | --- |
| pptx-20 @600 | 1.838 | 0.916 | 0.92 | 0.107 (pixels unchanged) | none |
| pptx-20 @1200 | 2.924 | 1.568 | 1.36 | 0.080 (pixels unchanged) | none |
| word-5 @600 | 9.874 | 2.248 | 7.63 | 7.313 | 1 × 640×480 RGB, no mask: 6.371 ms |
| word-5 @1200 | 15.221 | 6.543 | 8.68 | 7.787 | 1 × 640×480 RGB, no mask: 7.139 ms |

pptx-20 page 1 has no images, so it has almost nothing to do on the first draw. **That alone is the difference from deck.** word-5 sits between the two because it decodes one image without a mask.

### real-mixed-120 page 1

The ~400 ms comes from page content. The real-doc lane's paired ablations, run on the same commit lineage, found that skipping the `sh` operator cut page 1 from 570 to 139 ms. Its two axial gradients evaluated 5.1 M samples, and one of them paints inside a graphics-state soft mask. Its page 81, which has no gradients, renders cold in 3.1 ms in the same PDF. [Real-doc report](../real-doc-throughput-20261118/REPORT.md) (branch `perf/real-doc-throughput`). Its cost scales with output pixels: 111.7 ms at 600 px against 395.9 ms at 1200 px (section 4).

## 4. Unified definition and remeasurement

**Definition:** start a new process, then open the document once, then render page 1 once.
- **First render** is that one `exr_fixed_render` call. Bitmap allocation is inside the timer. PNG encoding, hashing, copying and freeing are outside it.
- **Open** is the single `exr_fixed_open` call, reported separately.
- **Open + first** is the sum of the two.
- Process start-up and module load are excluded.
- PDF.js uses the window defined in section 1.

This is `tools/bench_firstscreen.py run`. There were three runs per cell. EXReader and PDF.js alternated ABA/BAB, each sample in a new process. Each run started only after CPU fell to 15% or lower; readings were 1.17–15.00%. EXReader's page-1 RGBA hash was identical across runs for every cell. PDF.js is `pdfjs-dist` 3.11.174 legacy build with node-canvas 3.2.3 on Node v24.19.0. [Raw samples, hashes, CPU readings](unified.json)

| Fixture @ px | EXReader first (ms) | Open (ms) | Open + first (ms) | PDF.js first (ms) | PDF.js open + first (ms) | First-render ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pptx-20 @ 600 | 1.986 (37.4%) | 0.427 | 2.446 | 381.630 (14.9%) | 389.545 | 0.005× |
| pptx-20 @ 1200 | 2.812 (2.5%) | 0.334 | 3.145 | 314.370 (4.9%) | 324.248 | 0.009× |
| word-5 @ 600 | 9.609 (10.9%) | 0.252 | 9.853 | 326.587 (1.2%) | 333.420 | 0.029× |
| word-5 @ 1200 | 14.436 (1.0%) | 0.284 | 14.748 | 332.250 (3.4%) | 339.174 | 0.043× |
| deck @ 600 | 73.222 (3.5%) | 0.393 | 73.633 | 384.735 (1.5%) | 393.852 | 0.190× |
| deck @ 1200 | 83.268 (3.1%) | 0.392 | 83.660 | 382.470 (1.3%) | 391.546 | 0.218× |
| long-100 @ 600 | 73.770 (5.9%) | 0.644 | 74.413 | 373.925 (3.9%) | 383.454 | 0.197× |
| long-100 @ 1200 | 86.357 (4.5%) | 0.672 | 87.029 | 377.110 (5.3%) | 386.549 | 0.229× |
| real-mixed-120 @ 600 | 111.728 (7.3%) | 0.760 | 112.487 | 375.780 (1.8%) | 385.932 | 0.297× |
| **real-mixed-120 @ 1200** | **395.916** (8.3%) | 0.741 | 396.657 | **384.212** (5.2%) | 394.565 | **1.030×** |

The EXReader figures match #247's `memory.json` within run-to-run noise: deck @ 600 75.606 → 73.222, long-100 @ 1200 86.417 → 86.357, pptx-20 @ 600 2.156 → 1.986. #247's numbers were correct. What was missing was the explanation that each fixture's page 1 drives its first-screen figure, plus the real-mixed-120 case where EXReader does not lead.

**How to quote first screen from now on:** use `bench_firstscreen.py run`, name the fixture and its page-1 content, and do not generalise from pptx-20. The other harnesses produce the same number (section 2), but only this one reports open, first render and their sum without extra work in the timing window.

## Scope and verification

- **No performance code changed.** The only `src/` edits are in the uncommitted scratch diagnostic build, recorded in [`diagnostic.diff`](diagnostic.diff). The branch adds `tools/bench_firstscreen.py` and this evidence.
- **Test suite.** CTest passed **577/577** on the Release build from the same commit with `EXR_BUILD_TOOLS=OFF`, the #247 configuration. That build's DLL SHA-256 is `6e0e4f8f…05ab`; its build options differ from the measured tree's. [ctest.txt](ctest.txt). The measured DLL's build tree, with `EXR_BUILD_TOOLS=ON`, passed 586/586; that count includes the tool tests.
- **Fixtures.**
  - `long-100.pdf` was regenerated with `make_memory_fixture.py` and is byte-identical to #247's (SHA-256 `7d118983…af0`).
  - `real-mixed-120.pdf` is the copy from `perf/real-doc-throughput` (SHA-256 `cdfc1ee6…693`). Every JSON file records the hash of each input.
- **Host.** Windows 11 build 26200, Intel Core Ultra 7 256V, MinGW-w64 GCC 16.2.0 Release, Python 3.14.

## Reproduce

```powershell
cmake --build build/perf --parallel 6
python -X utf8 tools/make_memory_fixture.py --out out/firstscreen/long-100.pdf
# bench_real_doc.py and its helpers from perf/real-doc-throughput, unmodified:
#   git show perf/real-doc-throughput:tools/<f> > out/firstscreen/realdoc-tools/<f>
#   for bench_real_doc.py benchmark_pdf_rect.py benchmark_pdf_blend.py bench_engine.py perf_policy.py
python -X utf8 tools/bench_firstscreen.py tools --library build/perf/libexreader.dll `
  --realdoc-tools out/firstscreen/realdoc-tools `
  --case deck=tests/fixtures/pdf-ppt/deck.pdf:15 --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf:20 `
  --widths 600 1200 --runs 3 --out evidence/firstscreen-baseline-20261118/tools.json
# diagnostic DLL: a scratch worktree of the same commit, `git apply diagnostic.diff`, Release build
python -X utf8 tools/bench_firstscreen.py ablate --library <diagnostic>/libexreader.dll `
  --case deck=tests/fixtures/pdf-ppt/deck.pdf --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf `
  --case word-5=tests/fixtures/pdf-hybrid-real/word-5.pdf --widths 600 1200 --runs 3 --warm 3 `
  --out evidence/firstscreen-baseline-20261118/ablation.json
python -X utf8 tools/bench_firstscreen.py run --side engine=engine:build/perf/libexreader.dll `
  --side pdfjs=pdfjs:C:/Users/Oscar/Documents/Codex/pdfjs-bench2 `
  --case pptx-20=tests/fixtures/pdf-hybrid-real/pptx-20.pdf --case deck=tests/fixtures/pdf-ppt/deck.pdf `
  --case word-5=tests/fixtures/pdf-hybrid-real/word-5.pdf --case long-100=out/firstscreen/long-100.pdf `
  --case real-mixed-120=out/firstscreen/real-mixed-120.pdf --widths 600 1200 --runs 3 `
  --out evidence/firstscreen-baseline-20261118/unified.json
```
