#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Restore the tested simulator's Booted state and locate its existing app data."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udid', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'darwin':
        parser.error('Run only on GitHub Actions macOS')
    report = {'schema': 1, 'diagnostic_only': True, 'accepted': False,
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'udid': args.udid,
              'commands': [], 'status': 'failed'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # A second diagnostic phase must not erase the collector's first failure.
    # Reserve the name before any simulator observation and refuse reuse.
    with args.output.open('x'):
        pass

    def command(arguments, timeout):
        record = {'argv': arguments, 'timeout_seconds': timeout,
                  'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        report['commands'].append(record)
        try:
            proc = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def text(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            record.update({'timed_out': True, 'stdout': text(error.stdout), 'stderr': text(error.stderr)})
            raise RuntimeError('simulator command timed out: ' + arguments[2]) from None
        record.update({'exit_code': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})
        if proc.returncode:
            raise RuntimeError('simulator command failed: %s (exit %s)' % (arguments[2], proc.returncode))
        return proc.stdout.strip()

    def state():
        payload = json.loads(command(['xcrun', 'simctl', 'list', 'devices', '--json'], 30))
        matches = [device for devices in payload['devices'].values() for device in devices
                   if device.get('udid') == args.udid]
        if len(matches) != 1 or matches[0].get('isAvailable') is not True:
            raise RuntimeError('tested simulator identity is missing or unavailable')
        return matches[0]['state']

    try:
        report['initial_state'] = state()
        if report['initial_state'] == 'Shutdown':
            command(['xcrun', 'simctl', 'boot', args.udid], 60)
        elif report['initial_state'] != 'Booted':
            raise RuntimeError('unsupported simulator state: ' + report['initial_state'])
        command(['xcrun', 'simctl', 'bootstatus', args.udid, '-b'], 180)
        report['final_state'] = state()
        if report['final_state'] != 'Booted':
            raise RuntimeError('tested simulator did not reach Booted state')
        container = command(['xcrun', 'simctl', 'get_app_container', args.udid, 'org.exreader.host', 'data'], 30)
        if not container or '\n' in container or not Path(container).is_dir():
            raise RuntimeError('existing host data container is unavailable')
        report.update({'status': 'resolved', 'container': container})
        print(container)
        return 0
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        print('Container resolution failed; command evidence: ' + str(args.output), file=sys.stderr)
        return 1
    finally:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
