#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Aggregate the raw GTK performance samples and gate exact coverage.

No performance budget is created here: every number is an observation. The only
pass/fail decisions are identity, fixed-environment, complete-sample-coverage and
no-filtering checks, so a missing, timed-out or failed sample fails the run.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

SCREEN = '1440x900x24'
WINDOW = (1040, 820)
MIN_LAUNCHES = 30
PACKAGE_FILES = ('tests/reader_perf_gtk/', '.github/workflows/reader-perf-gtk.yml',
                 'docs/READER-PERF-GTK.md', 'docs/validation/reader-perf-gtk.json')
LIMITATIONS = [
    'Measurements cover the GTK host built in this run with the options recorded in its CMake cache.',
    'Latency starts just before xdotool starts and ends at the host observation write; the '
    'injection command overhead is measured separately and is included in every sample.',
    'The frozen host exposes a monotonic painted_generation counter, not per-frame frame-clock '
    'timestamps, so no frame interval, frame-time percentile or dropped-frame count is claimed.',
    'Screenshots and AT-SPI are not used for any latency; screenshots are not collected at all.',
    'The X server, window manager, screen and window size are fixed for this run only; absolute '
    'values are not comparable to other runners, other GTK themes or other machines.',
    'OS page cache is uncontrolled: launches marked warm inherit the previous launch cache, and '
    'cold launches report whether the privileged cache drop succeeded.',
    'RSS is the kernel-reported resident high-water mark of the host process; engine object '
    'accounting is not claimed.',
    'The measured import workload is a fixed 6 MiB text original per import while the host '
    'worker is busy; SDK parse throughput itself is not claimed.',
    'During an import the sample set compares key input and a real window resize against the '
    'main-loop answer; the frozen host does not guarantee a page repaint on resize, so the '
    'resize sample reports the observed paint delta instead of claiming one.',
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def nearest_rank(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def aggregate(rows):
    values = sorted(row['latency_ms'] for row in rows)
    return {
        'count': len(rows),
        'min_ms': values[0] if values else None,
        'p50_ms': nearest_rank(values, 0.50),
        'p95_ms': nearest_rank(values, 0.95),
        'max_ms': values[-1] if values else None,
        'samples_ms': [round(row['latency_ms'], 3) for row in rows],
        'launches': sorted({row['launch'] for row in rows}),
    }


def expected_counts(plan):
    launches = plan['launches']
    per_kind = launches // len(plan['kinds'])
    turns = plan['turns']
    imports = per_kind
    shelf = per_kind * 2
    per_import = plan['import_key_slots']
    resizes = plan['imports_per_launch'] - 1
    if resizes < 0:
        resizes = 0
    return {
        'startup_shelf_rows': shelf + imports,
        'startup_key_response': shelf,
        'shelf_selection_move': shelf,
        'search_title_unique': shelf,
        'search_author_literal': per_kind,
        'search_empty': per_kind,
        'search_clear': per_kind,
        'open_book_applied': shelf,
        'open_book_painted': shelf,
        'page_turn_forward': (per_kind * turns['shelf_search_open_turn'][0]
                              + per_kind * turns['shelf_search_variants'][0]
                              + per_kind * turns['resume_turn'][0]
                              + imports * plan['import_turns']),
        'page_turn_backward': (per_kind * turns['shelf_search_open_turn'][1]
                               + per_kind * turns['shelf_search_variants'][1]
                               + per_kind * turns['resume_turn'][1]),
        'resume_frame_applied': per_kind,
        'resume_frame_painted': per_kind,
        'import_complete': imports * plan['imports_per_launch'],
        'import_input_response': imports * plan['imports_per_launch'] * per_import,
        'import_resize_response': imports * resizes,
    }, per_kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guards', type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('Run the GTK performance summary on a GitHub Actions Linux runner')
    source = os.environ['GITHUB_SHA']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']

    environment = json.loads((output / 'environment.json').read_text())
    samples_document = json.loads((output / 'samples.json').read_text())
    plan = json.loads((output / 'plan.json').read_text())
    launches = json.loads((output / 'launches.json').read_text())['launches']
    corpus = json.loads((output / 'corpus.json').read_text())
    calibration = json.loads((output / 'calibration.json').read_text())
    import_corpus = json.loads((output / 'import-corpus.json').read_text())
    guards = json.loads(arguments.guards.read_text())
    shutil.copyfile(arguments.guards, output / 'guards.json')
    results = samples_document['samples']
    planned = samples_document['plan']
    expected, per_kind = expected_counts(plan)

    checks = []

    def check(name, passed, detail):
        checks.append({'name': name, 'status': 'passed' if passed else 'failed', 'detail': detail})
        print('%s %s: %s' % ('PASS' if passed else 'FAIL', name, detail), flush=True)

    identity = (environment['source_sha'] == source and samples_document['source_sha'] == source
                and str(environment['run_id']) == run_id and str(samples_document['run_id']) == run_id
                and str(environment['attempt']) == attempt
                and str(samples_document['attempt']) == attempt)
    check('same-source-run-attempt-identity', identity,
          {'source_sha': source, 'run_id': run_id, 'attempt': attempt,
           'environment': environment['source_sha']})

    guard_ok = (guards.get('head') == source and guards.get('github_sha') == source
                and bool(guards.get('components')))
    check('source-and-component-identities', guard_ok, guards)

    completed = len(launches)
    launch_ok = (completed == plan['launches'] and completed >= MIN_LAUNCHES)
    check('independent-launch-count', launch_ok,
          {'planned': plan['launches'], 'completed': completed, 'minimum': MIN_LAUNCHES,
           'kinds': {kind: sum(1 for row in launches if row['kind'] == kind) for kind in plan['kinds']}})

    exits = [row.get('process_exit') for row in launches]
    failures = [{'launch': row['launch'], 'failure': row.get('failure')}
                for row in launches if row.get('failure')]
    clean = all(code == 0 for code in exits) and not failures
    check('every-launch-clean-exit-and-no-observation-failure', clean,
          {'exits': exits, 'launch_failures': failures,
           'observation_failures': [row['launch'] for row in launches
                                    if row.get('observation_failure')]})

    geometries = [row.get('geometry') or {} for row in launches]
    fixed_window = all(geometry.get('WIDTH') == WINDOW[0] and geometry.get('HEIGHT') == WINDOW[1]
                       for geometry in geometries)
    check('fixed-screen-window-and-border', environment['screen'] == SCREEN and fixed_window,
          {'screen': environment['screen'], 'window': list(WINDOW),
           'observed': sorted({(geometry.get('WIDTH'), geometry.get('HEIGHT'))
                               for geometry in geometries}, key=str)})

    corpus_ok = (corpus.get('books') == 2202 and corpus.get('first_id') and corpus.get('last_id')
                 and corpus['long_book_bytes'] > 100000
                 and environment.get('seed', {}).get('corpus_sha256')
                 and environment.get('seed', {}).get('library_sha256'))
    check('fixed-2202-original-corpus', corpus_ok,
          {'books': corpus.get('books'), 'first_id': corpus.get('first_id'),
           'last_id': corpus.get('last_id'), 'long_book_bytes': corpus.get('long_book_bytes'),
           'total_original_bytes': corpus.get('total_original_bytes'),
           'corpus_sha256': environment.get('seed', {}).get('corpus_sha256'),
           'seed_sha256': environment.get('seed', {}).get('seed_sha256')})

    writes = sum(row.get('state_writes') or 0 for row in launches)
    paints = sum(row.get('paint_count') or 0 for row in launches)
    event_ok = (writes > 0 and paints > 0
                and all((row.get('state_writes') or 0) > 0 for row in launches))
    check('event-driven-observation-not-polling', event_ok,
          {'state_writes': writes, 'paint_events': paints,
           'calibration_median_ms': calibration['median_ms']})

    planned_keys = [(row['launch'], row['metric'], row['slot']) for row in planned]
    result_keys = [(row['launch'], row['metric'], row['slot']) for row in results]
    duplicates = len(result_keys) - len(set(result_keys))
    unmatched = [key for key in result_keys if key not in set(planned_keys)]
    unrecorded = [key for key in planned_keys if key not in set(result_keys)]
    by_metric = {}
    for row in results:
        by_metric.setdefault(row['metric'], []).append(row)
    coverage = {}
    coverage_ok = not duplicates and not unmatched and not unrecorded
    for metric, expected_count in sorted(expected.items()):
        rows = by_metric.get(metric, [])
        good = [row for row in rows if row['outcome'] == 'ok']
        bad = [row for row in rows if row['outcome'] != 'ok']
        coverage[metric] = {'expected': expected_count, 'recorded': len(rows), 'ok': len(good),
                            'not_ok': [{'outcome': row['outcome'], 'note': row['note'],
                                        'launch': row['launch']} for row in bad]}
        if len(good) < expected_count or bad:
            coverage_ok = False
    extra = sorted(set(by_metric) - set(expected))
    check('complete-planned-sample-coverage', coverage_ok,
          {'duplicates': duplicates, 'unmatched': unmatched, 'unrecorded': unrecorded,
           'extra_metrics': extra, 'coverage': coverage})

    payload = environment['payload']
    package = environment.get('package') or {}
    package_ok = bool(payload.get('bytes')) and bool(payload.get('binary_sha256')) and bool(
        payload.get('font_sha256')) and bool(package.get('tarball_sha256'))
    check('package-identity-and-size', package_ok,
          {'payload_bytes': payload.get('bytes'), 'binary_bytes': payload.get('binary_bytes'),
           'binary_sha256': payload.get('binary_sha256'), 'font_sha256': payload.get('font_sha256'),
           'tarball_bytes': package.get('tarball_bytes'),
           'tarball_sha256': package.get('tarball_sha256'),
           'import_files': [row['bytes'] for row in import_corpus]})

    high_water = [row.get('vm_hwm_kb') for row in launches]
    rss_ok = all(isinstance(value, int) and value > 0 for value in high_water)
    check('rss-high-water-recorded', rss_ok,
          {'per_launch_kb': high_water, 'max_kb': max(high_water) if high_water else None,
           'median_kb': sorted(high_water)[len(high_water) // 2] if high_water else None})

    metrics = {}
    for metric, rows in sorted(by_metric.items()):
        good = [row for row in rows if row['outcome'] == 'ok']
        value = aggregate(good)
        value['outcomes'] = {outcome: sum(1 for row in rows if row['outcome'] == outcome)
                             for outcome in sorted({row['outcome'] for row in rows})}
        groups = {}
        for group in sorted({row['group'] for row in good if row['group']}):
            groups[group] = aggregate([row for row in good if row['group'] == group])
        if groups:
            value['groups'] = groups
        value['start_reference'] = START_REFERENCE.get(metric, 'key injection')
        metrics[metric] = value

    with (output / 'samples.csv').open(newline='') as handle:
        csv_rows = list(csv.DictReader(handle))
    csv_ok = len(csv_rows) == len(results)
    if csv_ok:
        for row, source_row in zip(csv_rows, results):
            if source_row['outcome'] == 'ok':
                if abs(float(row['latency_ms']) - source_row['latency_ms']) > 1e-6:
                    csv_ok = False
                    break
            elif row['outcome'] != source_row['outcome']:
                csv_ok = False
                break
    retained = sum(1 for row in results if row['outcome'] == 'ok')
    aggregated = sum(value['count'] for value in metrics.values())
    check('all-samples-retained-without-filtering', csv_ok and aggregated == retained,
          {'csv_rows': len(csv_rows), 'results': len(results), 'ok_samples': retained,
           'aggregated_ok_samples': aggregated})

    for name, value in sorted(metrics.items()):
        print('METRIC %s count=%d min=%s p50=%s p95=%s max=%s start="%s"' % (
            name, value['count'], value['min_ms'], value['p50_ms'], value['p95_ms'],
            value['max_ms'], value['start_reference']), flush=True)

    rss = {'per_launch_kb': high_water,
           'p50_kb': sorted(high_water)[len(high_water) // 2] if high_water else None,
           'max_kb': max(high_water) if high_water else None,
           'cold': [row['vm_hwm_kb'] for row in launches if row['cache']['effective'] == 'cold'],
           'warm': [row['vm_hwm_kb'] for row in launches if row['cache']['effective'] == 'warm']}
    paint = {'total': sum(row.get('paint_count') or 0 for row in launches),
             'per_launch': {row['launch']: row.get('paint_count') for row in launches},
             'offsets_ms': {row['launch']: row.get('paint_offsets_ms') for row in launches}}

    accepted = all(row['status'] == 'passed' for row in checks)
    covered = lambda name, expected_value: (coverage.get(name, {}).get('ok', 0) >= expected_value
                                            and not coverage.get(name, {}).get('not_ok'))
    grants = {
        'first_screen_end_to_end_interactive': covered('startup_shelf_rows', expected['startup_shelf_rows'])
        and covered('startup_key_response', expected['startup_key_response'])
        and covered('shelf_selection_move', expected['shelf_selection_move']),
        'search_end_to_end': covered('search_title_unique', expected['search_title_unique'])
        and covered('search_author_literal', expected['search_author_literal'])
        and covered('search_empty', expected['search_empty']),
        'open_and_page_turn_end_to_end': covered('open_book_painted', expected['open_book_painted'])
        and covered('page_turn_forward', expected['page_turn_forward'])
        and covered('page_turn_backward', expected['page_turn_backward']),
        'continue_reading_end_to_end': covered('resume_frame_painted', expected['resume_frame_painted']),
        'import_input_responsiveness': covered('import_input_response', expected['import_input_response']),
        'import_resize_response_during_busy_worker': covered(
            'import_resize_response', expected['import_resize_response']),
        'process_rss_high_water': rss_ok,
        'package_size': package_ok,
        'frame_clock_interval': False,
        'frame_time_percentiles': False,
        'dropped_frame_accounting': False,
        'hard_cpu_or_memory_budget': False,
        'real_hardware_fluency': False,
        'screen_reader_accessibility': False,
        'product_completion': False,
    }

    summary = {
        'schema': 1, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
        'launches': {'planned': plan['launches'], 'completed': completed,
                     'minimum': MIN_LAUNCHES, 'per_kind': per_kind,
                     'cold': sum(1 for row in launches if row['cache']['effective'] == 'cold'),
                     'warm': sum(1 for row in launches if row['cache']['effective'] == 'warm'),
                     'kinds': plan['kinds'], 'plan': plan['metrics']},
        'environment': environment, 'corpus': corpus, 'package': {
            'payload': payload, 'tarball': package},
        'metrics': metrics, 'rss': rss, 'paint': paint, 'calibration': calibration,
        'guards': guards,
    }
    report = {
        'accepted': accepted, 'complete_product': False,
        'source_sha': source, 'run_id': run_id, 'attempt': attempt,
        'workflow': '.github/workflows/reader-perf-gtk.yml', 'platform': 'Linux',
        'launches': completed, 'samples': len(results),
        'metrics': {name: {'expected': value['expected'], 'ok': value['ok'],
                           'recorded': value['recorded']}
                    for name, value in sorted(coverage.items())},
        'checks': checks,
        'problems': [row['name'] for row in checks if row['status'] != 'passed'],
        'grants': grants, 'limitations': LIMITATIONS,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    bundle = {}
    for path in sorted(output.rglob('*')):
        if not path.is_file() or path.name == 'bundle.json':
            continue
        bundle[str(path.relative_to(output))] = {'bytes': path.stat().st_size,
                                                 'sha256': sha256_file(path)}
    (output / 'bundle.json').write_text(json.dumps({'schema': 1, 'files': bundle}, indent=2) + '\n')
    print(json.dumps({'accepted': accepted, 'checks': len(checks),
                      'problems': report['problems'],
                      'launches': completed, 'samples': len(results)}, sort_keys=True), flush=True)
    if not accepted:
        raise SystemExit('GTK performance coverage is incomplete')


START_REFERENCE = {
    'startup_shelf_rows': 'process start to the first bounded 50-row shelf page',
    'startup_key_response': 'process start to the first real key response',
    'shelf_selection_move': 'key injection to the keyboard row selection change',
    'search_title_unique': 'query injection to the filtered single-row result',
    'search_author_literal': 'query injection to the literal author result page',
    'search_empty': 'query injection to the empty result',
    'search_clear': 'query injection to the restored first page',
    'open_book_applied': 'Return injection to the applied reader frame',
    'open_book_painted': 'Return injection to the first real paint of the reader frame',
    'page_turn_forward': 'F4 injection to the first real paint of the next page',
    'page_turn_backward': 'F3 injection to the first real paint of the previous page',
    'resume_frame_applied': 'process start to the restored reader frame',
    'resume_frame_painted': 'process start to the first real paint of the restored frame',
    'import_complete': 'F1 injection to the completed import and opened original',
    'import_input_response': 'key injection to the host answer while the worker is busy',
    'import_resize_response': 'resize to the main-loop answer while the worker is busy',
}


if __name__ == '__main__':
    main()
