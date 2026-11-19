# Real-mixed courseware slides at 1200 px

On the matched Release run against `d8148bbd2`, the candidate rendered pages 1–21 in a median **878.61 ms** versus **956.80 ms** on main. The median paired saving was **66.08 ms (7.08%)**, with **11/11** faster sweeps and **zero** differences across **22,680,000** active RGBA pixels. [Focused production samples](raw/main266/production-slides-1200.json)

## Current-main baseline and #264

On `c01b82c2b`, the main snapshot at the start of this work, pages 1–21 took **895.66 ms in EXReader and 648.79 ms in PDF.js**, a **246.88 ms** gap between the two selected warm sweep totals. The median of matched sweep differences within rounds was **255.53 ms**. The cohort contains 22,680,000 pixels at 1200 px.

| Session | EXReader (ms) | PDF.js (ms) | EXReader − PDF.js (ms) |
| --- | ---: | ---: | ---: |
| Twocells fresh baseline | 1,340.11 | 877.27 | +462.84 |
| This session, `c01b82c2b` | 895.66 | 648.79 | +246.88 |

The cross-session EXReader and PDF.js differences are −444.45 ms and −228.48 ms, respectively. To isolate #264, the same machine and fixture also ran `9a4f3ba0c` versus `c01b82c2b` in pairs. Their median times were **914.26 ms and 876.35 ms**, with a **42.56 ms** median paired saving. The candidate was faster in **11/11** warm sweeps, with savings of **16.57–75.19 ms** and zero pixel differences. [Matched pre/post-#264 samples](raw/pre264-main.json)

The `c01b82c2b` renderer sources, headers, and CMake inputs match `f77d6712a`; the Windows Release DLL was reused from #264 and matches the reported SHA-256 `8a34941d6a88bf1fd9530c6d9684e8459f9dc1f84bd295fbd64fed13148ddd3f`. The pre-#264 DLL SHA-256 is `c2c817db1db5dc2bbeadd289ddaa143ea3cbed683d4f1a462a0ef61dca3ca017`. PDF.js 3.11.174 ran with Node 24.19.0 and node-canvas 3.2.3. [#264 build evidence](../slides-gradient-20261118/REPORT.md)

After #263 merged, a new baseline on `716ca5e22` measured **1,201.85 ms in EXReader and 854.95 ms in PDF.js**, a **346.90 ms** gap between the selected totals. The median of matched sweep differences within rounds was **333.06 ms**. In separate four-arm captures from that session, the mean main time was **1,139.56 ms** and the mean candidate time was **1,070.93 ms**. Using the mean of the two PDF.js controls in each sweep gave a shared **825.33 ms** reference. Mean gaps were **314.23 ms** for main and **245.60 ms** for the candidate. The median paired native saving was **64.57 ms** and all 15 warm sweeps were faster. [#263-era PDF.js samples](raw/current/)

## Operator and renderer audit

The 21 page streams contain 46 image draws, 22 shading operators, 55 strokes, 15 fills, 302 text-show operators and 462 explicit clips. The pages have 21 `/Group` dictionaries, and 21 graphics-state soft masks each contain one additional shading in a transparency group. There are 64 `gs` operators overall. The variant generator parses each edited stream to check its operator changes and retains the original PDF prefix. The identity PDF rewrites the same page streams with whitespace and preserves every parsed operator. [Variant audit](real-mixed-120-operator-audit.json)

| Input | Native shading calls | Native mask builds | PDF.js shading ops | PDF.js mask group starts |
| --- | ---: | ---: | ---: | ---: |
| Full | 43 | 21 | 43 | 21 |
| Omit page shading | 0 | 0 | 21 | 21 |
| Omit mask shading | 22 | 21 | 22 | 21 |
| Omit all shading | 0 | 0 | 0 | 21 |
| Omit graphics-state soft masks | 22 | 0 | 22 | 0 |
| Omit page `/Group` dictionaries | 43 | 21 | 43 | 21 |

The nested Form group callback count was zero in both engines. The EXReader hook for those callbacks and the edit that removes the page `/Group` dictionaries exercise separate group scopes. Each luminosity mask still needs a group to run its retained content. Omitting page shading prevented EXReader's 21 on-demand mask builds, so the shading ablation includes their downstream cost. [Runtime audit](raw/runtime-audit.json.gz)

## Paired drawing-class ablations

Each row uses three fresh rounds of five warm sweeps. EXReader and PDF.js open the same edited input. Positive gap reduction means the edited gap was smaller. The Form group hook is native-only and uses the original PDF in both PDF.js controls.

| Edit or hook | EXReader full → edit (ms) | PDF.js full → edit (ms) | Gap reduction (ms) | Round range (ms) | Changed pages, EXReader / PDF.js |
| --- | ---: | ---: | ---: | ---: | ---: |
| Identity | 1,055.33 → 1,058.97 | 759.59 → 752.98 | −10.26 | −24.98 to +9.15 | 0 / 0 |
| 22 page shadings | 1,095.93 → 629.63 | 788.90 → 613.86 | **+291.27** | +250.87 to +341.52 | 21 / 21 |
| 21 mask shadings | 1,061.73 → 795.57 | 763.50 → 754.10 | **+256.77** | +230.25 to +279.41 | 21 / 21 |
| All 43 shadings | 1,040.13 → 607.61 | 746.96 → 558.41 | **+243.97** | +229.15 to +265.76 | 21 / 21 |
| 21 soft-mask entries | 1,077.90 → 1,368.20 | 777.61 → 568.44 | −499.47 | −531.77 to −482.78 | 21 / 21 |
| 15 fills | 1,082.20 → 1,081.42 | 773.64 → 778.23 | +5.36 | −6.03 to +11.82 | 7 / 7 |
| 55 strokes | 1,129.19 → 1,129.42 | 810.08 → 816.74 | +6.44 | −5.03 to +17.02 | 21 / 21 |
| 302 text-show operators | 1,072.39 → 1,007.46 | 770.95 → 673.49 | −32.53 | −41.75 to −23.29 | 20 / 20 |
| 46 image draws | 1,052.61 → 582.36 | 752.24 → 360.61 | +78.63 | +60.27 to +98.90 | 21 / 21 |
| 462 explicit clips | 1,022.42 → 1,111.05 | 720.50 → 1,036.06 | +226.93 | +200.29 to +261.34 | 4 / 4 |
| Nested Form group hook | 1,055.93 → 1,063.96 | 744.06 → 751.91 | −0.19 | −13.14 to +6.43 | 0 / 0 |
| 21 page `/Group` entries, #263-era main | 1,102.05 → 1,098.60 | 793.99 → 798.76 | +8.23 | +4.97 to +10.08 | 0 / 0 |

Page shading produced the largest gap reduction. The mask-only shading omission kept all native mask builds and still narrowed the gap by 256.77 ms. The page-only and all-shading omissions produced identical pixels within each engine. Removing the soft-mask entries eliminated 13,144,950 pixels from EXReader's masked store while keeping page shading. Deleting the clips slowed both engines, with a larger increase in PDF.js. The mean results for fill, stroke, and both group cases fell within the observed round-level range of the identity control. Repeating the image omission on `716ca5e22` narrowed the gap by **92.11 ms**, ranging from 75.08 to 103.11 ms across rounds. [Initial main samples](raw/) · [#263-era samples](raw/current/)

## Scanline reuse and shading paths

The probe reproduced the same event counts on two consecutive passes through all 21 pages. Its render matched the uninstrumented DLL on all 42 full-input page hashes. Stage timings below use the second pass and include diagnostic overhead. [Probe patch](probe.patch) · [Full-input trace](raw/probe-full.txt.gz)

- **#245 clip row reuse.** There were 184 reused rows out of 189 eligible rows (**97.35%**). The general scanline rasterizer covered 101,387 rows overall, including 101,198 ineligible rows. Separately, the mask rectangle fast path handled 68,172 rows. Active crossings were 1,097,794 of 16,949,924 edge tests (**6.48%**). The dense-vector lane's 4.93% is the edge-test rate for its cubic strokes. The row reuse rate for all general scanline rows here is **0.18%**.
- **#248 axial reuse.** All 43 shading calls entered the clipped axial path and **zero** rows entered the generic sampling path. The 21 mask-internal draws reused 13,169,520 of 13,507,200 covered pixels (**97.50%**). The 22 page draws reused 13,170,990 of 13,510,200 (**97.49%**). The group and masked page stores each ran across 13,144,950 pixels.
- **Explicit clips.** The page renderer processed 462 explicit clip operations per pass, including 363 canvas-covering identity clips and 99 nonidentity clips. Those callbacks took **7.09 ms and 7.26 ms** in the two passes. An additional 21 clips inside mask content and 42 implicit bounds clips brought the canvas total to 525 per pass. Both passes repeated the same clip rebuild counts.
- **Luminosity masks.** All 21 builds had distinct resolved mask IDs. Mask rasterization took **279.69 ms**, including **72.57 ms** preparing the group, **130.72 ms** painting its contents, and **73.17 ms** committing the group. Extraction took **32.60 ms**. Each of the 18,900 rendered RGBA input rows was uniform across its width, and **13,503 rows (71.44%)** matched the immediately preceding row byte for byte within their mask.

## Changes and pilot runs

Soft-mask extraction reuses the resolved bytes from the previous row when the two RGBA rows are byte-identical. It checks cancellation and charges the original sample work before testing for reuse. The run is local to one mask build and holds no extra buffer.

RGB group commit batches contiguous fully covered pixels that have accumulated group opacity of one and exactly equal float RGB components. The existing float conversion runs once for the span. Commit retains the original row cancellation and work charges. If the budget runs out within the span, commit writes the original successful prefix before returning the same error.

| Native pilot on #264 main | A median (ms) | B median (ms) | Median paired saving (ms) | Paired saving range (ms) | Faster sweeps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main → repeated mask rows | 1,152.53 | 1,146.30 | 16.44 | −99.55 to +64.55 | 7/11 |
| Repeated mask rows → both changes | 1,122.95 | 1,052.07 | 55.72 | −150.01 to +227.53 | 9/11 |
| Main → both changes | 1,124.81 | 1,062.23 | 59.58 | −21.21 to +142.38 | 10/11 |

Each pilot compared all 22,680,000 active RGBA pixels on its first sweep and recorded zero differences. [Row pilot](raw/main-row.json) · [Group increment](raw/row-both.json) · [Combined pilot](raw/main-both.json)

## Production verification against #263-era main

Both production DLLs came from the same Windows Release build directory. They include #263. A is `716ca5e22` with SHA-256 `2c7412eb0a6a47fc0e0c5e492011736123eaffb72fad35c4ad580288da398b09`. B adds the two changes in this branch and has SHA-256 `86cc5a6ca48d2072109738bd152b6c57b426722a06d19c0c13647ab39c019bd0`. For p1–21, main's median was 976.35 ms and the candidate's was 918.70 ms. The median paired saving was 57.64 ms (5.90%), with all 11 sweeps faster. Savings ranged from 15.69 to 102.67 ms. CPU gate samples ranged from 8.59% to 14.29%. [#263-era native samples](raw/production-slides-1200.json)

| Other real-mixed pages | Main sum of page medians (ms) | Candidate sum of page medians (ms) | Change | Median paired sweep change |
| --- | ---: | ---: | ---: | ---: |
| 22–51, Deck | 396.97 | 399.17 | +0.55% | −0.46% |
| 52–76, Word | 158.76 | 161.61 | +1.79% | +0.71% |
| 77–116, PPTX | 72.64 | 73.48 | +1.16% | −1.40% |
| 117 and 119, Excel | 26.15 | 26.53 | +1.43% | −2.75% |
| 118 and 120, Chinese | 4.54 | 4.32 | −4.77% | −1.08% |

The median paired changes all fall within ±3%. The two Chinese pages show a 4.77% improvement by sum of page medians. [Full-corpus matched sample](raw/production-real-mixed-120-1200.json)

| Small fixture | Main p50 (ms) | Candidate p50 (ms) | Change | Ceiling (ms) | Candidate meets ceiling |
| --- | ---: | ---: | ---: | ---: | --- |
| PPTX @600 | 0.89430 | 0.87885 | −1.73% | 0.844 | No |
| PPTX @1200 | 1.62340 | 1.61130 | −0.75% | 1.729 | Yes |
| Deck @1200 | 12.62350 | 12.69780 | +0.59% | 15.4 | Yes |
| Word @1200 | 5.83250 | 5.82140 | −0.19% | 5.75 | No |

Both builds exceeded the PPTX @600 and Word @1200 ceilings. The four relative p50 changes fall within ±3%. [Small-fixture samples](raw/)

The byte comparison found zero differences across **353,143,200** pixels from three large PDFs and **111,897,000** pixels from seven small fixture/width pairs. Each cold pass compared active RGBA rows and recorded page hashes. [Parity captures](raw/)

CTest passed **577/577** in 86.98 seconds. [CTest output](raw/ctest.txt)

| Peak working set at 1200 px | Main (bytes) | Candidate (bytes) | Change |
| --- | ---: | ---: | ---: |
| image-heavy-100 | 153,505,792 | 153,657,344 | +0.10% |
| real-mixed-120 | 112,369,664 | 112,660,480 | +0.26% |
| vector-heavy-100 | 82,477,056 | 82,554,880 | +0.09% |

The table uses the maximum of three fresh-process peaks per arm. Runs used AB, BA, and AB order, with two render passes per process. The largest growth within a matched process pair was 0.32%, below the 10% limit. [RSS captures](raw/rss.json)

## Final verification against #266-era main

Main is `d8148bbd2`, and the rebased production code is `d704cdacc`. Main DLL SHA-256 is `d6366a1e1aaaf593c7497af2f3ed0aa81456af73369941c2f71b89449bf444bc` and candidate DLL SHA-256 is `d7be9e348da70e1609cccc3a9843d667bce9363b44f4fb65dd68ac861e42392b`. The focused run passed the CPU gate at 5.08–14.84%, and paired savings ranged from 10.67 to 82.72 ms.

| Other real-mixed pages | Main sum of page medians (ms) | Candidate sum of page medians (ms) | Change | Median paired sweep change |
| --- | ---: | ---: | ---: | ---: |
| 22–51, Deck | 379.61 | 378.58 | −0.27% | −0.70% |
| 52–76, Word | 150.88 | 149.77 | −0.73% | +0.13% |
| 77–116, PPTX | 67.68 | 66.87 | −1.19% | −1.54% |
| 117 and 119, Excel | 24.71 | 24.02 | −2.80% | +0.18% |
| 118 and 120, Chinese | 4.25 | 3.78 | −11.03% | −6.31% |

Deck, Word, PPTX, and Excel fell within ±3% by both measures. The Chinese pages were faster in this full-corpus capture, outside the requested ±3% band on the faster side. A separate isolated retest produced no accepted timings because another benchmark kept the idle gate closed. [Full-corpus matched sample](raw/main266/production-real-mixed-120-1200.json)

| Small fixture | Main p50 (ms) | Candidate p50 (ms) | Change | Ceiling (ms) | Candidate meets ceiling |
| --- | ---: | ---: | ---: | ---: | --- |
| PPTX @600 | 0.86950 | 0.86790 | −0.18% | 0.844 | No |
| PPTX @1200 | 1.66170 | 1.66535 | +0.22% | 1.729 | Yes |
| Deck @1200 | 12.88470 | 12.70270 | −1.41% | 15.4 | Yes |
| Word @1200 | 5.89470 | 5.98820 | +1.59% | 5.75 | No |

The four relative p50 changes fall within ±3%. Both builds again exceeded the PPTX @600 and Word @1200 absolute ceilings. The PR remains a draft. [Small-fixture samples](raw/main266/)

The final byte comparison again found **zero differing pixels** across **353,143,200** large-fixture pixels and **111,897,000** small-fixture pixels. [Final parity captures](raw/main266/)

CTest passed **577/577** in 92.53 seconds. [Final CTest output](raw/main266/ctest.txt)

| Peak working set at 1200 px | Main (bytes) | Candidate (bytes) | Change |
| --- | ---: | ---: | ---: |
| image-heavy-100 | 153,292,800 | 153,686,016 | +0.257% |
| real-mixed-120 | 112,574,464 | 112,582,656 | +0.007% |
| vector-heavy-100 | 82,403,328 | 82,399,232 | −0.005% |

The largest increase in any of the nine matched process pairs was **0.51%**, below the 10% limit. [Final RSS captures](raw/main266/rss.json)

## Measurement protocol

All samples use the same Windows 11 machine, Intel Core Ultra 7 256V, Balanced power plan, and the Release GCC 16.2.0 toolchain. The benchmark fixture SHA-256 is `cdfc1ee6952652613c15fe91288450c6e168994e3b1792e52bb56db14ab8a693`. The PDF.js worker times page lookup, canvas creation, and the render promise. Native timing covers `exr_fixed_render`. Startup, pixel hashing, disposal, and dispatch are outside the timers.

Each bilateral round opens fresh processes and documents, takes one cold sweep for hashes, and records five warm sweeps. Engines alternate AB/BA page by page, with the starting order reversing each warm sweep and each round. Ablations also vary which document arm starts on each pair of pages. The 15% machine CPU gate requires a valid half-second reading and retries closed windows. The bilateral runner discards attempts with detected competing builds or renders. Native A/B checks alternate by page and reverse the starting arm each sweep. Their cold pass compares the active RGBA bytes in each row.

The main-versus-PDF.js baseline uses the median of five sweep totals within each round and then the median of the three round medians per engine. The ablations average paired differences in warm sweep totals and show the range of round means. Removing an operator can change the work of retained operators. Native candidate timing uses the median paired saving across sweeps. The paired percentage divides each sweep's change by that sweep's main time before taking the median. Small-fixture gates use the median across all warm page renders. Cohort comparisons report the sum of page medians and the median paired sweep change. [Ablation driver](ablate.py) · [Native matrix driver](validate.py) · [Summary script](summarize.py)

## Reproduce

Build `9a4f3ba0c`, `c01b82c2b`, `716ca5e22`, `d8148bbd2`, and the two candidates as Windows Release builds with MinGW and Ninja. Apply the production commit to each corresponding base. Use `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF`, and `EXR_ENABLE_IMAGE_AVIF=OFF`. Build the diagnostic DLL in a separate checkout of `c01b82c2b` with [probe.patch](probe.patch). Set the DLL variables below to the corresponding builds, and install the PDF.js dependencies in the sibling `pdfjs-bench2` directory. Run from the repository root.

```powershell
$d = 'evidence/realmixed-slides-20261118'
$classes = @('identity','shading-page','shading-mask','shading','softmask','fill','stroke','glyph','image','clip')
python -B "$d/variants.py" real-mixed-120 1 21 @classes page-group
python -B "$d/ablate.py" $main264 real-mixed-120 1 21
python -B evidence/slides-gradient-20261118/paired_sweep.py $pre264 $main264 tests/fixtures/pdf-large/real-mixed-120.pdf 1200 11 "$d/raw/pre264-main.json" --pages 21
python -B "$d/ablate.py" $main264 real-mixed-120 1 21 @classes group
python -B "$d/probe.py" $main264 $probe
python -B "$d/validate.py" $main263 $candidate263
python -B "$d/ablate.py" $main263 real-mixed-120 1 21 baseline page-group image candidate --candidate $candidate263 --raw "$d/raw/current"
python -B "$d/validate.py" $main266 $candidate266 --raw "$d/raw/main266"
ctest --test-dir build/realmixed-slides --parallel 6 --output-on-failure
python -B "$d/summarize.py"
python -B "$d/summarize.py" "$d/raw/current"
python -B "$d/summarize.py" "$d/raw/main266"
```
