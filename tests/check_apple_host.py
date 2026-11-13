#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check isolated simulator ownership and failure propagation without Xcode."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main():
    spec = importlib.util.spec_from_file_location(
        'apple_host', Path(__file__).resolve().parents[1]/'tools/check_apple_host.py')
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    cases = 0
    for family in ('iphone', 'ipad'):
        for failure in (None, 'bootstatus', 'install', 'stale-report', 'failed-report', 'short-report'):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                bundle = root/'EXReader.app'; bundle.mkdir()
                container = root/'container'
                (container/'Documents').mkdir(parents=True)
                source = container/'Documents/exreader-host-selftest.json'
                if failure == 'stale-report':
                    source.write_text('{}')
                output = root/'evidence'
                runtime = 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'
                device_type = 'com.apple.CoreSimulator.SimDeviceType.'+family
                inventory = {'devices': {runtime: [{
                    'udid': 'preinstalled', 'isAvailable': True, 'state': 'Booted',
                    'name': family, 'deviceTypeIdentifier': device_type}]}}
                calls = []

                def command(*args):
                    calls.append(args)
                    operation = args[2]
                    if operation == 'list':
                        return json.dumps(inventory)
                    if operation == 'create':
                        assert args[4:] == (device_type, runtime)
                        return 'isolated'
                    assert args[3] == 'isolated', 'modified a pre-existing simulator'
                    if operation == failure:
                        raise subprocess.CalledProcessError(1, args)
                    if operation == 'get_app_container':
                        return str(container)
                    if operation == 'launch':
                        source.write_text(json.dumps({
                            'passed': failure != 'failed-report',
                            'check_count': 19 if failure == 'short-report' else 21}))
                    if operation == 'io':
                        Path(args[-1]).write_bytes(b'PNG')
                    return ''

                def run(args, **kwargs):
                    calls.append(tuple(args))
                    assert args[3] == 'isolated', 'modified a pre-existing simulator'
                    if args[2] == 'bootstatus':
                        assert kwargs == {'check': True, 'timeout': 180}
                        if failure == 'bootstatus':
                            raise subprocess.TimeoutExpired(args, 180)
                    return subprocess.CompletedProcess(args, 0)

                argv = ['check', '--bundle', str(bundle), '--device', family, '--output', str(output)]
                error = None
                with patch.object(sys, 'argv', argv), patch.object(sys, 'platform', 'darwin'), \
                     patch.object(host, 'command', command), patch.object(host.subprocess, 'run', run), \
                     patch.object(host.time, 'sleep'):
                    try:
                        host.main()
                    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, RuntimeError) as caught:
                        error = caught
                assert (error is not None) == (failure is not None), (family, failure, error)
                assert calls[-2:] == [('xcrun', 'simctl', 'shutdown', 'isolated'),
                                      ('xcrun', 'simctl', 'delete', 'isolated')]
                assert json.loads((output/'device.json').read_text())['udid'] == 'isolated'
                operations = [call[2] for call in calls]
                if failure in ('bootstatus', 'install', 'stale-report'):
                    assert 'launch' not in operations and not (output/'report.json').exists()
                if failure is None:
                    assert operations == ['list', 'create', 'boot', 'bootstatus', 'install',
                                          'get_app_container', 'launch', 'io', 'shutdown', 'delete']
                    assert (output/'report.json').read_bytes() == source.read_bytes()
                    assert (output/'screen.png').exists()
                cases += 1
    print(f'Apple host simulator checks: {cases} passed')


if __name__ == '__main__':
    main()
