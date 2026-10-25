#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shared statistics, identity and sample-schema rules for the C02 tools.

Cloud-only. Nothing here measures anything: it defines the single sample row
schema both platform drivers write, the nearest-rank statistics, the CPU
stratum identity and the read-time assertions the aggregator applies to every
sample before it may be counted.
"""
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA = 1
ROWS_STATUS = ('ok', 'failed', 'missing', 'not_observed')
SHELF_SIZES = (500, 5000)
PLATFORMS = ('windows', 'gtk')
# metric -> unit. Anything else in a sample row is rejected at read time.
METRICS = {
    'start_window': 'ms', 'start_first_rows': 'ms', 'start_interactive': 'ms',
    'resume_restored': 'ms', 'shelf_scroll_page': 'ms',
    'search_author': 'ms', 'search_clear': 'ms', 'search_title': 'ms',
    'open_book': 'ms', 'page_turn': 'ms', 'back_to_library': 'ms',
    'import_complete': 'ms', 'post_import_search': 'ms',
    'ui_roundtrip_idle': 'ms', 'ui_roundtrip_reading': 'ms', 'ui_roundtrip_import_busy': 'ms',
    # GTK event-driven observation names (frozen sampler vocabulary).
    'startup_shelf_rows': 'ms', 'startup_key_response': 'ms', 'shelf_selection_move': 'ms',
    'search_title_unique': 'ms', 'search_author_literal': 'ms', 'search_empty': 'ms',
    'open_book_applied': 'ms', 'open_book_painted': 'ms',
    'page_turn_forward': 'ms', 'page_turn_backward': 'ms',
    'resume_frame_applied': 'ms', 'resume_frame_painted': 'ms',
    'import_input_response': 'ms', 'import_resize_response': 'ms',
}
MEMORY_FIELDS = ('rss_final_bytes', 'rss_peak_bytes', 'private_peak_bytes')

RSS_DEFINITION = {
    'windows': {'rss': 'PROCESS_MEMORY_COUNTERS_EX.WorkingSetSize of the product process, sampled '
                       'every 20 ms by the observer; rss_peak_bytes = max(PeakWorkingSetSize over '
                       'all samples and the pre-close read); rss_final_bytes = last sample before '
                       'close; private_peak_bytes = max PrivateUsage',
                'scope': 'the single product process, no children'},
    'gtk': {'rss': '/proc/<pid>/status VmRSS read once before close = rss_final_bytes; VmHWM read at '
                   'the same moment = rss_peak_bytes (kernel high-water mark, kB * 1024)',
            'scope': 'the single product process, no children; private_peak_bytes is not measured'},
}


class Rejected(ValueError):
    """A sample, record or bundle violated the evidence contract."""


def require(condition, message):
    if not condition:
        raise Rejected(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def nearest_rank(values, percent):
    """Nearest-rank percentile: the value at rank ceil(p/100 * n) of the sorted samples."""
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, math.ceil(percent * len(ordered) / 100.0))
    return float(ordered[rank - 1])


def stats(values):
    values = [float(value) for value in values]
    if not values:
        return {'n': 0, 'min': None, 'p50': None, 'p95': None, 'max': None}
    return {'n': len(values), 'min': min(values), 'p50': nearest_rank(values, 50),
            'p95': nearest_rank(values, 95), 'max': max(values)}


def cpu_stratum(platform_name, model, logical):
    """Stratum identity: a result may only be compared inside its own stratum."""
    slug = re.sub(r'[^a-z0-9]+', '-', (model or 'unknown').lower()).strip('-') or 'unknown'
    return {'id': '%s/%s/%sc' % (platform_name, slug, logical), 'platform': platform_name,
            'cpu_model': model, 'logical_processors': logical}


def sample_row(identity, launch, cohort, metric, slot, status, ms=None, note=''):
    require(metric in METRICS, 'unknown metric ' + repr(metric))
    require(status in ROWS_STATUS, 'unknown status ' + repr(status))
    return {'sample_id': '%s/%s/%d' % (launch, metric, slot), 'platform': identity['platform'],
            'round': identity['round'], 'shelf_size': identity['shelf_size'],
            'cohort': cohort, 'launch': launch, 'metric': metric, 'slot': slot,
            'status': status, 'ms': None if ms is None else round(float(ms), 3),
            'unit': METRICS[metric], 'note': note}


IDENTITY_FIELDS = ('platform', 'round', 'consumer_sha', 'run_id', 'attempt', 'job', 'program_sha256',
                   'producer_source', 'sdk_version', 'stratum', 'shelf_size')


def assert_row(row, identity):
    """Read-time assertion for one raw sample against its round identity."""
    require(isinstance(row, dict), 'sample is not an object')
    for key in ('sample_id', 'platform', 'round', 'shelf_size', 'cohort', 'launch', 'metric', 'slot',
                'status', 'ms', 'unit'):
        require(key in row, 'sample lacks ' + key)
    require(row['platform'] == identity['platform'], 'sample platform differs: %s' % row['sample_id'])
    require(row['round'] == identity['round'], 'sample round differs: %s' % row['sample_id'])
    require(row['metric'] in METRICS and row['unit'] == METRICS[row['metric']],
            'sample metric/unit unknown: %s' % row['sample_id'])
    require(row['status'] in ROWS_STATUS, 'sample status unknown: %s' % row['sample_id'])
    require(row['shelf_size'] in SHELF_SIZES, 'sample shelf size unknown: %s' % row['sample_id'])
    if row['status'] == 'ok':
        value = row['ms']
        require(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0, 'ok sample without finite time: %s' % row['sample_id'])
    else:
        require(row['ms'] is None or isinstance(row['ms'], (int, float)),
                'failed sample carries a non-numeric time: %s' % row['sample_id'])


def assert_identity(identity, expected_source, expected_run, expected_attempt):
    for key in IDENTITY_FIELDS:
        require(identity.get(key) not in (None, ''), 'identity lacks ' + key)
    require(identity['platform'] in PLATFORMS, 'identity platform unknown')
    require(identity['round'] in (1, 2), 'identity round unknown')
    require(identity['consumer_sha'] == expected_source, 'identity consumer source differs')
    require(str(identity['run_id']) == str(expected_run), 'identity run differs')
    require(str(identity['attempt']) == str(expected_attempt), 'identity attempt differs')
    require(re.fullmatch(r'[0-9a-f]{64}', identity['program_sha256']), 'identity program hash malformed')
    require(identity['shelf_size'] in SHELF_SIZES, 'identity shelf size unknown')


def assert_memory(record, identity):
    require(record.get('platform') == identity['platform'] and record.get('round') == identity['round']
            and record.get('shelf_size') == identity['shelf_size'], 'memory record identity differs')
    for key in ('rss_final_bytes', 'rss_peak_bytes'):
        value = record.get(key)
        require(isinstance(value, int) and value > 0, 'memory %s invalid in %s' % (key, record.get('launch')))
    require(record['rss_peak_bytes'] >= record['rss_final_bytes'] * 0.5, 'memory peak implausible')


def bundle_for(directory):
    """Digest every file under a round directory, excluding the bundle file itself."""
    root = Path(directory)
    files = {}
    for path in sorted(root.rglob('*')):
        if (path.is_file() and path.name != 'bundle.json' and 'perf-host-state' not in path.parts
                and 'external' not in path.parts):
            files[path.relative_to(root).as_posix()] = {'bytes': path.stat().st_size,
                                                         'sha256': sha256_file(path)}
    return {'schema': SCHEMA, 'files': files}


def check_bundle(directory):
    root = Path(directory)
    declared = read_json(root / 'bundle.json')
    require(declared.get('schema') == SCHEMA, 'bundle schema differs')
    actual = bundle_for(root)
    require(declared['files'] == actual['files'], 'bundle digests differ from the extracted files')
    return len(actual['files'])


def self_test():
    assert nearest_rank([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5.0
    assert nearest_rank([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10.0
    assert nearest_rank(list(range(1, 21)), 95) == 19.0
    assert stats([])['n'] == 0 and stats([3.0])['p95'] == 3.0
    assert cpu_stratum('windows', 'Intel(R) Xeon(R) Platinum 8272CL', 4)['id'] == \
        'windows/intel-r-xeon-r-platinum-8272cl/4c'
    identity = {'platform': 'gtk', 'round': 1, 'shelf_size': 500}
    good = sample_row(identity, 'g1-n500-0', 'x', 'page_turn_forward', 0, 'ok', 12.5)
    assert_row(good, identity)
    for broken in (dict(good, ms=float('nan')), dict(good, ms=-1.0), dict(good, status='unknown'),
                   dict(good, metric='made_up'), dict(good, round=2), dict(good, unit='s'),
                   dict(good, ms=None), dict(good, shelf_size=2202)):
        try:
            assert_row(broken, identity)
        except Rejected:
            continue
        raise AssertionError('broken sample accepted: %r' % broken)
    failed = sample_row(identity, 'g1-n500-0', 'x', 'page_turn_forward', 1, 'failed', None, 'timeout')
    assert_row(failed, identity)
    print('common self-test ok')


if __name__ == '__main__':
    self_test()
