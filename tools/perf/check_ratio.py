"""Runnable quantile, signature, zero/NaN and raw-integrity checks."""
import copy
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ratio_capture import metrics, read, summarize, TIERS
from e1_capture import sha, stats, write

samples = [{'total_ms': i, 'reference_ms': 100, 'ratio': i/100} for i in range(1, 33)]
assert metrics(samples)['target_ms'] == 31  # nearest-rank ceil(32*.95)
assert metrics(samples)['ratio'] == .31
assert metrics(samples)['paired_ratio_p95'] == .31
assert stats([100, 100, 100, 100, 105])['range_over_median_pct'] == 5
assert TIERS == {'warning': 1.10, 'gate': 1.25, 'hard': 1.50}
for bad in (0, -1, math.nan, math.inf):
    broken = copy.deepcopy(samples)
    broken[0]['reference_ms'] = bad
    try:
        metrics(broken)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid denominator accepted')
broken = copy.deepcopy(samples)
broken[0]['ratio'] = 1
try:
    metrics(broken)
except ValueError:
    pass
else:
    raise AssertionError('incorrect paired ratio accepted')

if len(sys.argv) == 2:
    source = Path(sys.argv[1])
    report = summarize(source)
    assert len(report['runs']) >= 5
    assert len(report['signatures']) == 19
    with tempfile.TemporaryDirectory() as directory:
        copied = Path(directory)/'capture'
        shutil.copytree(source, copied)
        raw = next((copied/'raw').glob('1-*.json'))
        raw.write_bytes(raw.read_bytes()+b' ')
        try:
            summarize(copied)
        except ValueError as error:
            assert 'digest mismatch' in str(error)
        else:
            raise AssertionError('raw tampering accepted')
    policy = source.parent/'ratio-policy.json'
    if policy.exists():
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)/'capture'
            shutil.copytree(source, copied)
            manifest = read(copied/'capture.json')
            manifest['source_revision'] = 'f'*40
            manifest['sdk_sha256'] = 'f'*64
            write(copied/'capture.json', manifest)
            result = Path(directory)/'result.json'
            command = [sys.executable, str(Path(__file__).with_name('ratio_capture.py')), 'check',
                       str(policy), str(copied), str(result)]
            control = subprocess.run(command, capture_output=True)
            report_control = read(result)
            assert report_control['compatible'] and report_control['signatures_match']
            assert not report_control['failed_books'] and not report_control['exceeded']
            assert bool(control.returncode == 0) == summarize(source)['eligible']
            # Inject a localized 60% slowdown in the fastest book. It can hide
            # below the pooled p95; the independently frozen book hard cap must catch it.
            book = min(report['per_book'], key=lambda key: report['per_book'][key]['ratio']['p95'])
            for run in manifest['runs']:
                entry = next(b for b in run['books'] if b['id'] == book)
                path = copied/entry['file']
                raw = read(path)
                for sample in raw['samples']:
                    sample['total_ms'] *= 1.6
                    sample['target_ms'] = sample['total_ms']
                    sample['ratio'] = sample['total_ms']/sample['reference_ms']
                write(path, raw)
                entry['sha256'] = sha(path)
            write(copied/'capture.json', manifest)
            slowed = subprocess.run(command, capture_output=True)
            negative = read(result)
            assert slowed.returncode != 0 and book in negative['failed_books']
            row = next(r for r in negative['book_comparisons'] if r['id'] == book)
            assert 'hard' in row['exceeded']
            print('SDK provenance compatibility and localized +60% slowdown rejection passed')
print('ratio quantile, denominator, pairing and raw-integrity checks passed')
