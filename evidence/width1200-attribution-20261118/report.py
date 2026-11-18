# SPDX-License-Identifier: MIT
"""Assemble the report from the validated summary; no hand-entered timings."""
import json
from pathlib import Path
import tables

HERE = Path(__file__).resolve().parent


def main():
    d = json.loads((HERE / 'summary.json').read_text())
    assert d['validation']['accepted_children'] == 186
    archive = json.loads((HERE.parent / 'p95-then-throughput-20261118/results.json').read_text())
    rows = []
    for case in d['baseline']:
        a, b = [archive['cases'][f'{case}@{w}'] for w in (600, 1200)]
        x, y = a['exreader']['round_wall_ms_median'], b['exreader']['round_wall_ms_median']
        u, v = a['pdfjs']['round_wall_ms_median'], b['pdfjs']['round_wall_ms_median']
        rows.append([case, a['exreader']['page_count'], f'{x:.2f}', f'{y:.2f}', f'{y/x:.3f}×',
                     f'{u:.2f}', f'{v:.2f}', f'{v/u:.3f}×'])
    historical = tables.table(['Fixture', 'Pages on both sides/widths', 'EXReader 600 ms', 'EXReader 1200 ms',
                               'EXReader growth', 'PDF.js 600 ms', 'PDF.js 1200 ms', 'PDF.js growth'], rows)
    rows = []
    allocation = []
    for case, widths in d['telemetry'].items():
        a, b = widths['600']['warm'], widths['1200']['warm']
        delta = lambda k: b[k] - a[k]
        rows.append([case, f"{delta('ms'):.3f}", f"{delta('canvas_image_ms'):.3f}", f"{delta('mask_ms'):.3f}",
                     f"{delta('canvas_paint_ms'):.3f}", f"{delta('canvas_create_ms') + delta('other_ms'):.3f}"])
        allocation.append(f"{case}: allocator interval Δ **{delta('allocator_ms'):+.3f} ms**, decode Δ **{delta('decode_ms'):+.3f} ms**")
    increments = tables.table(['Fixture', 'Total extra ms', 'RGB image sink extra ms', 'Mask building extra ms',
                                'Source paint outside masks extra ms', 'Other incl. canvas creation extra ms'], rows)
    image = d['telemetry']['image-heavy-100']
    image_delta = image['1200']['warm']['canvas_image_ms'] - image['600']['warm']['canvas_image_ms']
    total_delta = image['1200']['warm']['ms'] - image['600']['warm']['ms']
    alloc = '\n'.join('- ' + s for s in allocation)
    v = d['validation']
    c600, c1200 = d['cache256']['600'], d['cache256']['1200']
    savings = lambda r: ' / '.join(f'{x:+.3f}' for x in r['paired_saving_samples_ms'])
    ratios = ', '.join(f"{case} **{widths['1200']['ms']/widths['600']['ms']:.3f}×**" for case, widths in d['baseline'].items())
    preface = f'''# Width-1200 throughput attribution — 2026-11-18

**The crossover is explained by EXReader's larger resolution-sensitive paint cost. It does not require a superlinear whole-document cliff.** The unchanged #257 DLL reproduced warm-sweep growth of {ratios}. In #257, PDF.js's corresponding growth was much smaller, as the archived table below shows. Winning at 600 px therefore does not rule out a costly pixel-processing algorithm: that cost can overtake the other renderer when the output area increases.

**Measured causes:** RGB image painting dominates image-heavy's extra time; mixed adds substantial image and gradient/soft-mask work; vector-heavy adds clipped-path work as well as the shared gradient slides. In the image-heavy instrumented sweeps, the RGB image sink accounts for **{image_delta:.3f} / {total_delta:.3f} ms ({100*image_delta/total_delta:.2f}%)** of the width increment. Measured allocation intervals do not show comparable growth. The decoded-image cache has exactly the same warm hit/miss/eviction counts at both widths.

**Unresolved physical split:** the paint intervals contain both computation and memory traffic. DRAM-bandwidth milliseconds, CPU-cache-miss cost, and their split from arithmetic were not measured. They are not assigned fabricated shares of the residual. [Available PMU sources](pmc-sources.txt) and [the current process token's privileges](token-privileges.txt) are retained; the token has no `SeSystemProfilePrivilege`. There are no hardware-counter samples in this evidence.

## Check the original crossover and denominator

This table is **archived #257 data**, not a fresh PDF.js comparison. [Exact archive](../p95-then-throughput-20261118/results.json) · [Original method](../p95-then-throughput-20261118/REPORT.md).

{historical}
Both sides rendered the same **120 / 100 / 100** pages at both widths. Throughput is `N × 1000 / median(sum of timed page-render ms in each warm sweep)`. The validation reconstructs that denominator from every saved per-page sample, checks page IDs and sample counts, and checks the reported pages/s. Open time, hashing and output-bitmap freeing are outside that sum. The throughput ratio convention in #257 is **PDF.js pages/s / EXReader pages/s**; above one means EXReader is slower.

The new original-DLL results below confirm the resolution response on the same renderer binary. They are not combined with archived PDF.js samples to claim a new same-session engine comparison.

## Where the extra time goes

These are differences of **mean instrumented warm sweeps**, over three fresh children × five warm sweeps each. They are separate from the original-DLL throughput medians.

{increments}
The RGB image sink, mask construction, source painting outside masks and canvas creation outside masks are separate scopes. The probe suppresses child paint/create buckets during a mask build; every telemetry page has at most one mask build. `other_ms` is the timed-render residual after those scopes, and contains path/glyph/clip work, interpretation, decoding and remaining setup/probe work. It is not a bandwidth estimate.

Allocator and decode timers overlap the scopes above and must **not** be added as extra rows of that partition:

{alloc}

Allocator intervals include the intercepted malloc/calloc/realloc/free calls and their timer/counter overhead. Counts cover link-visible calls from EXReader and linked static dependencies; CRT/DLL-internal calls are outside that scope. Output-bitmap freeing is outside the timed render and excluded from these metrics. The per-page table below gives the actual call counts and requested bytes.

## Decoded-image cache intervention

At 64 MiB, mixed records **341 hits / 0 misses / 0 evictions** per warm sweep at each width; vector records **20 / 0 / 0**. Image-heavy records **308 / 110 / 110** at **both** widths. Thus the measured 600→1200 increment is not accompanied by any extra decoded-image eviction events. This is distinct from CPU hardware-cache behavior, which was not measured.

For image-heavy, the existing byte-limit override was changed between **64 and 256 MiB**, with 64/256, 256/64, 64/256 process order at each width. The width-pair order also reverses on the middle repeat. The 128-entry limit stays unchanged. At 256 MiB the sequential warm traces have **{c600['warm_trace']['hits']:.0f} hits / {c600['warm_trace']['misses']:.0f} misses / {c600['warm_trace']['evictions']:.0f} evictions** at 600 and **{c1200['warm_trace']['hits']:.0f} / {c1200['warm_trace']['misses']:.0f} / {c1200['warm_trace']['evictions']:.0f}** at 1200. The resident decoded set is **{c600['warm_trace']['image_cache_bytes']/1024**2:.3f} MiB** at 600 and **{c1200['warm_trace']['image_cache_bytes']/1024**2:.3f} MiB** at 1200. Decoded textures are loaded in source resolution, before the placement transform in [image_event](../../src/pdf_paint.c); output width does not quadruple their cached bytes.

Observed paired warm-sweep savings are **{c600['paired_saving_ms']:.3f} ms at 600** and **{c1200['paired_saving_ms']:.3f} ms at 1200**. The three signed pair differences are **{savings(c600)} ms** and **{savings(c1200)} ms**, respectively. Median paired differences need not equal the difference of separately reported medians. The larger cache removes scan re-decode at both widths, while the measured 256 MiB native sweep still grows **{c1200['ms']/c600['ms']:.3f}×** with width. Cache capacity is an independent image-heavy cost; the counters do not support a resolution-triggered image-cache eviction cliff. Peak RSS for this intervention is included in its table.

## Memory interpretation and the 4× criterion

The RSS table decomposes Windows peak-working-set growth arithmetically into process start, opening, the cold-sweep peak, and any later warm peak. It uses means of three original-DLL processes so the components sum to the mean final peak. It does not relabel all working-set growth as live bitmap bytes.

The measured maximum retained PDF scratch-pool payload is **{image['600']['warm']['pdf_pool_bytes']/1024**2:.3f} → {image['1200']['warm']['pdf_pool_bytes']/1024**2:.3f} MiB**; the fixed-render pool is **{image['600']['warm']['fixed_pool_bytes']/1024**2:.3f} → {image['1200']['warm']['fixed_pool_bytes']/1024**2:.3f} MiB**. These observed page-boundary maxima are the same across the three fixtures. Their individual limits are 64 MiB, and neither observed retained maximum reaches its limit. They are separate from the decoded-image cache, whose byte occupancy is width-independent here. Pool maxima need not coincide with a Windows RSS peak and are not additive RSS components.

Full sweeps grow below 4×. Image-sink intervals grow below 4×; direct gradient/mask intervals are close to 4× and sometimes slightly above it. Canvas creation grows more than 4× but contributes only the small absolute increment shown in the timer tables. A ratio slightly over four, or a ratio of two noisy ablation differences, does not establish a cache-threshold mechanism. The nominal 4× comparison also differs slightly from the exact output-pixel ratio because bitmap heights are rounded; the active-pixel counts are reported below.

Class ablations are interventions, not additive standalone class CPU times. Each saving is the median of three within-repeat differences: full-child median warm sweep minus disabled-child median warm sweep. It need not equal the difference between the two displayed median-time columns. Their tables retain these signed differences. Negative group deltas are observed intervention results. Bypassing boundaries retains children but changes the conditions under which they are composited; these deltas are not pure group overhead. Small or negative path/glyph effects in some fixtures should be read with their three raw paired deltas in [summary.json](summary.json), rather than turned into a fixed/linear classification from the median ratio alone.

## Recommendations, not implemented

1. Profile sampling versus blending in `exr_vector_texture_blend` for image-heavy and mixed; separate coverage generation from blending in the clipped-path rasterizer for the vector cohort. The native cohort table and image/path ablations identify these independently of image-cache misses.
2. Profile the gradient/soft-mask pixel loops next. Their measured resolution scaling is near area scaling. The next experiment should distinguish arithmetic from memory stalls with hardware counters before choosing a bandwidth-specific rewrite. Canvas initialization is a smaller measured target.
3. Treat a larger or scan-aware decoded-image cache as a separate image-heavy tradeoff. The paired capacity trial measures its benefit and memory cost; it does not remove the resolution-sensitive paint work. The current traces do not justify an allocator-focused rewrite as the cause of this width crossover.

## Capture and validation

- Source snapshot: `d234e41a46b3f8986daef55d3c112d32325558eb` (#257 merge). Original DLL SHA-256: `2640521cb124a7533c808429391a93bfa8d4db75443f79cd92f765c158f2c5ee`, exactly #257's DLL. The existing Release MinGW `-O3 -DNDEBUG` objects were reused; all **214** source/header files matched this worktree. [Build cache](CMakeCache.txt) · [Provenance](provenance.json).
- No `src/`, `include/`, CMake or existing benchmark-tool edits. [probe.c](probe.c) relinks the existing objects with GNU linker wrapping, reusing [#252's probe](../p95-tail-20261118/probe.c). Its constructor honors `EXR_ATTRIBUTION_SKIP=path|glyph|image|shading|group`.
- [capture.py](capture.py) calls unchanged `bench_real_doc.run_child_gated` for full-document throughput and unchanged `bench_firstscreen.run_child` for fresh first-page controls. It reuses #252's document bindings for sequential telemetry. Each capture is a fresh process. Throughput and telemetry captures have one cold full sweep plus five warm full sweeps, three repeats. First-page controls open once and render page 1 once. The initial probe sanity capture uses one warm sweep. Class order rotates; width orders are **600/1200, 1200/600, 600/1200**.
- Path ablation preserves clips; glyph ablation preserves text clipping; image ablation skips before decode; shading ablation bypasses dispatch including graphics-state-mask shading; group ablation bypasses sink layer/group boundaries while retaining children and rasterizer root setup.
- Every accepted child passed the fail-closed **≤15%** pre-child system-CPU gate plus competing-benchmark checks before and after capture. **{v['accepted_children']} accepted children**, gate range **{v['min_cpu']:.2f}–{v['max_cpu']:.2f}%**. All repeats, including wide timing outliers, remain in the accepted data.
- Two initial mixed baseline samples taken before the competing-process check was added were excluded. A new external benchmark appeared during the last 256 MiB trace; its post-child check rejected that sample, and the preceding 600 px partner was withdrawn so the pair could be repeated together. [Excluded records](excluded-overlap/) · [Wait/process log](competition.jsonl). Excluded samples do not contribute to any table.
- [analyze.py](analyze.py) verifies counts, alternating width order, cache A/B order, throughput denominators and pixel hashes. It performed **{v['matching_page_hash_checks']:,} matching page-hash comparisons** across original/full-probe/telemetry/cache/first-page controls. The six full-render fixture/width cells cover **640 distinct page/width combinations**. Class-disabled output is intentionally different. [Validated summary](summary.json).

## Reproduce

Use a matching configured MinGW Release build, target `exreader`. To avoid resuming the saved captures, copy `capture.py`, `probe.c`, `run_all.py`, `analyze.py`, `tables.py`, and `report.py` into a **new directory directly under `evidence/`**. Then run, substituting that directory for `evidence/width1200-retest`:

```powershell
python -X utf8 evidence/width1200-retest/capture.py build --build build/perf
python -X utf8 evidence/width1200-retest/run_all.py --library build/perf/libexreader.dll
python -X utf8 evidence/width1200-retest/analyze.py
python -X utf8 evidence/width1200-retest/report.py
```

The capture runner checkpoints accepted children and fails closed on CPU timeout or a competing workload. Run it again to resume only unaccepted samples. If interference splits a width pair, withdraw its accepted partner and repeat both members together, as done here. Raw child files, indices and their hashes are retained alongside the summary; compressed JSON can be loaded by `analyze.py`.

'''
    tables.main()
    generated = (HERE / 'TABLES.md').read_text()
    (HERE / 'REPORT.md').write_text(preface + generated, encoding='utf-8')
    print(HERE / 'REPORT.md')


if __name__ == '__main__':
    main()
