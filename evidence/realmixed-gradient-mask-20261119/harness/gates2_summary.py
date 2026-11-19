# Summarise gates2 runs into gates/<item>.json. All rounds counted; pre-CPU reported, never filtered.
import json, statistics as st, sys
from pathlib import Path
run = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
frozen = json.loads((run.parent/'opus-Cacc-20261119-155040'/'frozen-gates.json').read_text())
def load(k, arm):
    x = json.loads((run/f'{k}-{arm}.json').read_text())
    A = [v for r in x['per_page_ms'].values() for v in r['A']]; B = [v for r in x['per_page_ms'].values() for v in r['B']]
    cpu = [r['cpu_busy_pre_percent'] for r in x['rounds']]
    return {'json': str((run/f'{k}-{arm}.json').as_posix()), 'a_sha256': x['a_sha256'], 'b_sha256': x['b_sha256'],
            'rounds': len(x['rounds']), 'mismatched_pages': x['mismatched_pages'], 'compared_pixels': x['compared_pixels'],
            'A_page_p50_ms': st.median(A), 'B_page_p50_ms': st.median(B), 'pooled_page_p50_ms': st.median(A+B),
            'ratio_B_over_A': st.median(B)/st.median(A),
            'per_round_saving_ms': [r['saving_ms'] for r in x['rounds']], 'saving_median_ms': st.median(r['saving_ms'] for r in x['rounds']),
            'rounds_b_faster': sum(r['saving_ms'] > 0 for r in x['rounds']),
            'pre_cpu': {'min': min(cpu), 'median': st.median(cpu), 'max': max(cpu), 'per_round': cpu}}
summary = {}
for k, it in frozen['items'].items():
    d = {a: load(k, a) for a in ('cand-vs-main', 'cand-vs-frozen', 'frozen-null', 'main-null')}
    lim = frozen['margin']
    res = {'item': k, 'fixture': it['fixture'], 'pages': it['pages'], 'width': it['width'],
           'frozen_baseline_ms': it['baseline_ms'], 'frozen_limit_ms': it['limit_ms'], 'margin': lim,
           'frozen_dll_today_pooled_p50_ms': d['frozen-null']['pooled_page_p50_ms'],
           'frozen_dll_today_meets_own_limit': d['frozen-null']['pooled_page_p50_ms'] <= it['limit_ms'],
           'candidate_p50_ms_vs_main_run': d['cand-vs-main']['B_page_p50_ms'],
           'absolute_gate_pass': d['cand-vs-main']['B_page_p50_ms'] <= it['limit_ms'],
           'ratio_cand_over_main': d['cand-vs-main']['ratio_B_over_A'],
           'ratio_cand_over_frozen': d['cand-vs-frozen']['ratio_B_over_A'],
           'rescaled_limit_ms': lim*d['cand-vs-frozen']['A_page_p50_ms'],
           'ratio_gate_pass_vs_main': d['cand-vs-main']['ratio_B_over_A'] <= lim,
           'ratio_gate_pass_vs_frozen': d['cand-vs-frozen']['ratio_B_over_A'] <= lim,
           'null_ratio_frozen': d['frozen-null']['ratio_B_over_A'], 'null_ratio_main': d['main-null']['ratio_B_over_A'],
           'runs': d}
    (out/f'{k}.json').write_text(json.dumps(res, indent=1)+'\n')
    summary[k] = {x: res[x] for x in res if x != 'runs'}
    summary[k]['pre_cpu_by_arm'] = {a: {y: d[a]['pre_cpu'][y] for y in ('min', 'median', 'max')} for a in d}
    summary[k]['mismatched'] = {a: d[a]['mismatched_pages'] for a in d}
(out/'summary.json').write_text(json.dumps(summary, indent=1)+'\n')
for k, s in summary.items():
    print(f"{k:13s} frozen_today={s['frozen_dll_today_pooled_p50_ms']:.4f} (limit {s['frozen_limit_ms']:.4f}) cand={s['candidate_p50_ms_vs_main_run']:.4f} "
          f"c/main={s['ratio_cand_over_main']:.4f} c/frozen={s['ratio_cand_over_frozen']:.4f} null_f={s['null_ratio_frozen']:.4f} null_m={s['null_ratio_main']:.4f}")
