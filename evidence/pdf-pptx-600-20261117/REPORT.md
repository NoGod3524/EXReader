# pptx-20 at 600 px: per-page font program re-inflation

pptx-20 at 600 px fell from **1.529 to 1.005 ms/page p50** (−34%) across interleaved canonical runs. The target was ≤ 1.2 ms. The ideal ≤ 0.9 ms (PDF.js 0.870 ms) was **not** reached.

**Cause.** `exr_pdf_operation_end` freed every decoded stream after each page. pptx-20 embeds one 80,200-byte FontFile2 used by all 20 pages, so every render re-inflated it. That decode was **0.503 ms of a 1.738 ms instrumented page** (29%). It is a fixed per-page cost, so it weighs more at 600 px than at 1200 px.

**Fix.** Font programs, ToUnicode CMaps and CIDToGIDMap streams are now read through `exr_pdf_stream_data_retained`. `exr_pdf_operation_end` keeps these decodes, up to 16 MiB per file. The kept bytes are counted in the next operation's `decoded_bytes`, so the live-memory budget is unchanged. Every other stream is still freed after each operation. No drawing, sampling or quality changes.

## Setup

- **Builds:** baseline `8c603624f` (main) and candidate `db088357a`. Both are Windows x64 MinGW-W64 GCC 16.2.0 UCRT Release (`-O3`) builds from `build/perf`.
- **Host:** Intel Core Ultra 7 256V, Balanced power plan, Python 3.14.7.
- **Hashes:** the [manifest](manifest.json) records the DLL, fixture and script hashes. The benchmarked candidate DLL differs from a clean rebuild at `db088357a` in 6 bytes only (PE timestamps and checksum).
- **Machine load:** two other agents' benchmark processes (`out/deck1200/paired.py`, `evidence/pdf-simd-blit-v2/run_ab.py`) ran on the same machine during this work. They were not stopped. Because of them, every timing below is either interleaved A/B in one session or paired in one process, and contaminated runs are reported, not dropped.

## Category-disable table (pptx-20, 600 px)

I added temporary env switches (`ZZ_SKIP`) and QPC timers to `pdf_paint.c` and the walker. The [patch](diag/profiling-instrumentation.diff) is kept as evidence and was removed from the source before commit.

Both diagnostic DLLs ran in one process ([matrix.py](diag/matrix.py)). Every category and both builds were interleaved within each of 20 rounds, after one warmup round. Values are p50 ms/page over 400 renders.

| Disabled work | Baseline p50 | Baseline saving | Candidate p50 | Candidate saving |
| --- | ---: | ---: | ---: | ---: |
| Nothing (full) | 1.671 | — | 1.056 | — |
| Image event | 1.680 | −0.009 | 1.010 | 0.046 |
| Path paint (clips kept) | 1.417 | 0.254 | 0.775 | 0.281 |
| Glyph callback (outline + fill) | 1.118 | 0.553 | 0.511 | 0.545 |
| Glyph fill only (outline kept) | 1.260 | 0.411 | 0.610 | 0.446 |
| Content groups | 1.628 | 0.043 | 1.047 | 0.009 |

pptx-20 has no image or content-group events, so those rows are noise.

The switches did not find the fixed cost: each one removes about the same time from both builds. The candidate is about 0.6 ms lower under every switch. The font is opened in the `Tf` operator inside the content walker, which none of the paint-callback switches bypass. The timers located it ([baseline](diag/timers-base.txt) · [candidate](diag/timers-new.txt), µs per page, 420 renders):

| Stage | Baseline µs/page | Candidate µs/page |
| --- | ---: | ---: |
| `exr_fixed_render` total | 1738.0 | 1238.7 |
| `exr_pdf_draw_ops` | 1333.4 | 827.6 |
| `exr_pdf_font_open` (`Tf`) | **507.5** | **5.0** |
|   of which FontFile2 `stream_data` (80,200 B inflate) | **502.9** | **1.2** |
| path events (7/page, incl. clips) | 343.2 | 349.4 |
| glyph fill `geometry` (28.5 glyphs/page) | 308.1 | 303.1 |
| root page group begin + end | 236.9 | 246.4 |
| full-page canvas clip | 85.0 | 87.6 |
| canvas create / FT init / face open | 12.9 / 7.6 / 12.5 | 14.0 / 7.3 / 13.7 |

What remains is mostly path and glyph rasterization, plus about 0.24 ms for the root page group.

## Render results

All values are ms/page. "Canonical" is the handoff `bench_engine.py`: 20 runs × 3 repeats, 15% idle gate, median of repeat p50s. Runs alternated base, new, new, base for each fixture. Word-5 and deck at 1200 px got a second alternated pair (runs 3–4), because candidate run 2 at that width was hit by outside load. "Paired" is [paired_ab.py](paired_ab.py): both DLLs in one process, call order swapped on every page, 15% idle gate before each round. Its absolute values are higher than canonical (two DLLs share caches, and the machine was loaded), so only its relative change should be read.

| Fixture | Width | Baseline canonical p50 (runs) | Candidate canonical p50 (runs) | Change | Paired change |
| --- | ---: | --- | --- | ---: | ---: |
| pptx-20 | 600 | 1.543, 1.515 | **1.011, 0.999** | −34.3% | −36.1% |
| pptx-20 | 1200 | 2.701, 2.828 | 2.107, 2.023 | −25.3% | −20.3% |
| word-5 | 600 | 2.498, 2.590 | 2.505, 2.375 | −4.1% | −8.3% |
| word-5 | 1200 | 7.130, 7.472, 7.084, 7.038 | 7.139, *9.179*, 6.900, 6.913 | −2.7% (excl. *9.179*) | −4.7% |
| deck | 600 | 39.883, 39.841 | 35.175, 35.105 | −11.8% | −12.2% |
| deck | 1200 | 121.057, 120.653, 120.846, 118.936 | 116.817, *176.346*, 115.040, 114.227 | −4.2% (excl. *176.346*) | −3.9% |

- **Italic runs were contaminated.** Word-5 candidate run 2 at 1200 px was the only candidate run above every baseline run. Deck candidate run 2 at 1200 px had 209% repeat spread, best 116.956 against median 176.346. Both were rerun in fresh alternated pairs. The paired probes, which share the load between builds, agree with the clean runs.
- **Repeat spread and pre-run CPU.** The CPU busy share measured before each canonical run was 4.3–14.8%. Repeat spread was ≤ 5.8% in every run except these: baseline deck 1200 run 1 at 17.4% and word-5 600 run 2 at 23.2%; candidate pptx 1200 run 1 at 18.8%, deck 600 runs at 11.8% and 9.2%, and word-5 600 runs at 13.8% and 13.9%, plus the two contaminated runs. Each run's p95, spread and idle CPU are in [bench/](bench/). The paired probes' per-round idle readings were 3.9–14.5%, except one pptx 1200 round at 79.7%, which still affected both builds equally.
- **Other fixtures improved too.** Word-5 and deck also embed fonts that were re-inflated on every page.

### Against the handoff numbers

| Guard | Handoff reference | This session's baseline | Candidate | Result |
| --- | ---: | ---: | ---: | --- |
| pptx-20 @600 ≤ 1.2 (ideal ≤ 0.9) | 2.064 | 1.529 | 1.005 | pass (ideal not met) |
| pptx-20 @1200 no slowdown (±3%) | 2.817 | 2.764 | 2.065 | pass |
| deck @1200 no slowdown (±3%) | 51.564 | 120.373 | 115.361 | pass |
| word-5 @1200 no slowdown (±3%) | 7.032 | 7.181 | 6.984 | pass |

The handoff's deck 51.564 ms and pptx 2.817 ms numbers come from the unmerged #243 branch. main still renders deck @1200 in about 120 ms, so the guard is checked against this session's baseline. The candidate column averages the clean runs.

## Open time

The change does not touch the open path. Canonical open p50 (ms, baseline runs → candidate runs):

| Fixture | Canonical | Paired (1,000 alternating opens per build, two sessions) |
| --- | --- | --- |
| pptx-20 | 0.106, 0.114 → 0.107, 0.106 | −0.12%, −0.06% |
| word-5 | 0.060, 0.060 → 0.057, 0.068 | −0.30%, +0.51% |
| deck | 0.148, 0.142 → 0.143, 0.143 | −0.39%, −0.27% |

The single +0.51% paired reading is +0.0005 ms (0.0985 → 0.0990). The handoff guard values were pptx 0.11, deck 0.16 and word-5 0.06 ms.

## Pixel identity and CTest

`tools/benchmark_pdf_rect.py compare` decompressed every captured RGBA page and compared each pixel. Each capture also checks its measured rounds against the warmup image.

| Fixture | Widths | Pixels compared | Different | Max channel delta |
| --- | --- | ---: | ---: | ---: |
| word-5 | 600, 1200 | 11,649,000 | 0 | 0 |
| pptx-20 | 600, 1200, 2400 | 85,056,000 | 0 | 0 |
| deck | 600, 1200 | 15,192,000 | 0 | 0 |
| **Total** | | **111,897,000** | **0** | **0** |

[Word-5](pixels-word.json) · [PPTX](pixels-pptx.json) · [Deck](pixels-deck.json)

Full Release CTest: **577/577 passed** ([output](ctest.txt)). `native-pdf-objects` now also checks that a retained Flate stream keeps the same decoded pointer and bytes after `exr_pdf_operation_end`.

## Remaining gap to PDF.js

At 1.005 ms the page is still about 15% slower than PDF.js's 0.870 ms. The next fixed costs per page are the root page group (≈ 0.24 ms, begin + end) and the full-page clip (≈ 0.085 ms). Neither was touched here.
