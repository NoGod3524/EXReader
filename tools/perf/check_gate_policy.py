"""Small runnable boundary and evidence-tampering check; optional capture path exercises raw audit."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from e1_capture import METRICS
from gate_capture import summarize
from gate_policy import audit, derive, TIERS

trials = [{'idle_target_met': True, 'metrics': {key: 100 for key in METRICS}} for _ in range(5)]
assert summarize(trials)['stable']
trials[-1]['metrics']['open_ms'] = 105
assert not summarize(trials)['stable'], '5% is excluded'
trials[-1]['metrics']['open_ms'] = 104.9
assert summarize(trials)['stable']
trials[-1]['idle_target_met'] = False
assert not summarize(trials)['stable'], 'idle failure invalidates the entire batch'
assert not summarize(trials[:4])['stable'], 'at least five processes'
assert TIERS == {'warning': 1.10, 'gate': 1.25, 'hard': 1.50}

if len(sys.argv) == 2:
    source = Path(sys.argv[1])
    policy = derive(source)
    env, report, summaries, signatures, problems = audit(source)
    assert policy['eligible'] == (not problems)
    for name, summary in summaries.items():
        for metric, values in policy['latency_ms'][name].items():
            assert values['baseline_p95'] == summary['metrics'][metric]['p95']
            assert values['warning'] < values['gate'] < values['hard']
    with tempfile.TemporaryDirectory() as directory:
        copied = Path(directory) / 'capture'
        shutil.copytree(source, copied, ignore=shutil.ignore_patterns('fixed.epub'))
        first = next(iter(report['groups'].values()))['batches'][0]['trials'][0]
        raw = copied / first['stdout'].replace('\\', '/')
        raw.write_bytes(raw.read_bytes() + b' ')
        try:
            audit(copied)
        except ValueError as error:
            assert 'digest mismatch' in str(error)
        else:
            raise AssertionError('raw tampering must be rejected')
print('strict boundary, derivation and raw-tampering checks passed')
