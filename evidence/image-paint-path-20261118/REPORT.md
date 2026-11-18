# Image paint path — continuation of `4a025e0c0`

Completed on `perf/firstscreen-cold`. Image-heavy p71–100 mean of per-page warm medians: **86.773 → 31.909 ms/page**; slowest candidate page median **37.044 ms**. All four requested absolute small-fixture ceilings pass. Direct comparison: **465,040,200 pixels, zero differences**. CTest: **577/577**.

## Build identities and scope

A uses the affine-image source from `809b3743d`, immediately before the WIP kernel; all other source, including the corrected ablation code, is shared. B retains the committed WIP axis kernel and adds exact SSE2 solid-mask blending into opaque RGBA destinations, keeps that solid-mask loop out of line, and fixes the diagnostic placeholder alpha from 128 to 255. No cache limit, render scale or interpolation setting was changed in production runs. [Source and DLL fingerprints](final-builds.json).

| Build | DLL SHA-256 |
| --- | --- |
| A | 2cadc856fb0d5f945203173f72807652bc0c088e979f6a89f9dcca8749bd1a8c |
| B | b819e41ecbbe5a2cf3629b751e3654d739f8a2d7dec2358c1df8fb77e6bab12a |

Release, gcc (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r1) 16.2.0; `-O3 -DNDEBUG`, C11, `-Wall -Wextra -Wpedantic -Werror`. Every variant build removed the DLL before linking and checked the resulting timestamp. The decoded-image cache retained its default 64 MiB limit.

## Instrumentation before the final change

Five alternating fresh-process A/WIP pairs per case, 1200 px, one additional warm render, with an idle check before each process. These are QPC image-call scopes from the diagnostic builds, not the final production timings. Path 2 = unmasked bilinear; path 4 = masked axis; path 9 = generic; path 3 = solid-mask. [Raw traces](continue-path-trace.json), [diagnostic builder](build_trace.py), [trace runner](run_path_trace.py).

| Sample | Path A → WIP | A paint ms | WIP paint ms |
| --- | --- | --- | --- |
| mixed image 1 | 2 → 2 | 19.106 | 16.805 |
| mixed image 2 | 2 → 2 | 2.698 | 2.109 |
| bitmap image 1 | 2 → 2 | 18.168 | 15.732 |
| heavy80 image 1 | 9 → 4 | 85.873 | 20.646 |
| heavy80 image 2 | 2 → 2 | 3.623 | 2.527 |
| heavy80 image 3 | 9 → 4 | 17.272 | 3.960 |

The large page-80 masked images were using the generic sampler. The WIP axis path precomputes column taps and reuses converted source/mask rows while retaining the generic tap, multiplication and accumulation order. It falls back for unsupported transforms, matte/nested masks, composite state and strong minification. The large images therefore get the new masked path; the first-page images use the existing unmasked path.

The WIP also slowed the deck solid-mask path: its largest first-page image call measured 2.938 → 5.184 ms in the diagnostic pair. A counter-only render found 810,000 nonzero partial-opacity pixels and zero fully opaque source results in that paint. [Counts](deck-opacity-counts.txt). The out-of-line-only candidate still missed the deck ceiling at 16.023 ms ([paired result](noinline-deck-ab.json)). The final code blends four 16-bit lanes and uses the exact identity `(n+127)/255 = (t+(t>>8))>>8`, `t=n+128`, for `0 <= n <= 65025`. Transparent destinations retain the existing scalar blend. The added image test compares 65,536 pixels against the independent generic sampler, varying mask bytes, source bytes, destination colors and coverage.

## Production measurement protocol

Final first-screen runs use seven alternating AB/BA pairs, with a new process, one open and one first render per side. Whole-document runs use AB/BA/AB across three repeats, a fresh process per side, one initial render sweep, then three timed sweeps for large fixtures or twenty for small fixtures. Tables use the median across repeats of the tool’s p50/p95. Throughput excludes hashing, copying and frees. Peak RSS is Windows PeakWorkingSetSize, including DLL/document/bitmap allocations. Whole-document JSON retains per-repeat values; hidden `.realdoc-final-*-ab` directories retain all per-page samples.

The system-CPU gate is 15%, measured over 0.5 seconds. It runs before each first-screen/ablation pair and before each whole-document child. Failed gates take no samples and retry. An inherited `out/run_all.sh` was stopped. The overlapping exploratory `continue-image-heavy-ab.json`, inherited `firstscreen-ab.json`, and earlier `ablate-*` files are excluded from final acceptance. Final acceptance uses only `final-*` files.

## First screen, 1200 px

| Fixture | A cold render ms | B cold render ms | A open + render ms | B open + render ms |
| --- | --- | --- | --- | --- |
| mixed@1200 | 62.525 | 59.000 | 63.333 | 59.735 |
| bitmap@1200 | 37.762 | 35.519 | 38.498 | 36.272 |

Render includes bitmap allocation; startup, DLL loading, hashing and freeing are outside the timer. Open-plus-render is calculated per sample before taking its median. [Seven-pair raw samples](final-firstscreen-ab.json).

## Image-heavy p71–100, 1200 px

| Metric | A | B |
| --- | --- | --- |
| Mean of 30 per-page warm medians, ms | 86.773 | 31.909 |
| Largest per-page warm median, ms | 118.361 | 37.044 |

The handoff’s 158 ms/page is a historical reference; the same-session control here measured 86.773 ms/page. Every candidate per-page median in this cohort is below 60 ms. [Full data](final-heavy-ab.json).

| Page | A p50 ms | B p50 ms |
| --- | --- | --- |
| 71 | 114.147 | 35.515 |
| 72 | 46.215 | 28.471 |
| 73 | 115.102 | 34.037 |
| 74 | 45.263 | 26.963 |
| 75 | 114.598 | 33.856 |
| 76 | 115.750 | 36.094 |
| 77 | 46.120 | 28.321 |
| 78 | 113.770 | 34.356 |
| 79 | 43.953 | 26.226 |
| 80 | 113.076 | 33.861 |
| 81 | 112.757 | 35.284 |
| 82 | 45.551 | 29.373 |
| 83 | 113.704 | 33.870 |
| 84 | 44.404 | 26.861 |
| 85 | 114.587 | 33.412 |
| 86 | 116.637 | 36.147 |
| 87 | 45.663 | 28.262 |
| 88 | 112.940 | 34.425 |
| 89 | 45.001 | 27.129 |
| 90 | 112.156 | 33.578 |
| 91 | 114.440 | 37.044 |
| 92 | 47.050 | 29.130 |
| 93 | 113.725 | 34.132 |
| 94 | 44.332 | 26.509 |
| 95 | 112.132 | 34.484 |
| 96 | 116.966 | 36.203 |
| 97 | 47.529 | 28.760 |
| 98 | 118.361 | 34.327 |
| 99 | 45.263 | 26.330 |
| 100 | 112.012 | 34.322 |

## Large-fixture throughput and memory

| Fixture | p95 ms A → B | Pages/s A → B | Max peak RSS MiB A → B | Peak RSS change |
| --- | --- | --- | --- | --- |
| heavy | 119.330 → 54.721 | 26.17 → 47.63 | 146.87 → 147.14 | 0.19% |
| mixed | 49.325 → 45.723 | 70.33 → 75.87 | 107.68 → 108.16 | 0.44% |
| vector | 100.241 → 96.071 | 25.60 → 25.52 | 79.06 → 78.91 | -0.20% |

RSS columns use the largest process peak across the three repeats, rather than the median peak. [Heavy](final-heavy-ab.json), [mixed](final-mixed-ab.json), [vector](final-vector-ab.json). Vector throughput changed from 25.60 to 25.52 pages/s.

## Small-fixture guards

| Fixture | A p50 ms | B p50 ms | Change | Requested ceiling ms | Guard |
| --- | --- | --- | --- | --- | --- |
| pptx @600 | 0.854 | 0.862 | 0.94% | 0.871 | pass |
| pptx @1200 | 1.532 | 1.588 | 3.66% | 1.768 | pass |
| pptx @2400 | 6.530 | 6.627 | 1.49% | — | — |
| deck @1200 | 14.321 | 13.507 | -5.68% | 15.4 | pass |
| word @600 | 2.109 | 2.111 | 0.09% | — | — |
| word @1200 | 6.072 | 6.351 | 4.59% | 6.5 | pass |

All four absolute ceilings pass. Relative increases remain: PPTX @1200 +3.66%, Word @1200 +4.59%. [PPTX](final-pptx-ab.json), [deck](final-deck-ab.json), [Word](final-word-ab.json).

## Complete image ablations, 1200 px

Each cell is **cold / warm median ms**. Five alternating full/disabled pairs per mode; every child starts fresh and performs three additional warm renders. Each mode has its own paired full controls, so the paired savings below are used rather than subtracting independently displayed medians.

| Sample | Build | Full | Skip image | Skip decode | Skip paint |
| --- | --- | --- | --- | --- | --- |
| mixed@1200#p1 | A | 62.339 / 44.600 | 24.979 / 23.243 | 47.586 / 46.809 | 41.850 / 23.229 |
| bitmap@1200#p1 | A | 38.026 / 18.916 | 1.479 / 0.797 | 22.504 / 21.749 | 20.353 / 0.799 |
| imageheavy@1200#p80 | A | 112.462 / 111.167 | 3.127 / 1.831 | 111.351 / 110.959 | 6.542 / 1.962 |
| mixed@1200#p1 | B | 58.384 / 40.798 | 24.109 / 23.612 | 44.049 / 42.304 | 41.478 / 23.247 |
| bitmap@1200#p1 | B | 35.361 / 16.427 | 1.583 / 0.787 | 20.723 / 19.490 | 19.648 / 0.857 |
| imageheavy@1200#p80 | B | 34.475 / 30.721 | 2.798 / 2.034 | 31.842 / 31.670 | 6.625 / 1.901 |

| Sample | Build | Paired saving: skip decode ms | Paired saving: skip paint ms |
| --- | --- | --- | --- |
| mixed@1200#p1 | A | 15.509 | 20.250 |
| bitmap@1200#p1 | A | 15.143 | 17.929 |
| imageheavy@1200#p80 | A | 2.306 | 108.003 |
| mixed@1200#p1 | B | 14.683 | 17.580 |
| bitmap@1200#p1 | B | 15.405 | 15.784 |
| imageheavy@1200#p80 | B | 3.108 | 28.364 |

`image-paint` still decodes, then releases the image and native-ink allocation without drawing. `image-decode` paints a dimension/interpolation/soft-mask-shaped opaque white placeholder, with no payload decoding. The WIP’s source placeholder had alpha 128 despite its opaque comment; that was corrected before these runs. Placeholder allocation and changed pixel contents are included in its timing, so full-minus-placeholder is not presented as an exact decoder measurement.

The established decode/paint split is retained: the earlier mixed-page run measured 17.570 ms decode and 21.717 ms paint; the bitmap run measured 18.738 ms decode and 18.018 ms paint. Thus the original image cost was roughly half decode and half paint, not 37–38 ms of decode. [Previously committed split](../firstscreen-cold-20261118/REPORT.md). The page-80 paint-disabled paired saving is 108.003 → 28.364 ms in the final ablation; that is the measured paint bottleneck addressed here. [A p1](final-ablate-p1-A.json), [B p1](final-ablate-p1-B.json), [A p80](final-ablate-p80-A.json), [B p80](final-ablate-p80-B.json).

## Final correctness

| Fixture | Widths | Directly compared pixels | Different pixels |
| --- | --- | --- | --- |
| real-mixed-120 | 1200 | 131,317,200 | 0 |
| image-heavy-100 | 1200 | 112,872,000 | 0 |
| vector-heavy-100 | 1200 | 108,954,000 | 0 |
| pptx-20 | 600, 1200, 2400 | 85,056,000 | 0 |
| deck | 600, 1200 | 15,192,000 | 0 |
| word-5 | 600, 1200 | 11,649,000 | 0 |

Large fixtures: **353,143,200 / 0**; small fixtures: **111,897,000 / 0**. This compares active RGBA bytes directly on every row and counts differing pixels. [Raw comparison](final-pixels.json), [verifier](verify_pixels.py).

CTest passed **577/577** in **91.77 seconds**, after rebuilding the final source, including the added solid-mask/generic comparison. [Build log](final-build.txt), [CTest log](final-ctest.txt).

## Reproduce

From the repository root, with the existing Release `build/perf` configuration:

```powershell
python -X utf8 evidence/firstscreen-cold-20261118/make-bitmap-fixture.py build/bitmap-first-120.pdf
python -X utf8 evidence/image-paint-path-20261118/build_ab.py
$env:EXR_BENCH_A = "out/image-paint-reproduce/A/libexreader.dll"
$env:EXR_BENCH_B = "out/image-paint-reproduce/B/libexreader.dll"
python -X utf8 evidence/image-paint-path-20261118/run_acceptance.py first heavy pptx deck word mixed vector ablate
python -X utf8 evidence/image-paint-path-20261118/verify_pixels.py $env:EXR_BENCH_A $env:EXR_BENCH_B evidence/image-paint-path-20261118/final-pixels.json
cmake --build build/cold -j 4
ctest --test-dir build/cold -j 4 --output-on-failure
```

The diagnostic A/WIP trace is separately reproducible with `build_trace.py` and `run_path_trace.py`. The production builder restores the working source in a `finally` block, forces each DLL relink, and records timestamps and hashes.
