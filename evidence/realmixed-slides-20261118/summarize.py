# SPDX-License-Identifier: MIT
"""Summarize the recorded cohort, ablations, and native validation."""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

RAW = Path(__file__).with_name('raw')
COHORTS = {'slides': range(1, 22), 'deck': range(22, 52), 'Word': range(52, 77),
           'PPTX': range(77, 117), 'Excel': (117, 119), 'Chinese': (118, 120)}


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes())


def captures(directory):
    cases = defaultdict(list)
    for path in sorted(directory.glob('real-mixed-120-r*.json.gz')):
        data = read(path)
        assert data['pages'] == list(COHORTS['slides']) and 0 <= data['idle_before'] <= 15
        cases[data['name']].append(data)
    return cases


def sweeps(data, arm):
    return [sum(values) / 1e6 for values in data['times_ns'][arm][1:]]


def baseline(rounds):
    arms = ('X full', 'J full')
    totals = [median(median(sweeps(r, k)) for r in rounds) for k in arms]
    gaps = [median(x - j for x, j in zip(*(sweeps(r, k) for k in arms))) for r in rounds]
    return *totals, totals[0] - totals[1], median(gaps)


def ablation(rounds):
    arms = ('X full', 'J full', 'X edit', 'J edit')
    times = [mean(t for r in rounds for t in sweeps(r, arm)) for arm in arms]
    gaps = [mean(x - j - xe + je for x, j, xe, je in zip(*(sweeps(r, k) for k in arms)))
            for r in rounds]
    hashes = rounds[0]['hashes']
    assert all(r['hashes'] == hashes for r in rounds)
    changes = [sum(x != y for x, y in zip(hashes[k + ' full'], hashes[k + ' edit'])) for k in 'XJ']
    return *times, times[0] - times[1], times[2] - times[3], mean(gaps), min(gaps), max(gaps), *changes


def paired(data):
    a, b = [data['summary'][k]['round_sum_ms'] for k in 'AB']
    saves = [x - y for x, y in zip(a, b)]
    return median(a), median(b), median(saves), min(saves), max(saves), sum(x > 0 for x in saves)


def cohort(data, pages):
    rows = [page for page in data['pages'] if page['page'] in pages]
    a, b = [sum(p[k + '_p50_ms'] for p in rows) for k in 'AB']
    a_sums, b_sums = [[sum(row[k][i] for row in rows) for i in range(data['runs'])] for k in 'AB']
    return a, b, 100 * (b / a - 1), median(100 * (y / x - 1) for x, y in zip(a_sums, b_sums))


def show(label, values):
    print(label, '|', ' | '.join(f'{v:.2f}' if isinstance(v, float) else str(v) for v in values))


if __name__ == '__main__':
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW
    print(directory.name)
    for name, rounds in captures(directory).items():
        show(f'{name} ({len(rounds)} rounds)', baseline(rounds) if name == 'baseline' else ablation(rounds))
    for path in sorted(directory.glob('*.json')):
        data = read(path)
        if not data.get('runs'):
            continue
        show(path.name, paired(data))
        if path.name == 'production-real-mixed-120-1200.json':
            for label, pages in COHORTS.items():
                show(label, cohort(data, pages))
        if path.name.startswith(('production-pptx-', 'production-deck-', 'production-word-')):
            show('warm per-render p50', [data['summary'][k]['p50_ms'] for k in 'AB'])
