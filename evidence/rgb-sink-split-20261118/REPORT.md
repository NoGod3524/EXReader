# RGB sink: full blend versus mapped copy

Base: `acfcdd4f92bff41cc7b67ae0ae5f884962e57e19`. Evidence-only branch `perf/rgb-sink-split`; no production source, headers, CMake or existing benchmark edits.

The full-minus-copy interval is the measured cost removed by replacing the RGB sink with a nearest mapped copy. It is a compute-side **upper-bound proxy**, including the source/mask/destination traffic removed alongside arithmetic. The copy residual includes mapping, clip tests, branches and stores. Neither column is a hardware measurement of pure computation or DRAM time.

## Measured sink intervals

All numbers below are ms per complete document sweep. Means use three fresh children per width, four measured warm sweeps per child. The first sweep is retained but excluded from timing summaries. Width order reverses by repeat.

| Fixture | Width | Full blend | Mapped copy residual | Full − copy |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 600 | 192.332 | 39.344 | 152.988 |
| real-mixed-120 | 1200 | 509.998 | 144.584 | 365.414 |
| image-heavy-100 | 600 | 359.739 | 59.352 | 300.387 |
| image-heavy-100 | 1200 | 1165.865 | 229.713 | 936.151 |

## Extra cost from 600 to 1200 px

| Fixture | Δ full | Δ copy residual | Δ removed-work proxy | Proxy / Δ full | Stride/padding time |
| --- | ---: | ---: | ---: | ---: | --- |
| real-mixed-120 | 317.666 | 105.240 | 212.426 | 66.87% | Unmeasured |
| image-heavy-100 | 806.126 | 170.362 | 635.764 | 78.87% | Unmeasured |

Paired repeat increments (mean warm 1200 minus mean warm 600), with all repeats retained:

| Fixture | Repeat | Δ full | Δ copy | Δ full − copy |
| --- | ---: | ---: | ---: | ---: |
| real-mixed-120 | 0 | 317.855 | 105.904 | 211.951 |
| real-mixed-120 | 1 | 313.454 | 105.069 | 208.385 |
| real-mixed-120 | 2 | 321.689 | 104.748 | 216.941 |
| image-heavy-100 | 0 | 786.174 | 172.067 | 614.106 |
| image-heavy-100 | 1 | 806.606 | 169.823 | 636.782 |
| image-heavy-100 | 2 | 825.598 | 169.194 | 656.404 |

Order check: each page appears equally often in both pair orders. Values sum per-page means for that order, in ms per document.

| Fixture | Width | Copy/full: full | Copy/full: copy | Full/copy: full | Full/copy: copy |
| --- | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 | 600 | 192.464 | 39.979 | 192.200 | 38.709 |
| real-mixed-120 | 1200 | 507.359 | 145.261 | 512.637 | 143.908 |
| image-heavy-100 | 600 | 363.961 | 59.989 | 355.517 | 58.714 |
| image-heavy-100 | 1200 | 1167.710 | 230.777 | 1164.019 | 228.649 |

## Interpretation and what stayed unmeasured

**Method 5 favors the work removed from sampling/compositing over the minimal-copy residual. A physical compute-versus-memory dominance claim remains unmeasured.** Removing interpolation, masks and blending also removes memory reads; this experiment cannot assign those saved reads to arithmetic. Full − copy is an upper-bound proxy for omitted computation only if removing those accesses does not increase memory cost and common mapping/control costs are comparable. Copy uses a different sampler, so no rigorous numeric bound on all production arithmetic is established. It is not a measured pure-compute duration.

The brief’s historical RGB increments, image-heavy **2233.8 ms** and mixed **461.9 ms**, come from #259’s earlier #257 DLL. They were not remeasured or proportionally redistributed. This experiment uses the later #258 base and a different cache-warming diagnostic. Their exact computation / traffic / stride partition remains **unmeasured**.

Also unmeasured: DRAM bandwidth and stall milliseconds; cache hit/miss rates; RFO/writeback traffic; independent interpolation, colour-conversion and alpha-blend costs; padding/row-pitch cache penalties; effects of tiling or streaming stores. Logical copy byte counts below are access counts, not DRAM-transfer counters. No PMU, cache flush, small-cache experiment or altered-stride intervention was run.

## Copy definition and output preservation

- A GNU linker shim wraps `exr_canvas_get_sink_ex` and replaces only its RGB image callback in the diagnostic DLL. Calls made while building graphics-state soft masks are excluded, matching #259’s top-level RGB sink scope. Native CMYK and direct paint callbacks are outside this experiment.
- Full executes the original callback with its original image, transform, alpha, clip, blend state and destination. Copy uses that same destination allocation, row stride, source allocation, transform bounds and clip; it maps each covered destination center to one nearest source pixel and copies its channels. Four-channel pixels use a four-byte copy; gray/RGB sources expand to RGBA. Copy omits interpolation, image masks, soft masks, destination reads, alpha and blend arithmetic. Destination-center coverage can differ from full’s supersampled edge coverage.
- Before each pair, the destination bytes are saved. Copy/full: copy, restore input, full. Full/copy: full, save output, restore input, copy, restore output. Allocation, byte snapshots, restoration, validation hashes and metric aggregation are outside both timed intervals. Copy never updates work accounting or auxiliary compositing state. The original full callback executes exactly once.
- Pair order alternates by page, sweep and repeat. Each page therefore runs in both orders across warm sweeps. QPC scopes aggregate per image invocation. Snapshot/restore touches destination cache lines, and the first arm may warm source/clip data for the second. Alternation reduces order bias but does not recover the untouched production cache state. These scopes must not be treated as production sweep timings.

## Geometry and logical bytes

Counts are per full warm sweep; source/destination allocations and padding are summed once per image callback, so reused images and targets are counted repeatedly. No claim is made that allocated padding was read or written.

| Fixture | Width | RGB calls | Copied pixels | Logical source-read + dest-write bytes | Dest row-padding bytes | Source row-padding bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| real-mixed-120 | 600 | 341 | 13544304 | 108354432 | 0 | 0 |
| real-mixed-120 | 1200 | 341 | 54110341 | 432882728 | 0 | 0 |
| image-heavy-100 | 600 | 418 | 21452508 | 171620064 | 0 | 0 |
| image-heavy-100 | 1200 | 418 | 85844402 | 686755216 | 0 | 0 |

## Validation and provenance

- 6,600 diagnostic page hashes match the original DLL’s control output at the same width, including every cold and warm diagnostic render. Zero skipped RGB callbacks. Each fresh child independently computes the control hashes.
- Every sweep passes the fail-closed ≤15% system-CPU gate; 60 accepted gates span 1.581–14.844%. Competing benchmark/compiler checks run before and after every sweep; failed sweeps remain partial files and are never analyzed.
- Unmodified Release objects are relinked with an `-O3 -Wall -Wextra -Werror` diagnostic shim; GCC 16.2.0, Windows, Intel(R) Core(TM) Ultra 7 256V. The 214 renderer/header files match the clean object-build worktree byte-for-byte.
- `analyze.py` checks page counts, pair order, hashes, skip counts, idle gates and raw-file hashes. `git diff --check` passes. No production tests were rerun: this change only adds evidence and its probe; output equivalence is checked against the original DLL.
- `verify.py` rehashes 12 raw children, six probe/harness source files and 139 measured binary/build input files. [Verification](verification.json). On a checkout without the local build inputs, use `verify.py --text-only`.
- Raw gzip hashes cover exact bytes; text hashes normalize CRLF to LF for Git portability. Build metadata byte hashes identify the measured Windows object files and DLLs.
- [Raw children](raw/) · [validated summary](summary.json) · [object/DLL hashes and compiler](build.json) · [source/CPU provenance](provenance.json) · [power/environment](environment.json).

## Next direction

Investigate the sampling/compositing path before implementing a bare destination-copy optimization. These measurements support that priority but do not select arithmetic optimization over reduced sampling traffic. A matched-access replay or PMU measurement would be needed to make that choice. Tiling, streaming stores and channel preconversion remain untested proposals.

## Reproduce

From this repository, using an existing clean MinGW/Ninja Release build at the recorded base commit:

```powershell
python evidence/rgb-sink-split-20261118/build.py C:/path/to/build/perf
python -X utf8 evidence/rgb-sink-split-20261118/capture.py run --base C:/path/to/build/perf/libexreader.dll
python evidence/rgb-sink-split-20261118/analyze.py
python evidence/rgb-sink-split-20261118/report.py
python evidence/rgb-sink-split-20261118/verify.py
```

The capture refuses to overwrite accepted raw files. Archive or move an earlier raw directory before a new run. Build and timing phases must run sequentially.
