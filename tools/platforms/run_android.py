"""Install the test APK, invoke JNI in two cold processes, retrieve evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

PACKAGE = 'org.exreader.platformprobe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('choose a fresh output directory')
    args.out.mkdir(parents=True, exist_ok=True)
    commands = []

    def adb(*command, binary=False, check=True):
        full = [args.adb, '-s', args.serial, *map(str, command)]
        commands.append(full)
        result = subprocess.run(full, capture_output=True, check=check)
        return result.stdout if binary else result.stdout.decode('utf-8', errors='replace').strip()

    if adb('shell', 'getprop', 'sys.boot_completed') != '1':
        raise RuntimeError('Android has not finished booting')
    system = {key: adb('shell', 'getprop', key) for key in
              ('ro.build.fingerprint', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.product.cpu.abi')}
    system['uname'] = adb('shell', 'uname', '-a')
    print(adb('install', '-r', args.apk), flush=True)
    # Only this dedicated probe application's data is cleared.
    if adb('shell', 'pm', 'clear', PACKAGE) != 'Success':
        raise RuntimeError('cannot clear previous probe data')
    pids = []
    for mode in ('create', 'reopen'):
        adb('shell', 'am', 'force-stop', PACKAGE)
        print(adb('shell', 'am', 'start', '-W', '-n', PACKAGE + '/.MainActivity', '--ez', 'reopen',
                  str(mode == 'reopen').lower()), flush=True)
        pids.append(adb('shell', 'pidof', PACKAGE))
        deadline = time.monotonic() + 60
        while True:
            log = adb('exec-out', 'run-as', PACKAGE, 'cat', 'files/' + mode + '.log', check=False)
            if ('STORED highlight' if mode == 'create' else 'PASS platform checks=5/5') in log:
                break
            if 'FAIL' in log or time.monotonic() >= deadline:
                raise RuntimeError('JNI probe failed or timed out: ' + log)
            time.sleep(0.5)
        (args.out / (mode + '.log')).write_text(log + '\n', encoding='utf-8')
        print(log, flush=True)
    if not all(pids) or pids[0] == pids[1]:
        raise RuntimeError('reopen must run in a distinct Android process')
    for name in ('page.png', 'reopen.png', 'highlight.png', 'highlight.json', 'position.txt'):
        (args.out / name).write_bytes(adb('exec-out', 'run-as', PACKAGE, 'cat', 'files/' + name, binary=True))
    logcat = adb('logcat', '-d', '-s', 'EXRPlatform:I', '*:S')
    (args.out / 'logcat.txt').write_text(logcat + '\n', encoding='utf-8')
    if not all(re.search(r'PASS shipped_jni version=\S+ pid=' + pid + r'\b', logcat) for pid in pids):
        raise RuntimeError('missing shipped JNI version call for one of the processes')
    checks = {name: bool(re.search(r'^PASS ' + name + r'\b', log, re.M))
              for name in ('load', 'open', 'render', 'search', 'annotation')}
    if not all(checks.values()):
        raise RuntimeError('incomplete five-check evidence')
    result = {'checks': checks, 'passed': sum(checks.values()), 'pids': pids, 'system': system,
              'apk_sha256': hashlib.sha256(args.apk.read_bytes()).hexdigest(), 'commands': commands}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PASS Android 5/5; independent PIDs=' + ','.join(pids))


if __name__ == '__main__':
    main()
