"""One runnable check of thresholds, fail-closed inputs and retained raw integrity."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
from gate import check
from sample import audit, read
from refresh_baseline import freeze


def refuses(call):
    try:
        call()
    except (OSError, ValueError, KeyError, TypeError):
        return
    raise AssertionError('invalid evidence accepted')


root = Path(sys.argv[1])
baseline = read(root / 'perf-baseline-local.json')
candidate = root / 'qualification/repeat-1'
data, books, sigs = audit(candidate)
# Valid evidence can expose a real false positive; never assert it away here.
assert check(baseline, candidate, local=True)['exit_code'] in (0, 1)
refuses(lambda: check(baseline, candidate))
refuses(lambda: check({'schema': 1, 'status': 'blocked'}, candidate))
for field, value in [('tiers', {'gate': 1.50}), ('books', {}), ('plan', {}),
                     ('frozen_utc', '9999-01-01T00:00:00+00:00'), ('signatures', {})]:
    bad = dict(baseline, **{field: value})
    refuses(lambda: check(bad, candidate, local=True))
book = 'black-boy'
for bad_value in (0, -1, True, float('nan'), float('inf')):
    bad = copy.deepcopy(baseline)
    bad['books'][book]['thread_cycles_p95'] = bad_value
    refuses(lambda: check(bad, candidate, local=True))
for ratio, tier, status in [(1.099, None, 'pass'), (1.10, 'warning', 'pass'),
                            (1.199, 'warning', 'pass'), (1.20, 'gate', 'fail'), (1.35, 'hard', 'fail')]:
    observed = copy.deepcopy(baseline['books'])
    observed[book]['thread_cycles_p95'] *= ratio
    with patch('gate.audit', return_value=(data, observed, sigs)):
        result = check(baseline, candidate, local=True)
    assert result['status'] == status, result
    assert (not result['exceeded']) if tier is None else tier in result['exceeded'][0]['exceeded']
observed = copy.deepcopy(baseline['books'])
observed[book]['wall_ms_p95'] *= 3
with patch('gate.audit', return_value=(data, observed, sigs)):
    assert check(baseline, candidate, local=True)['failed_books'] == [book]
scratch = root / 'build'
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as temporary:
    path = Path(temporary)
    refuses(lambda: freeze(root / 'local-baseline', path / 'fake-ci.json'))
    refuses(lambda: freeze(root / 'qualification/positive-25', path / 'injected-baseline.json', local=True))
    shutil.copytree(candidate, path / 'raw-test')
    target = next((path / 'raw-test/raw').glob('*.json'))
    target.write_bytes(target.read_bytes() + b' ')
    refuses(lambda: audit(path / 'raw-test'))
    target.unlink()
    refuses(lambda: audit(path / 'raw-test'))
print('PASS: tier boundaries, wall watchdog, invalid inputs, missing/tampered raw, CI provenance and injected-baseline refusals')
