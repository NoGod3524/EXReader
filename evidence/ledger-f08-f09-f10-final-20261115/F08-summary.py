# SPDX-License-Identifier: MIT
"""Recompute F08 per-book numbers from the archived f08-realbooks.json raw samples.

Standard library only. Usage: python F08-summary.py <f08-realbooks.json>
Prints per book: candidate-side pooled render/present p50/p95 over every raw
sample, the median first_interactive_ms / setup / peak working set across the
fresh processes, the fixed budgets and whether the exporter's verdict agrees.
"""
import json
import math
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
report = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))


def p95(values):
    ordered = sorted(values)
    return ordered[math.ceil(.95 * len(ordered)) - 1]


print('source=%s run=%s/%s passed=%s accepted=%s product_budget_accepted=%s' % (
    report['source'], report['environment']['run'], report['environment']['attempt'],
    report['passed'], report['accepted'], report['product_budget_accepted']))
print('display_present_frame=%s' % report['display_present_frame'])
print('first_interactive=%s' % report['first_interactive'])
print('budgets=%s' % json.dumps(report['budgets'], sort_keys=True))
problems = 0
for book in report['books']:
    candidates = [sample['metrics'] for sample in book['candidate'] if 'metrics' in sample]
    render = [x for m in candidates for x in m['raw_render_ms']]
    present = [x for m in candidates for x in m['raw_present_ms']]
    interactive = statistics.median(m['first_interactive_ms'] for m in candidates)
    setup = statistics.median(m['setup_render_ready_ms'] for m in candidates)
    peak = statistics.median(m['peak_working_set_bytes'] for m in candidates)
    budgets = report['budgets']
    mine = {'render_p50_ms': statistics.median(m['render_p50_ms'] for m in candidates),
            'render_p95_ms': statistics.median(m['render_p95_ms'] for m in candidates),
            'present_p50_ms': statistics.median(m['present_p50_ms'] for m in candidates),
            'present_p95_ms': statistics.median(m['present_p95_ms'] for m in candidates),
            'first_interactive_ms': interactive, 'peak_working_set_bytes': peak}
    within = all(mine[key] <= budgets[key] for key in budgets)
    exporter = book.get('comparison', {})
    agree = exporter.get('budgets_passed') == within
    problems += not agree
    print('%s processes=%d samples=%d render_p50=%.6f render_p95=%.6f present_p50=%.6f present_p95=%.6f '
          'first_interactive_ms=%.3f setup_ms=%.3f peak_ws=%d within_budgets=%s exporter_budgets_passed=%s '
          'ratios_passed=%s' % (
              book['path'].replace('\\', '/').rsplit('/', 1)[-1], len(candidates), len(render), statistics.median(render), p95(render),
              statistics.median(present), p95(present), interactive, setup, int(peak), within,
              exporter.get('budgets_passed'), exporter.get('ratios_passed')))
print('recompute_agrees_with_exporter=%s' % (problems == 0))
raise SystemExit(1 if problems else 0)
