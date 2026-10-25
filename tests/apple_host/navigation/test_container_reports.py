# SPDX-License-Identifier: MIT
"""Actions-only rejection tests for immutable container observation files."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = Path(__file__).resolve().parents[1] / 'resolve_container.py'
    spec = importlib.util.spec_from_file_location('container_locator', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        container = root / 'data'; container.mkdir()
        output = root / 'collector.json'
        state = json.dumps({'devices': {'runtime': [{'udid': 'fixture-uuid', 'isAvailable': True, 'state': 'Booted'}]}})
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            if argv[2] == 'list': return subprocess.CompletedProcess(argv, 0, state, '')
            if argv[2] == 'bootstatus': return subprocess.CompletedProcess(argv, 0, '', '')
            return subprocess.CompletedProcess(argv, 1, 'first stdout', 'first stderr')

        arguments = ['locator', '--udid', 'fixture-uuid', '--output', str(output)]
        with patch.object(sys, 'argv', arguments), patch.object(sys, 'platform', 'darwin'), patch.object(module.subprocess, 'run', run):
            assert module.main() == 1
        first = output.read_bytes(); report = json.loads(first)
        assert report['status'] == 'failed' and len(report['commands']) == 4
        assert report['commands'][-1]['stdout'] == 'first stdout' and report['commands'][-1]['stderr'] == 'first stderr'
        assert report['commands'][-1]['exit_code'] == 1
        calls.clear()
        with patch.object(sys, 'argv', arguments), patch.object(sys, 'platform', 'darwin'), patch.object(module.subprocess, 'run', run):
            try: module.main()
            except FileExistsError: pass
            else: raise AssertionError('prior report overwritten')
        assert output.read_bytes() == first and not calls

        def successful(argv, **kwargs):
            if argv[2] == 'get_app_container': return subprocess.CompletedProcess(argv, 0, str(container), '')
            return subprocess.CompletedProcess(argv, 0, state if argv[2] == 'list' else '', '')

        trace = root / 'always-trace.json'
        with patch.object(sys, 'argv', ['locator', '--udid', 'fixture-uuid', '--output', str(trace)]), \
             patch.object(sys, 'platform', 'darwin'), patch.object(module.subprocess, 'run', successful):
            assert module.main() == 0
        assert json.loads(trace.read_text())['status'] == 'resolved' and output.read_bytes() == first
        timeout = root / 'timeout.json'
        with patch.object(sys, 'argv', ['locator', '--udid', 'fixture-uuid', '--output', str(timeout)]), \
             patch.object(sys, 'platform', 'darwin'), \
             patch.object(module.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['xcrun'], 30, b'partial out', b'partial err')):
            assert module.main() == 1
        last = json.loads(timeout.read_text())['commands'][0]
        assert last['timeout_seconds'] == 30 and last['timed_out'] is True
        assert last['stdout'] == 'partial out' and last['stderr'] == 'partial err'
    workflow = (source.parents[2] / '.github/workflows/reader-apple-shelf.yml').read_text()
    assert workflow.count('container-collector.json') == workflow.count('container-always-trace.json') == 1
    assert 'build/apple-shelf-ui/container.json' not in workflow
    print('CONTAINER_REPORTS checks=5 passed=5 first_failure_preserved=true retries=0')


if __name__ == '__main__':
    main()
