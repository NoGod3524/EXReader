"""Observe the failing OS appearance command with its unchanged 45s budget."""
import json
import os
from pathlib import Path
import subprocess
import sys
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
    platform = sys.argv[1] if len(sys.argv)==2 else 'iphone'
    if platform not in ('iphone','ipad'):
        raise RuntimeError('Unknown platform')
    prefix = 'iPhone' if platform=='iphone' else 'iPad'
    runtime, name, udid = max((runtime, row['name'], row['udid']) for runtime, group in rows.items()
                             for row in group if row.get('isAvailable') and row['name'].startswith(prefix))
    report.update(runtime=runtime, device=name, udid=udid)
    command(['xcrun', 'simctl', 'shutdown', udid])
    for argv, timeout in [(['xcrun', 'simctl', 'erase', udid],45),
                          (['xcrun', 'simctl', 'boot', udid],45),
                          (['xcrun', 'simctl', 'bootstatus', udid, '-b'],180)]:
        if command(argv, timeout).get('exit_code') != 0:
            raise RuntimeError('Original simulator initialization failed')
    if command(['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid]).get('exit_code')!=0:
        raise RuntimeError('Native Simulator launch failed')
    if command(['xcrun', 'simctl', 'bootstatus', udid, '-b'],180).get('exit_code')!=0:
        raise RuntimeError('Post-window boot check failed')
    # New diagnostic preparation: query-only bounded readiness. The formal
    # original setter below is issued exactly once with the original45s budget.
    deadline=time.monotonic()+180
    ready=False
    while time.monotonic()<deadline:
        row=command(['xcrun','simctl','ui',udid,'appearance'],min(45,deadline-time.monotonic()))
        if row.get('exit_code')==0 and row.get('stdout','').strip() in ('light','dark'):
            ready=True
            break
    report['query_only_service_ready']=ready
    if not ready:
        raise RuntimeError('Appearance service never became ready inside diagnostic180s')
    if command(['xcrun', 'simctl', 'ui', udid, 'appearance', 'light']).get('exit_code')!=0:
        raise RuntimeError('Original45s setter still failed after readiness')
    observed=command(['xcrun', 'simctl', 'ui', udid, 'appearance'])
    if observed.get('exit_code')!=0 or observed.get('stdout','').strip()!='light':
        raise RuntimeError('Actual appearance readback differs')
    command(['xcrun', 'simctl', 'shutdown', udid])


if __name__ == '__main__':
    main()
