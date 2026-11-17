# PDF decoded-image and compositing-buffer reuse — 2026-11-17

The deck target of ≤60 ms/page is **not met**. The final DLL measures 237.200 ms/page at 1200 px. All nine image loads on each deck page use Matte and therefore retain the required original decode path. These fixtures produce no decoded-cache hits or scratch-buffer reuse. At 1200 px, decoding is not the largest measured component; clip callbacks take more time. At 600 px, decoding accounts for 56.2% of elapsed time.

Implementation: document-owned decoded texture trees, bounded by 64 MiB and 128 entries by default, with LRU eviction. Keys include the stable document-local stream value ID, resource dictionary, rendering intent, stencil color and native-ink mode. Hits retain the exact decoded tree, bypass inflate/conversion, and preserve the logical work charge. Owned bitmap outputs and native-ink outputs remain independent copies. Matte and >64-bit sample tuples, including mask descendants, bypass caching. Inline operand arenas use the original path. Closing the document releases its cache.

Group RGBA, floating compositing/CMYK/shape arrays and graphics-state soft-mask buffers use exact-size pools. Each pool retains at most 16 idle buffers / 64 MiB. The outer canvas owns one pool; nested PDF soft-mask canvases share the document-operation pool. Canvas destruction / operation end frees the corresponding idle buffers. Existing active layer/mask budgets remain enforced. This can retain up to 128 MiB of idle scratch across the two pool scopes during a render, separately from the decoded cache.

`src/vector.c` is unchanged from baseline `baf348d2d`; the manifest records its Git blob hash. No clipping function was edited.

## Render measurements

Same Release build configuration as the handoff, MinGW GCC 16.2.0, baseline commit `baf348d2d`. Each width has one warmup round and 12 measured rounds across every page, repeated twice. The supplied summary selects the **higher of two repeat p50s**, called “p50 median” by that tool. Both repeat p50s and every raw render sample are retained here. Table summaries follow that same convention; they are not a pooled median.

| Fixture | Width | Baseline repeat p50s (ms) | Final repeat p50s (ms) | Baseline summary | Final summary |
|---|---:|---|---|---:|---:|
| deck, 15 pages | 600 | 112.396, 114.456 | 115.405, 116.814 | 114.456 | 116.814 |
| deck, 15 pages | 1200 | 233.225, 233.825 | 233.829, 237.200 | 233.825 | 237.200 |
| pptx-20, 20 pages | 600 | 1.982, 2.078 | 1.961, 2.033 | 2.078 | 2.033 |
| pptx-20, 20 pages | 1200 | 3.429, 3.585 | 3.518, 3.682 | 3.585 | 3.682 |
| pptx-20, 20 pages | 2400 | 11.200, 11.396 | 11.427, 11.473 | 11.396 | 11.473 |

Deck at 1200 px is +1.4%; this is no speedup. PPTX at 1200 px is +2.7%, within the allowed ±3% against the newly measured baseline. Its repeat spread exceeds the tolerance, so an additional alternating A/B render probe was run with both DLLs loaded, alternating order for each page, one warmup and 12 measured rounds. That probe measures baseline **3.1657 ms**, final **3.1846 ms**, **+0.60%**. Its timing context differs from the canonical capture, which hashes and writes snapshots outside its render timer. Neither probe demonstrates a PPTX speedup.

Canonical deck 1200 px p95 summaries are 244.233 → 331.166 ms; the tail did not improve. All canonical reports, including open samples and dispersion, are retained rather than replacing unfavorable measurements.

The supplied Windows idle gate counted idle time inside kernel time as busy time, making a 15% gate unreachable. The workspace copy subtracts idle from kernel + user. Canonical entry CPU readings were 6.08% / 8.17% for baseline deck / PPTX and 8.95% / 4.71% for final deck / PPTX. Builds, tests, comparisons and profiles did not overlap canonical render measurements.

## Open, pixels and tests

A separate idle-gated open probe alternated DLL order over 1,000 opens per fixture and DLL, after 50 warmups. Freeing is outside the open timer:

| Fixture | Baseline open p50 | Final open p50 | Change |
|---|---:|---:|---:|
| deck | 0.1512 ms | 0.1509 ms | −0.20% |
| pptx-20 | 0.1009 ms | 0.1007 ms | −0.20% |

The later paired PPTX render probe also measured equal open p50s of 0.0989 ms. The short canonical open samples vary; the paired samples show no measured open regression.

All active RGBA bytes were decompressed from baseline and final captures and compared by the existing exhaustive pixel comparator:

| Fixture | Coverage | RGBA pixels compared | Different pixels | Max channel difference |
|---|---|---:|---:|---:|
| pptx-20 | 20 pages × 600/1200/2400 px, 60 combinations | 85,056,000 | 0 | 0 |
| deck | 15 pages × 1200 px | 12,150,000 | 0 | 0 |
| deck, extra check | 15 pages × 600 px | 3,042,000 | 0 | 0 |

Each canonical capture also checks every measured round against its warmup pixel signature. The manifest verifies that capture DLL hashes match the preserved baseline and final DLLs. Raw compressed snapshots remain locally under `out/imgcache`; per-page counts and hashes are committed in `diff-*.json`.

CTest: **577/577 passed**, final run 66.83 s, full output in `ctest.txt`. Added checks exercise cache hits after operation end, complete cached/uncached RGB + soft-mask + stencil raster equality, ordered LRU eviction while callers retain textures, document isolation, byte/entry/zero limits, stencil/intent/resource/native-ink variants, steady allocation counts under group churn and clearing a discarded buffer before reuse. Existing cancellation, work-limit and transparency tests pass.

## Attribution and actual reuse counters

The internal profile follows the same canvas, viewport and page painter as `fixed_render`. Opt-in monotonic timers surround the complete image decode, outer image-paint sink calls and clip sink callbacks. This diagnostic is separate from the headline DLL benchmark. Deck profiles use six rounds, dropping the first for timing statistics: 75 measured page renders per width. Percentages use summed measured durations; component medians need not add to the total median.

| Deck stage | 600 px median | 1200 px median | Share at 1200 px |
|---|---:|---:|---:|
| Image decode, including inflate, conversion and image masks | 63.284 ms | 63.864 ms | 27.55% |
| Painting decoded images | 15.438 ms | 64.430 ms | 27.77% |
| Clip callbacks | 21.735 ms | 83.602 ms | 35.82% |
| Remaining work | 12.180 ms | 20.775 ms | 8.85% |
| Total | 112.667 ms | 233.054 ms | 100% |

Each deck width profile records **0 hits / 810 misses**, all **810 Matte bypasses**, zero >64-bit bypasses, **0 resident decoded bytes / 0 entries**, nine image-paint calls and 57 clip callbacks per page. The initial viewport clip precedes those callback timers. The hit rate is 0%; a bounded eligible cache cannot accelerate these excluded images.

The PPTX profile has **0 image loads**, 0 hits/misses and **0 resident decoded bytes / 0 entries** across three rounds of 20 pages. A hit rate is not applicable.

Both fixtures allocate **2 pool-managed canvas/compositing pixel buffers per page**, with **0 reused buffers**: one output bitmap and one root group bitmap. This count excludes image-decoder, clip-mask, font and small metadata allocations. Thus one of those two allocations is group scratch; these fixtures do not exercise graphics-state soft-mask scratch reuse. Pool reuse is exercised by the group-churn tests. Static PDF `/Group` and `/SMask` counts do not describe the allocations actually made while rendering these fixtures.

The next performance work belongs first in the measured clip callback path, followed by decoded-image/mask sampling. This lane leaves clip logic to its separate owner. Decoding remains significant, especially at 600 px, but removing the measured 1200 px decode time would still leave most of the 233 ms render. The required Matte exclusion also prevents that removal through this cache.

## Controls and reproduction

`EXR_PDF_IMAGE_CACHE_BYTES` sets the per-document decoded-cache byte limit when first used; `0` disables it. The internal `exr_pdf_image_cache_limits` also sets the entry limit, capped at 128; zero disables reuse. `EXR_BUFFER_POOL=0` disables scratch reuse. `EXR_PDF_IMAGE_PROFILE=1` enables decode timing; headline benchmarks ran without it.

After configuring with the handoff's dependency paths and flags:

```powershell
cmake --build build/perf --parallel 6
ctest --test-dir build/perf --output-on-failure -j 6
python -X utf8 tools/bench_engine.py --library build/perf/libexreader.dll --input tests/fixtures/pdf-ppt/deck.pdf --expect-pages 15 --widths 600 1200 --runs 12 --repeat 2 --idle-threshold 15 --repo . --out out/imgcache/final-deck/bench.json
python -X utf8 tools/bench_engine.py --library build/perf/libexreader.dll --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --expect-pages 20 --widths 600 1200 2400 --runs 12 --repeat 2 --idle-threshold 15 --repo . --out out/imgcache/final-pptx/bench.json
python -X utf8 tools/probe_pdf_open.py --baseline build/baseline/libexreader.dll --candidate build/perf/libexreader.dll --input tests/fixtures/pdf-ppt/deck.pdf tests/fixtures/pdf-hybrid-real/pptx-20.pdf --out out/imgcache/open-probe.json
python -X utf8 tools/probe_pdf_open.py --baseline build/baseline/libexreader.dll --candidate build/perf/libexreader.dll --input tests/fixtures/pdf-hybrid-real/pptx-20.pdf --render-width 1200 --out out/imgcache/paired-pptx.json
python tools/benchmark_pdf_rect.py compare --before out/imgcache/baseline-pptx/.repeat-0/2400 --after out/imgcache/final-pptx/.repeat-0/2400 --output out/imgcache/diff-pptx-2400
$env:EXR_PDF_IMAGE_PROFILE='1'
build/perf/exreader-pdf-image-profile.exe tests/fixtures/pdf-ppt/deck.pdf 1200 6
Remove-Item Env:EXR_PDF_IMAGE_PROFILE
```

Use the same comparison command for all widths and both fixtures. `build/baseline/libexreader.dll` is the preserved build of `baf348d2d`; source and fixture hashes, binary hashes and measurement conventions are in `manifest.json`.
