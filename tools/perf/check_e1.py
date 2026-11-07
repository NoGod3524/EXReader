#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run: python tools/perf/check_e1.py [CAPTURE_DIRECTORY ...]."""
import copy
import json
from pathlib import Path
import sys
from e1_capture import METRICS, derive_budget, metrics, percentile, sha, stats, summarize


def check():
    assert percentile([3, 1, 2], 50) == 2 and percentile([3, 1, 2], 95) == 3
    assert stats([100, 102, 104])['range_over_median_pct'] == 400 / 102
    for bad in ([], [float('nan')], [float('inf')], [-1], [True]):
        try:
            percentile(bad, 50)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Accepted invalid sample {bad}')
    raw = {'success': True, 'stage': 'complete', 'status': 0, 'open_ms': 2,
           'first_visible_ms': 4, 'peak_rss_bytes': 8192,
           'samples': [{'phase': phase, 'total_ms': i + 1, 'render_ms': 1} for i, phase in
                       enumerate(['first'] + ['sequential'] * 32 + ['random'] * 16)]}
    assert metrics(raw)['turn_p95_ms'] == 32
    incomplete = copy.deepcopy(raw)
    incomplete['samples'].pop()
    try:
        metrics(incomplete)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted incomplete operation plan')
    trials = [{'metrics': {key: value for key in METRICS}} for value in (100, 102, 104)]
    assert summarize(trials)['stable']
    noisy = trials + [{'metrics': {key: 120 for key in METRICS}}]
    assert not summarize(noisy)['stable']
    assert not summarize([{'error': 'native failure'}])['stable']
    print('PASS: nearest-rank, invalid samples, complete plan and 10% dispersion rejection')
    for directory in map(Path, sys.argv[1:]):
        env = json.loads((directory / 'env.json').read_text(encoding='utf-8'))
        report = json.loads((directory / 'samples.json').read_text(encoding='utf-8'))
        budgets = json.loads((directory / 'proposed-budgets.json').read_text(encoding='utf-8'))
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        assert all(sha(directory / name) == digest for name, digest in manifest.items()), 'Custody hash mismatch'
        for name, group in report['groups'].items():
            for batch in group['batches']:
                for trial in batch['trials']:
                    if 'metrics' in trial:
                        observed = json.loads((directory / trial['stdout']).read_text(encoding='utf-8'))
                        assert metrics(observed) == trial['metrics']
                assert summarize(batch['trials']) == batch['summary']
            assert group['final'] == group['batches'][-1]['summary']
        assert derive_budget(env, report, sha(directory / 'samples.json')) == budgets, 'Budget was not derived from raw samples'
        print(f'PASS: {directory}: raw hashes, all metrics, dispersion and budget derivation')


if __name__ == '__main__':
    check()
