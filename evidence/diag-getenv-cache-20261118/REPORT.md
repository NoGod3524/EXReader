# Diagnostic toggle process cache — 2026-11-18

Branch: `perf/diag-getenv-cache`, based on `acfcdd4f9`. This change caches only `EXR_ATTRIBUTION_SKIP`. It preserves `image`, `image-paint`, `image-decode`, `path`, `glyph`, `group`, `shading`, and `softmask` ablations.

Measured small-fixture warm p50 changes: **deck −4.87%, Word −4.59%, PPTX −2.69%**. The census falls from **62,756 toggle lookups to 1** over 282 renders. Fresh direct comparison: **465,040,200 pixels, zero differences**. CTest: **577/577**.

## Count before changing the cache

An untimed DLL records each actual `getenv("EXR_ATTRIBUTION_SKIP")` call, with the owning function or paint category. One fresh process opens all five fixtures and renders a cold sweep followed by a warm sweep at 1200 px. Mixed is restricted to page 1; the other fixtures include every page. These instrumented binaries are excluded from timing measurements. [Builder](build.py), [counter](count.py), [baseline trace](count-A-trace.txt), [per-page baseline census](count-A.json).

| Baseline route | Direct toggle lookups per eligible event | Additional conditional lookups |
| --- | ---: | --- |
| `glyph_event` | 1 | Geometry adds 1 if a graphics-state soft mask is present. Type3 and invisible mode 3 return before the toggle check. |
| `path_event` (path paint/clip callback) | 1 | Geometry adds 1 for a graphics-state soft mask when painting. There is no function named `begin_path` in this layer. |
| `image_event` | 2 | A cache miss adds 1 in `load_cached`; each decoded image/mask adds 1 in `decode_image`. A graphics-state soft mask can add 1. Missing image sinks return before the checks; skipping image returns after the first. |
| `begin_group_event` | 1 | Adds 1 if a graphics-state soft mask is present. |
| `end_layer_event` | 1 | — |
| `shading_operation` | 1 | Painting can add a graphics-state soft-mask lookup. |

The requested fixtures do not invoke the paint group callbacks. A separate existing group fixture, `alpha-source-blend-opacity-group-Normal.pdf` at 64 px, records **4 group lookups**, covering two begin/end pairs. Its full and group-disabled outputs differ, and both match the corresponding baseline outputs. [Trace](group-count-trace.txt), [validation](validation.json). Per-event counts above follow the instrumented call sites and their guards; recursive mask decoding is counted separately.

The supplied **1.08 µs per lookup** is used without remeasurement. Milliseconds in the following table are **calculated lookup costs**, not observed render savings.

| Fixture | Pages counted | First-page cold lookups | First-page warm lookups | First-page cold calculated ms | Whole cold sweep lookups | Whole warm sweep lookups |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| deck | 15 | 578 | 557 | 0.62424 | 8,391 | 8,361 |
| word-5 | 5 | 168 | 166 | 0.18144 | 830 | 828 |
| pptx-20 | 20 | 35 | 35 | 0.03780 | 711 | 711 |
| real-mixed-120 page 1 | 1 | 52 | 48 | 0.05616 | 52 | 48 |
| image-heavy-100 | 100 | 52 | 52 | 0.05616 | 21,412 | 21,412 |

[All page counts and calculated costs](page-counts.csv) retain each page individually. Across the **282 renders**, the baseline makes **62,756** toggle lookups: 47,574 glyph, 12,284 path, 1,120 image, 1,120 image-paint, 359 decode-image soft-mask, 233 cache-miss image-decode, 44 shading, and 22 graphics-state soft-mask checks. The cached build makes **1 lookup total** over the identical process workload. [Cached trace](count-B-trace.txt), [cached census](count-B.json).

These counts concern `EXR_ATTRIBUTION_SKIP`; other variables, including the per-page `EXR_ATTRIBUTION_TRACE` check and document-cached image profile/cache settings, are unchanged.

## Cache behavior and diagnostic checks

`pdf_objects.c` owns one C11 atomic enum cache shared by content parsing, painting, and image decoding. A strong compare/exchange selects one initializer; it reads the environment, parses the existing mode names, and release-publishes the enum. Concurrent callers acquire-load until initialization completes. Hot calls read the cached integer and compare it with the requested enum. No environment pointer is retained and no allocation is added.

**Set `EXR_ATTRIBUTION_SKIP` before process startup. It is snapshotted on the first diagnostic check; changing it during execution no longer changes the mode.** Start another process for another ablation. Missing, empty, and unknown values keep normal rendering. This lifetime is documented in the private header and `bench_firstscreen.py` documentation.

[Validation script](validate.py) compiles the exact production function and enum with a counted `getenv` substitution. For each of 11 fresh-process settings, 32 threads race initialization, followed by a later environment change: 320,001 mode checks pass and each process records exactly 1 lookup. Integration checks compare baseline and candidate hashes for every existing mode plus empty and unknown values. The image-disabled hash differs from full rendering. The live-environment test changes empty → image → glyph: baseline output changes, while candidate output remains identical. [Raw results](validation.json).

## Alternating production A/B

The baseline is unmodified main at `acfcdd4f9`; the candidate differs only by the shared toggle cache and its call sites. Both DLLs were built in the same Release build directory and copied into separate directories. Their recorded fingerprints match the libraries identified by every timing report. No instrumented DLL is used for timing, and no environment override is set.

The existing `tools/bench_real_doc.py` alternates **AB/BA** across independent process pairs. Small fixtures use **15 pairs**, one initial untimed sweep and **20 timed warm sweeps per process**. Image-heavy uses **7 pairs**, one initial sweep and **3 timed warm sweeps**. Every page is rendered at 1200 px. Each child passes a **≤15% system CPU gate over 0.5 seconds** immediately before launch. Compilation, CTest, pixel verification, and diagnostic checks finished before timing began. All requested trials completed without a gate timeout. Hashing and freeing are outside render timing; bitmap allocation is inside it.

| Fixture @1200 | A p50 ms | B p50 ms | Change | A p95 ms | B p95 ms | A / B pages/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| deck | 13.564 | 12.903 | −4.87% | 15.491 | 14.426 | 73.55 / 76.98 |
| word-5 | 6.029 | 5.752 | −4.59% | 6.980 | 6.411 | 165.03 / 174.46 |
| pptx-20 | 1.596 | 1.553 | −2.69% | 2.032 | 2.017 | 602.81 / 617.98 |
| image-heavy-100 | 13.850 | 12.794 | −7.62% | 54.836 | 55.089 | 47.05 / 47.38 |

Cells are medians of process-level statistics across repeats. [Deck](deck-ab.json), [Word](word-ab.json), [PPTX](pptx-ab.json), [image-heavy](heavy-ab.json). Raw per-page process samples are retained in the corresponding `.realdoc-*-ab` directories.

Paired effects compare each process p50 with its paired control. Bootstrap intervals resample **process pairs**, 20,000 draws, seed 261118; pages and repeated renders are not independent trials. [Analysis and all paired changes](analysis.json), [analysis script](analyze.py).

| Fixture | Mean paired change | Bootstrap 95% interval | Faster pairs | A / B process-p50 spread |
| --- | ---: | --- | ---: | --- |
| deck | −6.655% | −10.896% to −3.410% | 14/15 | 51.3% / 17.5% |
| word-5 | −4.855% | −6.504% to −3.312% | 14/15 | 11.4% / 9.4% |
| pptx-20 | −2.035% | −3.905% to −0.183% | 12/15 | 8.3% / 14.3% |
| image-heavy-100 | −7.127% | −12.233% to −2.555% | 6/7 | 18.5% / 13.0% |

Spread is `(max process p50 − min process p50) / min process p50`. Every sample is retained, including deck's −30.754% paired outlier. All three small-fixture paired intervals are below zero.

The image-dominated **p71–100** cohort measures **32.74888 → 32.88791 ms/page**, the mean of 30 per-page warm medians across repeats. Its mean paired cohort change is **−0.052%**, bootstrap interval **−4.906% to +4.719%**. Thus the image cohort's paired estimate is centered near zero; the whole-document p50 improvement includes the fixture's other pages. Whole-document image-heavy p95 rises **0.253 ms (+0.46%)**, while throughput rises **0.70%**.

### Peak working set and observed CPU

Peak RSS uses Windows `PeakWorkingSetSize`, including the Python harness, DLL, document and bitmap allocations. Values below are the **largest process peak** across repeats, not the median peak displayed in the tool's console output.

| Fixture | A max peak bytes | B max peak bytes | Change |
| --- | ---: | ---: | ---: |
| deck | 49,672,192 | 49,704,960 | +0.066% |
| word-5 | 50,905,088 | 50,962,432 | +0.113% |
| pptx-20 | 34,156,544 | 34,152,448 | −0.012% |
| image-heavy-100 | 154,722,304 | 154,304,512 | −0.270% |

The largest observed peak increase is **57,344 bytes, +0.113%** on Word. The implementation adds static cache state and no heap allocation.

| Fixture | A / B pre-gate CPU range % | A / B capture CPU range % |
| --- | --- | --- |
| deck | 3.52–14.90 / 5.58–13.28 | 19.55–49.37 / 20.09–36.35 |
| word-5 | 3.91–13.67 / 4.30–14.62 | 17.65–35.39 / 18.02–26.67 |
| pptx-20 | 3.94–14.06 / 3.49–11.37 | 20.56–37.94 / 18.76–44.38 |
| image-heavy-100 | 3.91–11.33 / 7.06–10.28 | 20.07–26.60 / 21.86–30.18 |

Capture CPU includes rendering itself and records the load after the gate. The paired intervals and spreads above retain this session's variation.

## Correctness

Fresh direct comparisons use the existing [active-RGBA verifier](../image-paint-path-20261118/verify_pixels.py), alternating A/B render order by page. All pages and widths are included:

| Cohort | Compared pixels | Different pixels |
| --- | ---: | ---: |
| deck/Word at 600 and 1200; PPTX at 600, 1200 and 2400 | 111,897,000 | 0 |
| mixed/image-heavy/vector-heavy at 1200 | 353,143,200 | 0 |

[Raw pixel results](pixels.json). Fresh full build and CTest: **577/577 passed**, 100.64 seconds total. [CTest output](ctest.txt). The concurrency/lifetime checks above are additional checks, not included in the 577 count.

## Reproduction

Windows, Intel Core Ultra 7 256V, 8 logical processors; GCC MinGW-W64 UCRT POSIX 16.2.0, Release `-O3 -DNDEBUG`, C11 and warnings-as-errors. [Session metadata](session.json). [A source/DLL hashes](build-A.json), [B source/DLL hashes](build-B.json); count-build hashes are recorded separately.

```powershell
# Run the census before applying the source change; A is unmodified main.
python evidence/diag-getenv-cache-20261118/build.py count-A
python evidence/diag-getenv-cache-20261118/count.py count-A
python evidence/diag-getenv-cache-20261118/build.py A
# Apply the production cache diff, then:
python evidence/diag-getenv-cache-20261118/build.py count-B
python evidence/diag-getenv-cache-20261118/count.py count-B
python evidence/diag-getenv-cache-20261118/build.py B
python evidence/diag-getenv-cache-20261118/validate.py
cmake --build build/perf -j 4
ctest --test-dir build/perf --output-on-failure -j 4
python evidence/image-paint-path-20261118/verify_pixels.py build/diag/A/libexreader.dll build/diag/B/libexreader.dll evidence/diag-getenv-cache-20261118/pixels.json
python evidence/diag-getenv-cache-20261118/run_ab.py
python evidence/diag-getenv-cache-20261118/analyze.py
```

`build.py` reuses the local pinned dependency-source paths from the sibling main verification checkout when creating a new build directory. On another host, configure the same Release options and pinned dependencies first. Instrumentation is temporary and restored byte-for-byte after each count build.
