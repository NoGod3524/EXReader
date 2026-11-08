"""Small runnable check: accounting, denominator, tampering and local regressions."""
import copy
import math
from pathlib import Path
import shutil
import sys
import tempfile
from load_capture import metrics, read, summarize, check
from e1_capture import sha, write


def rejects(call):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError('invalid evidence accepted')


stamp = {'cycles': 100, 'tsc': 100, 'cpu_100ns': 10, 'switches': 2, 'wall_ms': 10}
samples = [{'total_ms': 10, 'reference_ms': 20, 'load': {
    'before': {'wall_ms': 20, 'work': dict(stamp, tsc=200)},
    'after': {'wall_ms': 80, 'work': dict(stamp, cycles=400, tsc=800)},
    'target': dict(stamp), 'layout': {k: v//2 for k, v in stamp.items()},
    'render': {k: v//2 for k, v in stamp.items()}}}]
assert metrics(samples, True)['ratio'] == .5
assert metrics(samples, True)['wall_sandwich_ratio'] == .25
assert metrics(samples, False)['ratio'] == 1
for bad in (0, -1, math.nan, math.inf, True):
    broken = copy.deepcopy(samples)
    broken[0]['load']['after']['work']['cycles'] = bad
    rejects(lambda: metrics(broken, True))
broken = copy.deepcopy(samples)
broken[0]['load']['layout']['cycles'] += 1
rejects(lambda: metrics(broken, True))
broken = copy.deepcopy(samples)
broken[0]['total_ms'] *= 2  # reproduces omitted chapter-transition work
rejects(lambda: metrics(broken, True))

if len(sys.argv) == 2:
    root = Path(sys.argv[1])
    source, policy = root/'none', read(root/'policy.json')
    baseline = summarize(source)
    assert len(baseline['runs']) == 5 and len(baseline['per_book']) == 19
    with tempfile.TemporaryDirectory(dir=root.parent/'build') as tmp:
        directory = Path(tmp)/'capture'
        shutil.copytree(source, directory)
        manifest = read(directory/'capture.json')
        manifest['sdk_sha256'] = 'f'*64
        manifest['source_revision'] = 'f'*40
        write(directory/'capture.json', manifest)
        result = check(policy, directory)
        assert result['compatible'] and result['signatures_match'] and not result['failed_books']
        book = min(baseline['per_book'], key=lambda b: baseline['per_book'][b]['ratio']['p95'])
        for run in manifest['runs']:
            entry = next(b for b in run['books'] if b['id'] == book)
            path = directory/entry['file']
            raw = read(path)
            for s in raw['samples']:
                for phase in ('layout', 'render'):
                    s['load'][phase]['cycles'] = round(s['load'][phase]['cycles']*1.6)
                s['load']['target']['cycles'] = sum(s['load'][p]['cycles'] for p in ('layout', 'render'))
            write(path, raw)
            entry['sha256'] = sha(path)
        write(directory/'capture.json', manifest)
        result = check(policy, directory)
        assert not result['local_numeric_pass'] and book in result['failed_books']
        path.write_bytes(path.read_bytes()+b' ')
        rejects(lambda: summarize(directory))
    print('19-book raw integrity, SDK compatibility and localized +60% CPU-work rejection passed')
print('cycle geometric denominator, native accounting and invalid observations checks passed')
