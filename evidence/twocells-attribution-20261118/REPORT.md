# Fresh page-type attribution at 1200 px

The fresh gap was **406.29 ms** for real-mixed-120 and **581.51 ms** for vector-heavy-100. Mixed concentrated its gap on courseware slides, where omitting page shading narrowed the isolated gap by **355.30 ms**. Vector concentrated its gap on synthetic dense-vector pages, where omitting polygon fill and stroke narrowed the isolated gap by **249.69 ms**.

## Whole-document baselines

All times are warm sweep sums in milliseconds. A positive gap means EXReader took longer.

| Cell | Session | EXReader | PDF.js | EXReader / PDF.js | Gap |
| --- | --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | #259 | 1663.09 | 1445.18 | 1.151× | +217.91 |
| real-mixed-120 | Fresh | **2300.26** | **1893.97** | **1.215×** | **+406.29** |
| vector-heavy-100 | #259 | 1436.36 | 1016.45 | 1.413× | +419.91 |
| vector-heavy-100 | Fresh | **1864.14** | **1282.64** | **1.453×** | **+581.51** |

For real-mixed-120 the fresh EXReader time rose 637.17 ms (+38.31%) and PDF.js rose 448.79 ms (+31.05%). The archived PDF.js denominator was 23.70% below the fresh one. The ratio rose 0.064× and the gap rose 188.38 ms (+86.45%).

For vector-heavy-100 the fresh EXReader time rose 427.78 ms (+29.78%) and PDF.js rose 266.19 ms (+26.19%). The archived PDF.js denominator was 20.75% below the fresh one. The ratio rose 0.040× and the gap rose 161.60 ms (+38.48%).

| Cell | Engine | Round 1 | Round 2 | Round 3 | Selected round / warm sweep |
| --- | --- | ---: | ---: | ---: | --- |
| real-mixed-120 | EXReader | 2136.70 | 2300.26 | 2456.57 | 2 / 2 |
| real-mixed-120 | PDF.js | 1748.81 | 1893.97 | 2118.52 | 2 / 2 |
| vector-heavy-100 | EXReader | 1753.33 | 1866.89 | 1864.14 | 3 / 4 |
| vector-heavy-100 | PDF.js | 1212.38 | 1348.94 | 1282.64 | 3 / 4 |

## Page-type decomposition

### real-mixed-120

| Page type | Pages | EXReader (ms) | PDF.js (ms) | Gap (ms) | Share of net gap |
| --- | --- | ---: | ---: | ---: | ---: |
| Courseware slides | 1–21 | 1340.11 | 877.27 | **+462.84** | **113.92%** |
| Deck | 22–51 | 612.93 | 631.57 | −18.65 | −4.59% |
| Word | 52–76 | 210.28 | 208.82 | +1.46 | +0.36% |
| PPTX | 77–116 | 98.94 | 134.09 | −35.15 | −8.65% |
| Excel | 117, 119 | 33.24 | 35.06 | −1.82 | −0.45% |
| Chinese | 118, 120 | 4.76 | 7.16 | −2.40 | −0.59% |
| **All pages** | **1–120** | **2300.26** | **1893.97** | **+406.29** | **100%** |

Courseware slides had the largest positive gap in every round (+434.21 to +462.84 ms). The other page types offset 56.56 ms in the selected sweeps.

### vector-heavy-100

| Page type | Pages | EXReader (ms) | PDF.js (ms) | Gap (ms) | Share of net gap |
| --- | --- | ---: | ---: | ---: | ---: |
| Courseware vector/table slides | 1–10 | 621.03 | 395.16 | +225.87 | +38.84% |
| Excel | 11–25 | 225.06 | 282.91 | −57.86 | −9.95% |
| PPTX | 26–65 | 91.68 | 117.09 | −25.40 | −4.37% |
| Synthetic dense vector | 66–100 | 926.37 | 487.48 | **+438.89** | **75.48%** |
| **All pages** | **1–100** | **1864.14** | **1282.64** | **+581.51** | **100%** |

Synthetic dense vector had the largest positive gap in every round (+414.86 to +438.89 ms). Courseware vector/table slides were the next largest contributor in all three rounds.

## Bilateral drawing-class ablation

Each row times a cohort in isolation, with its own fresh full controls. A positive reduction means the omission narrowed the EXReader–PDF.js gap. The control totals here describe the isolated page range.

### real-mixed-120, courseware slides 1–21

The page streams contain 46 image draws, 22 shadings, 55 strokes, 15 fills, 302 text-show operators and 462 explicit clips. There are 21 graphics-state soft masks, each containing one additional shading. The clip variant retains path construction and the end-path operator. The soft-mask variant removes the 21 graphics-state mask entries. [Per-page operator audit](real-mixed-120-operator-audit.json)

| Omitted in both engines | EXReader full → omit (ms) | PDF.js full → omit (ms) | Full gap (ms) | Omit gap (ms) | Reduction (ms) | Round range (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 22 page shadings | 1245.67 → 713.09 | 830.07 → 652.80 | +415.59 | +60.29 | **+355.30** | +349.70 to +364.67 |
| 43 shadings, including in masks | 1272.41 → 723.70 | 862.27 → 651.41 | +410.14 | +72.30 | **+337.84** | +314.39 to +353.23 |
| 462 page-stream clips | 1218.59 → 1319.55 | 808.45 → 1112.68 | +410.14 | +206.87 | +203.27 | +189.58 to +216.10 |
| 46 image draws | 1252.86 → 702.05 | 849.51 → 376.97 | +403.34 | +325.07 | +78.27 | +50.40 to +93.59 |
| 70 path paints | 1207.28 → 1208.23 | 798.69 → 791.44 | +408.60 | +416.80 | −8.20 | −13.98 to −0.43 |
| 302 text-show operators | 1250.11 → 1180.28 | 839.13 → 736.28 | +410.98 | +443.99 | −33.01 | −57.55 to −19.63 |
| 21 graphics-state soft masks | 1228.28 → 1378.97 | 810.24 → 624.28 | +418.03 | +754.69 | −336.65 | −360.15 to −323.95 |

Shading had the largest positive gap reduction and narrowed the gap in all 15 matched warm sweeps for both shading omissions. Images saved substantial time in both engines and narrowed the gap by 78.27 ms. Removing clips narrowed the gap while slowing EXReader by 100.96 ms and PDF.js by 304.23 ms. The independent cost of clip construction remains unmeasured. Removing the soft masks while retaining the page shadings widened the gap in all 15 sweeps.

Each edit changed the cold pixel hashes on 21 of 21 pages within each engine, with 20 changed by the text omission and four by the clip omission.

A separate EXReader warm trace and PDF.js operator-list audit verified the shading and mask work outside the timing runs. Omitting page shading also eliminated every native mask build, while the PDF.js operator list still contained 21 soft-mask groups with their own shading. The independent page-shading and soft-mask costs remain unmeasured. [Per-page runtime audit](raw/courseware-runtime-audit.json)

| Input | EXReader shading calls | EXReader mask builds | PDF.js shading operators | PDF.js soft-mask groups |
| --- | ---: | ---: | ---: | ---: |
| Full | 43 | 21 | 43 | 21 |
| Without page shadings | 0 | 0 | 21 | 21 |
| Without page and mask shadings | 0 | 0 | 0 | 21 |
| Without soft masks | 22 | 0 | 22 | 0 |

### vector-heavy-100, synthetic dense-vector pages 66–100

The page streams contain 2,100 cubic-curve strokes, 875 even-odd polygon fill-and-strokes, 35 background fills and 35 explicit polygon clips. The separate polygon omissions retain the remaining branch of the original paint operator. The all-path variant retains path construction and ends each path without painting. [Per-page operator audit](vector-heavy-100-operator-audit.json)

| Omitted in both engines | EXReader full → omit (ms) | PDF.js full → omit (ms) | Full gap (ms) | Omit gap (ms) | Reduction (ms) | Round range (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3,010 path paints | 775.26 → 122.91 | 477.47 → 116.85 | +297.79 | +6.06 | **+291.73** | +286.59 to +298.95 |
| 875 polygon fill-and-strokes | 775.33 → 445.45 | 479.53 → 399.34 | +295.80 | +46.11 | **+249.69** | +235.43 to +275.07 |
| 875 polygon fills, keeping stroke | 722.91 → 496.38 | 458.13 → 433.55 | +264.77 | +62.82 | +201.95 | +194.52 to +208.48 |
| 875 polygon strokes, keeping fill | 735.14 → 493.68 | 455.46 → 412.90 | +279.68 | +80.78 | +198.90 | +189.86 to +212.02 |
| 2,100 cubic-curve strokes | 756.79 → 442.29 | 477.78 → 201.78 | +279.01 | +240.51 | +38.49 | +30.63 to +51.72 |
| 35 background fills | 731.70 → 711.96 | 466.40 → 459.90 | +265.30 | +252.05 | +13.24 | +4.21 to +21.76 |
| 35 explicit polygon clips | 799.62 → 654.44 | 498.85 → 353.75 | +300.77 | +300.69 | +0.08 | −5.60 to +8.29 |

Both polygon components narrowed the gap in every matched sweep. Their individual effects overlap, and a fill-versus-stroke ranking remains unmeasured. Removing all path paint brought the isolated gap to 6.06 ms. The clip result crossed zero across rounds. Clip omission changed 0 of 35 EXReader hashes and 35 of 35 PDF.js hashes. Each paint omission changed 35 of 35 hashes in both engines.

## Measurement

The two original fixtures match the SHA-256 hashes in the fixture manifest and the #259 archive. The page ranges follow the fixture generator. [Fixture manifest](../../tests/fixtures/pdf-large/manifest.json) · [#259 archive](../p95-then-throughput-20261118/results.json) · [Fixture generator](../../tools/generate_real_doc_fixtures.py)

The driver and its workers come from the slides attribution harness at `03d539cb7`. A round opens a fresh process and document per arm, runs one cold sweep for pixel hashes and five warm sweeps for timing. The two engines alternate AB/BA page by page. The first warm sweep starts A/B/A across the three rounds, and the starting engine flips between warm sweeps. Ablation rounds also balance the full-versus-edited order and reverse the class sequence in the middle round. [Driver](ablate.py) · [EXReader worker](worker.py) · [PDF.js worker](worker.cjs)

A sweep total is the sum of the timed page renders. Native timing covers `exr_fixed_render`. PDF.js timing covers `getPage`, viewport and canvas creation, and the render promise. Document open, pixel hashing, output disposal, and interprocess dispatch are outside the timers. Whole-document totals use the median of each round's five warm sums, then the median of the three round medians for each engine. Page-type contributions use the page times in those two selected whole-document sweeps, so they sum to the whole-document gap.

The same unmodified Windows Release DLL was used for every timed EXReader arm. It came from the slides worktree at `0d9ec7ddf`, whose renderer sources, headers, and CMake inputs match this branch's base `9a4f3ba0c`. Its SHA-256 is `e283bea43cc9fa1326bf34d55d7fe8176dcd24bb956ccdd8540912c00c8f416d`. PDF.js 3.11.174 ran with Node 24.19.0 and node-canvas 3.2.3. The machine was an Intel Core Ultra 7 256V running Windows 11 build 26200 on the Balanced power plan.

The idle gate requires a valid 500 ms sample at or below 15% system CPU busy. The driver retries the gate and discards a whole attempt if it sees a competing benchmark or build before completion. The 48 accepted rounds had pre-capture CPU busy readings of 1.56–14.79%. Full-input cold hashes matched within each engine across all baseline and ablation rounds. The archived #259 runs used a different DLL and alternated whole child-process runs. The archive-to-fresh differences describe the two measurement sessions. [Raw captures](raw/)

The variant builder appends incremental PDF updates and verifies the operator edits against parsed content streams. Each edited input is identical for both engines. Per-class gap reduction is the paired full gap minus the paired omission gap. Its point estimate averages all 15 warm sweeps, and its range uses the three five-sweep round means. Overlapping omissions can remove common work. [Variant builder](variants.py)

The capture commands below use the recorded Release DLL, Python 3.14.7, pypdf 6.16.1 and psutil 7.2.2. The driver keeps completed capture files when rerun. A fresh capture uses an empty `raw/` directory.

```powershell
$dll = (Resolve-Path '../EXReader-slides/build/perf/libexreader.dll').Path
$d = 'evidence/twocells-attribution-20261118'
python -B -u "$d/ablate.py" $dll real-mixed-120 1 120
python -B -u "$d/ablate.py" $dll vector-heavy-100 1 100
python -B "$d/variants.py" real-mixed-120 1 21 image shading shading-page softmask path glyph clip
python -B -u "$d/ablate.py" $dll real-mixed-120 1 21 image shading shading-page softmask path glyph clip
python -B "$d/variants.py" vector-heavy-100 66 100 path curve-stroke polygon-paint polygon-fill polygon-stroke background clip
python -B -u "$d/ablate.py" $dll vector-heavy-100 66 100 path curve-stroke polygon-paint polygon-fill polygon-stroke background clip
```
