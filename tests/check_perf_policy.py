#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check E3 identity and non-performance gate without running SDK matrices."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from perf_policy import advisory


def main():
    with patch('perf_policy.environment', return_value={'cpu': 'fixture', 'cores': 2, 'memory_bytes': 1024, 'os': 'fixture', 'kernel': 'fixture', 'compiler': 'fixture', 'flags': {}, 'runner_label': 'fixture'}):
        report = advisory({'accepted': True, 'problems': ['retained raw failure']})
    assert report['advisory'] is True and report['accepted'] is False
    assert report['problems'] == ['retained raw failure']
    assert report['policy']['issue'] == 32
    doc = yaml.load((ROOT / '.github/workflows/reading-required-core.yml').read_text(), Loader=yaml.BaseLoader)
    expected = {'protocol', 'native', 'profiles', 'platforms', 'corpus'}
    assert set(doc['jobs']) == expected | {'required'}
    assert set(doc['jobs']['required']['needs']) == expected
    assert doc['jobs']['required']['name'] == 'reading-required-core'
    script = doc['jobs']['required']['steps'][0]['run'].split("python3 - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    for failed in (None, 'protocol', 'native', 'profiles', 'platforms', 'corpus'):
        needs = {key: {'result': 'success'} for key in expected}
        if failed:
            needs[failed]['result'] = 'failure'
        result = subprocess.run([sys.executable, '-c', script], env=dict(os.environ, UPSTREAM_RESULTS=json.dumps(needs)), text=True, capture_output=True)
        assert result.returncode == int(failed is not None), result.stdout + result.stderr
    print('PASS: advisory never grants acceptance; every non-performance group remains blocking')


if __name__ == '__main__':
    main()
