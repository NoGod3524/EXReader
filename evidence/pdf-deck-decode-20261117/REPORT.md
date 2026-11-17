PDF deck decode cache — 2026-11-17

The deck render target, PPTX render check, pixel comparisons and CTest pass. The strict deck open-time condition is not met: the 10,000-sample probe measured a 0.85% increase.

Continued the existing uncommitted changes on `perf/pdf-image-cache`. `/Matte` is reversed during decode and is now cached. Keys use the stable resolved stream value ID and encoded `/Length`, with a separate native-ink representation flag. Resource-dependent color spaces, inherited intent conversions, root stencils and samples wider than 64 bits remain uncached. The existing cache remains bounded to 67,108,864 bytes and 128 entries.

The retained renderer changes simplify span interiors, add a single-channel white mask row loop, preserve byte rounding with a saturating integer conversion, and share nearest-sample indices across matching image/mask grids. Tests compare the mask loop against RGBA source-over and compare the matching-grid sampler against the generic recursive sampler.

Render measurements use the local canonical `bench_engine.py`: 12 measured rounds, one warmup, two repeats, idle threshold 15%. Only `exr_fixed_render` is timed; copy/hash/PNG are outside the window. No build or test ran alongside these completed acceptance captures. The tool reports the higher repeat p50 as `p50_ms_median` when repeat=2.

| Fixture | Width | Baseline p50 ms | Final p50 ms | Change | Final repeats ms | Final p95 ms | Spread |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| deck | 600 | 145.163 | 33.383 | -77.00% | [32.509, 33.383] | 40.984 | 2.7% |
| deck | 1200 | 307.448 | 110.268 | -64.13% | [103.854, 110.268] | 121.334 | 6.2% |
| pptx-20 confirmation | 1200 | 3.474 | 3.316 | -4.55% | [3.232, 3.316] | 4.166 | 2.6% |

The initial final-build PPTX 1200px run had repeat p50s 3.167 and 10.596 ms (234.6% spread). It is retained as `measurements/final-pptx-initial-unstable.json` and excluded from the performance verdict. The separate serial confirmation above has 2.5% baseline spread and 2.6% candidate spread. The additional alternating render probe measured 3.96100 → 3.61975 ms (−8.62%).

Class-disable measurements use the saved diagnostic cache-only DLL, before the retained raster optimizations. The temporary switches are preserved in `diagnostics.patch`; the production DLL contains no diagnostic skip switch.

| Disabled classes | p50 ms | Repeats ms | Spread |
| --- | ---: | --- | ---: |
| None (decode cache fixed) | 231.944 | [226.849, 231.944] | 2.2% |
| Images | 134.043 | [132.3, 134.043] | 1.3% |
| Images + text painting | 132.834 | [126.609, 132.834] | 4.9% |
| Images + path painting | 130.621 | [126.904, 130.621] | 2.9% |
| Images + text + path painting | 122.940 | [122.051, 122.94] | 0.7% |
| Images + clipping | 20.434 | [20.347, 20.434] | 0.4% |
| Images + text + paths + clipping | 5.609 | [5.578, 5.609] | 0.6% |
| Content walker | 1.693 | [1.64, 1.693] | 3.2% |

Disabling text and paths while retaining clips measured 122.940 ms; disabling images and clips measured 20.434 ms. This directed the next work to clip rasterization. The interpreter-only measurement retains graphics-state callbacks; skipping the content walker still retains viewport/canvas setup and content-stream fetching. Rows are separate class-disable runs, not an additive partition.

Cache probe: 810 calls = 800 hits + 10 misses; 10 entries; 8,945,312 resident bytes; Matte/wide/state bypass counts all zero. The fixture has 10 distinct root image objects, not the expected 9: 6, 13, 15, 17, 19, 21, 23, 29, 31, 33. Page 1 adds 7 entries and page 2 adds 3; subsequent calls hit. The object/generation/length trace and full six-round probe are preserved in `measurements/`.

Open timing uses alternating baseline/candidate calls after 50 warmups, with 10,000 measured samples per library per fixture:

| Fixture | Baseline p50 ms | Candidate p50 ms | Change |
| --- | ---: | ---: | ---: |
| deck.pdf | 0.152200 | 0.153500 | +0.85% |
| pptx-20.pdf | 0.163400 | 0.163200 | -0.12% |

Earlier 1,000-sample open probes measured deck 0.143100 → 0.143500 ms and PPTX 0.099100 → 0.099950 ms. The later paired-render probe measured PPTX open 0.111700 → 0.112300 ms. All raw samples are retained. Deck’s strict no-slowdown condition remains unfulfilled; no tolerance was substituted.

Pixel comparison reads the compressed active RGBA snapshots, verifies their recorded SHA-256 and dimensions, and compares the actual bytes:

| Fixture | Combinations | Active RGBA pixels | Different pixels | Max channel difference |
| --- | ---: | ---: | ---: | ---: |
| deck | 30 | 15,192,000 | 0 | 0 |
| pptx | 60 | 85,056,000 | 0 | 0 |

Final CTest: **577/577 passed**, 77.09 seconds. Release build uses MinGW with the repository’s `-Werror` checks. `git diff --check` passes.

Final DLL SHA-256: `4298659cd7cd41a327f493e14625bd069592b95f5f05722c1c5d6899c83761f1`. Source hashes, baseline/candidate capture metadata, raw timings, pixel hashes, cache counters, build log and CTest output are in `measurements/`. Raw RGBA snapshots remain under `out/deck-decode/production-baseline-*` and `out/deck-decode/production-final-v5-*`.

Reproduce the final measurements serially after building: `python -X utf8 evidence/pdf-deck-decode-20261117/run_measurements.py --final-only`, then `python -X utf8 evidence/pdf-deck-decode-20261117/finish_checks.py`. The runner rejects stale DLL hashes and missing idle admission. `verify_pixels.py` can rerun the byte comparisons independently. The saved diagnostic DLL is `out/deck-decode/cache-only/libexreader.dll`; applying `diagnostics.patch` to the clean painter and using HEAD versions of `vector.c` and `affine_image.c` recreates that control while retaining the cache fix. Preserve and restore the current sources around diagnostic builds.

All work and artifacts remain in this worktree. No commit, remote PR update or workflow change was made.
