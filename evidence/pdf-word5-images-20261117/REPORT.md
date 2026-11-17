# PDF word-5 rendering evidence

The reviewed build reached **7.257 ms/page p50 at 1200 px** against the **10 ms** target. The same-session baseline was **16.897 ms/page**, a **57.1%** reduction. At 600 px, p50 fell from **7.111 to 2.582 ms/page**, a **63.7%** reduction. The 1200 px target applies to repeated page renders after one warmup round.

## Benchmark setup

Baseline `04e7a31a1` and candidate `75a2d3738` were Windows x64 MinGW GCC 16.2.0 Release builds with PDF, PDF edit and tests enabled. The host used an Intel Core Ultra 7 256V, the Balanced power plan and Python 3.14.7. The [manifest](manifest.json) records the DLL, fixture and capture hashes.

The handoff copy of `bench_engine.py` reported a 1200 px p50 summary of **7.261 ms** for the candidate, with repeat p50s of **7.218** and **7.261 ms** and launch CPU at **8.20%**. That version reports the larger of two repeat p50s and gates the first capture. The benchmark wrapper from `ffe8b67f4` gated every repeat at **15%** system-wide CPU and took the median of the two repeat statistics. Launch CPU ranged from **0.78% to 14.96%** across its 60 repeats. Each repeat measured 12 rounds over all pages after one warmup round. CPU during capture includes the benchmark process. The fresh suite ran serially after the duplicate in-flight capture scripts were stopped. Build, CTest and pixel comparison work ran outside the timing suite. [Handoff run](bench/word-handoff.json) · [Gated word-5 baseline](bench/word-base.json) · [Gated word-5 candidate](bench/word-final.json)

## Render and open results

All timings are in milliseconds. Render deltas use the same-session baseline.

| Fixture | Width | Baseline p50 | Candidate p50 | Change | Baseline → candidate p95 | Repeat p50 spread | Baseline → candidate open p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| word-5 | 600 px | 7.111 | 2.582 | −63.7% | 8.251 → 3.264 | 0.5% → 0.5% | 0.061 → 0.061 |
| word-5 | 1200 px | 16.897 | 7.257 | −57.1% | 18.605 → 8.528 | 0.0% → 5.3% | 0.061 → 0.062 |
| pptx-20 | 600 px | 2.224 | 1.680 | −24.5% | 2.920 → 2.248 | 25.0% → 2.8% | 0.121 → 0.111 |
| pptx-20 | 1200 px | 3.439 | 2.883 | −16.2% | 4.372 → 3.665 | 2.6% → 3.1% | 0.117 → 0.116 |
| pptx-20 | 2400 px | 12.301 | 9.096 | −26.1% | 18.150 → 10.878 | 8.1% → 0.6% | 0.114 → 0.123 |
| deck | 600 px | 32.264 | 38.710 | +20.0% | 39.293 → 45.404 | 0.6% → 16.0% | 0.164 → 0.167 |
| deck | 1200 px | 120.572 | 120.895 | +0.3% | 131.497 → 127.789 | 1.6% → 0.7% | 0.202 → 0.168 |

At 1200 px, pptx-20 passed the guard against both the same-session baseline and the handoff reference of 3.283 ms. Its canonical open p50 was 0.116 ms, within the handoff's 0.10–0.13 ms range. [PPTX baseline](bench/pptx-base.json) · [PPTX candidate](bench/pptx-final.json)

At 1200 px, deck was within 3% of the same-session baseline. Both builds exceeded the historical 86.274 ms reference and its 88.862 ms ceiling. The 600 px sequential run showed a 20.0% slowdown with 16.0% repeat spread on the candidate. [Deck baseline](bench/deck-base.json) · [Deck candidate](bench/deck-final.json)

An idle-gated paired deck probe alternated DLL order per page across 12 measured rounds after one warmup. Paired p50 was **40.795 → 40.721 ms at 600 px (−0.18%)** and **120.216 → 120.721 ms at 1200 px (+0.42%)**. [600 px paired run](deck-paired-600.json) · [1200 px paired run](deck-paired-1200.json)

An idle-gated open probe alternated DLL order for 1,000 opens per build and fixture after 50 warmups. It measured word-5 at **0.0554 → 0.0574 ms**, pptx-20 at **0.1032 → 0.1068 ms**, and deck at **0.1459 → 0.1501 ms**. PPTX stayed within the historical range. The paired open change was +0.0036 ms and the canonical 1200 px open change was −0.001 ms. The strict no-slowdown open guard has mixed evidence. [Alternating open probe](open-probe.json)

## Word-5 component ablations

The 1200 px runs below used two separate diagnostic DLLs with temporary `EXR_DIAG_SKIP` switches. Each difference compares the selected switch with the fully enabled run of the same diagnostic DLL. Changing a callback can alter the cost of downstream compositing, so the deltas overlap. The image-load estimate is the difference between skipping only the RGB image draw and skipping the entire image event. It includes image-event work and any decoding or cache lookup performed in the warmed benchmark. The page-group switch bypasses the root group around page content and the annotation pass. The all-skips row measures the work left by those switches, including content traversal and output setup. The production DLLs used for the render, open and pixel checks contain none of these diagnostics.

| Disabled work | Mask | Baseline p50 (ms) | Baseline savings (ms) | Candidate p50 (ms) | Candidate savings (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fully enabled diagnostic control | 0 | 16.949 | 0.000 | 7.158 | 0.000 |
| Entire image event | 1 | 10.662 | 6.287 | 5.716 | 1.442 |
| RGB image draw, keeping the image load | 2 | 10.673 | 6.276 | 5.749 | 1.409 |
| Path paint, keeping clips | 4 | 16.677 | 0.272 | 6.879 | 0.279 |
| Clips, keeping path paint | 8 | 13.420 | 3.529 | 5.660 | 1.498 |
| Glyph callback | 16 | 15.512 | 1.437 | 5.798 | 1.360 |
| Root page group | 32 | 16.390 | 0.559 | 10.824 | −3.666 |
| Combined skips, residual work | 63 | 2.214 | 14.735 | 2.191 | 4.967 |

RGB image drawing accounted for the largest measured baseline saving among individual components. The observed image-load differences were 0.011 ms on the baseline and 0.033 ms on the candidate, small relative to run-to-run spread. Bypassing the root group increased candidate p50 by 3.666 ms. [Benchmark records](bench/)

## Pixel identity and CTest

The existing comparator decompresses the captured RGBA, checks each snapshot against its capture hash and compares every pixel. Each capture also checks all measured rounds against its warmup image.

| Fixture | Widths | Page/width combinations | Pixels compared | Different pixels | Max channel delta |
| --- | --- | ---: | ---: | ---: | ---: |
| word-5 | 600, 1200 px | 10 | 11,649,000 | 0 | 0 |
| pptx-20 | 600, 1200, 2400 px | 60 | 85,056,000 | 0 | 0 |
| deck | 600, 1200 px | 30 | 15,192,000 | 0 | 0 |

[Word-5 comparison](pixels-word.json) · [PPTX comparison](pixels-pptx.json) · [Deck comparison](pixels-deck.json)

The full Release CTest run on the reviewed build passed **577/577** tests in **222.96 s**, including `native-pdf-image` and `native-canvas`. The image test checks 48 fast-path and generic-path cases for byte equality. [CTest output](ctest.txt)
