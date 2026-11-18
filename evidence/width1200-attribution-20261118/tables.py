# SPDX-License-Identifier: MIT
"""Generate Markdown tables using only accepted, validated measurements."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]]) + '\n'


def main():
    d = json.loads((HERE / 'summary.json').read_text())
    text = []
    rows = []
    for case, widths in d['baseline'].items():
        for w, row in widths.items():
            rows.append([case, w, row['pages'], f"{row['pixels']:,}", f"{row['ms']:.3f}",
                         ' / '.join(f'{v:.3f}' for v in row['samples_ms']), f"{row['pages_s']:.2f}"])
    text += ['## Original-DLL throughput\n', table(['Fixture', 'Width', 'Pages', 'Active pixels/round',
             'Warm round median (ms)', 'Three repeat medians (ms)', 'Pages/s'], rows)]
    rows = []
    for case, widths in d['cohorts'].items():
        for cohort, a in widths['600'].items():
            b = widths['1200'][cohort]
            x, y = a['sum_page_medians_ms'], b['sum_page_medians_ms']
            rows.append([case, cohort, a['pages'], f'{x:.3f}', f'{y:.3f}', f'{y-x:+.3f}', f'{y/x:.3f}×'])
    text += ['## Native per-page time by cohort (sum of cross-repeat page p50s)\n', table(['Fixture', 'Cohort', 'Pages',
             '@600 ms', '@1200 ms', 'Difference ms', 'Ratio'], rows)]
    for case, widths in d['ablation'].items():
        rows = []
        for mode in widths['600']:
            a, b = widths['600'][mode], widths['1200'][mode]
            if a['saving_ms'] > 0 and b['saving_ms'] > 0:
                value = b['saving_ms'] / a['saving_ms']
                ratio = f"{value:.3f}× ({'>' if value > 4 else '<='}4)"
            else:
                ratio = 'undefined (signed/noise)'
            rows.append([mode, f"{a['ms']:.3f}", f"{b['ms']:.3f}", f"{b['ms']/a['ms']:.3f}×",
                         f"{a['saving_ms']:+.3f}", f"{b['saving_ms']:+.3f}", '—' if mode == 'full' else ratio,
                         f"{a['changed_pages'][0]} / {b['changed_pages'][0]}"])
        text += [f'## {case}: full vs class disabled\n', table(['Disabled', '@600 ms', '@1200 ms',
                 'Disabled-render ratio', 'Saving @600 ms', 'Saving @1200 ms', 'Saving ratio (compare 4×)', 'Changed pages 600/1200'], rows)]
    rows = []
    for case, widths in d['telemetry'].items():
        for w, row in widths.items():
            for kind in ('cold', 'warm'):
                r = row[kind]
                rows.append([case, w, kind, f"{r['hits']:.0f}", f"{r['misses']:.0f}", f"{r['evictions']:.0f}",
                             f"{r['decode_ms']:.3f}", f"{r['image_cache_bytes']/1024**2:.3f}", f"{r['image_cache_entries']:.0f}"])
    text += ['## Image cache counters per complete sweep\n', table(['Fixture', 'Width', 'Sweep', 'Hits', 'Misses',
             'Evictions', 'Decode ms', 'Maximum resident MiB', 'Maximum entries'], rows)]
    for case, widths in d['telemetry'].items():
        a, b = widths['600']['warm'], widths['1200']['warm']
        rows = []
        for k in ('ms', 'allocator_ms', 'canvas_create_ms', 'canvas_image_ms', 'mask_ms',
                  'canvas_paint_ms', 'mask_canvas_paint_ms', 'decode_ms', 'other_ms'):
            rows.append([k, f'{a[k]:.3f}', f'{b[k]:.3f}', f'{b[k]-a[k]:+.3f}',
                         f'{b[k]/a[k]:.3f}×' if a[k] else '—'])
        text += [f'## {case}: instrumented warm sweep times\n', table(['Scope', '@600 ms', '@1200 ms', 'Difference ms', 'Ratio'], rows)]
    rows = []
    for case, widths in d['telemetry'].items():
        count = d['baseline'][case]['600']['pages']
        for w, row in widths.items():
            r = row['warm']
            rows.append([case, w, f"{r['malloc']/count:.2f}", f"{r['calloc']/count:.2f}", f"{r['realloc']/count:.2f}",
                         f"{r['free']/count:.2f}", f"{r['requested_bytes']/count/1024**2:.3f}", f"{r['allocator_ms']/count:.4f}",
                         f"{r['pdf_pool_bytes']/1024**2:.3f}", f"{r['fixed_pool_bytes']/1024**2:.3f}"])
    text += ['## Link-visible allocation calls per warm page and observed retained pools\n', table(['Fixture', 'Width',
             'malloc/page', 'calloc/page', 'realloc/page', 'free(non-null)/page', 'Requested MiB/page', 'Allocator ms/page',
             'Max PDF pool MiB', 'Max fixed pool MiB'], rows)]
    rows = []
    for case, widths in d['baseline'].items():
        for w, row in widths.items():
            r = row['rss_mean_mib']
            rows.append([case, w, *[f'{r[k]:.3f}' for k in ('start', 'open_growth', 'cold_peak_growth', 'warm_peak_growth', 'peak')]])
    text += ['## Peak working-set growth by phase (mean of three processes, MiB)\n', table(['Fixture', 'Width',
             'Process-start RSS', 'Open growth', 'Cold-sweep peak growth', 'Further warm peak growth', 'Final peak'], rows)]
    rows = []
    for w, row in d['cache256'].items():
        native = d['baseline']['image-heavy-100'][w]
        r = row['warm_trace']
        rows.append([w, f"{row['paired64_ms']:.3f}", f"{row['ms']:.3f}", f"{row['paired_saving_ms']:.3f}",
                     f"{row['pages_s']:.2f}", f"{r['hits']:.0f}", f"{r['misses']:.0f}", f"{r['evictions']:.0f}",
                     f"{r['decode_ms']:.3f}", f"{r['image_cache_bytes']/1024**2:.3f}", f"{row['peak_rss_mean_mib']:.3f}"])
    text += ['## Image-heavy: alternating 64/256 MiB cache intervention\n', table(['Width', 'Paired 64 MiB native ms', '256 MiB native ms',
             'Observed reduction ms', '256 MiB pages/s', 'Warm hits', 'Warm misses', 'Warm evictions', 'Warm decode ms', 'Resident MiB', 'Native mean peak RSS MiB'], rows)]
    rows = []
    for case, widths in d['firstscreen'].items():
        for w, row in widths.items():
            rows.append([case, w, f"{row['open_ms']:.3f}", f"{row['render_ms']:.3f}"])
    text += ['## Unified fresh first page (bench_firstscreen, three processes)\n', table(['Fixture', 'Width', 'Open median ms', 'Render median ms'], rows)]
    (HERE / 'TABLES.md').write_text('\n'.join(text), encoding='utf-8')


if __name__ == '__main__':
    main()
