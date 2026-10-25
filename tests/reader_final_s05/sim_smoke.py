#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install and launch an app bundle on a clean iPhone or iPad simulator.

The device is erased before the installation, the absence of an earlier
container is asserted, the installed copy is hashed against the source bundle,
the launched process is required to stay alive and to be the installed program,
and the device is erased again afterwards. Every command, exit code and byte
count is retained. A simulator run is simulator evidence only: it never grants
a physical device run, a signing identity or an App Store delivery.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import bundle_copy
import time

APP_PREFIX = {'iphone': 'iPhone', 'ipad': 'iPad'}
ALIVE_SECONDS = 4.0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    import hashlib
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def runtime_version(runtime):
    tail = str(runtime).split('.')[-1]
    numbers = re.findall(r'\d+', tail)
    return '.'.join(numbers[:3]) if numbers else tail


def inventory():
    output = subprocess.run(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'],
                            capture_output=True, text=True, check=True)
    return json.loads(output.stdout)


def select(device_class):
    require(device_class in APP_PREFIX, 'unknown device class: ' + str(device_class))
    prefix = APP_PREFIX[device_class]
    devices = inventory().get('devices') or {}
    candidates = [(runtime, device['name'], device['udid'])
                  for runtime, values in devices.items() for device in values
                  if device.get('isAvailable') and device['name'].startswith(prefix)]
    require(candidates, 'no available %s simulator on this runner' % device_class)

    def rank(item):
        numbers = tuple(int(value) for value in re.findall(r'\d+', runtime_version(item[0]))[:3])
        return (numbers, item[1], item[2])

    runtime, name, udid = sorted(candidates, key=rank, reverse=True)[0]
    return {'runtime': runtime, 'runtime_version': runtime_version(runtime), 'name': name, 'udid': udid}


def _run(app, device_class, output, bundle_identifier, executable):
    app = Path(app).absolute()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    facts = {'device_class': device_class, 'status': 'fail', 'steps': []}
    facts['host'] = {
        'platform': 'darwin',
        'xcode': subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True).stdout.strip(),
        'system': subprocess.run(['sw_vers'], capture_output=True, text=True).stdout.strip(),
    }
    device = select(device_class)
    facts['device'] = device
    udid = device['udid']

    def step(name, argv, timeout=900, check=True):
        proc = subprocess.run([str(value) for value in argv], capture_output=True, text=True, timeout=timeout)
        facts['steps'].append({'name': name, 'argv': [str(value) for value in argv],
                               'exit': proc.returncode, 'stdout': (proc.stdout or '')[-4000:],
                               'stderr': (proc.stderr or '')[-4000:]})
        (output / 'simulator.json').write_text(json.dumps(facts, indent=2) + '\n')
        if check and proc.returncode != 0:
            raise RuntimeError('simulator step failed: %s\n%s\n%s'
                               % (name, (proc.stdout or '')[-2000:], (proc.stderr or '')[-2000:]))
        return proc

    step('shutdown-before-erase', ['xcrun', 'simctl', 'shutdown', udid], timeout=300, check=False)
    step('erase-before-install', ['xcrun', 'simctl', 'erase', udid], timeout=600)
    identity = Path(executable).name
    require(identity, 'the bundle declares no executable to verify')
    require(bundle_identifier, 'the bundle has no CFBundleIdentifier to launch')
    prior = step('container-before-install', ['xcrun', 'simctl', 'get_app_container', udid, bundle_identifier, 'app'],
                 timeout=120, check=False)
    facts['clean'] = {'erased': True, 'prior_container': prior.returncode == 0,
                      'prior_container_exit': prior.returncode,
                      'prior_container_log': ((prior.stdout or '') + (prior.stderr or '')).strip()[-400:]}
    step('boot', ['xcrun', 'simctl', 'boot', udid], timeout=600)
    step('bootstatus', ['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=600)
    step('install', ['xcrun', 'simctl', 'install', udid, str(app)], timeout=900)
    container = step('installed-app-container', ['xcrun', 'simctl', 'get_app_container', udid, bundle_identifier, 'app'],
                     timeout=300)
    installed = Path(container.stdout.strip())
    data = step('installed-data-container', ['xcrun', 'simctl', 'get_app_container', udid, bundle_identifier, 'data'],
                timeout=300, check=False)
    data_path = Path(data.stdout.strip()) if data.returncode == 0 and data.stdout.strip() else None
    installed_executable = installed / identity
    facts['installation'] = {
        'installed_app': str(installed),
        'installed_app_exists': installed.is_dir(),
        'data_container': str(data_path) if data_path else None,
        'documents_dir': bool(data_path and (data_path / 'Documents').is_dir()),
        'executable': identity,
        'source_executable_sha256': sha256(app / identity),
        'installed_executable_sha256': sha256(installed_executable) if installed_executable.is_file() else None,
    }
    facts['installation']['identity_matches'] = (
        facts['installation']['installed_executable_sha256'] is not None and
        facts['installation']['installed_executable_sha256'] == facts['installation']['source_executable_sha256'])
    facts['installation']['bundle_copy'] = bundle_copy.installed_facts(app, installed)
    started = time.time()
    launch = step('launch', ['xcrun', 'simctl', 'launch', udid, bundle_identifier], timeout=300)
    match = re.search(r':\s*(\d+)\s*$', (launch.stdout or '').strip().splitlines()[-1] if (launch.stdout or '').strip() else '')
    pid = int(match.group(1)) if match else None
    time.sleep(ALIVE_SECONDS)
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    program_path = ''
    if pid:
        program = step('running-program', ['ps', '-ww', '-p', str(pid), '-o', 'pid=,comm='], timeout=120, check=False)
        program_path = (program.stdout or '').strip()
    facts['launch'] = {'bundle_identifier': bundle_identifier, 'pid': pid,
                       'alive_after_seconds': ALIVE_SECONDS, 'alive': alive,
                       'program': program_path or None,
                       'expected_program': str(installed_executable.resolve()),
                       'program_matches': bool(pid) and bundle_copy.running_program(pid, program_path, installed_executable)}
    screenshot = step('screenshot', ['xcrun', 'simctl', 'io', udid, 'screenshot', str(output / 'screen.png')],
                      timeout=300, check=False)
    screen = output / 'screen.png'
    facts['screenshot'] = {'captured': screenshot.returncode == 0 and screen.is_file() and screen.stat().st_size > 0,
                           'bytes': screen.stat().st_size if screen.is_file() else 0,
                           'sha256': sha256(screen) if screen.is_file() else None}
    crash_roots = [Path.home() / 'Library/Logs/DiagnosticReports',
                   Path.home() / 'Library/Developer/CoreSimulator/Devices' / udid / 'data/Library/Logs/CrashReporter']
    crash_reports = []
    for root in crash_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            try:
                if not path.is_file() or path.stat().st_mtime < started - 1:
                    continue
                sample = path.read_text(errors='replace')[:65536] if path.suffix in ('.ips', '.crash', '.txt') else ''
                if bundle_identifier in path.name or bundle_identifier in sample:
                    crash_reports.append({'path': str(path), 'bytes': path.stat().st_size})
            except OSError:
                continue
    facts['crash_reports'] = crash_reports
    step('terminate', ['xcrun', 'simctl', 'terminate', udid, bundle_identifier], timeout=300, check=False)
    step('uninstall', ['xcrun', 'simctl', 'uninstall', udid, bundle_identifier], timeout=300, check=False)
    step('shutdown-after-run', ['xcrun', 'simctl', 'shutdown', udid], timeout=300, check=False)
    step('erase-after-run', ['xcrun', 'simctl', 'erase', udid], timeout=600, check=False)
    clean = facts['clean']['erased'] and not facts['clean']['prior_container']
    facts['status'] = 'pass' if all([clean, facts['installation']['installed_app_exists'],
                                     facts['installation']['identity_matches'], pid is not None,
                                     alive, facts['launch']['program_matches']]) else 'fail'
    (output / 'simulator.json').write_text(json.dumps(facts, indent=2) + '\n')
    return facts


def run(app, device_class, output, bundle_identifier, executable):
    output = Path(output)
    try:
        return _run(app, device_class, output, bundle_identifier, executable)
    except Exception as error:
        record = {}
        path = output / 'simulator.json'
        if path.is_file():
            record = json.loads(path.read_text())
        record.setdefault('device_class', device_class)
        record['status'] = 'fail'
        record['error'] = str(error)
        output.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + '\n')
        raise
