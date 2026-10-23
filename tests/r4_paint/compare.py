"""Cloud-only fresh-process active-clip work accounting comparison."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

if not os.environ.get('GITHUB_ACTIONS'):
    raise SystemExit('Run in GitHub Actions')
baseline, candidate, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=False)
records = []
for repeat in range(3):
    for role, binary in ([('baseline', baseline), ('candidate', candidate)] if repeat % 2 == 0
                         else [('candidate', candidate), ('baseline', baseline)]):
        completed = subprocess.run([str(binary.resolve())], capture_output=True, timeout=120)
        stem = output / f'{repeat}-{role}'
        stem.with_suffix('.stdout').write_bytes(completed.stdout)
        stem.with_suffix('.stderr').write_bytes(completed.stderr)
        rows = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith(b'{')]
        records.append({'role': role, 'repeat': repeat, 'exit': completed.returncode,
            'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'rows': rows})
summary = {'source_sha': os.environ['GITHUB_SHA'], 'baseline_sha': '94a318ddfa09782ccf3a6bd344fc8bf6d47352a4',
    'run_id': os.environ['GITHUB_RUN_ID'], 'budget': 256*1024*1024, 'records': records, 'cases': {}}
for scenario in ('full-canvas', 'tiny-clip-with-hole'):
    case = {}
    for role in ('baseline', 'candidate'):
        rows = [row for record in records if record['role'] == role for row in record['rows'] if row['scenario'] == scenario]
        assert len(rows) == 3
        case[role] = {key: statistics.median(row[key] for row in rows) for key in ('cpu_ms', 'calls', 'charged_work')}
        assert all(row['status'] == (0 if role == 'candidate' and scenario.startswith('tiny') else 6) for row in rows)
    assert len({row['pixel_hash'] for record in records for row in record['rows'] if row['scenario'] == scenario}) == 1
    assert case['baseline']['calls'] == case['candidate']['calls']
    summary['cases'][scenario] = case
summary['accepted'] = all(record['exit'] == 0 for record in records)
(output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['accepted'] else 1)
