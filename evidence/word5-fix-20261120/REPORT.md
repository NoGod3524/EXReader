# Word-5 render performance at 600, 1200 and 2400 px

The final Release DLL met all three pooled-p50 targets in two locked sweeps. At 2400 px it rendered a page in 13.44 ms against 13.91 ms for PDF.js. Rectangular clip storage fell from 7,454,400 to 9,600 bytes per live mask at that width. The clip change alone put 1200 px below parity. Reaching parity at 2400 px also required reducing work in group commit and image paint. [Prior attribution](../word5-scaling-20261120/REPORT.md)

## Timing

All five pages, 12 rounds, 60 measured renders per engine and width. Ratios divide the native pooled p50 by the PDF.js pooled p50. Round wins compare sums over all five pages.

| Width | Prior ratio | Target | Native p50 ms | Identical copy ms | PDF.js p50 ms | Final ratio | Rounds won |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 0.589× | ≤ 0.70× | 2.19510 | 2.10260 | 6.42785 | **0.341×** | 12/12 |
| 1200 | 1.104× | ≤ 1.00× | 4.08705 | 4.09945 | 7.15955 | **0.571×** | 12/12 |
| 2400 | 1.717× | ≤ 1.00× | 13.44115 | 13.61615 | 13.91200 | **0.966×** | 7/12 |

Raw captures include every sample, page hash, arm order, pre-round CPU and DLL digest. The 2400 px margin was 0.47 ms. Its median absolute native/null round-sum difference was 1.86%. A single native outlier in round four raised the maximum difference to 102%. All samples are included. [600 px](raw/final/paired-600.json) · [1200 px](raw/final/paired-1200.json) · [2400 px](raw/final/paired-2400.json)

The independent repeat reversed the starting arm order and kept the same DLL and 12-round schedule. At 2400 px, both engines took longer in this session. The candidate won 11 of the 12 rounds. [Repeat lock log](raw/reverse/locks.txt)

| Width | Native p50 ms | Identical copy ms | PDF.js p50 ms | Repeat ratio | Rounds won |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 2.26095 | 2.20470 | 6.60705 | **0.342×** | 12/12 |
| 1200 | 5.25525 | 5.12730 | 9.92840 | **0.529×** | 12/12 |
| 2400 | 20.88745 | 22.28165 | 25.81695 | **0.809×** | 11/12 |

The native and null arms matched on dimensions and RGBA SHA-256 for every page and round in both sweeps. PDF.js matched the native canvas dimensions at all three widths. [Repeat 600 px](raw/reverse/paired-600.json) · [Repeat 1200 px](raw/reverse/paired-1200.json) · [Repeat 2400 px](raw/reverse/paired-2400.json)

### Changes measured along the way

| Build | 600 ratio | 1200 ratio | 2400 ratio | Native p50 at 2400 |
| --- | ---: | ---: | ---: | ---: |
| Four-row rectangle clips | 0.426× | 0.798× | 1.525× | 20.092 ms |
| Plus group block classification and opaque image taps | 0.367× | 0.640× | 1.166× | 15.171 ms |
| Plus painted bounds for isolated groups | 0.341× | 0.571× | 0.966× | 13.441 ms |

Each row used its own locked PDF.js session. The 2400 px PDF.js p50 was 13.175, 13.015 and 13.912 ms respectively. [Clip-only sweep](raw/pilot/paired-2400.json) · [Group and image sweep](raw/blocks/paired-2400.json) · [Final sweep](raw/final/paired-2400.json)

## Renderer changes

- **Rectangular clips.** Axis-aligned clips on larger canvases store four byte rows for outside, first, interior and last coverage. Nested clips multiply the already rounded parent byte by the new coverage byte, including at one-pixel intersections. The existing mask path handles arbitrary contours, unions and dense parents. Vector paint, images and compositing now read clips through a shared row accessor. [Clip construction](../../src/canvas.c) · [Row selection](../../src/graphics_internal.h) · [Dense-versus-compact regression](../../tests/test_canvas.c)
- **Group commit.** Initially transparent isolated layers record conservative painted x extents in 32 horizontal bands. Normal RGBA commit skips untouched regions, then classifies blocks of up to 32 source pixels. Fully transparent blocks need no destination access, opaque blocks copy directly and mixed blocks use the existing pixel arithmetic. Retrieving the writable layer bitmap disables the bounds optimization for that layer. Row work charges and the budget-boundary fallback remain in place. [Layer tracking](../../src/canvas.c) · [Compositor](../../src/blend.c)
- **Image paint.** Four opaque, in-bounds nearest-neighbor taps at full opacity and full clip coverage can replace the destination. The renderer averages each byte with integer rounding, including when the image is minified. Other coverage and alpha values use the existing sampler. The image test compares this path to the generic sampler. [Image paint](../../src/affine_image.c) · [Image regression](../../tests/test_pdf_image.c)

## Tests, pixels and memory

**CTest passed 577/577** on the final Release build in 110.00 seconds. [Full CTest output](raw/final/ctest.txt)

The pre-fix DLL and final DLL matched on every active RGBA pixel in the established small-fixture matrix. The additional 2400 px word-5 check brings the direct comparison to **149,169,000 pixels with zero differences**. [Pixel log](raw/final/pixels.txt)

| Fixture | Widths | Pages per width | Pixels compared | Different |
| --- | --- | ---: | ---: | ---: |
| pptx-20 | 600, 1200, 2400 | 20 | 85,056,000 | 0 |
| deck | 600, 1200 | 15 | 15,192,000 | 0 |
| word-5 | 600, 1200 | 5 | 11,649,000 | 0 |
| **Small-fixture gate** | | | **111,897,000** | **0** |
| word-5 additional | 2400 | 5 | 37,272,000 | 0 |

RSS uses peak Windows working set from three fresh processes per DLL per case, in AB, BA, AB order. The table compares the maximum of the three peaks. Every matched pair also decreased. All three large documents matched the baseline on every page's RGBA SHA-256 at 1200 px, covering 353,143,200 additional pixels. [RSS captures](raw/final/rss.json)

| Fixture | Width | Baseline peak bytes | Candidate peak bytes | Change |
| --- | ---: | ---: | ---: | ---: |
| word-5 | 600 | 34,418,688 | 33,087,488 | −3.87% |
| word-5 | 1200 | 51,200,000 | 40,763,392 | −20.38% |
| word-5 | 2400 | 112,336,896 | 70,696,960 | −37.07% |
| image-heavy-100 | 1200 | 154,300,416 | 148,676,608 | −3.64% |
| real-mixed-120 | 1200 | 112,762,880 | 106,823,680 | −5.27% |
| vector-heavy-100 | 1200 | 82,255,872 | 76,386,304 | −7.14% |

## Build and protocol

Source base is `052d2b3b2`. Its tracked renderer sources match the previous Openperf baseline `a35fed391`. The pixel and RSS baseline DLL is `89ee7f81953459f0633aa66fb6e8f8bd65cd80bb8870963414283a625ef2b0db`. The final DLL and its separately loaded null copy are `48c2a0ad9aedf4763a33e907f3eef60705bf6e56773333ba3b7cf09e2394e2c7`. Release build used MinGW GCC 16.2.0, Ninja, tests enabled, tools and AVIF disabled. A pilot test link exposed two private symbols in the new regression test. Switching that test to the public drawing sink fixed the link. [Final build](raw/bands/build.txt) · [Build gate](raw/bands/locks.txt)

The shared build gate covered compilation. Bench holder `codex-word5-fix` acquired the shared lock, checked zero build slots and refreshed its heartbeat for each sweep. The idle gate was off per the attribution protocol. Native timing covers `exr_fixed_render`. Node timing covers `page.render(...).promise`, with canvas creation before the timer. Both exclude document open, page lookup and RGBA hashing. PDF.js 3.11.174 ran on Node 24.19.0 with node-canvas 3.2.3. [Final lock log](raw/final/locks.txt) · [Comparator](../../../EXReader-openperf/tools/render_vs_pdfjs.py)

Run `./evidence/word5-fix-20261120/run.ps1` from PowerShell with `build final`, then `bench final`, then `test final`. Use `bench reverse` for the reversed starting order. The bench mode also runs the baseline pixel and RSS comparisons when the run name is `final`. [Driver](run.ps1) · [Validation matrix](validate.py)
