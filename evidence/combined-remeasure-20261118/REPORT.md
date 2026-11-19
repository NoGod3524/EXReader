# Combined re-measure of #263, #264 and densevec at 1200 px

Measure-only. No renderer source was changed. All builds come from real commits.

On current main (#264 + #263), EXReader took **1.054×** PDF.js time on image-heavy-100, **1.127×** on real-mixed-120 and **1.330×** on vector-heavy-100. Adding densevec in a test merge moved these to **1.041×**, **1.127×** and **1.239×**. These numbers use the twocells two-arm method.

The three changes do **not** measurably eat each other on the pages they target. Each one keeps 93–97% of its on-base saving when the other two are present. The exception is #264 on image-heavy courseware, which keeps 78–96%. The naive "sum of single effects" overstates the combined saving by 22–49 ms per cell. That excess sits mostly on pages none of the changes targets, at the same size as the build-to-build noise floor.

All three changes are pixel-exact. Across all ten arms, the cold-sweep hashes matched the base build on every page of all three cells and were stable across rounds.

## ① Current gaps

Two-arm method: the twocells `ablate.py` baseline, used unchanged. Each DLL is paired with PDF.js page by page, using the median of round medians. Positive gap means EXReader is slower.

| Cell | Build | EXReader (ms) | PDF.js (ms) | Ratio | Gap (ms) | Per-round ratios |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| image-heavy-100 | Brief baseline (non-sink session) | 2890.99 | 2167.04 | 1.334× | +723.95 | — |
| | Same-day control: baseline DLL `e283bea4` | 2738.87 | 2013.28 | 1.360× | +725.59 | 1.340 / 1.357 / 1.360 |
| | **Main `716ca5e22`** | **2161.61** | **2050.05** | **1.054×** | **+111.56** | 1.049 / 1.128 / 1.042 |
| | Main + densevec (test merge) | 2297.35 | 2206.38 | 1.041× | +90.97 | 1.041 / 1.016 / 1.064 |
| real-mixed-120 | Brief baseline (twocells session) | 2300.26 | 1893.97 | 1.215× | +406.29 | — |
| | Same-day control: baseline DLL | 1811.89 | 1538.48 | 1.178× | +273.41 | 1.192 / 1.174 / 1.178 |
| | **Main** | **1797.29** | **1595.14** | **1.127×** | **+202.15** | 1.147 / 1.124 / 1.127 |
| | Main + densevec | 1664.23 | 1476.45 | 1.127× | +187.78 | 1.143 / 1.127 / 1.123 |
| vector-heavy-100 | Brief baseline (twocells session) | 1864.14 | 1282.64 | 1.453× | +581.51 | — |
| | Same-day control: baseline DLL | 1621.65 | 1164.45 | 1.393× | +457.19 | 1.393 / 1.382 / 1.361 |
| | **Main** | **1576.05** | **1185.42** | **1.330×** | **+390.63** | 1.311 / 1.330 / 1.398 |
| | Main + densevec | 1274.02 | 1027.87 | 1.239× | +246.14 | 1.277 / 1.233 / 1.228 |

Use the ratios, not the millisecond gaps, to compare runs. Each build ran in its own three-round session. Machine speed moved both engines together by up to ±15% between sessions: the PDF.js denominators ran from 1027.87 to 2206.38 ms. The same-day control ran the byte-identical DLL behind the brief's mixed and vector baselines. It reproduced the image-heavy gap (+725.59 vs +723.95 ms) but gave lower ratios than the brief on mixed (1.178 vs 1.215) and vector (1.393 vs 1.453). Part of the apparent improvement against the brief baselines is therefore session drift, not code. The code effects below come from the paired factorial, where session drift cancels.

## ② Do the changes eat each other?

### Factorial design

Each change touches exactly one source file:

| Change | File | Commit |
| --- | --- | --- |
| #264 (G) | `src/canvas.c` | `f77d6712a` |
| #263 (I) | `src/affine_image.c` | `578d942e3` |
| densevec (V) | `src/blend.c` | `b5ba2f363` |

No other renderer source, header or CMake input differs between `9a4f3ba0c` and main + densevec. So all eight on/off combinations are real code. The base, G, GI, GV and GIV arms match the renderer trees of `9a4f3ba0c`, `c01b82c2b`, main `716ca5e22`, `b5ba2f363` and the test merge `4101f21e5`. The I, V and IV arms are base plus the committed file. [Build script](build.sh) · [Build info](build-info.json)

One session ran PDF.js, the brief's baseline DLL (`orig`) and all eight builds. Each round opened one fresh process per arm, then ran 1 cold sweep and 5 warm sweeps. Every page was rendered by all ten arms back to back. Pages 2m and 2m+1 use mirrored order (A…J / J…A), so every pair of arms alternates page by page. The order rotates every two pages, and the starting direction flips each warm sweep and each round. Savings are paired within each sweep: the mean of 15 warm sweeps, with the three round means as the range. [Driver](measure.py) · [Reducer](analyze.py) · [Results](results.json)

### Whole-document savings against the pre-change base

| Cell | #264 alone | #263 alone | densevec alone | Sum of singles | All three together | Sum − together |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| image-heavy-100 | 49.30 | 500.66 | 15.39 | 565.35 | 516.79 | **+48.56** [+31.97, +72.94] |
| real-mixed-120 | 56.97 | 15.34 | 20.28 | 92.59 | 70.38 | **+22.21** [+18.41, +24.66] |
| vector-heavy-100 | 46.29 | 24.57 | 186.49 | 257.35 | 211.22 | **+46.13** [+35.16, +51.97] |

Main (#264 + #263) saved 527.07 ms on image-heavy, 71.84 ms on mixed and 45.29 ms on vector. Each saving was positive in all 15 sweeps.

### Each change's saving on its target pages, in every background

| Change → target group | On base | With #264 | With #263 | With densevec | With the other two | Kept |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| #263 → image-heavy synthetic multi-image p71–100 | 490.43 | 477.56 | — | 483.34 | 477.35 | 97.3% |
| densevec → vector-heavy synthetic dense p66–100 | 180.33 | 163.60 | 163.97 | — | 167.87 | 93.1% |
| #264 → image-heavy courseware p1–10 | 30.21 | — | 30.85 | 27.99 | 23.66 | 78.3% |
| #264 → real-mixed courseware p1–21 | 59.29 | — | 57.38 | 53.60 | 56.78 | 95.8% |
| #264 → vector-heavy courseware p1–10 | 29.66 | — | 28.28 | 26.64 | 27.59 | 93.0% |

All savings in this table are in milliseconds.

The largest target loss is the drop from "on base" to every other background: 13 ms for #263 and 12–17 ms for densevec. The same base-only drop shows up on pages a change cannot affect:

- **Dense-vector pages (no images, no shading).** #263 saves 15.66 ms against base but only −4.93 to −0.66 ms against any other background. #264 saves 14.86 ms against base and −5.74 to −1.84 ms elsewhere.
- **Synthetic multi-image pages.** densevec saves 8.47 ms against base and −4.14 to +1.38 ms elsewhere.

The pre-change source is 10–16 ms slower on these page types than **any** modified build, whichever file was modified. A pure work overlap cannot produce that pattern: affine image code does no vector work. The same offset inflates every "on base" single effect, which is why the naive sum overstates the combined saving.

The build noise floor is the same size. The original baseline DLL and my rebuild of identical source differ by 8.55 ms [5.01, 13.21] on the synthetic multi-image group. The cause of the base offset (for example code layout) is **未测出**.

**Conclusion:** across the three non-base backgrounds, each target saving varies by at most 7.2 ms: #263 by 6.0 ms, densevec by 4.3 ms and #264 by 1.6–7.2 ms. No change loses a measurable share of its target saving to the others. #264 on image-heavy courseware dropped to 23.66 ms only when both other changes were present. With #263 alone it kept the full 30.85 ms, and the three-way interaction is +4.97 [−1.05, +14.57] ms. The naive overlap of 22–49 ms per cell is not real lost work on the target pages.

### Against the individually reported effects

| Change | Individually reported | Here, in the same background as the original measurement | Here, fully stacked |
| --- | --- | --- | --- |
| #263 | p71–100 −37.98% (2135.55 → 1315.62 ms, pinned CPU) | 1206.46 → 728.90 ms, −39.6% (main vs #264) | −39.4% |
| #264 | p1–10 paired median −30.80 ms | Median −26.66 ms on base, −28.65 ms on #263 | Mean −23.66 ms |
| densevec | p66–100 −17.35% (710.66 → 587.34 ms, −123.33 ms) | 862.20 → 698.60 ms, −163.60 ms (−19.0%, vs #264) | −167.87 ms (−19.4%) |

Absolute milliseconds differ from the individual reports because those used different harnesses. #263 ran on a pinned CPU, at about 2× the time. densevec timed pages 66–100 only, with two arms. The relative effects reproduce. The 10-arm interleave also raised absolute times, and raised PDF.js more than EXReader (see Measurement), which is why the absolute gaps for headlines come from the two-arm runs.

## Page types: before vs now

Gap columns:
- **Brief** is the group split from the brief's baseline session. The image-heavy baseline came from the non-sink session's whole-process harness.
- **2-arm** columns use the selected sweeps of the two-arm runs above.
- **Factorial** columns are the paired 15-sweep mean gaps.

Savings are paired factorial values against base. All values are in milliseconds.

### image-heavy-100

| Group | Pages | Brief gap | 2-arm control gap | 2-arm main gap | 2-arm +densevec gap | Factorial base gap | Factorial main gap | Factorial +densevec gap | Main saving | densevec on main |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Courseware slides | 1–10 | +315.35 | +331.59 | +298.02 | +302.93 | +305.15 | +272.99 | +277.66 | +32.17 | −4.67 |
| Deck | 11–40 | −9.47 | −56.52 | −67.96 | −110.66 | −45.48 | −51.21 | −48.28 | +5.73 | −2.93 |
| Word | 41–60 | −72.68 | −0.11 | +4.15 | +8.32 | +2.40 | +3.18 | +2.65 | −0.78 | +0.53 |
| Image-only | 61–70 | +43.21 | +45.03 | +42.57 | +35.85 | +40.75 | +40.50 | +39.56 | +0.25 | +0.94 |
| Synthetic multi-image | 71–100 | +447.54 | +405.59 | −165.22 | −145.47 | +351.60 | −138.11 | −133.97 | **+489.71** | −4.14 |
| All | 1–100 | +723.95 | +725.59 | +111.56 | +90.97 | +654.42 | +127.34 | +137.62 | +527.07 | −10.28 |

### real-mixed-120

| Group | Pages | Brief gap | 2-arm control gap | 2-arm main gap | 2-arm +densevec gap | Factorial base gap | Factorial main gap | Factorial +densevec gap | Main saving | densevec on main |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Courseware slides | 1–21 | +462.84 | +359.78 | +298.29 | +277.70 | +331.54 | +262.84 | +259.94 | **+68.70** | +2.90 |
| Deck | 22–51 | −18.65 | −41.45 | −54.70 | −53.00 | −62.66 | −66.73 | −61.21 | +4.06 | −5.52 |
| Word | 52–76 | +1.46 | +0.51 | +0.89 | −5.50 | −10.44 | −10.11 | −10.32 | −0.33 | +0.20 |
| PPTX | 77–116 | −35.15 | −31.01 | −30.12 | −24.67 | −36.68 | −36.42 | −37.23 | −0.26 | +0.80 |
| Excel | 117, 119 | −1.82 | −11.94 | −9.14 | −5.86 | −9.73 | −9.34 | −9.44 | −0.39 | +0.09 |
| Chinese | 118, 120 | −2.40 | −2.49 | −3.05 | −0.89 | −2.53 | −2.59 | −2.64 | +0.06 | +0.05 |
| All | 1–120 | +406.29 | +273.41 | +202.15 | +187.78 | +209.49 | +137.65 | +139.11 | +71.84 | −1.46 |

### vector-heavy-100

| Group | Pages | Brief gap | 2-arm control gap | 2-arm main gap | 2-arm +densevec gap | Factorial base gap | Factorial main gap | Factorial +densevec gap | Main saving | densevec on main |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Courseware vector/table slides | 1–10 | +225.87 | +174.69 | +146.55 | +115.86 | +161.59 | +127.89 | +130.41 | **+33.70** | −2.52 |
| Excel | 11–25 | −57.86 | −47.65 | −60.03 | −41.87 | −72.76 | −73.81 | −74.51 | +1.05 | +0.70 |
| PPTX | 26–65 | −25.40 | −22.45 | −36.07 | −25.20 | −35.49 | −36.10 | −35.98 | +0.61 | −0.11 |
| Synthetic dense vector | 66–100 | +438.89 | +352.60 | +340.18 | +197.36 | +355.62 | +345.69 | +177.82 | +9.93 | **+167.87** |
| All | 1–100 | +581.51 | +457.19 | +390.63 | +246.14 | +408.96 | +363.67 | +197.74 | +45.29 | +165.93 |

**Which groups dropped:**
- **#263** turned image-heavy synthetic multi-image from a +352 ms gap into EXReader being 134–165 ms *faster* than PDF.js.
- **#264** took 30–69 ms off each courseware group: image p1–10, mixed p1–21 and vector p1–10.
- **densevec** roughly halved the vector dense-vector gap, from +346 to +178 ms in the factorial.

These match the individually reported effects in relative terms (table above). Single-sweep group splits move by ±20–40 ms between runs; the brief and 2-arm Deck/Word columns show this. Use the paired factorial columns for group-level changes.

## ④ densevec stacked on main

The test branch `test/combo-densevec-20261118` is local, in the build worktree only, at `4101f21e5`. It is main merged with `perf/dense-vector-439` with no conflicts, and is not merged to or pushed toward main.

| Cell | densevec on main (GI → GIV) | Sweeps faster | Two-arm ratio, main → main + densevec |
| --- | ---: | ---: | --- |
| vector-heavy-100 | **−165.93 ms** [−173.69, −154.24] | 15/15 | 1.330× → 1.239× |
| — of which synthetic dense p66–100 | −167.87 ms (−19.4% of 867.13 ms) | 15/15 | gap +340.18 → +197.36 ms |
| real-mixed-120 | +1.46 ms [−3.00, +8.07] | 5/15 | 1.127× → 1.127× |
| image-heavy-100 | +10.28 ms slower [+4.17, +14.45] | 5/15 | 1.054× → 1.041× |

Stacked on main, densevec saves more than its standalone −123.33 ms in absolute terms. In relative terms it saves −19.4% here against −17.35% standalone. In this session it also saved −163.60 ms in its own #264 background, so stacking on #263 cost it nothing.

On image-heavy, densevec made main 10.28 ms slower (0.5%), and every round mean was slower. On the #264 background it was 6.53 ms slower. This is within the build noise floor, and whether it is real is **未测出**. The two-arm image-heavy ratio still improved (1.054× → 1.041×), but those are unpaired sessions.

## ③ Groups still not covered

Remaining gaps after all three changes:
- **2-arm** is the main + densevec two-arm gap.
- **Factorial** is the main + densevec paired gap.
- **Covered by** lists the saving each change made on that group.

| Cell / group | 2-arm | Factorial | Covered by | Status |
| --- | ---: | ---: | --- | --- |
| real-mixed courseware p1–21 | +277.70 | +259.94 | #264 −57 ms | Partly covered; largest remaining gap. twocells attributed it to page shading (−355 ms on omission) and soft masks |
| image-heavy courseware p1–10 | +302.93 | +277.66 | #264 −30 ms | Partly covered |
| vector-heavy synthetic dense p66–100 | +197.36 | +177.82 | densevec −168 ms | Partly covered; polygon paint is still the main cost per twocells |
| vector-heavy courseware p1–10 | +115.86 | +130.41 | #264 −28 ms | Partly covered |
| **image-heavy image-only p61–70** | +35.85 | +39.56 | none (≤ 1.2 ms) | **Not covered by any change** |
| image-heavy Word p41–60 | +8.32 | +2.65 | none | Not covered; near parity |

Not covered, but EXReader is already faster than PDF.js:
- image-heavy: Deck
- real-mixed: Deck, Word, PPTX, Excel, Chinese
- vector-heavy: Excel, PPTX

Image-heavy synthetic multi-image is now in this group too, after #263.

## Measurement

### Machine and software

- Intel Core Ultra 7 256V, Windows 11 build 26200, Balanced power plan.
- PDF.js 3.11.174 with Node 24.19.0 and node-canvas 3.2.3. Python 3.14.7 with psutil 7.2.2.
- The fixtures match the manifest SHA-256 hashes.

### Builds

All eight factorial builds came from one build tree with MinGW GCC 16.2.0, Ninja, Release `-O3 -DNDEBUG`, `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF` and `EXR_ENABLE_IMAGE_AVIF=OFF`. All `EXR_` options were identical to the tree that built the brief's baseline DLL. The `orig` arm is that baseline DLL, `e283bea4…`. [Build info](build-info.json)

### Timers and idle gate

The workers are the twocells workers, used unchanged. Native timing covers `exr_fixed_render`. PDF.js timing covers `getPage`, viewport and canvas creation, and the render promise. Pixel hashing runs on the cold sweep, outside the timers.

The idle gate fails closed. Before each round it needs a 500 ms sample at or below 15% system CPU busy and no competing build or benchmark process. It also checks every 5 pages and at the end of each round, and discards the round if anything competing appears. Another session's benchmarks were running at the start, so capture waited until they finished.

- **Factorial:** all 9 rounds were accepted, with pre-round CPU busy of 8.98–12.50%.
- **Two-arm controls:** 27 rounds were accepted, at 4.23–14.40%. One vector round was discarded for a competing process and rerun.
- **In-run CPU busy:** 31–35%, in line with the twocells captures (29–51%). The renderers use helper threads.

### Arm count changes the engine ratio

With the same baseline DLL, the 10-arm factorial gave EXReader/PDF.js ratios of 1.328 / 1.115 / 1.308 (15-sweep means). The two-arm driver gave 1.360 / 1.178 / 1.393.

In the 10-arm run, PDF.js slowed more than EXReader. On mixed, PDF.js ran at 1809.51 vs 1538.48 ms and EXReader at 2017.82 vs 1811.89 ms. A plausible reason is that more processes between a worker's renders mean colder caches, and PDF.js is hit harder; that cause is **未测出**. This does not bias differences *between* EXReader builds, because every EXReader arm ran under the same conditions in each sweep. Headline gaps therefore use the two-arm method, and code effects use the factorial.

## Reproduce

```bash
# 1. Detached worktree at 9a4f3ba0c, configured like EXReader-slides/build/perf (see build-info.json), then:
bash evidence/combined-remeasure-20261118/build.sh <worktree> <dll-root>
cp ../EXReader-slides/build/perf/libexreader.dll <dll-root>/orig/      # sha256 e283bea4…
# 2. Ten-arm factorial (empty raw/ for a fresh capture)
python -B -u evidence/combined-remeasure-20261118/measure.py <dll-root>
python -B evidence/combined-remeasure-20261118/analyze.py
# 3. Two-arm controls: twocells ablate.py/workers with ROOT path depth adjusted, one copy per DLL
d=evidence/combined-remeasure-20261118/twoarm
for a in orig GI GIV; do for c in image-heavy-100:100 real-mixed-120:120 vector-heavy-100:100; do
  python -B -u $d/$a/ablate.py <dll-root>/$a/libexreader.dll ${c%%:*} 1 ${c##*:}; done; done
python -B $d/summarize.py
# Test merge for step 4 (local only): git checkout -b test/combo-densevec-20261118 716ca5e22 && git merge origin/perf/dense-vector-439
```

[Factorial raw captures](raw/) · [Two-arm raw captures](twoarm/) · [Two-arm results](twoarm/results.json)
