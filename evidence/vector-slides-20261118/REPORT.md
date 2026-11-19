# vector-heavy-100 p1–10 courseware slides at 1200 px

On current main, pages 1–10 of vector-heavy-100 took **472.94 ms in EXReader and 362.25 ms in PDF.js**, a **+110.69 ms** gap. These pages are not vector or table pages: path painting costs about 1 ms in total, and neither the #253 nor the #266 compound path runs. Most of the time goes to a shared full-page background JPEG and a soft-masked axial shading on every page.

The change extends #263's exact uniform-span image path from magnified images to images minified by up to two texels per pixel. In the 12-round bilateral run, the candidate narrowed the p1–10 gap from **+116.80 to +15.08 ms**, a **+101.72 ms** reduction. It was faster in **60/60** warm sweeps. The same-protocol identity control moved the gap by **−2.08 ms**. In the production native A/B, the median paired saving was **90.54 ms (20.16%)**, faster in **12/12** sweeps. The same-DLL empty control gave **5.09 ms (1.15%)**. Every pixel matched: **353,143,200 + 111,897,000 pixels, zero differences**. CTest passed **577/577**.

## 1. Current state and code paths

### Fresh baseline on main

Main is `5580d505b`. Its renderer sources match `d704cdacc` (#267). EXReader and PDF.js ran 12 fresh rounds. Each round had one cold and five warm sweeps, and the engine alternated AB/BA page by page, with the starting engine reversed every sweep and every round.

| Session | EXReader (ms) | PDF.js (ms) | Gap (ms) |
| --- | ---: | ---: | ---: |
| twocells fresh baseline | 621.03 | 395.16 | +225.87 |
| This session, `5580d505b`, 12 rounds | **472.94** | **362.25** | **+110.69** |
| Change | −148.09 (−23.85%) | −32.91 (−8.33%) | −115.18 (−51.0%) |

- **Paired gaps:** the median of the per-round median paired gaps was +118.39 ms, with round values from +100.26 to +146.64 ms.
- **Machine drift:** EXReader's round medians ranged from 423.90 to 582.50 ms, so the absolute totals moved substantially between rounds. The paired gap is the more stable quantity.
- **Interpreting the change from twocells:** it is a cross-session difference. It mixes main's progress with machine and session drift. #264 (clipped axial scan narrowing) and #267 (mask row reuse and RGB group commit) both act on these courseware pages. The two sessions were not run in pairs, so this report does not attribute the change to either PR. [Baseline captures](raw/)

### Content

The ten pages are courseware slides 6, 8, 9, 10, 11, 13, 14, 18, 20 and 21, the same source that real-mixed-120 p1–21 uses. [Fixture generator](../../tools/generate_real_doc_fixtures.py)

| Operator class | Count across p1–10 |
| --- | ---: |
| Stroke `S` / fill `f*` | 33 / 15 |
| Fill-and-stroke `B` / `B*` | **0** |
| Path segments `m` / `l` / `re` | 44 / 112 / 332 (328 rectangles are clip paths) |
| Explicit clips `W* n` | 328 |
| Text-show `TJ` | 238 (4,503 glyph outlines at run time) |
| Image draws `Do` | 20: one 1500×1125 JPEG background and one 1920×154 JPEG banner per page, both `/Interpolate true`, both shared across all ten pages |
| Shadings `sh` | 11 on pages, plus 10 inside soft masks |
| Graphics-state soft masks | 10 luminosity masks, each a non-isolated transparency group holding one clipped axial shading |
| Page `/Group` | 10 |

[Per-page operator audit](vector-heavy-100-operator-audit.json)

### Instrumented paths

The probe DLL applies the #267 probe plus per-class top-level timers, a compound-path marker and an image-branch marker. [Probe patch](probe.patch) Its rendered output matched the production main DLL on 20 full-input and 50 edited-input page hashes. The figures below come from the second of two full passes and include probe overhead, which also writes one line per path. [Trace](raw/probe-full.txt.gz) · [Summary](raw/probe-summary.json) · [Runner](probe.py)

| Top-level class (p1–10) | Calls | Probe time (ms) |
| --- | ---: | ---: |
| Image draws | 20 | 239.80, of which the backgrounds take 211.12 and the banners 28.16 |
| Shading sources | 11 | 188.84, including 10 soft-mask builds at 142.61 |
| Glyph outlines | 4,503 | 80.67 |
| Clip callbacks | 328 | 8.44 |
| Path fills / strokes | 15 / 33 | 0.25 / 0.82 |
| Fill+stroke compounds | **0** | 0 |
| Total page draw | 10 | 528.73 |

- **#253 coverage-bounded compound and #266 opaque compound spans: not taken.** `exr_composite_compound` ran zero times. The canvas received 4,551 paths: 4,518 fill-only (glyphs and the 15 fills) and 33 stroke-only.
- **#245 scanline coverage reuse: 0%.** Zero of 75,159 general scanline rows were eligible. Active crossings were 807,356 of 12,217,216 edge tests (6.61%). A separate exact-rectangle path covered 52,340 rows.
- **#248 axial reuse.** All 21 shading paints used the clipped axial path. Zero rows used generic sampling, and 12,543,870 of 12,867,000 covered pixels reused the previous sample (97.49%).
- **Soft masks.** The 10 mask builds took 130.26 ms to rasterize:
  - 40.27 ms preparing the canvas, clip and non-isolated group state;
  - 74.42 ms painting content;
  - 14.32 ms committing the group.

  Extraction took 8.95 ms. Of 9,000 rendered mask rows, 6,430 (71.44%) repeated the previous row.
- **Images.** All 20 draws took the SSE2 `bilinear_axis` → `axis_paint` path with no composite state. The background has no clip; the banner has one. At 1200 px the background is minified to 1.25 texels per pixel. #263's uniform-span path was gated to magnified images, so every background pixel paid 16 bilinear taps.

The PDF.js operator list showed the same work: 21 shading operators and 10 soft-mask groups.

## 2. Drawing-class ablation

All rows use 12 fresh rounds, with five warm sweeps and four arms per round. EXReader and PDF.js open the same edited PDF. Arms alternate AB/BA by page, the starting engine reverses each sweep, the full-versus-edit order is balanced, and the class order reverses on every other round. A positive reduction means the edit narrowed the gap. The point estimate averages all 60 paired warm sweeps; the range shows the 12 round means.

Each edit is an incremental update that keeps the original bytes as a prefix. The builder parses every edited stream and asserts that exactly the expected operators were removed or replaced. Path omissions replace the paint operator with `n`; the clip omission keeps the path and the `n`. [Variant builder](variants.py) · [Operator audit](vector-heavy-100-operator-audit.json) · [Driver](ablate.py)

| Edit, both engines | EXReader full → edit (ms) | PDF.js full → edit (ms) | Gap reduction (ms) | Round range (ms) | Changed pages, EXReader / PDF.js |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Identity (empty control)** | 558.83 → 557.29 | 435.25 → 431.63 | **−2.08** | −63.57 to +44.47 | 0 / 0 |
| 10 mask-internal shadings | 534.29 → 409.93 | 408.94 → 403.62 | **+119.03** | +100.09 to +149.66 | 10 / 10 |
| 11 page shadings (also skips the mask builds) | 538.63 → 324.78 | 416.82 → 316.51 | +113.55 | +101.48 to +142.54 | 10 / 10 |
| All 21 shadings | 543.17 → 334.96 | 424.48 → 313.00 | +96.73 | +77.38 to +117.21 | 10 / 10 |
| 20 image draws | 524.17 → 293.33 | 403.73 → 230.04 | **+57.15** | +33.71 to +77.54 | 10 / 10 |
| 328 explicit clips | 535.46 → 610.45 | 417.95 → 601.18 | +108.24 | +77.30 to +161.66 | 1 / 1 |
| 15 fills | 511.40 → 511.15 | 391.83 → 392.80 | +1.22 | −9.74 to +23.54 | 7 / 7 |
| 33 strokes | 528.59 → 525.96 | 409.23 → 406.99 | +0.39 | −53.08 to +26.79 | 10 / 10 |
| 10 page `/Group` entries | 529.55 → 527.54 | 410.00 → 412.24 | +4.25 | −16.27 to +54.07 | 0 / 0 |
| 238 text-show operators | 536.84 → 481.28 | 419.85 → 338.79 | −25.51 | −85.05 to −2.36 | 10 / 10 |
| 10 graphics-state soft masks | 520.80 → 681.56 | 398.54 → 291.95 | −267.34 | −336.73 to −193.31 | 10 / 10 |

The identity control's round range spans about ±50 ms. On that basis:

- **Fill, stroke and page-group edits:** inside the noise. Path painting is not a measurable contributor on these pages.
- **Shading:** the mask-internal shadings are the largest isolated gap. Omitting them saved EXReader 124.36 ms while PDF.js changed by 5.32 ms.
- **Images:** narrowed the gap in every round.
- **Clips:** removing them slowed both engines, PDF.js by more. Removal leaves the page unclipped, so it measures downstream work rather than clip cost; it is not a clip-cost estimate.
- **Text:** EXReader is already faster than PDF.js.
- **Soft masks:** removing them made EXReader slower, because the page shading then paints unmasked across its whole clip.

The 144 accepted runs (12 baseline + 132 ablation) passed the 15% CPU idle gate at 5.08–15.00% busy. Five attempts were discarded because the driver saw a compiler running. [Raw captures](raw/)

## 3. Change

From the data, the four suggested vector directions do not apply to these pages:

- **Merging table lines into one path:** strokes total 0.82 ms, and the stroke edit falls inside the identity noise.
- **Merged traversal of adjacent paths:** fills and strokes together cost 1.07 ms, and both edits fall inside the identity noise.
- **Reusing clip coverage across paths or pages:** clip callbacks total 8.44 ms.
- **Bounding-box culling of path segments:** 187 top-level path segments in total.

The two measurable contributors were mask shading and images.

**Change kept.** `axis_paint` reuses one exact pixel across spans whose full footprint contains equal opaque texels. That path was gated to `inv[0]*width <= 1 && |inv[3]|*height <= 1`, meaning magnified images only. The claim it relies on does not depend on scale: if every texel in the footprint has the same bytes and alpha 255, every bilinear sum equals that byte within about 1e-13, and `image_byte` rounds with +0.5. The gate is now two texels per pixel in each axis. Footprints taller than four rows already fall back to the ordinary row path inside `axis_flat_row_paint`. Footprints with partial samples or mixed texels still take the ordinary sampler. [Commit diff](../../src/affine_image.c)

**New test.** A 160×140 image of flat 8×8 opaque blocks also has a noisy strip, a transparent texel and a semi-transparent texel. It is drawn at 1.24–2.0 texels per pixel: flipped and unflipped, with fractional and off-target placement, with and without clip coverage. The output is compared byte for byte with the generic sampler, which a nested unit mask forces. To check that the test actually exercises the change, the flat-span color was corrupted by one bit. The test failed with the new gate and passed with the old gate. [Test](../../tests/test_pdf_image.c)

**Change tried and dropped.** Group working buffers shrink to the clip's bounding box only when the box covers at most half the canvas. The soft-mask clip here covers 536 of 900 rows. Allowing any smaller box measured as follows:

| Native pilot, p1–10, 12 sweeps | A median (ms) | B median (ms) | Median paired saving | Range (ms) | Faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Empty control: main vs a copy of main | 422.74 | 414.16 | 5.09 ms (1.15%) | −6.82 to +27.05 | 9/12 |
| main → uniform spans to 2× | 412.44 | 327.14 | **86.96 ms (21.32%)** | +77.83 to +105.18 | **12/12** |
| uniform spans → plus any smaller group region | 330.95 | 328.66 | 6.62 ms (2.03%) | −17.02 to +13.04 | 7/12 |

The region change was indistinguishable from the empty control, so it is not part of this branch. All three pilots compared 10,800,000 pixels with zero differences. [Pilot captures](raw/pilot/)

The remaining gap sits in the mask-internal shading: its non-isolated float group state, content paint and commit. This session does not reduce it.

## 4. Verification

Main DLL: `14c6a3dcf76365d4bc16459dda0c1cd927f608b3ba95aa84b2b32008af30a4c1`. Candidate DLL, built from the clean commit: `5e43bba36738326dc98889e6ba8e5d1024d23bc79179f372d07cd607fe4c5fac`. The pilot candidate was built from the same `affine_image.c` before the region experiment; its SHA-256 is `0e71f9b6…`.

### p1–10 at 1200 px

| Measurement | Main | Candidate | Change | Range | Faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Native A/B, 12 warm sweeps, median sweep (ms) | 447.55 | 359.96 | median paired **−90.54 ms (−20.16%)** | −104.52 to −75.59 | **12/12** |
| Same-DLL empty control, 12 warm sweeps | 422.74 | 414.16 | −5.09 ms (−1.15%) | −27.05 to +6.82 | 9/12 |
| Bilateral gap vs PDF.js, 12 rounds, mean (ms) | +116.80 | **+15.08** | **−101.72** | −118.87 to −83.13 | 60/60 |
| Identity edit, same bilateral protocol | | | −2.08 (gap change) | −63.57 to +44.47 | |

- **Bilateral run:** the four arms were EXReader main, EXReader candidate and two PDF.js workers, all on the original PDF. Mean sweep totals were 483.83 / 378.44 ms for EXReader main / candidate and 367.03 / 363.36 ms for the two PDF.js arms. Cold hashes changed on 0 of 10 pages.
- **Gates:** the native A/B gate ran before every sweep at 4.69–14.45% CPU; the bilateral runs started at 5.86–13.28%.

[Native A/B](raw/final/production-slides-1200.json) · [Bilateral](raw/final/) · [Empty control](raw/pilot/empty-control.json)

### Other page types

The full vector-heavy-100 ran 12 alternating sweeps. Changes are shown both as the sum of per-page medians and as the median paired sweep change. A separate same-DLL control on the full document gives the noise level.

| Pages | Main (ms) | Candidate (ms) | Change | Median paired change | Empty control: change / paired |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1–10 courseware slides | 418.92 | 327.92 | **−21.72%** | −20.58% | −0.14% / +0.47% |
| 11–25 Excel | 178.49 | 179.16 | +0.37% | −0.04% | −0.43% / +0.22% |
| 26–65 PPTX | 65.92 | 65.57 | −0.54% | −0.26% | +0.96% / +0.21% |
| 66–100 synthetic dense vector | 584.43 | 585.62 | +0.20% | +0.03% | +0.55% / +0.38% |
| 1–100 total, median sweep | 1,241.13 | 1,148.72 | median paired −88.26 ms (−6.87%), 12/12 | | −3.43 ms (−0.26%), 5/12 |

Excel, PPTX and dense vector stayed within ±3% on both measures. real-mixed-120 and image-heavy-100 were checked for pixel parity only; their timing is not measured here. [Full-document A/B](raw/final/production-vector-heavy-100-1200.json) · [Empty control](raw/final/empty-control-vector-heavy-100-1200.json)

### Small fixtures

Warm per-render p50 over 15 alternating sweeps.

| Fixture | Main p50 (ms) | Candidate p50 (ms) | Change | Ceiling (ms) | Candidate meets ceiling |
| --- | ---: | ---: | ---: | ---: | --- |
| PPTX @600 | 0.83615 | 0.83825 | +0.25% | 0.844 | Yes |
| PPTX @1200 | 1.71770 | 1.68075 | −2.15% | 1.729 | Yes |
| Deck @1200 | 12.90630 | 12.88080 | −0.20% | 15.4 | Yes |
| Word-5 @1200 | 5.91550 | 5.86030 | −0.93% | 5.75 | **No** |

Main also exceeds the Word-5 @1200 ceiling in this session. The candidate is 0.93% faster than main there, but it does not pass the absolute ceiling. [Small-fixture captures](raw/final/)

### Pixels, tests and memory

- **Large-fixture pixels:** 353,143,200 compared, **zero different**: image-heavy-100 112,872,000, real-mixed-120 131,317,200 and vector-heavy-100 108,954,000, all at 1200 px.
- **Small-fixture pixels:** 111,897,000 compared, **zero different**: PPTX at 600/1200/2400, deck at 600/1200 and Word-5 at 600/1200.
- **CTest:** **577/577** passed in 88.22 s. [Output](raw/ctest.txt)

Peak working set at 1200 px is the maximum of three fresh-process peaks per arm, run in AB, BA, AB order:

| Peak working set | Main (bytes) | Candidate (bytes) | Change | Largest matched pair |
| --- | ---: | ---: | ---: | ---: |
| image-heavy-100 | 153,870,336 | 153,853,952 | −0.011% | +0.051% |
| real-mixed-120 | 112,660,480 | 112,721,920 | +0.055% | +0.178% |
| vector-heavy-100 | 82,558,976 | 82,530,304 | −0.035% | +0.179% |

The largest increase is far below the 10% limit, and the change allocates nothing. [RSS](raw/final/rss.json)

## Measurement notes

- **Machine:** Intel Core Ultra 7 256V, Windows 11 build 26200, Balanced power plan.
- **Toolchain:** Release builds with GCC 16.2.0 (MinGW-w64 UCRT) and Ninja, with `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF`, `EXR_ENABLE_IMAGE_AVIF=OFF`.
- **PDF.js:** 3.11.174 on Node 24.19.0 and node-canvas 3.2.3. Python 3.14.7, pypdf 6.16.1, psutil 7.2.2.
- **Timers:** native timing covers `exr_fixed_render`. PDF.js timing covers `getPage`, viewport and canvas creation, and the render promise.
- **Idle gate:** every timed sweep or run waits for a valid 500 ms sample at or below 15% system CPU busy. The threshold was not changed.
- **Concurrent load:** another session's measurement script (`evidence/drop-mask-row-20261118/measure.py`, from a different worktree) ran on the machine during part of this session. The driver's competing-process check does not recognize that script name. The gate still held at every start, and the identity and empty controls above were captured under the same conditions.
- **Tooling:** the drivers are copied from #267 [`realmixed-slides-20261118`](../realmixed-slides-20261118/), which itself descends from the twocells and slides ablation drivers. The changes are a `--rounds` option and a combined `path` class in `ablate.py`, and the cohort, page and sweep settings in `probe.py`, `validate.py` and `summarize.py`. Native A/B and parity use #264's [`paired_sweep.py`](../slides-gradient-20261118/paired_sweep.py) and [`verify.py`](../slides-gradient-20261118/verify.py).

## Reproduce

Run from the repository root. `$main`, `$main_copy` (a byte-identical copy in another directory), `$cand` and `$probe` are the DLLs above. The probe DLL is built from main with [probe.patch](probe.patch) applied.

```powershell
$d = 'evidence/vector-slides-20261118'
$classes = @('identity','fill','stroke','glyph','clip','shading','shading-page','shading-mask','softmask','page-group','image')
python -B "$d/variants.py" vector-heavy-100 1 10 @classes path
python -B "$d/probe.py" $main $probe
python -B "$d/probe_summary.py" full
python -B -u "$d/ablate.py" $main vector-heavy-100 1 10 --rounds 12
python -B -u "$d/ablate.py" $main vector-heavy-100 1 10 @classes --rounds 12
python -B -u evidence/slides-gradient-20261118/paired_sweep.py $main $main_copy tests/fixtures/pdf-large/vector-heavy-100.pdf 1200 12 "$d/raw/pilot/empty-control.json" --pages 10
python -B -u "$d/validate.py" $main $cand --raw "$d/raw/final"
python -B -u "$d/ablate.py" $main vector-heavy-100 1 10 candidate --candidate $cand --rounds 12 --raw "$d/raw/final"
python -B -u evidence/slides-gradient-20261118/paired_sweep.py $main $main_copy tests/fixtures/pdf-large/vector-heavy-100.pdf 1200 12 "$d/raw/final/empty-control-vector-heavy-100-1200.json"
ctest --test-dir build/vhslides --parallel 6 --output-on-failure
python -B "$d/summarize.py"
python -B "$d/summarize.py" "$d/raw/pilot"
python -B "$d/summarize.py" "$d/raw/final"
```
