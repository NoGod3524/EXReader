Implemented item 2 only. `src/vector.c` and `src/blend.c` are unchanged from HEAD; their byte hashes and the implementation source hashes are in [report.json](report.json).

The document owns one bounded LRU of tight 8-bit coverage bitmaps, dimensions and bearings. Keys contain face identity, resolved glyph ID, F26Dot6 pixel size, four subpixel phases per axis and flags, refined by exact affine coefficients/fractional positions. A character index lets hits recover the resolved glyph ID without loading even raw CID CFF outlines. Embedded masks survive page changes and decoded-font teardown. Host-font masks use a temporary scope within the same LRU and are removed when their paint operation ends, so all masks share the entry/byte ceiling.

Default limits are 4096 entries and 64 MiB, configured through `EXR_GLYPH_ATLAS_ENTRIES` and `EXR_GLYPH_ATLAS_BYTES`; zero disables reuse. The byte ceiling also adapts to four page-sized coverage masks, with a 1 MiB floor. Entry/hash metadata counts toward the active budget. Misses use the existing vector coverage rasterizer; hits use existing pixel compositors and clipping. Sink setup completes before atlas lookup, allowing nested soft-mask painting to evict entries safely. Oversized/OOM masks and stroke/clip text, Type3, custom sinks and native CMYK groups retain their ordinary paths.

`tools/benchmark_pdf_rect.py` captured all 20 pages of `pptx-20.pdf` at 600/1200/2400 px, with five measured rounds after warmup. Its exhaustive comparison checked **85,056,000 active pixels**, with **0 differences, maximum channel delta 0, RGBA RMSE 0**. Raw snapshots, PNGs and per-page hashes are retained in `before`, `after` and `comparison`.

Final measured milliseconds (render p50 is across 100 measured page renders):

| Width | Before render | Atlas render | Before open | Atlas open |
|---:|---:|---:|---:|---:|
| 600 | 4.517550 | 4.146650 | 0.273200 | 0.243700 |
| 1200 | 16.091400 | 11.883250 | 0.233800 | 0.448900 |
| 2400 | 62.636350 | 55.122400 | 0.314900 | 0.392600 |

The 1200 px / 4 ms target was not met. Background load was uncontrolled; [intermediate captures](../glyph-atlas/README.md) also retain mixed timing results. No consistent speedup is claimed. Open values are repeated-open medians, not a separately controlled cold-process experiment. The JSON also reports derived total render ns/output-pixel; no individual subpath timings were measured.

Untimed `exr_pdf_raster_page` cache probe, fresh document per width:

| Width | First pass hits / misses | Second pass hits / misses | Resident bytes incl. metadata |
|---:|---:|---:|---:|
| 600 | 525 / 46 | 571 / 0 | 21136 |
| 1200 | 525 / 46 | 571 / 0 | 33260 |
| 2400 | 525 / 46 | 571 / 0 | 81364 |

The probe covers two complete 20-page passes and releases decoded font data after every page. [fixture-stats.jsonl](fixture-stats.jsonl) retains the counters.

**588/588 CTest tests passed**, with zero failures/errors/skips. [ctest.xml](ctest.xml) and [ctest.log](ctest.log) retain the full run. The final stress test compared 335,872 pixels with zero differences, exercising quadratic/cubic glyphs, affine transforms, exact phases, page edges, grayscale/RGBA, fractional clips, soft masks and forced cache eviction during sink setup. [stress.json](stress.json) records its counters. The standalone unit test covers LRU entry/byte bounds, key isolation and temporary-scope cleanup.

Repeat the complete capture/comparison/test/probe sequence with the retained Release DLLs:

```powershell
python -X utf8 evidence/glyph-atlas/reproduce.py --output evidence/glyph-atlas-reproduced
```

The baseline DLL, built from `2b24c3ea87144e25b371d227340cd8bc80251bb1`, remains at `build/baseline/libexreader.dll`; the final DLL is `build/perf/libexreader.dll`. Captures record their hashes. Both use MinGW GCC, Ninja and Release configuration; local dependency paths remain in `build/perf/CMakeCache.txt`. The complete pinned OpenJPEG sources were read from the existing `EXReader-pdf-fast-rect/build/perf/_deps/openjpeg-src` tree because the handoff cache contained object files only. Generated files and evidence stay inside this workspace.
