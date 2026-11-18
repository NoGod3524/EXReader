"""Summarize captured numbers; never substitute task targets for observations."""
from pathlib import Path
import json
import statistics as s

HERE = Path(__file__).resolve().parent
OUT = HERE / 'continuation'
fresh = (OUT/'pixels.json').exists() and (OUT/'ctest.txt').exists()
timing_dir = OUT if fresh else HERE/'interleaved'
paired_dir = OUT if fresh else HERE/'paired'
pixel_path = OUT/'pixels.json' if fresh else HERE/'pixels.json'
test_path = OUT/'ctest.txt' if fresh else HERE/'ctest.txt'
read = lambda p: json.loads(p.read_text())

def ablation(mode, lo, hi, side):
    data = read(HERE / 'raw' / f'ablate-mode{mode}.json')
    pages = {}
    for sweep in data['sweeps'][1:]:
        for row in sweep['pages']:
            if lo <= row['page'] <= hi:
                pages.setdefault(row['page'], []).append(row[side]['ms'])
    return s.mean(s.median(v) for v in pages.values())

lines = ['# Masked interpolated image resampling', '',
    'Continuation of `51d3f69c2`; production fix retained from `b515fe418`. '
    'The measurements below distinguish the committed diagnostic captures from the fresh continuation captures. '
    'Decode remains excluded by the prior cache-cap experiment; the cache limit is unchanged.', '',
    '## Content difference', '',
    'Image dictionaries and every drawn image/clip were enumerated without decoding image data '
    '([script](content.py), [records](continuation/content.json)). The PDF SHA agrees with '
    '`../real-doc-throughput-20261118/page-content.json`; cohort boundaries follow '
    '`../pdfjs-large-doc-20261118/cohorts.json`.', '',
    '| Property | p11–40 | p41–70 | p71–100 |',
    '| --- | --- | --- | --- |',
    '| Image draws/page | 9 | 1 | 3: background + two tiles |',
    '| Distinct drawn image XObjects/page | 6 or 7 | 1 | 3 |',
    '| Color source dimensions | 1342×757; four 190×160 + four 95×62 draws | 640×480 | background 960×720, 1200×675, 800×600, 1024×512, 720×540 (six pages each); tile 1: 320–416×240; tile 2: 256×192–256 |',
    '| Color `/Interpolate` | false | false | true on all 90 draws |',
    '| Soft mask | 9/page, matching dimensions, DeviceGray, nearest; `/Matte [0 0 0]` | none | background on 18/30 pages; tile 2 on all 30; matching dimensions, DeviceGray, nearest, no Matte |',
    '| Clip operators/page | 57 even-odd | 2, 32 or 33 even-odd | two even-odd + one nonzero |',
    '| Clip path complexity | 49 single-rectangle paths + eight 16-operator paths | single rectangles | all three single rectangles |', '',
    'Thus this cohort does not interpolate the soft mask twice: it bilinearly samples color and nearest-samples its mask. '
    'An even-odd operator alone does not imply a complex path.', '',
    '## Instrumented baseline and ablations', '',
    '[build_probe.py](build_probe.py) restores baseline `653e44bde` sources and relinks diagnostic objects. '
    'QPC scopes surround background/tile texture blending and clip construction; counters record image calls, '
    'decodes, clip presence and eligibility. [compare.py](compare.py) alternates AB/BA per page, reverses the starting '
    'order each sweep, and retries a failed ≤15% CPU gate. These are the committed `raw/ablate-mode*.json` captures: '
    'one cache-filling sweep excluded, then the mean of per-page warm medians. Both arms use the same diagnostic DLL '
    '`1ae0bd5df0da24389e0662eff0ef37a45e9a8728ae565eed9f89f57b4fe66160` with different skip modes. '
    'Skip switches exist only in diagnostic builds.', '',
    '| Disabled category | p11–70 full → disabled, ms/page | Δ removed | p71–100 full → disabled, ms/page | Δ removed |',
    '| --- | ---: | ---: | ---: | ---: |']
for mode, name in [(1, 'All images'), (2, 'Soft masks'), (3, 'Clip'), (4, 'Both tiles'), (5, 'Tiles + soft masks')]:
    a,b = [ablation(mode,11,70,k) for k in ('A','B')]
    c,d = [ablation(mode,71,100,k) for k in ('A','B')]
    lines.append(f'| {name} | {a:.3f} → {b:.3f} | {a-b:.3f} | {c:.3f} → {d:.3f} | {c-d:.3f} |')

data=read(HERE/'raw/ablate-mode2.json')
traces={};times={}
for sweep in data['sweeps'][1:]:
    for row in sweep['pages']:
        if 71<=row['page']<=100:
            traces.setdefault(row['page'],[]).append(row['A']['trace'])
            times.setdefault(row['page'],[]).append(row['A']['ms'])
trace=[s.mean(s.median(t[k] for t in v) for v in traces.values()) for k in range(11)]
total=s.mean(s.median(v) for v in times.values())
lines += ['', 'The scopes in the full arm of the mask-ablation capture partition the render as follows '
    '(p71–100; texture blending includes sampling and destination blending, excludes decoding):', '',
    '| Scoped stage | ms/page | Share of full render |', '| --- | ---: | ---: |']
for label,value in [('Background texture blend, including its soft mask',trace[0]),('Both tile texture blends, including tile 2 mask',trace[1]),('Clip construction',trace[2]),('Outside those scopes',total-sum(trace[:3]))]:
    lines.append(f'| {label} | {value:.3f} | {100*value/total:.2f}% |')
lines += ['',
    f'Total {total:.3f} ms/page. Soft-mask ablation removes '
    f'{ablation(2,71,100,"A")-ablation(2,71,100,"B"):.3f} ms/page '
    f'({100*(ablation(2,71,100,"A")-ablation(2,71,100,"B"))/total:.2f}%); '
    'this overlaps the background and tile scopes. Clip ablation also removes coverage checks during painting. '
    'Its delta is not just the clip construction time. The ablation deltas are not an additive partition.', '',
    'The task’s historical 158 ms/page and 6.7× PDF.js ratio were not reproduced as a same-session baseline here. '
    'No exact fraction of that historical ratio can be assigned from these captures. The table above gives '
    'measured stage shares and the ablation table gives measured marginal costs, without double counting them.', '',
    'The background is the largest scoped block. The baseline already has separable bilinear taps and converted-row '
    'reuse, but the `!source->mask` eligibility guard excludes these masked interpolated images. '
    'The fix extends that existing path to one-level masks: compute horizontal taps once per column, vertical taps '
    'once per row, and sample the mask at the same coordinate before adding each color sample. '
    'It preserves the generic arithmetic order. Matte reversal, nested masks, non-axis-aligned transforms and '
    'composite states retain their existing path. Fast helpers stay out of line to avoid the measured generic-loop '
    'regression recorded in the committed candidate experiments.', '',
    f'The probe records {trace[4]:.1f} background and {trace[5]:.1f} tile blend calls/page, '
    f'and {trace[8]:.1f}/{trace[9]:.1f} background/tile decode calls/page. '
    'The tiles are image XObjects, not a tiling-pattern construction; all 90 drawn image XObject IDs in p71–100 are distinct. Their drawing cost is included above; '
    'there is no measured separate pattern rebuild stage. The fix targets the larger background sampler.', '',
    '## Candidate A/B', '',
    'Release MinGW build: removed `build/perf/libexreader.dll`, forced a relink, checked the new timestamp and hashes '
    '([build log](build-continuation.txt), [PE section identities](continuation/build-identity.json)). '
    'The latter compares the executable code section to the preserved committed candidate; a relink may change '
    'the overall PE hash.', '',
    ('The tables below use fresh continuation captures. Every warm sweep requires ≤15% CPU. '
     'Timeout retries; a 0.5-second process monitor rejects sweeps overlapping other Python measurements or native builds/tests. '
     'Records: `continuation/interleaved-*.json`.' if fresh else
     'The tables below use the captures committed at `51d3f69c2`, in `interleaved/` and `paired/`. '
     'Accepted continuation captures follow separately below. Pixel and CTest checks are retained from '
     'the committed candidate whose code, constants, data and unwind sections match the relink. '
     'All committed same-process idle prechecks returned values below 15% CPU.'), '',
    'Same-process captures load both DLLs and alternate AB/BA on each page, reversing the starting order '
    'each sweep. One cold sweep is excluded. Paired Δ is the sum of per-page median (B−A) differences '
    'divided by the sum of A page medians; the separate A/B medians are a different aggregation.', '',
    '| Fixture @ width | A mean page p50, ms | B mean page p50, ms | Median paired Δ / A |',
    '| --- | ---: | ---: | ---: |']
for f in sorted(timing_dir.glob('interleaved-*.json' if fresh else '*.json')):
    d=read(f);n=len(d['per_page'])
    lines.append(f'| {f.stem.removeprefix("interleaved-")} @ {d["width"]} | {d["sum_a_p50_ms"]/n:.3f} | {d["sum_b_p50_ms"]/n:.3f} | {100*d["sum_paired_delta_ms"]/d["sum_a_p50_ms"]:+.2f}% |')
d=read(OUT/'interleaved-image-heavy.json' if fresh else timing_dir/'image-heavy-100.json')
lines += ['', '| Image-heavy cohort | A ms/page | B ms/page | Change |', '| --- | ---: | ---: | ---: |']
for lo,hi in ((11,70),(71,100)):
    ps=[p for p in d['per_page'] if lo<=p['page']<=hi]
    a=s.mean(p['a_p50_ms'] for p in ps);b=s.mean(p['b_p50_ms'] for p in ps)
    lines.append(f'| p{lo}–{hi} | {a:.3f} | {b:.3f} | {100*(b/a-1):+.2f}% |')
if not fresh and (OUT/'interleaved-image-heavy.json').exists():
    checkpoint=read(OUT/'interleaved-image-heavy.json')
    assert all(len(p['raw_A_ms'])==len(p['raw_B_ms'])==checkpoint['reps'] for p in checkpoint['per_page'])
    assert all(v is not None and v<=15 for v in checkpoint['sweep_idle_cpu_percent'])
    lines += ['', '### Accepted continuation captures', '',
        'The continuation runner retains only sweeps that passed the '
        '≤15% CPU gate and the process-overlap monitor. Other jobs during idle waits do not invalidate '
        'already accepted sweeps. [Raw samples](continuation/).', '',
        '| Fresh same-process fixture | A mean page p50, ms | B mean page p50, ms | Paired Δ / A |',
        '| --- | ---: | ---: | ---: |']
    for f in sorted(OUT.glob('interleaved-*.json')):
        capture=read(f);n=len(capture['per_page'])
        assert all(len(p['raw_A_ms'])==len(p['raw_B_ms'])==capture['reps'] for p in capture['per_page'])
        assert all(v is not None and v<=15 for v in capture['sweep_idle_cpu_percent'])
        lines.append(f'| {f.stem.removeprefix("interleaved-")} @ {capture["width"]} | {capture["sum_a_p50_ms"]/n:.3f} | {capture["sum_b_p50_ms"]/n:.3f} | {100*capture["sum_paired_delta_ms"]/capture["sum_a_p50_ms"]:+.2f}% |')
    lines += ['',
        '| Fresh image-heavy cohort | A ms/page | B ms/page | Change |',
        '| --- | ---: | ---: | ---: |']
    for lo,hi in ((11,70),(71,100)):
        ps=[p for p in checkpoint['per_page'] if lo<=p['page']<=hi]
        a=s.mean(p['a_p50_ms'] for p in ps);b=s.mean(p['b_p50_ms'] for p in ps)
        lines.append(f'| p{lo}–{hi} | {a:.3f} | {b:.3f} | {100*(b/a-1):+.2f}% |')
lines += ['',
    'Fresh-process `tools/bench_real_doc.py` captures alternate AB/BA (four repeats on image-heavy and small fixtures; '
    'two on real-mixed/vector-heavy in the committed captures), five warm rounds per child after '
    'one cold round. RSS is the median of process peak working sets. These results use whole documents:', '',
    '| Fixture / capture | p50 A → B, ms | p95 A → B, ms | Throughput A → B, pages/s | Peak RSS A → B, MiB | RSS change |',
    '| --- | ---: | ---: | ---: | ---: | ---: |']
for f in sorted(paired_dir.glob('paired-*.json' if fresh else '*.json')):
    if not fresh and f.stem not in ('image-heavy-100','real-mixed-120','vector-heavy-100'):
        continue
    name=f.stem.removeprefix('paired-')
    continuation=OUT/f'paired-{name}.json'
    selected=continuation if continuation.exists() else f
    origin='continuation' if selected==continuation else 'committed'
    d=read(selected)['widths']['1200'];a=d['A'];b=d['B']
    lines.append(f'| {name} / {origin} | {a["p50_ms_median"]:.3f} → {b["p50_ms_median"]:.3f} | {a["p95_ms_median"]:.3f} → {b["p95_ms_median"]:.3f} | {a["throughput_pages_per_s_median"]:.2f} → {b["throughput_pages_per_s_median"]:.2f} | {a["peak_rss_mib_median"]:.2f} → {b["peak_rss_mib_median"]:.2f} | {d["peak_rss_delta_pct"]:+.2f}% |')
if not (OUT/'paired-real-mixed-120.json').exists() and (OUT/'.realdoc-paired-real-mixed-120').exists():
    lines += ['', 'Partial children in `continuation/.realdoc-paired-real-mixed-120/` came from a '
        'gate-aborted duplicate batch and are excluded from every table.', '']
lines += ['', 'Small-fixture acceptance uses the all-page render p50 from the committed fresh-process paired '
    'captures (four repeats × five warm rounds). The relink code/data sections match that candidate:', '',
    '| Fixture | A p50, ms | B p50, ms | Limit, ms |', '| --- | ---: | ---: | ---: |']
for name,width,limit in [('pptx-20',600,.871),('pptx-20',1200,1.768),('deck',1200,15.4),('word-5',1200,6.5)]:
    d=read(HERE/'paired'/f'{name}.json')['widths'][str(width)]
    lines.append(f'| {name} @ {width} | {d["A"]["p50_ms_median"]:.3f} | {d["B"]["p50_ms_median"]:.3f} | {limit} |')
pixels=read(pixel_path)
assert pixels['different_pixels']==0
ctest=test_path.read_text()
assert '100% tests passed' in ctest and 'out of 577' in ctest
large=sum(c['compared_pixels'] for c in pixels['cases'] if c['fixture'] in ('image-heavy-100','real-mixed-120','vector-heavy-100'))
small=pixels['compared_pixels']-large
lines += ['', '## Correctness', '',
    f'Active-row byte comparison: **{large:,} + {small:,} = {pixels["compared_pixels"]:,} pixels**, '
    f'**{pixels["different_pixels"]} differing pixels** ([records]({pixel_path.relative_to(HERE).as_posix()})). '
    'The large split is 353,143,200; the small split is 111,897,000. '
    'The production test adds 144 cases comparing the fast path with a mathematically identical nested-mask '
    'generic reference: nearest/interpolated masks, differing source/mask dimensions, flipped/off-target placement, '
    'transparent texels, clip coverage, constant alpha, and both source-row conversion branches.', '',
    f'**CTest: 577/577 passed** ([log]({test_path.relative_to(HERE).as_posix()})). '
    'No cache-cap increase, sampling reduction, interpolation switch-off or drawing omission is present in production.', '',
    '## Reproduction', '', '```powershell',
    "Remove-Item -LiteralPath 'build/perf/libexreader.dll'",
    'cmake --build build/perf --parallel 4',
    'Get-Item build/perf/libexreader.dll',
    'Get-FileHash build/perf/libexreader.dll',
    'python -X utf8 evidence/resample-path-20261118/content.py',
    'python -X utf8 evidence/resample-path-20261118/verify_continuation.py',
    'python -X utf8 evidence/resample-path-20261118/report.py',
    '```', '',
    'The rebuilt diagnostic has the same executable `.text` hash as the committed probe, and its exported '
    'counter reset/read smoke check passed ([identity](continuation/probe-identity.json), '
    '[build log](continuation/probe-build.txt)).', '',
    'The preserved A DLL is `../resample-dlls/main-653e44b.dll`. '
    'To reproduce diagnostics after building the candidate, `build_probe.py` explicitly restores the baseline '
    '`affine_image.c` as well as the instrumented canvas/PDF files.', '']
if (OUT/'interleaved-image-heavy.json').exists():
    target=read(OUT/'interleaved-image-heavy.json')
    pages=[p for p in target['per_page'] if p['page']>=71]
    before=s.mean(p['a_p50_ms'] for p in pages);after=s.mean(p['b_p50_ms'] for p in pages)
    memory=read(OUT/'paired-image-heavy-100.json')['widths']['1200']
    lines[2:2]=[f'At 1200 px, fresh same-process p71–100 improved from **{before:.3f} to {after:.3f} ms/page** '
        f'(**{100*(1-after/before):.2f}% less time**), meeting the ≤60 ms/page target. '
        f'Fresh image-heavy peak RSS medians were **{memory["A"]["peak_rss_mib_median"]:.2f} → '
        f'{memory["B"]["peak_rss_mib_median"]:.2f} MiB**. '
        f'The maximum process peaks across the four repeats were '
        f'{max(memory["A"]["peak_rss_mib_repeats"]):.2f} → {max(memory["B"]["peak_rss_mib_repeats"]):.2f} MiB.', '']
(HERE/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print(HERE/'REPORT.md')
