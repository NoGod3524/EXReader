#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-source SDK 3.42 product-performance handoff record (GitHub Actions only).

Reads the measured Windows and Linux summaries produced by the existing perf
drivers and writes one report: source SHA, SDK version, program hashes, per
metric samples/p50/p95/max against the *ratified* threshold. No numeric product
budget has been ratified (docs/READER-PRODUCT-PERFORMANCE.md), so thresholds are
null, nothing is judged against an invented limit, and F08 is never granted here.
Exit status is non-zero only for identity or coverage failures.
"""
import argparse
import json
import os
import sys
from pathlib import Path

SDK = '3.42.0'
NOT_MEASURED = ['Windows scroll/font switch', 'locate/jump', 'frame time / dropped frames',
                'physical-device fluency', 'Apple', 'Android']
WIN = (('cold_shelf', 'first_screen_interactive_ms'), ('warm_shelf', 'first_screen_interactive_ms'),
       ('warm_shelf', 'shelf_next_page_ms'), ('warm_shelf', 'search_result_ms'),
       ('reading', 'book_page_turn_ms'), ('reading', 'resume_ms'),
       ('import_epub', 'input_during_import_p50_ms'), ('cold_shelf', 'peak_working_set_bytes'),
       ('reading', 'peak_working_set_bytes'))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--windows-summary', required=True)
    p.add_argument('--windows-build', required=True)
    p.add_argument('--gtk-summary', required=True)
    p.add_argument('--gtk-interactions')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    source = os.environ.get('GITHUB_SHA', '')
    problems, rows = [], []
    ws, wb, gs = load(a.windows_summary), load(a.windows_build), load(a.gtk_summary)
    if wb.get('sdk_version') != SDK:
        problems.append('Windows package SDK is %r, not %s' % (wb.get('sdk_version'), SDK))
    if wb.get('source_sha') != source or (ws.get('source_sha') or ws.get('environment', {}).get('source_sha')) != source or gs.get('source_sha') != source:
        problems.append('source SHA differs between package, Windows or Linux evidence and GITHUB_SHA')
    if ws.get('problems'):
        problems.append('Windows has incomplete launches: %d' % len(ws['problems']))
    skipped = ws.get('skipped_cohorts') or {}
    for cohort, metric in WIN:
        s = (ws.get('aggregates', {}).get(cohort) or {}).get(metric) or {}
        if not s.get('n'):
            if cohort not in skipped:
                problems.append('Windows %s/%s has no samples' % (cohort, metric))
            rows.append({'platform': 'windows', 'cohort': cohort, 'metric': metric, 'n': 0,
                         'note': skipped.get(cohort) or 'no samples'})
            continue
        rows.append({'platform': 'windows', 'cohort': cohort, 'metric': metric, 'unit': s['unit'],
                     'n': s['n'], 'p50': s['p50'], 'p95': s['p95'], 'max': s['max'], 'ratified_threshold': None})
    if gs['launches']['completed'] < gs['launches']['minimum']:
        problems.append('Linux completed %d launches' % gs['launches']['completed'])
    for name, m in sorted(gs['metrics'].items()):
        rows.append({'platform': 'linux', 'metric': name, 'unit': 'ms', 'n': m['count'], 'p50': m['p50_ms'],
                     'p95': m['p95_ms'], 'max': m['max_ms'], 'ratified_threshold': None})
    if a.gtk_interactions and Path(a.gtk_interactions).exists():
        gi = load(a.gtk_interactions)
        if gi.get('source_sha') != source or gi.get('problems'):
            problems.append('Linux interaction evidence has a different source or failed samples')
        for name, m in sorted(gi['metrics'].items()):
            rows.append({'platform': 'linux', 'metric': name, 'unit': 'ms', 'n': m['n'], 'p50': m['p50'],
                         'p95': m['p95'], 'max': m['max'], 'ratified_threshold': None})
        ip = gi.get('inter_paint_interval_ms')
        if ip:
            rows.append({'platform': 'linux', 'metric': 'inter_paint_interval_proxy_not_frame_time', 'unit': 'ms',
                         'n': ip['n'], 'p50': ip['p50'], 'p95': ip['p95'], 'max': ip['max'], 'ratified_threshold': None})
    else:
        problems.append('Linux interaction summary is missing')
    rss = gs['rss']
    rows.append({'platform': 'linux', 'metric': 'rss_high_water_kb', 'unit': 'KiB',
                 'n': len(rss['per_launch_kb']), 'p50': rss['p50_kb'], 'max': rss['max_kb'], 'ratified_threshold': None})
    report = {'schema': 1, 'source_sha': source, 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'sdk_version': SDK,
              'windows_exe_sha256': wb.get('files', {}).get('EXReader.exe'),
              'linux_package': gs.get('package'), 'rows': rows, 'problems': problems,
              'evidence_complete': not problems, 'f08_accepted': False, 'ratified_numeric_budgets': 0,
              'not_measured': NOT_MEASURED,
              'reason': 'No product budget was ratified or frozen; observations are not acceptance.'}
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'handoff-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['| platform | metric | n | p50 | p95 | max | threshold |', '|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append('| %s | %s | %s | %s | %s | %s | none ratified |' % (
            r['platform'], (r.get('cohort', '') + ' ' + r['metric']).strip(), r['n'],
            r.get('p50'), r.get('p95'), r.get('max')))
    (out / 'handoff-report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    for item in problems:
        print('PROBLEM', item)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
