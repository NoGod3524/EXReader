#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-time assertion and per-stratum aggregation of the C02 round artifacts.

Every raw sample is checked against its round identity before it can be counted;
failed, missing or unknown samples are never dropped silently - they make the
result incomplete. Statistics are computed only inside one CPU stratum, and the
budgets in the output are proposals (approved=false), never approved limits.
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as K  # noqa: E402

REQUIRED_METRICS = {
    'windows': {'start_window', 'start_first_rows', 'start_interactive', 'resume_restored', 'shelf_scroll_page',
                'search_author', 'search_clear', 'search_title', 'open_book', 'page_turn', 'back_to_library',
                'import_complete', 'post_import_search', 'ui_roundtrip_idle', 'ui_roundtrip_reading'},
    'gtk': {'startup_shelf_rows', 'startup_key_response', 'shelf_selection_move', 'search_title_unique',
            'search_author_literal', 'search_empty', 'search_clear', 'open_book_applied', 'open_book_painted',
            'page_turn_forward', 'page_turn_backward', 'import_complete', 'import_input_response'},
}
# Race-dependent observations: a worker that finished first is recorded as not_observed.
NOT_OBSERVED_OK = {'import_input_response', 'import_resize_response'}
PROPOSAL_FACTOR = 1.25
PROPOSAL_MIN_N = 8


def planned_launches(directory, platform_name, sizes):
    plan = K.read_json(Path(directory) / 'plan.json')
    if platform_name == 'windows':
        return sum(plan['launch_counts'].values()) * len(sizes)
    return plan['launches_per_size'] * len(sizes)


def load_round(directory, platform_name, expected):
    directory = Path(directory)
    K.require(K.check_bundle(directory) > 0, 'empty bundle')
    sizes = sorted(int(path.stem.split('-n')[1]) for path in directory.glob('identity-n*.json'))
    K.require(sizes == [500, 5000], '%s round %s does not hold both shelf sizes: %r'
              % (platform_name, directory.name, sizes))
    identities = {}
    for size in sizes:
        identity = K.read_json(directory / ('identity-n%d.json' % size))
        K.assert_identity(identity, expected['source'], expected['run'], expected['attempt'])
        K.require(identity['platform'] == platform_name and identity['shelf_size'] == size,
                  'identity platform/size differs in ' + directory.name)
        identities[size] = identity
    base = {key: value for key, value in identities[500].items() if key != 'shelf_size'}
    K.require({key: value for key, value in identities[5000].items() if key != 'shelf_size'} == base,
              'the two shelf sizes of one round carry different identities')
    rows = K.read_json(directory / 'samples.json')['rows']
    seen = set()
    for row in rows:
        K.assert_row(row, identities[row['shelf_size']] if row.get('shelf_size') in identities else base)
        K.require(row['sample_id'] not in seen, 'duplicate sample id ' + row['sample_id'])
        seen.add(row['sample_id'])
    launches = K.read_json(directory / 'launches.json')['launches']
    memory = K.read_json(directory / 'memory.json')['records']
    for record in memory:
        K.assert_memory(record, identities[record['shelf_size']])
    environment = K.read_json(directory / 'environment.json')
    K.require(environment['cpu']['stratum']['id'] == base['stratum'], 'environment stratum differs from identity')
    return {'directory': directory.name, 'platform': platform_name, 'round': base['round'],
            'identity': base, 'rows': rows, 'launches': launches, 'memory': memory,
            'planned_launches': planned_launches(directory, platform_name, sizes),
            'environment': environment}


def group_stats(rows):
    result = {}
    for row in rows:
        if row['status'] != 'ok':
            continue
        key = (row['platform'], row['stratum'], row['shelf_size'], row['metric'])
        result.setdefault(key, {'rounds': {}, 'cohorts': {}})
        entry = result[key]
        entry['rounds'].setdefault(row['round'], []).append(row['ms'])
        entry['cohorts'].setdefault(row['cohort'], []).append(row['ms'])
    return result


def build_summary(loaded, expected):
    problems = []
    rows = []
    for item in loaded:
        for row in item['rows']:
            rows.append(dict(row, stratum=item['identity']['stratum']))
    for platform_name in K.PLATFORMS:
        present = sorted(item['round'] for item in loaded if item['platform'] == platform_name)
        if present != [1, 2]:
            problems.append('%s rounds present %r, both independent rounds are required' % (platform_name, present))
    for item in loaded:
        label = '%s round %d' % (item['platform'], item['round'])
        ok_launches = len(item['launches'])
        if ok_launches != item['planned_launches']:
            problems.append('%s ran %d of %d planned launches' % (label, ok_launches, item['planned_launches']))
        failed_launches = [launch.get('launch_id', launch.get('launch')) for launch in item['launches']
                           if launch.get('ok') is False or launch.get('failure')
                           or launch.get('observation_failure')]
        if failed_launches:
            problems.append('%s has failed launches %r' % (label, failed_launches))
        if len(item['memory']) != len(item['launches']):
            problems.append('%s has %d memory records for %d launches' % (label, len(item['memory']),
                                                                         len(item['launches'])))
        bad = [row for row in item['rows'] if row['status'] != 'ok'
               and not (row['status'] == 'not_observed' and row['metric'] in NOT_OBSERVED_OK)]
        if bad:
            problems.append('%s has %d non-ok samples, first %s (%s)' % (label, len(bad), bad[0]['sample_id'],
                                                                         bad[0]['status']))
        covered = {(row['shelf_size'], row['metric']) for row in item['rows'] if row['status'] == 'ok'}
        for size in K.SHELF_SIZES:
            for metric in sorted(REQUIRED_METRICS[item['platform']]):
                if (size, metric) not in covered:
                    problems.append('%s n%d never produced an ok %s sample' % (label, size, metric))
    grouped = group_stats(rows)
    metrics = []
    for (platform_name, stratum, size, metric), entry in sorted(grouped.items()):
        pooled = [value for values in entry['rounds'].values() for value in values]
        per_round = {str(number): K.stats(values) for number, values in sorted(entry['rounds'].items())}
        record = {'platform': platform_name, 'stratum': stratum, 'shelf_size': size, 'metric': metric,
                  'unit': K.METRICS[metric], 'pooled': K.stats(pooled), 'per_round': per_round,
                  'by_cohort': {name: K.stats(values) for name, values in sorted(entry['cohorts'].items())},
                  'rounds_in_stratum': sorted(entry['rounds'])}
        p95s = [stat['p95'] for stat in per_round.values() if stat['p95'] is not None]
        record['proposal'] = {
            'approved': False, 'basis': 'ceil(%.2f * max per-round p95) inside this stratum' % PROPOSAL_FACTOR,
            'proposed_p95_limit_ms': math.ceil(PROPOSAL_FACTOR * max(p95s)) if p95s and len(pooled) >= PROPOSAL_MIN_N else None,
            'withheld_reason': None if len(pooled) >= PROPOSAL_MIN_N else
            'fewer than %d samples in this stratum' % PROPOSAL_MIN_N}
        record['baseline_scope'] = 'both rounds' if len(entry['rounds']) == 2 else 'single round only'
        metrics.append(record)
    memory = {}
    for item in loaded:
        for record in item['memory']:
            key = (item['platform'], item['identity']['stratum'], record['shelf_size'])
            bucket = memory.setdefault(key, {'final': [], 'peak': [], 'private': [], 'rounds': set()})
            bucket['final'].append(record['rss_final_bytes'])
            bucket['peak'].append(record['rss_peak_bytes'])
            if record.get('private_peak_bytes'):
                bucket['private'].append(record['private_peak_bytes'])
            bucket['rounds'].add(item['round'])
    memory_out = [{'platform': key[0], 'stratum': key[1], 'shelf_size': key[2],
                   'rss_final_bytes': K.stats(bucket['final']), 'rss_peak_bytes': K.stats(bucket['peak']),
                   'private_peak_bytes': K.stats(bucket['private']) if bucket['private'] else None,
                   'rounds': sorted(bucket['rounds']), 'definition': K.RSS_DEFINITION[key[0]]}
                  for key, bucket in sorted(memory.items())]
    strata = {}
    for item in loaded:
        strata.setdefault(item['platform'], {}).setdefault(item['identity']['stratum'], []).append(item['round'])
    return {
        'schema': K.SCHEMA, 'measurement_complete': not problems, 'problems': problems,
        'budget_approved': False, 'frame_time_measured': False,
        'source': expected['source'], 'run_id': str(expected['run']), 'attempt': str(expected['attempt']),
        'percentile_definition': 'nearest rank: value at rank ceil(p*n/100) of the sorted samples',
        'strata': {platform_name: {name: sorted(numbers) for name, numbers in value.items()}
                   for platform_name, value in strata.items()},
        'cross_stratum_pooling': False,
        'identities': [dict(item['identity'], directory=item['directory']) for item in loaded],
        'rows_total': len(rows), 'rows_ok': sum(1 for row in rows if row['status'] == 'ok'),
        'rows_not_ok': sum(1 for row in rows if row['status'] != 'ok'),
        'metrics': metrics, 'memory': memory_out}


# -- self test --------------------------------------------------------------

def synthetic_round(root, platform_name, number, source, run, attempt, stratum='s', spoil=None):
    directory = Path(root) / ('%s-r%d' % (platform_name, number))
    directory.mkdir(parents=True)
    rows, launches, memory = [], [], []
    for size in K.SHELF_SIZES:
        identity = {'platform': platform_name, 'round': number, 'consumer_sha': source, 'run_id': run,
                    'attempt': attempt, 'job': 'j', 'program_sha256': 'a' * 64, 'producer_source': 'p',
                    'sdk_version': '3.41.0', 'stratum': stratum, 'shelf_size': size}
        K.write_json(directory / ('identity-n%d.json' % size), identity)
        launch = '%s%d-n%d-00' % (platform_name[0], number, size)
        launches.append({'launch': launch, 'ok': True})
        memory.append({'platform': platform_name, 'round': number, 'shelf_size': size, 'launch': launch,
                       'rss_final_bytes': 100 << 20, 'rss_peak_bytes': 120 << 20, 'private_peak_bytes': None})
        for metric in sorted(REQUIRED_METRICS[platform_name]):
            for slot in range(8):
                rows.append(K.sample_row(identity, launch, 'cohort', metric, slot, 'ok', 5.0 + slot + number))
    K.write_json(directory / 'samples.json', {'schema': 1, 'rows': rows})
    K.write_json(directory / 'launches.json', {'schema': 1, 'launches': launches})
    K.write_json(directory / 'memory.json', {'schema': 1, 'records': memory})
    K.write_json(directory / 'environment.json', {'cpu': {'stratum': {'id': stratum}}})
    if platform_name == 'windows':
        K.write_json(directory / 'plan.json', {'launch_counts': {'cold': 1}})
    else:
        K.write_json(directory / 'plan.json', {'launches_per_size': 1})
    if spoil == 'row':
        rows[0]['status'] = 'failed'
        K.write_json(directory / 'samples.json', {'schema': 1, 'rows': rows})
    K.write_json(directory / 'bundle.json', K.bundle_for(directory))
    if spoil == 'bundle':
        (directory / 'launches.json').write_text('{"schema": 1, "launches": []}\n')
    return directory


def self_test():
    K.self_test()
    expected = {'source': 'f' * 40, 'run': '1', 'attempt': '1'}

    def run(spoil=None, run_id='1', second_stratum='s'):
        with tempfile.TemporaryDirectory() as root:
            loaded = []
            for platform_name in K.PLATFORMS:
                for number in (1, 2):
                    directory = synthetic_round(root, platform_name, number, 'f' * 40, '1', '1',
                                                second_stratum if number == 2 else 's',
                                                spoil if (platform_name, number) == ('gtk', 2) else None)
                    loaded.append(load_round(directory, platform_name,
                                             dict(expected, run=run_id)))
            return build_summary(loaded, dict(expected, run=run_id))

    good = run()
    assert good['measurement_complete'], good['problems']
    assert good['budget_approved'] is False and good['frame_time_measured'] is False
    assert all(entry['proposal']['approved'] is False for entry in good['metrics'])
    assert run(second_stratum='other')['strata']['gtk'] == {'other': [2], 's': [1]}
    assert run(spoil='row')['measurement_complete'] is False
    for spoil, run_id in ((None, '2'), ('bundle', '1')):
        try:
            run(spoil, run_id)
        except K.Rejected:
            continue
        raise AssertionError('spoiled evidence was accepted: %r' % ((spoil, run_id),))
    print('aggregate self-test ok')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--round', action='append', default=[], metavar='PLATFORM=DIR')
    parser.add_argument('--source')
    parser.add_argument('--run')
    parser.add_argument('--attempt')
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
        return
    expected = {'source': arguments.source, 'run': arguments.run, 'attempt': arguments.attempt}
    loaded = []
    for item in arguments.round:
        platform_name, directory = item.split('=', 1)
        loaded.append(load_round(directory, platform_name, expected))
    summary = build_summary(loaded, expected)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    K.write_json(arguments.output, summary)
    print(json.dumps({'measurement_complete': summary['measurement_complete'],
                      'problems': summary['problems'], 'rows_total': summary['rows_total'],
                      'rows_not_ok': summary['rows_not_ok']}))
    if not summary['measurement_complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
