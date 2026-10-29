"""Actions-only: install the real host APK on the API34 emulator, run the frozen
HostSync UI suite (real Activity -> NativeSync JNI -> reader_session -> reader_sync
-> TLS WebDAV) and, while its native request is blocked in flight, snapshot the
live app process and the exact libraries it has mapped."""
import hashlib, json, os, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAVE = ROOT / 'build/wave3'
OUT = ROOT / 'build/c1-installed-sync/device'
PACKAGE = 'org.exreader.host'
MARKERS = {'host-ui-put-blocked': 'upload', 'host-ui-listing-blocked': 'listing'}


def adb(*args, check=True, timeout=120):
    p = subprocess.run(['adb', *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('adb %s failed: %s' % (args, p.stdout.decode(errors='replace')[-2000:]))
    return p.stdout


def run_as(command):
    return adb('shell', 'run-as', PACKAGE, 'sh', '-c', "'" + command + "'", check=False).decode(errors='replace')


def snapshot(kind):
    """Identity of the live process while the native request is outstanding."""
    pid = adb('shell', 'pidof', PACKAGE).decode().split()
    row = dict(kind=kind, pids=pid, taken=time.time())
    if len(pid) != 1:
        return row
    maps = run_as('cat /proc/%s/maps' % pid[0])
    libs = sorted({l.split()[-1] for l in maps.splitlines() if l.split() and l.split()[-1].endswith('.so') and 'exreader' in l.split()[-1]})
    hashes = {}
    for path in libs:
        out = run_as('sha256sum ' + path).split()
        hashes[path] = out[0] if out else None
    row.update(maps_libs=libs, lib_sha256=hashes, cmdline=run_as('cat /proc/%s/cmdline' % pid[0]).replace('\0', ' ').strip(),
               net_tcp=run_as('cat /proc/%s/net/tcp' % pid[0])[:4000])
    return row


def poller(stop, snaps, errors):
    seen = set()
    while not stop.is_set():
        for marker, kind in MARKERS.items():
            if kind in seen:
                continue
            try:
                if subprocess.run(['adb', 'shell', 'run-as', PACKAGE, 'test', '-f', 'files/' + marker],
                                  capture_output=True, timeout=15).returncode == 0:
                    snaps.append(snapshot(kind))
                    seen.add(kind)
            except Exception as error:
                errors.append(repr(error))
        time.sleep(.25)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    OUT.mkdir(parents=True, exist_ok=True)
    build = json.loads((ROOT / 'build/c1-installed-sync/build.json').read_text())
    host, runner = WAVE / 'artifacts/app-debug.apk', WAVE / 'artifacts/host-sync-342-androidTest.apk'
    assert hashlib.sha256(host.read_bytes()).hexdigest() == build['host_apk_sha256']
    adb('install', '-r', '-t', host)
    adb('install', '-r', '-t', runner)
    path = adb('shell', 'pm', 'path', PACKAGE).decode().strip()
    assert path.startswith('package:') and '\n' not in path, path
    adb('pull', path[len('package:'):], OUT / 'installed-host.apk')
    installed = hashlib.sha256((OUT / 'installed-host.apk').read_bytes()).hexdigest()
    assert installed == build['host_apk_sha256'], 'installed APK differs from the built host'
    (OUT / 'install.json').write_text(json.dumps(dict(pm_path=path, installed_sha256=installed,
        runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),
        package_dump=adb('shell', 'dumpsys', 'package', PACKAGE).decode(errors='replace')[:20000]), indent=2))
    stop, snaps, errors = threading.Event(), [], []
    thread = threading.Thread(target=poller, args=(stop, snaps, errors), daemon=True)
    thread.start()
    try:
        env = dict(os.environ)
        rc = subprocess.run([sys.executable, str(ROOT / 'build/c1-installed-sync/candidate/run_ui_342.py'),
            '--sdk-version', '3.42.0', '--fixture', str(WAVE / 'network-fixture'),
            '--reading-fixtures', str(WAVE / 'sync-reading-fixtures'), '--output', str(OUT / 'ui')],
            cwd=ROOT, env=env).returncode
    finally:
        stop.set()
        thread.join(15)
        (OUT / 'process-snapshots.json').write_text(json.dumps(dict(snapshots=snaps, poll_errors=errors), indent=2))
    sys.exit(rc)


if __name__ == '__main__':
    main()
