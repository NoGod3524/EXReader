# First-Image Decode Optimization Report (`perf/first-image-decode`)

## Summary

On `deck.pdf` page 1, the 57.7–58.0 ms single-image decode cost (`object 1107`, 1342×757 8-bit `DeviceRGB` with `/SMask` `object 1128`, 1342×757 8-bit `DeviceGray` + `/Matte`) was dominated by per-pixel waste in `src/pdf_image.c` and repeated restart-from-zero decompression in `src/pdf_objects.c`:

- **Single 1342×757 RGB+SMask decode (`object 1107`):** **57.992 ms → 6.981 ms** (**−88.0%**, **8.31× faster**) at 600 px; **59.065 ms → 7.064 ms** (**−88.0%**, **8.36× faster**) at 1200 px.
- **`deck @ 600` first screen:** **71.287 ms → 18.094 ms** first render (**−74.6%**, open+first **71.630 → 18.431 ms**; **75.236 → 18.256 ms** in `bench_real_doc.py` paired A/B, target ≤ 45 ms).
- **`deck @ 1200` first screen:** **80.879 ms → 27.846 ms** first render (**−65.6%**, open+first **81.280 → 28.202 ms**; **82.297 → 27.053 ms** in `bench_real_doc.py` paired A/B).
- **`word-5 @ 600` first screen:** **9.159 ms → 4.741 ms** first render (**−48.2%**; 640×480 RGB decode **6.845 ms → 1.669 ms**).
- **Warm renders & steady-state p50:** No regressions across `pptx-20`, `deck`, `word-5`, or `real-mixed-120` (all within ±3% or faster).
- **100-page fixture (`real-mixed-120 @ 1200`):** p95 **195.843 ms → 191.348 ms** (**−2.30%**, below #248's 197.0 ms); p50 **8.230 ms → 7.842 ms** (**−4.71%**).
- **Pixel equivalence:** **0 differing pixels** across all **111,897,000** small-fixture pixels and all **131,317,200** `real-mixed-120` pixels.
- **Test suite:** CTest **577/577 passed** (`77.64 s`).

---

## 1. Instrumentation Breakdown of the 57.7 ms First Image Decode

Before making any conclusion or optimization, `decode_image` (`src/pdf_image.c`), `decode_flate` / `undo_predictor` (`src/pdf_objects.c`), and `exr_pdf_soft_mask_build` (`src/pdf_softmask.c`) were instrumented with `QueryPerformanceCounter` timers (`trace-baseline.json`, `trace-optimized.json`, 3 runs per cell gated at ≤ 15% system CPU).

### 1.1 Four-Way Split of the 1342×757 Image (`object 1107` + `/SMask` `object 1128`, `deck @ 600`)

#### Top-level `decode_image(object 1107)` view

| Stage | Baseline median (ms) | Share of 57.992 ms | Optimized median (ms) | Saving (ms) | Speedup | What happens in this stage |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **1. Inflate (`payload_ms` / `decode_flate`, main RGB)** | **5.168** (`flate_ms` 5.165, `pred_ms` 0.0001) | 8.9% | **3.319** (`flate_ms` 3.318) | −1.849 | 1.56× | Decompress 3,047,682 bytes of 8-bit RGB (`Predictor=1`). Baseline called `mz_uncompress2` **11 times** from byte 0 (`4 KB → 4 MB`, attempting 8,384,512 bytes). |
| **2. Colour conversion & matte loop (`loop_ms`, main RGB)** | **45.091** | **77.8%** | **2.020** | **−43.071** | **22.32×** | 1,015,894 pixels: sample extraction + `/Matte` unpremultiplication + `DeviceRGB` conversion. Because `matte=1`, baseline disabled `memo` (`memo=NULL`) and ran 24 bit shifts + 6 `double` divisions + `exr_pdf_colorspace_rgb_intent` + 3 `floor()` calls per pixel. |
| **3. Soft mask (`smask_ms`, child `/SMask` `object 1128` + `pdf_softmask.c`)** | **7.710** (`pdf_softmask.c`: **0.000**) | 13.3% | **1.625** (`pdf_softmask.c`: **0.000**) | **−6.085** | **4.74×** | Recursive `decode_image` of 1342×757 8-bit `DeviceGray` `/SMask` (`1.158 ms` Flate across 9 retries + `6.360 ms` Gray sample/memo/RGBA loop + `0.089 ms` other). Graphics-state `build_mask` (`pdf_softmask.c`) is **not called** (0 calls, 0.000 ms) on `deck` page 1. |
| **4. Other (dict, bounds check, `malloc`, wrapper)** | **0.022** (`alloc_ms` 0.014) | 0.04% | **0.013** (`alloc_ms` 0.005) | −0.009 | 1.69× | Dictionary lookups, `malloc(4,063,576)` for output RGBA buffer, texture struct wrapper. |
| **Total (`object 1107` decode)** | **57.992** | **100.0%** | **6.981** | **−51.011** | **8.31×** | — |

#### Leaf-level combined view (merging main + child `/SMask` into pure functional categories)

When the child `/SMask` (`object 1128`, `7.630 ms` internal total, `7.710 ms` parent-bracketed) is expanded into its own inflate, pixel conversion, and allocation components:

| Combined leaf category | Baseline median (ms) | Share | Optimized median (ms) | Saving (ms) |
| --- | ---: | ---: | ---: | ---: |
| **Total Inflate** (main RGB `5.165 ms` [11 calls] + `/SMask` Gray `1.157 ms` [9 calls]) | **6.322** | 10.9% | **3.981** (`3.318 + 0.663`) | −2.341 |
| **Total Colour / Sample / Matte Conversion** (main RGB+Matte `45.091 ms` + `/SMask` Gray→RGBA `6.360 ms`) | **51.450** | **88.7%** | **2.948** (`2.020 + 0.928`) | **−48.502** |
| **Graphics-state `build_mask` (`src/pdf_softmask.c`)** | **0.000** (0 calls) | 0.0% | **0.000** (0 calls) | 0.000 |
| **Total Other** (dict resolution, `malloc`/`calloc`, call/wrapper overhead) | **0.220** | 0.4% | **0.052** | −0.168 |
| **Total (`object 1107` + `object 1128`)** | **57.992** | **100.0%** | **6.981** | **−51.011** |

### 1.2 All Images Decoded on `deck` Page 1 and `word-5` Page 1 (3-run medians at 600 px)

| Fixture | Object ID (Role) | Size & Format | Baseline total (ms) | Baseline inflate (ms) | Baseline smask (ms) | Baseline loop (ms) | Optimized total (ms) | Optimized inflate (ms) | Optimized smask (ms) | Optimized loop (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `deck` | `1107` (main RGB+Matte) | 1342×757 8-bit RGB | **57.992** | 5.168 | 7.710 | 45.091 | **6.981** | 3.319 | 1.625 | 2.020 |
| `deck` | `↳ 1128` (`/SMask` of 1107) | 1342×757 8-bit Gray | 7.630 | 1.158 | — | 6.360 | 1.591 | 0.663 | — | 0.928 |
| `deck` | `1460` (RGB+Matte) | 190×160 8-bit RGB | 1.627 | 0.104 | 0.268 | 1.233 | 0.566 | 0.068 | 0.097 | 0.391 |
| `deck` | `1550` (RGB+Matte) | 190×160 8-bit RGB | 1.705 | 0.182 | 0.278 | 1.256 | 0.523 | 0.055 | 0.081 | 0.378 |
| `deck` | `1505` (RGB+Matte) | 95×62 8-bit RGB | 0.329 | 0.033 | 0.074 | 0.214 | 0.264 | 0.011 | 0.024 | 0.222 |
| `deck` | `1595` (RGB+Matte) | 95×62 8-bit RGB | 0.339 | 0.034 | 0.077 | 0.220 | 0.294 | 0.012 | 0.025 | 0.249 |
| `deck` | `1640` (RGB+Matte) | 95×62 8-bit RGB | 0.324 | 0.033 | 0.076 | 0.213 | 0.287 | 0.011 | 0.029 | 0.241 |
| `deck` | `1685` (RGB+Matte) | 95×62 8-bit RGB | 0.325 | 0.035 | 0.077 | 0.209 | 0.272 | 0.011 | 0.029 | 0.229 |
| **Sum of 7 `deck` p1 decodes** | — | — | **62.641** | **5.589** | **8.560** | **48.436** | **9.187** | **3.487** | **1.910** | **3.730** |
| `word-5` | `529` (RGB, no mask) | 640×480 8-bit RGB | **6.845** | 1.910 | 0.000 | 4.908 | **1.669** | 1.139 | 0.000 | 0.522 |

---

## 2. Root Causes Identified & Fixed

1. **Bit-by-bit `sample()` extraction on byte-aligned 8-bit streams (`src/pdf_image.c`):**
   - `sample()` looped `for (i = 0; i < bits; i++)` extracting 1 bit per iteration even when `bits == 8` (24 loop iterations per RGB pixel + 8 per Gray mask pixel = 32.5 million bit-shift iterations on `1107`+`1128`).
   - Replaced with `sample_at(bytes, index, bits)` with direct indexing for `bits == 8, 16, 4, 2, 1`.
2. **Per-pixel floating-point `/Matte` unpremultiplication and `DeviceRGB` / `DeviceGray` conversion (`src/pdf_image.c`):**
   - Because `object 1107`'s `/SMask` has `/Matte`, `decode_image` set `memo = NULL` and executed 6 `double` divisions, `fmax`/`fmin` clamps, a cross-TU call to `exr_pdf_colorspace_rgb_intent`, and 3 `floor(rgb[k]*255+.5)` calls on all 1,015,894 pixels (**45.091 ms**), while `object 1128` (`DeviceGray`) allocated a 1024-slot memo table and hashed every pixel (**6.360 ms**).
   - Added an exact 8-bit `DeviceGray` / `DeviceRGB` LUT path (when `codec != EXR_PDF_STREAM_JPEG && bits == 8 && !stencil && (!inks || !inks->pixels) && !color_key`):
     - When `!matte`, precomputes the 256-entry `lut[k][256]` (and `uint32_t gray_rgba[256]` for `DeviceGray`) using the exact IEEE-754 `double` `Decode` and `floor(val * 255 + .5)` formula.
     - When `matte`, fast-paths `ma == 0` to `{0, 0, 0, 255}` and lazily populates `matte_lut[ma][k][256]` on first sight of each non-zero mask alpha `ma` using the exact IEEE-754 `double` matte formula (only 43 non-zero `ma` values occur across all 1,015,894 pixels of `object 1107`).
3. **Repeated restart-from-zero Flate decompression (`src/pdf_objects.c`):**
   - `decode_flate` called one-shot `mz_uncompress2` inside `for (capacity = 4096; capacity <= EXR_MAX_TEXT; capacity *= 2)`, discarding decompressed output and restarting from byte 0 on every `MZ_BUF_ERROR` (11 calls attempting 8.38 MB for a 3.05 MB stream).
   - Switched `decode_flate` to `tinfl_decompress` (`TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_COMPUTE_ADLER32 | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF`), which pauses at buffer full (`TINFL_STATUS_HAS_MORE_OUTPUT`) and resumes in place after `output_room` grows the buffer, while preserving the exact `output_room`, `decode_work`, Adler-32, and trailing-whitespace checks.

---

## 3. Paired Alternating A/B Verification

- **Baseline A (`origin/main` `fff5c2150`, after PR #248):** `out/first-image-decode/baseline-A/libexreader.dll` (SHA-256 `74e8e77876461867b276212830b3fd1c9cfc3816cb28fc3727fb248b23de9201`)
- **Candidate B (`perf/first-image-decode`):** `build/perf/libexreader.dll` / `out/first-image-decode/candidate-B/libexreader.dll` (SHA-256 `5aae4a7ea73785b9f9a18eaafdb162907b846cc48c0e55e752609d0e39e27907`)
- **Protocol:** All measurements alternated `AB / BA / AB` in one session, fresh child process per sample, gated on system CPU ≤ 15.0% (fail closed).

### 3.1 Unified First Screen (Cold) & Same-Process Warm Render (`firstscreen-ab.json`)

Each run starts a fresh process, times a single `exr_fixed_open` (`open_ms`), times the first `exr_fixed_render(page 0)` (`first_render_ms`), and then times 3 warm renders of the same page in the same process (`warm_render_ms`).

| Fixture @ Width | First Render A (ms) | First Render B (ms) | First Delta | Open+First A (ms) | Open+First B (ms) | Warm A (ms) | Warm B (ms) | Warm Delta | Idle CPU (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **deck @ 600** | **71.287** | **18.094** | **−74.6%** | **71.630** | **18.431** | 7.093 | 7.210 | +1.6% | 7.48, 1.95, 9.77 |
| **deck @ 1200** | **80.879** | **27.846** | **−65.6%** | **81.280** | **28.202** | 16.149 | 16.270 | +0.7% | 5.08, 4.28, 2.72 |
| **word-5 @ 600** | **9.159** | **4.741** | **−48.2%** | **9.383** | **5.012** | 1.998 | 1.911 | −4.4% | 7.03, 4.67, 3.89 |
| **word-5 @ 1200** | **14.475** | **9.508** | **−34.3%** | **14.773** | **9.749** | 5.862 | 5.870 | +0.1% | 3.57, 9.13, 5.47 |
| pptx-20 @ 600 | 1.731 | 1.464 | −15.4% | 2.094 | 1.855 | 0.811 | 0.801 | −1.2% | 2.73, 1.18, 5.91 |
| pptx-20 @ 1200 | 3.229 | 2.589 | −19.8% | 3.635 | 3.005 | 1.549 | 1.517 | −2.1% | 6.25, 5.04, 8.14 |

### 3.2 Small-Fixture p50, First Screen, and 111,897,000-Pixel Equivalence (`pptx-20-ab.json`, `deck-ab.json`, `word-5-ab.json`)

Measured with `tools/bench_real_doc.py --library-a ... --library-b ... --runs 20 --repeat 3` (paired `AB/BA/AB` per width, ≤ 15% idle gate).

| Fixture @ Width | Pages | A p50 (ms) | B p50 (ms) | p50 Delta | A First Screen (ms) | B First Screen (ms) | First Screen Delta | Compared Pixels | Differing Pixels |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pptx-20 @ 600 | 20 | 0.797 | 0.765 | −4.02% | 2.272 | 1.811 | −20.29% | 4,056,000 | 0 |
| pptx-20 @ 1200 | 20 | 1.552 | 1.594 | +2.71% | 3.629 | 2.986 | −17.72% | 16,200,000 | 0 |
| pptx-20 @ 2400 | 20 | 6.584 | 6.423 | −2.45% | 9.578 | 9.716 | +1.44% | 64,800,000 | 0 |
| **deck @ 600** | 15 | 6.998 | 6.985 | −0.19% | **75.236** | **18.256** | **−75.74%** | 3,042,000 | 0 |
| **deck @ 1200** | 15 | 16.075 | 16.080 | +0.03% | **82.297** | **27.053** | **−67.13%** | 12,150,000 | 0 |
| **word-5 @ 600** | 5 | 1.881 | 1.798 | −4.41% | **9.784** | **4.857** | **−50.36%** | 2,331,000 | 0 |
| **word-5 @ 1200** | 5 | 5.856 | 5.773 | −1.42% | **14.555** | **9.292** | **−36.16%** | 9,318,000 | 0 |
| **Total Small Fixtures** | — | — | — | **All ≤ +2.71%** | — | — | — | **111,897,000** | **0** |

### 3.3 Hundred-Page Fixture p95 (`real-mixed-120 @ 1200`, `real-mixed-120-ab.json`)

Measured with `tools/bench_real_doc.py --library-a ... --library-b ... --input tests/fixtures/pdf-large/real-mixed-120.pdf --expect-pages 120 --widths 1200 --runs 5 --repeat 3` (paired `AB/BA/AB`, ≤ 15% idle gate).

| Fixture @ Width | Metric | Baseline A | Candidate B | Delta | Reference (#248) |
| --- | --- | ---: | ---: | ---: | ---: |
| `real-mixed-120 @ 1200` | **p95 (ms)** | **195.843** | **191.348** | **−2.30%** | 197.0 ms |
| `real-mixed-120 @ 1200` | **p50 (ms)** | 8.230 | **7.842** | **−4.71%** | 8.337 ms |
| `real-mixed-120 @ 1200` | **Worst page p50 (ms)** | 218.390 (p2) | **216.107** (p2) | **−1.05%** | 226.481 ms |
| `real-mixed-120 @ 1200` | **Throughput (pages/s)** | 24.82 | **24.93** | **+0.44%** | 24.55 p/s |
| `real-mixed-120 @ 1200` | **First screen (ms)** | 156.154 | **152.417** | **−2.39%** | 152.503 ms |
| `real-mixed-120 @ 1200` | **Peak RSS (MiB)** | 107.62 | **107.57** | **−0.05%** | 107.47 MiB |
| `real-mixed-120 @ 1200` | **Compared pixels** | 131,317,200 | 131,317,200 | **0 diff (`identical=True`)** | — |

---

## 4. Acceptance Checklist

- [x] **Four-way breakdown of 57.7 ms first image decode:** Measured 57.992 ms median on `object 1107` (`deck@600`): main inflate `5.168 ms` (8.9%), main colour/matte loop `45.091 ms` (77.8%), child `/SMask` `7.710 ms` (13.3%; `1.158 ms` inflate + `6.360 ms` Gray loop + `0.089 ms` other; `pdf_softmask.c` `build_mask` = `0.000 ms`), other `0.022 ms` (0.04%). Reduced to **6.981 ms** total (**−88.0%**).
- [x] **`deck @ 600` first screen显著下降 (target ≤ 45 ms):** **71.287 ms → 18.094 ms** (`bench_firstscreen` child, open+first `71.630 → 18.431 ms`) / **75.236 ms → 18.256 ms** (`bench_real_doc.py` paired A/B, **−75.74%**).
- [x] **`deck @ 1200` first screen显著下降:** **80.879 ms → 27.846 ms** (`bench_firstscreen` child, open+first `81.280 → 28.202 ms`) / **82.297 ms → 27.053 ms** (`bench_real_doc.py` paired A/B, **−67.13%**).
- [x] **Warm renders do not regress (±3%):** `deck @ 600` warm `7.093 → 7.210 ms` (+1.6%); `deck @ 1200` warm `16.149 → 16.270 ms` (+0.7%).
- [x] **`pptx-20` / `word-5` / `deck` p50 do not regress (±3%):** All 7 width cells between `−4.41%` and `+2.71%`.
- [x] **111,897,000 pixels zero difference:** All 111,897,000 small-fixture pixels (plus 131,317,200 `real-mixed-120` pixels) matched with 0 differing pixels.
- [x] **100-page fixture p95 does not regress (≤ 197.0 ms):** `real-mixed-120 @ 1200` p95 **195.843 ms → 191.348 ms** (−2.30%).
- [x] **CTest 577/577:** 100% passed (577/577) in `ctest.txt`.
