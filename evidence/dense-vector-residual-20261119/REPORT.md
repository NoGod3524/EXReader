# Dense vector residual on pages 66–100

After #266, pages 66–100 of vector-heavy-100 still carried roughly 315 ms of the earlier +438.89 ms gap. This lane changes the scanline rasterizer in `src/vector.c` in three exact steps. On those pages at 1200 px, the median sweep fell from **626.85 ms to 409.44 ms**. The median paired saving was **217.88 ms (34.8%)**, and the change was faster in 21 of 21 rounds. In a three-arm run with PDF.js, the median EXReader–PDF.js gap went from **+199.84 ms to −15.53 ms**. EXReader is now slightly faster than PDF.js on this cohort.

Pixels are exact. 353,143,200 large-fixture pixels and 111,897,000 small-fixture pixels matched, with zero differences. CTest passed 577/577. Peak RSS rose by at most +0.41%.

## Where the time was

The attribution in the brief was not redone. I added a temporary cycle-counter probe inside `fill_blend` ([patch](patches/probe.patch)) and ran 5 warm sweeps of pages 66–100. Earlier probes timed whole calls; this one split the scanline into stages. Probe times are inflated: the probe sweep took 818 ms against about 620 ms for the same build unprobed. The split still settled where to look. [Base stages](probe/stages-base.json)

| Stage, ms per sweep (probe-inflated) | Masks (clip, compound fill and stroke) | RGBA (standalone cubic strokes) |
| --- | ---: | ---: |
| Edge tests | 59.7 | 78.2 |
| Crossing sort | 18.5 | **67.4** |
| Span accumulation | 76.7 | 30.4 |
| Mask pack and write | **110.7** | — |
| RGBA paint loop | — | **151.2** |

Three facts follow from the counts:

- **The sort was the inner-loop qsort.** Cubic strokes average 20.5 crossings per sample. Above 8 crossings the code called the CRT `qsort` through a function pointer.
- **Rows were mostly empty.** The 2,100 standalone strokes span 44.8 M row pixels, but a thin curve covers only a small part of each row. The paint loop converted coverage and read the clip for every pixel.
- **Interior pixels were paid for four times.** The clip mask (29,190 rows of about 1,150 px) and the star fill masks are mostly full interior. Each such pixel got four float adds, a float-to-byte pack, and a per-pixel mask write with a division in it.

This also explains the failed active-edge pilot in #266. That pilot comparison-sorted all edges on every call. The 60 cubic strokes per page have 312 edges but only 20 rows, so the per-call sort cost more than the tests it saved.

## The change

All three steps keep results bit-identical by construction, and they keep every `exr_vector_work` charge in the original order. Limit and cancellation failure points are therefore unchanged.

1. **Active edge list without a comparison sort.** Edges are bucketed by their first crossable row in one O(n) counting pass, keeping index order inside each bucket. Each row drops edges that end above it and merges in the row's new edges by edge index. Each sample then tests only active edges, with the original test and the original x formula. The crossings come out identical and in the same order as the all-edge scan. Crossings are insertion-sorted up to 64; `qsort` remains above that. Any x order is exact because equal crossings are summed as a group.
2. **Coverage blocks.** Each span marks the 16-pixel blocks it touches. The row clear, pack, mask write and RGBA paint loops visit only touched blocks. An untouched pixel has coverage exactly 0, and alpha 0 is a no-op in both the mask write and the paint loop. The packed bytes now live in their own row buffer instead of aliasing the float buffer.
3. **Interior runs.** A row records its spans and intersects the interiors of all four samples. A pixel strictly inside a span in every sample receives exactly four 1.0 adds, so its coverage is 4.0 and its alpha 255. Such pixels skip accumulation. Every other pixel gets the same adds in the same order as before. Runs are stored directly:
   - **Mask without a clip:** `memset(255)`.
   - **Opaque RGBA:** through the existing `rectangle_span` path. With alpha 255, `exr_pixel` reduces to a direct store on every branch.
   - **CMYK or composite state:** runs are disabled.
   - **Paths over 16,384 edges:** runs are disabled, which keeps transient scratch at or below 2 MB.

The vector test adds `scanline_reference`, which transcribes the original all-edge algorithm. It checks 400 random shapes × 8 target variants: gray, mask, opaque and translucent RGBA, both fill rules, clip on and off, multiple contours, integer vertices, vertical edges and stroke-like bands. Pixels and the work total must match. Mutating the block marking by one block, or dropping active edges one row early, makes the test fail.

## What each step bought

Each pilot pair ran in its own fresh process for 15 rounds (round 0 is the warm-up). Pages 66–100 alternated AB/BA per page, and the start order flipped each round. Saving is A − B; range is min to max across rounds. [Pilot captures](pilot/)

| Pair, A → B | Median saving, ms | Range, ms | Rounds B faster | Pre-sweep CPU busy |
| --- | ---: | ---: | ---: | --- |
| Empty control: base → same DLL copy | +5.57 | −55.00 to +44.05 | 10/15 | 22.8–45.6% |
| base → active edges + sort | +118.34 | +103.22 to +158.54 | 15/15 | 15.4–43.2% |
| active edges → + coverage blocks | +59.65 | +40.07 to +65.27 | 15/15 | 15.7–54.2% |
| coverage blocks → + runs, per-pixel mask write | +5.16 | −6.30 to +61.28 | 12/15 | 9.9–53.3% |
| coverage blocks → + runs, run-level stores | **+63.22** | +41.21 to +88.32 | 15/15 | 9.7–50.6% |
| Second empty control | +1.87 | −16.69 to +13.65 | 10/15 | 8.5–49.2% |
| base → all three (pre-tidy) | +212.56 | +202.53 to +241.20 | 15/15 | 8.7–29.3% |

Runs with a per-pixel mask write did not beat the control and were nearly dropped. The mask write loop does not vectorize because it divides by 255 when the target is nonzero. Storing whole runs with `memset` is what made runs pay. The pilots ran in separate sessions, so their medians do not add exactly to the combined row. A probe of the coverage-block build is in [probe/stages-aet-sparse.json](probe/stages-aet-sparse.json) ([patch](patches/probe-sparse.patch)). The intermediate builds are in [patches/](patches/).

## Production A/B

The final DLL is the tidied source in this PR (SHA-256 `2a52da3e…`). The base is main `34f3e2c04` (`fd99963f…`). Each row below ran in a fresh process. Round 0 is a warm-up and RGBA comparison. The CPU idle gate is cancelled; the busy percentage sampled for one second before each round is recorded instead. [Harness](harness/ab.py)

| Run | Rounds | Base median, ms | Final median, ms | Median paired saving | Range, ms | Rounds faster | Pre-sweep CPU busy |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| Empty control (base vs same-DLL copy) | 21 | 620.89 | 619.70 | **−0.40 ms** | −9.92 to +73.35 | 9/21 | 8.6–68.0% |
| Pages 66–100 | 21 | 626.85 | 409.44 | **+217.88 ms (34.8%)** | +194.33 to +240.60 | 21/21 | 9.9–34.4% |

The noise floor is the same-DLL control: a median of −0.40 ms and a worst round of +73.35 ms. That worst round started at the session's 68.0% CPU peak. The smallest production saving, 194.33 ms, is 2.6× that worst control round. [Control](control-1200.json) · [Production](dense-1200.json)

### Against PDF.js

Three arms ran in one process: base, final and PDF.js 3.11.174. Even (round + page) rendered ABC and odd rendered CBA, for 15 rounds. Pre-sweep CPU was 8.1–55.2%. [Capture](dense-vs-pdfjs-1200.json)

| Median sweep, ms | Base | Final | PDF.js |
| --- | ---: | ---: | ---: |
| Pages 66–100 | 633.80 | 428.79 | 422.31 |

The median per-round gap went from **+199.84 ms to −15.53 ms**, a reduction of 215.37 ms. Measured against the brief's +438.89 ms denominator, #266 and this change together take the cohort past parity.

### Whole documents and other cohorts

These are whole-document A/B runs, 11 rounds each, with each group split out of the same rounds. [Captures](paired/)

| Fixture | Group | Pages | Base, ms | Final, ms | Median paired change | Range, ms | Rounds faster |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| vector-heavy-100 | Courseware slides | 1–10 | 420.21 | 424.62 | −3.63 (−0.9%) | −11.16 to +10.42 | 5/11 |
| | Excel | 11–25 | 190.95 | 187.75 | +2.19 (+1.1%) | −9.07 to +13.06 | 10/11 |
| | PPTX | 26–65 | 71.13 | 69.18 | +2.09 (+2.9%) | −1.68 to +5.85 | 8/11 |
| | Synthetic dense vector | 66–100 | 609.90 | 402.71 | **+209.32 (+34.3%)** | +200.06 to +234.93 | 11/11 |
| | **All** | 1–100 | 1299.23 | 1081.31 | **+213.29** | +203.83 to +233.10 | 11/11 |
| real-mixed-120 | Courseware slides | 1–21 | 935.63 | 924.70 | −12.08 (−1.3%) | −39.66 to +10.93 | 3/11 |
| | Deck | 22–51 | 418.15 | 282.73 | **+140.94 (+33.7%)** | +124.92 to +240.38 | 11/11 |
| | Word | 52–76 | 164.18 | 167.59 | −1.42 (−0.9%) | −6.51 to +5.89 | 4/11 |
| | PPTX | 77–116 | 74.22 | 79.28 | +1.53 (+2.1%) | −6.33 to +5.56 | 8/11 |
| | Excel + Chinese | 117–120 | 30.69 | 30.53 | +0.07 (+0.2%) | −2.34 to +2.06 | 6/11 |
| | **All** | 1–120 | 1620.37 | 1486.10 | **+135.80** | +116.27 to +247.20 | 11/11 |
| image-heavy-100 | Courseware slides | 1–10 | 504.11 | 507.34 | −4.67 (−0.9%) | −21.39 to +2.36 | 2/11 |
| | Deck | 11–40 | 417.62 | 282.92 | **+138.14 (+33.1%)** | +132.29 to +186.63 | 11/11 |
| | Word | 41–60 | 129.07 | 132.42 | −1.15 (−0.9%) | −5.12 to +1.39 | 3/11 |
| | Image-only | 61–70 | 79.17 | 77.45 | +1.09 (+1.4%) | −2.44 to +7.29 | 8/11 |
| | Synthetic multi-image | 71–100 | 665.70 | 684.02 | +5.30 (+0.8%) | −24.03 to +14.40 | 8/11 |
| | **All** | 1–100 | 1831.79 | 1703.83 | **+142.80** | +115.59 to +167.19 | 11/11 |

The Deck pages also drop by a third. That is the same vector-fill path: deck.pdf alone saved 68.63 ms (33.4%) per sweep. Group columns are medians of per-round group sums, so they do not add up to the All row.

**Courseware and Word pages are slightly slower.** They lose 0.9–1.3%, the arm was faster in only 2–5 of 11 rounds, and every range crosses zero. That is inside the ±3% band used before, but the sign is consistent, so I report it as a real small cost. The likely source is the extra per-call scratch allocations on pages with many small fills. That was not isolated.

### Small fixture ceilings

| Fixture | Base page p50, ms | Final page p50, ms | Change | Ceiling, ms |
| --- | ---: | ---: | ---: | ---: |
| PPTX @600 | 0.914 | 0.891 | −2.5% | 0.844 |
| PPTX @1200 | 1.726 | 1.635 | −5.3% | 1.729 |
| Deck @1200 | 13.882 | 9.677 | −30.3% | 15.4 |
| Word-5 @1200 | 6.432 | 6.298 | −2.1% | 5.75 |

The final build is no slower than base on any of these four fixtures. However, **both arms exceed the absolute ceilings for PPTX @600 and Word-5 @1200** in this session. Base itself ran 4–12% slower than the absolute figures in the #266 report, under 8–30% background CPU from other desktop applications. I am not claiming those two ceilings pass. They need a re-check on a quiet machine.

### Pixel parity, CTest, RSS

The parity run rendered every page of every fixture with both DLLs and compared the active RGBA bytes. The three large fixtures at 1200 px matched on all **353,143,200** pixels. Seven small fixture and width combinations matched on all **111,897,000** pixels. Every timing capture also reported zero mismatched pages. [Pixels](pixels.json) · [Script](harness/pixels.py)

CTest passed **577/577** in 104.90 seconds; the new checks are inside the existing vector test. [Output](ctest.txt)

Peak working set was measured per arm in fresh processes, in AB, BA, AB order. [RSS](rss.json)

| Fixture | Base peak, bytes | Final peak, bytes | Change | Worst matched pair |
| --- | ---: | ---: | ---: | ---: |
| image-heavy-100 | 153,866,240 | 153,640,960 | −0.15% | −0.03% |
| real-mixed-120 | 112,611,328 | 113,078,272 | +0.41% | +0.41% |
| vector-heavy-100 | 82,444,288 | 82,448,384 | +0.00% | +0.13% |

## Directions from the brief

- **Raising the 4.93% edge-test hit rate.** Done, as the active edge list above. In the probe, edge tests fell from 59.7 + 78.2 to 19.0 + 18.3 probe-ms per sweep. The tested-edge count was not recounted.
- **Building the compound mask once per page and reusing it.** Not pursued. The 25 compounds on a page have distinct geometry, so their fill and stroke masks cannot be shared. The explicit clip they share is already rasterized once per page.
- **Caching clip coverage across pages by clip identity.** Not attempted. The clip geometry does repeat across pages, but after this change the cohort is already below PDF.js. A cross-render cache would need document-level plumbing for the one remaining piece of clip-mask work. Its benefit is unmeasured.

The gap on pages 66–100 is closed, so I stopped there. The next biggest items in the second probe were the compound compositor at about 44 probe-ms and the cubic-stroke paint loop at about 59 probe-ms. Pursuing those is optional.

## Measurement notes

- The global bench lock (holder `opus-densevec2`) covered every timed sweep, pilot, parity run, RSS run and ctest, with a heartbeat each round. The exception is the first stage probe, which ran for about 30 s while another lane (`dot-three-cells-20261119-000607`) held the lock. That probe is a stage split only, and none of its numbers are used as timings here. It may have disturbed one of that lane's sweeps.
- Background CPU from other desktop applications was 8–68% before rounds and is recorded per round in every capture. Session drift moved the base median by up to about 100 ms between pilot runs, so only paired savings within one process are compared.

## Reproduction

Base is main `34f3e2c04`; the change is this PR. Both are Release DLLs built with MinGW GCC 16.2.0 (`-O3`), Ninja 1.13.2, `EXR_BUILD_TESTS=ON`, `EXR_BUILD_TOOLS=OFF`, `EXR_ENABLE_IMAGE_AVIF=OFF`, and the dependency sources from the local cache. The tools were Python 3.14.7 with psutil 7.2.2, and Node 24.19.0 with PDF.js 3.11.174 and node-canvas 3.2.3. The harness imports `paired_sweep.py` and `pdfjs_worker.cjs` from `evidence/slides-gradient-20261118/`.

```powershell
# Copy the base and final DLLs to _work/dlls/base.dll and final.dll, and base.dll to base-copy.dll.
pwsh C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1 -Holder <name> -Wait
bash evidence/dense-vector-residual-20261119/harness/accept.sh
pwsh C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\bench-lock.ps1 -Holder <name> -Release
```

`accept.sh` runs the control, the production A/B, the PDF.js arm, the whole-document and small-fixture cells, pixel parity, RSS and ctest, in that order. For the stage split, apply [patches/probe.patch](patches/probe.patch) to main and run `harness/probe_run.py <dll> <out.json> 5`.
