"""Run the immutable complete G1 suite at either physical installed prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from g1 import BINARY_KEYS, REPORT_TAILS

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
p = argparse.ArgumentParser()
p.add_argument('--prefix', type=Path, required=True)
p.add_argument('--phase', choices=('fresh', 'relocated'), required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
scratch = root / 'build/g1-initial'
output = root / 'build/composition/g1/initial'
destination = output.parent / a.phase
assert not destination.exists(), 'phase evidence already exists'
if scratch.exists():
    # The fixed workspace-local scratch belongs only to this immutable runner.
    assert scratch.resolve().is_relative_to((root / 'build').resolve())
    shutil.rmtree(scratch)
assert not output.exists(), 'previous phase was not sealed'
done = subprocess.run([sys.executable, str(root / 'tests/reader_g1_integration/run_suites.py'),
                       '--prefix', str(a.prefix.resolve())], cwd=root)
if output.exists():
    output.rename(destination)
if done.returncode:
    raise SystemExit(done.returncode)
suffix = '.exe' if os.name == 'nt' else ''
(destination / 'binaries').mkdir()
for path, key in BINARY_KEYS.items():
    shutil.copyfile(scratch / (path + suffix), destination / 'binaries' / key)
reports = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
           for name in REPORT_TAILS if name != 'phase.json'}
record = dict(accepted=True, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
              attempt=os.environ['GITHUB_RUN_ATTEMPT'], platform=os.environ['RUNNER_OS'], phase=a.phase,
              physical_prefix=str(a.prefix.resolve()), reports=reports)
(destination / 'phase.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
