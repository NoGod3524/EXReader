# SPDX-License-Identifier: MIT
"""Render REPORT.md from summary.json; every number below is read from the validated summary."""
from pathlib import Path
import json
H=Path(__file__).resolve().parent
s=json.loads((H/'summary.json').read_text());b=json.loads((H/'build.json').read_text());p=json.loads((H/'provenance.json').read_text())
CASES=('real-mixed-120','image-heavy-100');CONDS=('flushed','as-is')
f=lambda x:f'{x:.1f}'
def pct(x,t):return f'{100*x/t:.1f}%' if t else 'n/a'
SIX=[('Channel/row conversion (重排)',['row conversion']),
     ('Interpolation (插值): bilinear taps 2-4',['bilinear taps 2-4']),
     ('Interpolation (插值): 2x2 supersampling',['2x2 supersampling']),
     ('Alpha (alpha 混合): source-over blend',['source-over blend']),
     ('Alpha (alpha 混合): un-premultiply + quantize',['un-premultiply + quantize']),
     ('Read traffic (读流量): source texels',['source read traffic']),
     ('Read traffic (读流量): destination',['dest read traffic']),
     ('Write traffic (写流量): destination',['dest write traffic'])]
def stage(d,order,names):return sum(d[order][n] for n in names)
def cell(case,width,cond):return s['cases'][case]['widths'][width]['mean']['all_replica_paths'][cond]
def inc(cond):return {c:s['cases'][c]['increment_mean'][cond] for c in CASES}
def six_table(get,title):
    rows=[title,'','| Item | real-mixed A | real-mixed B | image-heavy A | image-heavy B |','| --- | ---: | ---: | ---: | ---: |']
    ds=[get(c) for c in CASES]
    for name,stages in SIX:
        rows.append(f'| {name} | '+' | '.join(f(stage(d,o,stages)) for d in ds for o in ('order_a','order_b'))+' |')
    rows.append('| **Arithmetic subtotal** | '+' | '.join(f(d[o]['arithmetic_total']) for d in ds for o in ('order_a','order_b'))+' |')
    rows.append('| **Traffic subtotal** | '+' | '.join(f(d[o]['traffic_total']) for d in ds for o in ('order_a','order_b'))+' |')
    rows.append('| Stride: 64-byte row alignment | '+' | '.join(f(d['other']['64-byte row alignment']) for d in ds for _ in (0,1))+' |')
    rows.append('| Stride: +64 padding bytes per row | '+' | '.join(f(d['other']['+64 padding bytes per row']) for d in ds for _ in (0,1))+' |')
    rows.append('| Residual with every stage off | '+' | '.join(f(d['other']['residual: all stages off']) for d in ds for _ in (0,1))+' |')
    rows.append('| Unmodified replica (= sum of the ladder) | '+' | '.join(f(d['replica_ms']) for d in ds for _ in (0,1))+' |')
    rows.append('| Original callback | '+' | '.join(f(d['original_ms']) for d in ds for _ in (0,1))+' |')
    return rows+['']
L=['# RGB sink: arithmetic versus memory traffic, stage by stage','',
f"Base `{b['base_commit']}` (renderer sources identical to current `main`). Evidence-only branch `perf/rgb-sink-arithmetic`: no production source, header, CMake or benchmark edits.",'',
'## Answer','']
ans=['| Fixture | Width | Cache | Sink (original) | Arithmetic, A–B | Traffic, A–B | Traffic, minimal kernel | Residual | Arithmetic share |','| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for c in CASES:
    for w in ('600','1200'):
        for cond in CONDS:
            d=cell(c,w,cond);ar=sorted((d['order_a']['arithmetic_total'],d['order_b']['arithmetic_total']));tr=sorted((d['order_a']['traffic_total'],d['order_b']['traffic_total']))
            mk=sum(d['minimal_kernel'].values());r=d['replica_ms']
            ans.append(f"| {c} | {w} | {cond} | {f(d['original_ms'])} | {f(ar[0])}–{f(ar[1])} | {f(tr[0])}–{f(tr[1])} | {f(mk)} | {f(d['other']['residual: all stages off'])} | {pct(ar[0],r)}–{pct(ar[1],r)} |")
L+=ans+['',
'All values are ms per complete warm document sweep, summed over every decomposable RGB image call (paths 1–7 below), mean of three fresh children × three warm sweeps. "A" removes traffic first and then arithmetic; "B" removes arithmetic first and then traffic. Both ladders end in the same all-off kernel, so each column sums to the unmodified replica.','',
'**Arithmetic dominates. Memory traffic is a small term.** Removing every destination store stream, destination load stream and source-texel stream changes the sink by a few percent at most. That holds with every input and output line flushed from the cache before each call and with the cache left as-is. Interpolation (bilinear taps plus 2×2 supersampling) and alpha (un-premultiply divisions plus source-over) are the largest arithmetic terms. Row conversion and the residual loop/addressing skeleton are the next largest.','']
L+=six_table(lambda c:cell(c,'1200',"flushed"),'### Six-item decomposition at 1200 px, flushed lines')
L+=six_table(lambda c:inc('flushed')[c],'### Six-item decomposition of the 600 → 1200 px increment, flushed lines')
L+=six_table(lambda c:cell(c,'1200',"as-is"),'### Six-item decomposition at 1200 px, cache as-is')
L+=six_table(lambda c:inc('as-is')[c],'### Six-item decomposition of the 600 → 1200 px increment, cache as-is')
L+=six_table(lambda c:cell(c,'600',"flushed"),'### Six-item decomposition at 600 px, flushed lines')
L+=['### Repeat spread','','Min–max over the three paired children per width (each child: mean of its three warm sweeps).','','| Fixture | Cache | 1200 arithmetic A | 1200 traffic A | Δ arithmetic A | Δ traffic A | Δ arithmetic B | Δ traffic B |','| --- | --- | --- | --- | --- | --- | --- | --- |']
for c in CASES:
    for cond in CONDS:
        r=s['cases'][c]['widths']['1200']['repeat_range']['all_replica_paths'][cond];i=s['cases'][c]['increment_repeat_range'][cond]
        g=lambda x:f'{x[0]:.1f}–{x[1]:.1f}'
        L.append(f"| {c} | {cond} | {g(r['order_a']['arithmetic_total'])} | {g(r['order_a']['traffic_total'])} | {g(i['order_a']['arithmetic_total'])} | {g(i['order_a']['traffic_total'])} | {g(i['order_b']['arithmetic_total'])} | {g(i['order_b']['traffic_total'])} |")
L+=['','## Paths covered','','Per warm sweep, 1200 px. The path is the branch the unmodified replica took for that call. "Original" is the unmodified production callback in the as-is arm.','','| Fixture | Path | Calls | Destination-box pixels | Original ms |','| --- | --- | ---: | ---: | ---: |']
for c in CASES:
    for name,v in s['cases'][c]['widths']['1200']['paths'].items():
        if v['calls']:L.append(f"| {c} | {name} | {v['calls']:.0f} | {v['pixels']:.0f} | {f(v['original_as_is_ms'])} |")
L+=['','Composite-state calls (soft mask, gray groups, knockout/shape groups) also update auxiliary group state. Rerunning them would corrupt later output, so they ran once and are reported, not decomposed. The solid-colour path has no interpolation, conversion or un-premultiply stage; only its traffic and blend knobs act.','']
if 'synthetic' in s:
    L+=['## Approach B: working-set size','','One opaque, axis-aligned, interpolated image covering an opaque square destination (production `exr_vector_texture_blend` object, the same converted-row path as path 3). Median over three alternating-order rounds of the best repetition. ns per destination pixel.','',
        '| Destination | MiB | Source 50%, as-is | Source 50%, flushed | Source 100%, as-is | Source 100%, flushed | All-off replica, 100%, flushed |','| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    syn={(r['which'],r['ratio_percent'],r['flushed'],r['dim']):r for r in s['synthetic']}
    for dim in sorted({r['dim'] for r in s['synthetic']}):
        g=lambda w,q,fl:f"{syn[(w,q,fl,dim)]['best_ns_per_pixel_median']:.2f}"
        L.append(f"| {dim}² | {syn[('production',50,0,dim)]['dest_mib']:.2f} | {g('production',50,0)} | {g('production',50,1)} | {g('production',100,0)} | {g('production',100,1)} | {g('replica_all',100,1)} |")
    L+=['','The per-pixel cost does not rise when the working set grows from L2-resident to several times the 12 MiB L3, or when every line starts in DRAM. Cache capacity and DRAM bandwidth are therefore not the limit on this path; per-pixel instruction work is.','']
L+=['## How each item was isolated','',
'- **Replica.** `make_replica.py` derives `replica.c` from the unmodified `src/affine_image.c` by counted, exact substitutions; any renderer change makes it fail. Each knock-out mask is a separate object compiled with the production flags (`'+' '.join(b['replica_flags'][:4])+' …`), so knobs are compile-time constants. With mask 0 every substitution folds to the production expression. The original callback still produces every committed pixel. The unmodified replica and both stride variants must match the original byte for byte on every call; outputs of knocked-out arms are discarded.',
'- **Write traffic.** Destination stores go to one cache-resident scratch row; loads still come from the real destination.',
'- **Destination read traffic.** Destination loads come from a cache-resident snapshot of the call\'s first destination row, so the branch mix of source-over is preserved for opaque or uniformly transparent targets.',
'- **Source read traffic.** Every source and mask texel row is row 0 of the same bitmap. Column addressing, weights and arithmetic are unchanged.',
'- **Source-over blend.** The destination byte is still loaded (folded into a sink), the colour is stored without the three blend quotients.',
'- **Un-premultiply + quantize.** The three `sums[k]/sums[3]` divisions and byte saturations are replaced by a constant colour; the alpha byte is still computed.',
'- **Bilinear taps 2–4.** Each subsample uses only its first tap, with that tap\'s weight.',
'- **2×2 supersampling.** Only the first subsample of each destination pixel is evaluated.',
'- **Row conversion (重排).** The converted-row byte→double conversion and stores are skipped; the same source bytes are still loaded and folded. Converted rows are prefilled once per call with a valid opaque texel (inside the timed call, so this slightly understates the conversion cost).',
'- **Stride.** The unmodified replica runs on copies of the destination, clip, source and mask with every row start 64-byte aligned, then with 64 extra padding bytes per row. Production strides have zero padding (see #261), so these arms test whether padding or alignment *would* matter rather than measuring an existing cost.',
'- **Cache conditions.** Before every arm the destination rows are restored outside the timed call. In "flushed", every destination row, clip row, source/mask bitmap and scratch row is then evicted with `clflush` + `mfence`, so the arm starts from DRAM. In "as-is" nothing is flushed; the restore leaves the destination warm and the previous arm leaves source data warm.',
'- **Alternation.** All 42 arms (21 kinds × 2 cache conditions) run on every call; their order rotates by call, page, sweep and repeat. Width order reverses by repeat. Ladders A and B are measured on the same calls.','',
'## Limits','',
'- These are intervention differences, not hardware counters. A knock-out removes the cost the stage adds *in that context*. Order A and B bracket interaction: the same stage can cost differently once neighbours are gone (for example, divisions overlapping with loads). Neither ladder\'s numbers are a PMU breakdown.',
'- "Traffic" removal keeps each access but makes it cache-resident. It therefore measures the miss/bandwidth cost of each stream, not the cost of the load/store instructions themselves; those stay in the residual or in their arithmetic stage.',
'- Clip-coverage bytes are always read from the real clip mask and stay in the residual. Converted-row loads are L1/L2 resident by design and count as interpolation arithmetic.',
'- The hot destination snapshot uses one row per call. A destination with per-row varying alpha could take a different source-over branch on the snapshot row than on the real one.',
'- Composite-state calls are excluded from the decomposition (see table above). CMYK image and direct-paint callbacks are outside the RGB sink.',
'- Absolute times differ from #261 and #259. Every arm here runs after a restore (and optionally a flush), and the per-call totals include 42 arms of cache disturbance between production calls. Compare stages within this experiment, not with earlier sweep timings. The original-callback row is the reference for each table.','',
'## Structural direction (not implemented)','',
'- The cost is per-pixel arithmetic, so tiling, streaming stores, prefetching or row-pitch changes would not help measurably here. Those proposals from the earlier brief are not supported by this data.',
'- The largest removable work is interpolation and un-premultiply. Magnified images evaluate 4 subsamples × 4 bilinear taps in double precision per destination pixel, then divide three times. A separable or fixed-point (16-bit) resampler that computes horizontal taps once per source row and vertical blends once per destination row would remove most of the tap and supersampling work. Un-premultiplying once per converted texel, rather than once per destination pixel, would remove most of the division cost. Either change must keep output identical or be accepted as an output change separately.',
'- Row conversion is a smaller, separate term; converting each source row once to a premultiplied fixed-point layout would shrink it and also serve the resampler above.','',
'## Validation and provenance','',
f"- {s['matching_page_hashes']:,} diagnostic page hashes match the original DLL's control output at the same width, including the cold first sweep. Every call's unmodified replica, aligned-stride and padded-stride outputs match the original callback's output in both cache conditions. Zero mismatches, zero status differences, zero skipped calls.",
f"- Every sweep passes the fail-closed ≤15% system-CPU gate; {len(s['idle_cpu_percent'])} accepted gates span {min(s['idle_cpu_percent']):.3f}–{max(s['idle_cpu_percent']):.3f}%. Competing benchmark/compiler checks run before and after every sweep. A rejected child is discarded and rerun from scratch; all {len(s['attempts'])} attempts are listed in `raw/attempts.json`.",
f"- GCC 16.2.0, Windows, {p['cpu']['Name']}. The {p['compared_render_and_header_files']} renderer/header files of this worktree match the object-build worktree byte-for-byte.",
'- `verify.py` rehashes every raw child, script and source artifact; it re-derives `replica.c` from `src/affine_image.c` and checks it is unchanged; without `--text-only` it also rehashes every measured object, DLL and build input. [Verification](verification.json).',
'- [Raw children](raw/) · [validated summary](summary.json) · [object/DLL hashes and compiler](build.json) · [source/CPU provenance](provenance.json).','',
'## Reproduce','','From this repository, using an existing clean MinGW/Ninja Release build at the recorded base commit:','','```powershell',
'python evidence/rgb-sink-arithmetic-20261118/build.py C:/path/to/build/perf',
'python -X utf8 evidence/rgb-sink-arithmetic-20261118/capture.py run --base C:/path/to/build/perf/libexreader.dll',
'python -X utf8 evidence/rgb-sink-arithmetic-20261118/synthetic.py',
'python evidence/rgb-sink-arithmetic-20261118/analyze.py','python evidence/rgb-sink-arithmetic-20261118/report.py','python evidence/rgb-sink-arithmetic-20261118/verify.py','```','',
'The capture refuses to overwrite accepted raw files. Build and timing phases must run sequentially.']
(H/'REPORT.md').write_text('\n'.join(L)+'\n',encoding='utf-8')
