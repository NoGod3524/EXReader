#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the native Apple host self-check and retain its report and screenshot."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def command(*args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()


def wait_for(path, timeout=180, process=None):
    end = time.monotonic()+timeout
    while not path.exists():
        if process is not None and process.poll() is not None:
            raise RuntimeError('Reference host exited before writing its report')
        if time.monotonic() >= end:
            raise TimeoutError('Reference host did not write its report')
        time.sleep(.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--device', choices=['macos', 'iphone', 'ipad'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or not args.bundle.is_dir():
        parser.error('Run on macOS with an existing app bundle')
    output = args.output.absolute()
    if output.exists():
        parser.error('Choose a new evidence directory')
    output.mkdir(parents=True)
    report = output/'report.json'
    if args.device == 'macos':
        env = os.environ.copy()
        env['EXR_SELFTEST_OUTPUT'] = str(report)
        with (output/'application.log').open('wb') as log:
            process = subprocess.Popen([str(args.bundle.absolute()/'Contents/MacOS/EXReader'), '--self-test'],
                                       stdout=log, stderr=subprocess.STDOUT, env=env)
            try:
                wait_for(report, process=process)
                time.sleep(1)
                subprocess.run(['screencapture', '-x', str(output/'screen.png')], check=False)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    else:
        inventory = json.loads(command('xcrun', 'simctl', 'list', 'devices', 'available', '--json'))
        candidates = [(runtime, d) for runtime, devices in inventory['devices'].items() for d in devices
                      if d['isAvailable'] and d['name'].lower().startswith(args.device)]
        if not candidates:
            raise RuntimeError('No available '+args.device+' simulator')
        runtime, device = sorted(candidates, key=lambda row: (row[0], row[1]['name']), reverse=True)[0]
        udid = device['udid']
        booted_here = device['state'] != 'Booted'
        try:
            if booted_here:
                command('xcrun', 'simctl', 'boot', udid)
            subprocess.run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], check=True, timeout=180)
            command('xcrun', 'simctl', 'install', udid, args.bundle.absolute())
            container = Path(command('xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data'))
            source = container/'Documents/exreader-host-selftest.json'
            if source.exists():
                raise RuntimeError('Simulator contains earlier evidence; choose a fresh simulator')
            command('xcrun', 'simctl', 'launch', udid, 'org.exreader.host', '--self-test')
            wait_for(source)
            shutil.copyfile(source, report)
            time.sleep(1)
            command('xcrun', 'simctl', 'io', udid, 'screenshot', output/'screen.png')
            (output/'device.json').write_text(json.dumps({'runtime': runtime, **device}, indent=2)+'\n')
        finally:
            if booted_here:
                subprocess.run(['xcrun', 'simctl', 'shutdown', udid], check=False)
    result = json.loads(report.read_text())
    if result.get('passed') is not True or result.get('check_count', 0) < 20:
        raise RuntimeError('Reference host self-check failed; retained report: '+str(report))
    print(args.device+': '+str(result['check_count'])+' native host checks passed')


if __name__ == '__main__':
    main()
