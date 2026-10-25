#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only real API34 installation, UI instrumentation and process death."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from contract import CASES, PROCESS_CASES, UNAVAILABLE

ROOT = Path('build/android-display')
LOGS = ROOT / 'logs'
EVIDENCE = ROOT / 'evidence'
PACKAGE = 'org.exreader.display.probe'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(label, *args, allowed=False):
    done = subprocess.run(args, capture_output=True, timeout=360)
    (LOGS / (label + '.stdout')).write_bytes(done.stdout)
    (LOGS / (label + '.stderr')).write_bytes(done.stderr)
    need(allowed or done.returncode == 0, label + ' failed: ' + done.stderr.decode('utf-8', 'replace')[-1000:])
    return done.stdout.decode('utf-8', 'strict').strip()


def device_report(phase):
    target = EVIDENCE / (phase + '.json')
    for _ in range(90):
        done = subprocess.run(['adb', 'exec-out', 'run-as', PACKAGE, 'cat', 'files/' + phase + '.json'],
                              capture_output=True, timeout=20)
        if done.returncode == 0:
            target.write_bytes(done.stdout)
            return json.loads(done.stdout)
        time.sleep(1)
    raise RuntimeError('missing actual device report: ' + phase)


def identity(path):
    data = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    LOGS.mkdir(parents=True, exist_ok=True); EVIDENCE.mkdir(parents=True, exist_ok=True)
    summary = {'accepted': False, 'physical_effect': 'UNAVAILABLE', 'unavailable': UNAVAILABLE}
    try:
        need(command('api', 'adb', 'shell', 'getprop', 'ro.build.version.sdk') == '34', 'API34 required')
        need(command('abi', 'adb', 'shell', 'getprop', 'ro.product.cpu.abi') == 'x86_64', 'x86_64 required')
        global_before = {key: command('global-before-' + key, 'adb', 'shell', 'settings', 'get', 'system', key)
                         for key in ('screen_brightness', 'screen_brightness_mode')}
        command('uninstall', 'adb', 'uninstall', PACKAGE, allowed=True)
        apk = ROOT / 'consumer/probe-debug.apk'
        command('install', 'adb', 'install', str(apk))
        installed = command('installed-path', 'adb', 'shell', 'pm', 'path', PACKAGE)
        need(len(installed.splitlines()) == 1 and installed.startswith('package:'), 'unique installed package')
        command('pull-installed', 'adb', 'pull', installed[8:], str(ROOT / 'consumer/installed.apk'))
        need(apk.read_bytes() == (ROOT / 'consumer/installed.apk').read_bytes(), 'installed APK differs')
        instrument = command('instrumentation', 'adb', 'shell', 'am', 'instrument', '-w', '-r',
                             PACKAGE + '/.DisplayInstrumentation')
        suite = device_report('suite')
        need('INSTRUMENTATION_CODE: -1' in instrument, 'instrumentation result code')
        need([row['name'] for row in suite['cases']] == CASES, 'exact named UI cases')
        need(suite['accepted'] is True and all(row['passed'] is True for row in suite['cases']), 'UI failures retained')
        command('force-stop-before-seed', 'adb', 'shell', 'am', 'force-stop', PACKAGE)
        command('launch-seed', 'adb', 'shell', 'am', 'start', '-W', '-n', PACKAGE + '/.ProbeActivity', '--es', 'phase', 'seed')
        seed = device_report('process-seed')
        need(abs(seed['brightness'] - 0.73) < 0.00001 and seed['keep'] is True, 'seed active real window')
        live_pid = command('pid-before', 'adb', 'shell', 'pidof', PACKAGE)
        need(live_pid == str(seed['pid']), 'process seed PID binding')
        command('force-stop-active', 'adb', 'shell', 'am', 'force-stop', PACKAGE)
        dead_pid = command('pid-after-stop', 'adb', 'shell', 'pidof', PACKAGE, allowed=True)
        need(dead_pid == '', 'actual process must be absent after force-stop')
        command('launch-reopen', 'adb', 'shell', 'am', 'start', '-W', '-n', PACKAGE + '/.ProbeActivity', '--es', 'phase', 'reopen')
        reopened = device_report('process-reopen')
        new_pid = command('pid-reopen', 'adb', 'shell', 'pidof', PACKAGE)
        need(new_pid == str(reopened['pid']) and seed['pid'] != reopened['pid'], 'different actual process')
        need(reopened['brightness'] == -1 and reopened['keep'] is False, 'fresh defaults, no persisted setting')
        global_after = {key: command('global-after-' + key, 'adb', 'shell', 'settings', 'get', 'system', key)
                        for key in global_before}
        need(global_before == global_after, 'global brightness settings changed')
        analyzer = Path(os.environ['ANDROID_HOME']) / 'cmdline-tools/latest/bin/apkanalyzer'
        manifest = command('apk-manifest', str(analyzer), 'manifest', 'print', str(apk))
        xml = ET.fromstring(manifest)
        need(not xml.findall('uses-permission') and not xml.findall('.//service'), 'APK permissions/services forbidden')
        dex = command('apk-dex', str(analyzer), 'dex', 'packages', '--defined-only', str(apk))
        need('org.exreader.display.ReaderDisplay' in dex, 'installed library missing from actual APK DEX')
        command('dumpsys-package', 'adb', 'shell', 'dumpsys', 'package', PACKAGE)
        command('dumpsys-window', 'adb', 'shell', 'dumpsys', 'window', 'windows')
        aar = ROOT / 'stage/exreader-android-display-0.1.0.aar'
        with zipfile.ZipFile(aar) as archive:
            (ROOT / 'stage/classes.jar').write_bytes(archive.read('classes.jar'))
        manifest_files = [identity(path) for path in sorted(ROOT.rglob('*')) if path.is_file() and path.parent.name in ('stage', 'consumer')]
        for raw in (suite, seed, reopened):
            need(raw['source_sha'] == os.environ['GITHUB_SHA'] and raw['run_id'] == os.environ['GITHUB_RUN_ID']
                 and raw['run_attempt'] == os.environ['GITHUB_RUN_ATTEMPT'], 'runtime source binding')
            need(raw['installed_apk_sha256'] == identity(apk)['sha256'] and raw['apk_bytes'] == apk.stat().st_size, 'runtime APK identity')
            need(raw['aar_sha256'] == identity(aar)['sha256'], 'runtime installed AAR identity')
        summary.update(schema=1, module='EXReaderAndroidDisplay', module_version='0.1.0',
                       source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                       run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], job='android', api=34, abi='x86_64',
                       accepted=True, ui_cases=CASES, process_cases=PROCESS_CASES,
                       checks=len(CASES) + len(PROCESS_CASES), files=manifest_files,
                       global_before=global_before, global_after=global_after,
                       terminated_pid=seed['pid'], reopened_pid=reopened['pid'],
                       source_module_tree=subprocess.check_output(['git', 'rev-parse', 'HEAD:extras/android-reader-display'], text=True).strip())
    except Exception as error:
        summary['error'] = str(error)
    finally:
        command('final-logcat', 'adb', 'logcat', '-d', allowed=True)
        (EVIDENCE / 'report.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
