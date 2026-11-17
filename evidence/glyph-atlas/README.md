Intermediate implementation measurements. Final implementation evidence is in [../glyph-atlas-final/README.md](../glyph-atlas-final/README.md). This directory also contains the reusable verification driver.

Implemented item 2 only on `perf/pdf-glyph-atlas`, based on `2b24c3ea87144e25b371d227340cd8bc80251bb1`.

The PDF document owns a hash-indexed LRU of compact 8-bit coverage masks, dimensions and bearings. Its key contains a stable font dictionary identity, glyph ID, F26Dot6 pixel size, four subpixel phases per axis and rendering flags. Exact affine coefficients and fractional coordinates refine that key to preserve arbitrary PDF transforms. Embedded-font entries survive page changes and decoded-font teardown; host-provided fonts use an operation-local cache. Hits bypass outline loading, flattening and scan conversion, and use the canvas's existing pixel compositors, clip and soft mask.

`EXR_GLYPH_ATLAS_ENTRIES` defaults to 4096. `EXR_GLYPH_ATLAS_BYTES` defaults to 67108864 and cannot exceed that ceiling. The effective budget is further bounded by four page-sized coverage masks, with a 1 MiB floor, including entry and hash metadata. Either setting at zero disables reuse; settings are read at first use. Oversized glyph masks and allocation failures fall back to the ordinary path. Stroke/clip text, Type3, custom sinks and native CMYK groups retain their existing paths.

`src/vector.c` and `src/blend.c` are byte-for-byte unchanged from HEAD. Their SHA-256 values are in [report.json](report.json).

The required oracle was `tools/benchmark_pdf_rect.py`, using `pptx-20.pdf`, all 20 pages, widths 600/1200/2400 and five measured rounds after one warmup. Both independent pairs compared **85,056,000 active pixels each**, with **zero differing pixels, maximum channel delta 0 and RGBA RMSE 0**. Raw RGBA snapshots, PNGs, timings and per-page hashes remain in the capture directories.

Render p50, milliseconds:

| Pair | Width | Before | Atlas |
|---|---:|---:|---:|
| Initial | 600 | 4.479050 | 4.456500 |
| Initial | 1200 | 10.059250 | 12.664100 |
| Initial | 2400 | 52.209850 | 39.868400 |
| Repeat | 600 | 4.183350 | 4.139600 |
| Repeat | 1200 | 12.463200 | 13.553050 |
| Repeat | 2400 | 61.904200 | 64.040900 |

Open p50 for the repeat pair, milliseconds:

| Width | Before | Atlas |
|---:|---:|---:|
| 600 | 0.320300 | 0.355400 |
| 1200 | 0.507100 | 0.243900 |
| 2400 | 0.479800 | 0.244200 |

No consistent end-to-end speedup was demonstrated, and the 1200 px / 4 ms target was not met. The repeat ran after builds and tests finished; background load remains uncontrolled. The benchmark measures the complete `exr_fixed_render` call, including allocation. [report.json](report.json) includes derived total ns/output-pixel; these are not measurements of individual subpaths. Open results are the benchmark's repeated-open median, not a separately controlled cold-process experiment.

The untimed fixture probe, using `exr_pdf_raster_page` and a fresh document per width, recorded 525 hits / 46 misses during its first 20-page pass, then 571 hits / 0 misses during its second pass at every width. Resident atlas storage including metadata was 20,768 / 32,892 / 80,996 bytes, respectively, with no evictions. [fixture-stats.jsonl](fixture-stats.jsonl) records these values. The fixture contains 571 glyph requests across its 20 pages.

All **588/588 CTest tests passed**. The final expanded stress test also compared 327,680 pixels with zero differences and recorded 25,401 hits / 199 misses. It covers quadratic and cubic glyphs, all x/y quarter phases, a nearby exact fractional phase, fractional sizes, affine transforms, page edges, grayscale/RGBA, fractional clips, soft masks and font teardown. The standalone LRU test covers entry/byte eviction and key isolation. The two focused tests were rerun after expanding the stress test; see [focused-ctest.log](focused-ctest.log), [ctest.xml](ctest.xml) and [stress.json](stress.json).

To repeat captures, exhaustive comparison, CTest and cache probes with the retained DLLs in this workspace:

```powershell
python -X utf8 evidence/glyph-atlas/reproduce.py --output evidence/glyph-atlas-reproduced
```

The baseline DLL is retained at `build/baseline/libexreader.dll`; the implementation DLL is at `build/perf/libexreader.dll`. Each capture records their hashes. Both were built with MinGW GCC, Ninja and Release configuration. The local dependency configuration remains in `build/perf/CMakeCache.txt`. The handoff's `openjpeg-src` cache contained object files only, so this build read the pinned complete sources from the existing `EXReader-pdf-fast-rect/build/perf/_deps/openjpeg-src` tree; all generated files and evidence were written inside this workspace.

To regenerate the combined JSON from the existing captures without rerunning benchmarks:

```powershell
python -X utf8 evidence/glyph-atlas/reproduce.py --output evidence/glyph-atlas --summarize-only
```
