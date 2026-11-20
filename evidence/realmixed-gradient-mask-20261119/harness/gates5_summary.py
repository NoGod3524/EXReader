# Summarise cross-process gate runs (xab.py) into gates/<item>.json + gates/summary.json.
# Every round counted; pre-CPU reported (min/median/max + per round), never filtered.
import json, statistics as st, sys
from pathlib import Path
run, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(exist_ok=True)
fg = json.loads((run.parent/'opus-Cacc-20261119-155040'/'frozen-gates.json').read_text()); M = fg['margin']
ARMS = ('cand-vs-main', 'cand-vs-frozen', 'main-null', 'frozen-null')
def one(f):
    x = json.loads(f.read_text()); s = x['summary']; cpu = [r['cpu_busy_pre_percent'] for r in x['rounds']]
    assert len(x['rounds']) == 15 and not x['mismatched_pages']
    return {'json': f.as_posix(), 'a_sha256': x['a_sha256'], 'b_sha256': x['b_sha256'], 'compared_pixels': x['compared_pixels'],
            'A_page_p50_ms': s['A_page_p50_ms'], 'B_page_p50_ms': s['B_page_p50_ms'], 'ratio_B_over_A': s['ratio_B_over_A'],
            'per_round_A_minus_B_ms': [r['saving_ms'] for r in x['rounds']], 'saving_median_ms': s['saving_median_ms'],
            'rounds_b_faster': s['rounds_b_faster'], 'pre_cpu': {'min': min(cpu), 'median': st.median(cpu), 'max': max(cpu), 'per_round': cpu}}
summary = {}
for k, it in fg['items'].items():
    runs = {a: [one(run/f'{k}-{a}-{rep}.json') for rep in (0, 1)] for a in ARMS}
    r = {a: [x['ratio_B_over_A'] for x in runs[a]] for a in ARMS}
    worst = {a: max(r[a]) for a in ARMS}
    cpu_all = [c for a in ARMS for x in runs[a] for c in x['pre_cpu']['per_round']]
    res = {'item': k, 'fixture': it['fixture'], 'pages': it['pages'], 'width': it['width'], 'margin': M,
           'frozen_baseline_ms': it['baseline_ms'], 'frozen_limit_ms': it['limit_ms'],
           'ratio_cand_over_main': r['cand-vs-main'], 'ratio_cand_over_frozen': r['cand-vs-frozen'],
           'null_ratio_main': r['main-null'], 'null_ratio_frozen': r['frozen-null'],
           'pass_cand_over_main_le_margin_both_reps': worst['cand-vs-main'] <= M,
           'pass_cand_over_frozen_le_margin_both_reps': worst['cand-vs-frozen'] <= M,
           'frozen_dll_pooled_p50_today_ms': [st.median([x['A_page_p50_ms'], x['B_page_p50_ms']]) for x in runs['frozen-null']],
           'candidate_p50_today_ms': [x['B_page_p50_ms'] for x in runs['cand-vs-main']],
           'absolute_limit_met_by_frozen_dll_today': [st.median([x['A_page_p50_ms'], x['B_page_p50_ms']]) <= it['limit_ms'] for x in runs['frozen-null']],
           'pre_cpu_all_runs': {'min': min(cpu_all), 'median': st.median(cpu_all), 'max': max(cpu_all), 'n_rounds': len(cpu_all)},
           'runs': runs}
    (out/f'{k}.json').write_text(json.dumps(res, indent=1)+'\n')
    summary[k] = {x: v for x, v in res.items() if x != 'runs'}
    summary[k]['pre_cpu_by_run'] = {f'{a}-{i}': {y: runs[a][i]['pre_cpu'][y] for y in ('min', 'median', 'max')} for a in ARMS for i in (0, 1)}
    f = lambda v: '/'.join(f'{x:.4f}' for x in v)
    print(f"{k:13s} c/main={f(r['cand-vs-main'])} c/frozen={f(r['cand-vs-frozen'])} null_m={f(r['main-null'])} null_f={f(r['frozen-null'])} "
          f"frozen_today={f(res['frozen_dll_pooled_p50_today_ms'])} lim={it['limit_ms']:.4f} cand={f(res['candidate_p50_today_ms'])} cpu={res['pre_cpu_all_runs']}")
(out/'summary.json').write_text(json.dumps({'harness': 'harness/xab.py (one worker process per DLL)', 'run_dir': run.as_posix(), 'items': summary}, indent=1)+'\n')
