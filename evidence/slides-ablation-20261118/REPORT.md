# Slides rendering ablation

`image-heavy-100.pdf`, pages 1–10 at 1200 × 900. The reference comparison measured EXReader at 660.10 ms and PDF.js at 344.75 ms, a gap of 315.35 ms over these ten pages.

## Results

**Shading gave the largest mean gap reduction among the requested classes, 270.45 ms. Images reduced it by 224.82 ms and saved the most EXReader time.** The shading and image repeat ranges overlap. Removing soft masks while retaining the shading widened the gap in all three repeats. The path and glyph estimates crossed zero across repeats.

Positive savings mean that engine ran faster after the omission. All times are milliseconds per ten-page sweep.

| Class omitted in both engines | EXReader saved | PDF.js saved | Full gap | Omitted gap | Gap reduction | Share of 315.35 ms | Repeat range of reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Shading, including in masks | +478.47 | +208.02 | +502.28 | +231.84 | **+270.45** | **85.8%** | +252.99 to +298.97 |
| Soft mask | −132.50 | +199.99 | +558.61 | +891.10 | −332.49 | −105.4% | −398.57 to −287.69 |
| Path | −17.49 | +12.64 | +504.37 | +534.50 | −30.13 | −9.6% | −79.39 to +1.47 |
| Glyph | +69.72 | +26.56 | +565.08 | +521.92 | +43.16 | +13.7% | −25.61 to +145.24 |
| Image | +659.68 | +434.86 | +516.28 | +291.45 | **+224.82** | **71.3%** | +197.02 to +265.51 |
| Group | — | — | — | — | Unmeasured | — | — |

The EXReader-only group control averaged 1285.18 ms full and 1225.27 ms with the hook. The apparent saving varied from 6.80 to 135.23 ms with identical output on all ten pages in each repeat. The hook covers a group type with no observed draws in this fixture, so this spread illustrates timing variability.

| Additional omission | EXReader saved | PDF.js saved | Full gap | Omitted gap | Gap reduction | Share of 315.35 ms | Repeat range of reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Page shading only | +538.74 | +163.80 | +612.31 | +237.37 | +374.94 | +118.9% | +356.79 to +391.93 |
| Page shading and soft masks | +452.10 | +181.09 | +522.69 | +251.68 | +271.01 | +85.9% | +254.25 to +287.76 |
| Page-stream clips | −57.97 | −314.47 | +520.42 | +263.93 | +256.50 | +81.3% | +204.05 to +308.30 |

The page-shading omission also eliminates every EXReader mask build. PDF.js retains ten mask groups in that edit. The resulting 374.94 ms gap reduction includes this difference in mask work. All three shading-related edits in the audit that remove the page shading produced identical pixels within each engine. The clip gap narrowed because PDF.js slowed by 314.47 ms and EXReader slowed by 57.97 ms.

The renderer already uses an axial shading lookup table and reuses aligned samples within scanlines. All ten luminosity masks use gradients whose RGB stops include intermediate values. The measured shading effect covers both gradient painting and mask construction, and the image effect is of comparable size. This is an attribution-only result.

## Measurement

The existing [driver](ablate.py) from `03d539cb7` opens a fresh process for each arm in each repeat. It times only pages 1–10, rotates arm order by page, reverses order on alternate warm sweeps, and reverses class order on the middle repeat. Each repeat has one cold sweep for output hashes and eight warm sweeps for timing. The edited-PDF arms open the same file in both engines. The EXReader-only hooks serve as independent checks of the PDF edits where available.

The full and omitted gaps are EXReader minus PDF.js using the same repeat. The gap reduction is full minus omitted. Each repeat contributes its mean of eight ten-page sweep totals. The table averages those paired repeat means, with the repeat range alongside. The share divides the measured reduction by the historical 315.35 ms. Adding the shares would double-count some work.

The idle gate retries before starting a repeat. Its threshold is 15% for the first five seconds of waiting and 30% thereafter. The driver also checks for known competing render or build processes during each sweep. The summary uses 27 accepted captures, three per case. Five captures with detected overlap were archived and their slots retried. Before accepted captures, system CPU ranged from 3.20% to 29.96%. During captures it ranged from 22.62% to 66.48%, including the benchmark. Matched full gaps averaged 502.28 to 612.31 ms by case in this session. The 315.35 ms reference supplies the percentage denominator. [Raw timings and output hashes](raw/) · [overlap captures](raw/overlap/).

The EXReader Release DLL was already built. Its SHA-256 was `e283bea43cc9fa1326bf34d55d7fe8176dcd24bb956ccdd8540912c00c8f416d`. PDF.js was 3.11.174 with node-canvas 3.2.3 on Node 24.19.0. The capture command used the checked-in driver and existing PDFs.

```powershell
python -u evidence/slides-ablation-20261118/ablate.py build/perf/libexreader.dll 3
```

## Instrumentation

The fixture and all eight existing edits matched their [manifest hashes](variants.json). The content audit found 10 page shadings, 10 further shadings in luminosity-mask groups, 10 graphics-state soft-mask uses, 20 stroked paths, 42 text-show operators, 28 image draws, and 110 page-stream clips. All audited soft-mask uses came from graphics states. Five unique slide streams are each used twice.

The shading edit removes both sets of shading operators. The soft-mask edit deletes the graphics-state `/SMask` entries while retaining the page shadings. The page-shading edit removes the page `sh` operators only. The combined gradient edit removes those page operators and the graphics-state mask entries.

The EXReader trace and PDF.js operator-list audit ran outside the timing captures. Counts cover the ten pages. PDF.js still emits ten soft-mask groups in the page-shading and shading edits, while EXReader's mask builds run on demand when it paints the masked shading. [Per-page audit](raw/runtime-audit.json).

| Input | EXReader source draws | EXReader mask builds | PDF.js shading ops | PDF.js soft-mask groups |
| --- | ---: | ---: | ---: | ---: |
| Full | 20 | 10 | 20 | 10 |
| Omit all shading operators | 0 | 0 | 0 | 10 |
| Omit page shading | 0 | 0 | 10 | 10 |
| Omit soft masks | 10 | 0 | 10 | 0 |
| Omit page shading and soft masks | 0 | 0 | 0 | 0 |

The group hook covers only EXReader's nested Form group begin/end callbacks. All direct page XObjects are images, and the PDF.js operator list contains zero non-mask Form group starts. Page layers and the groups rasterized by the soft-mask builder use separate calls. The available group comparison is EXReader-only.

For each measured repeat, the EXReader hooks for shading, soft mask, path, glyph, and image produced the same ten hashes as their edited PDFs. Relative to full rendering, the edited PDFs changed ten page hashes in both engines for shading, soft mask, path, and image, eight for glyph, and six for clips.
