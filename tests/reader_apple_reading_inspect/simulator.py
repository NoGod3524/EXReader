"""Observe the failing OS appearance command with its unchanged 45s budget."""
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    out = Path('build/apple-simulator-observation')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(accepted=False, diagnostic_only=True, source=os.environ['GITHUB_SHA'],
                  run=os.environ['GITHUB_RUN_ID'], commands=[])

    def command(argv, timeout=45):
        started = time.monotonic()
        row = dict(argv=argv, timeout_seconds=timeout)
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired:
            row.update(exit_code=None, timed_out=True)
        row['elapsed_seconds'] = time.monotonic() - started
        report['commands'].append(row)
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(row), flush=True)
        return row

    devices = command(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], 180)
    if devices.get('exit_code') != 0:
        raise RuntimeError('Device inventory unavailable')
    rows = json.loads(devices['stdout'])['devices']
    runtime, name, udid = max((runtime, row['name'], row['udid']) for runtime, group in rows.items()
                             for row in group if row.get('isAvailable') and row['name'].startswith('iPhone'))
    report.update(runtime=runtime, device=name, udid=udid)
    command(['xcrun', 'simctl', 'shutdown', udid])
    for argv, timeout in [(['xcrun', 'simctl', 'erase', udid],45),
                          (['xcrun', 'simctl', 'boot', udid],45),
                          (['xcrun', 'simctl', 'bootstatus', udid, '-b'],180)]:
        if command(argv, timeout).get('exit_code') != 0:
            raise RuntimeError('Original simulator initialization failed')
    # Preserve the original command and timeout before trying a native UI launch.
    command(['xcrun', 'simctl', 'ui', udid, 'appearance', 'light'])
    command(['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid])
    command(['xcrun', 'simctl', 'bootstatus', udid, '-b'],180)
    command(['xcrun', 'simctl', 'ui', udid, 'appearance', 'light'])
    command(['xcrun', 'simctl', 'ui', udid, 'appearance'])
    command(['xcrun', 'simctl', 'shutdown', udid])


if __name__ == '__main__':
    main()
