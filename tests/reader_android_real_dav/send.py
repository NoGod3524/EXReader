"""Actual Android Activity uploads its own records to pinned real Apache WebDAV."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path[:0] = ['tests/reader_webdav_interop', 'tests/reader_android_record_interop']
from run_interop import Apache, Harness, Independent, USER, require, run
from bundle import folder

p = argparse.ArgumentParser()
for name in ('fixture', 'fixtures', 'output', 'work'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
identity = {key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]}
args = argparse.Namespace(service='apache', consumer=Path('/bin/false'), output=a.output / 'server', work=a.work)
h = Harness(args)
report = {**identity, 'accepted': False, 'android_activity_sync': False, 'desktop_receiver': False, 'bidirectional': False}
copies = []
package = 'org.exreader.host'
def adb(*args, input=None):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=120)
try:
    tls = h.work / 'tls'; tls.mkdir()
    for src, dest in [('public/server.crt', 'trusted.crt'), ('private/server.key', 'trusted.key'),
                      ('public/untrusted.crt', 'untrusted.crt'), ('private/untrusted.key', 'untrusted.key')]:
        shutil.copyfile(a.fixture / src, tls / dest)
        os.chmod(tls / dest, 0o644)
    ca = (a.fixture / 'public/ca.crt').resolve()
    h.service = Apache('apache', h.work, h.evidence, ca, h.secret)
    h.service.host = '127.0.0.1'
    h.client = Independent('127.0.0.1', h.service.port, ca, h.auth)
    h.service.pull(); h.service.start(h.client)
    report['service_image'] = h.service.image_identity(); report['service_versions'] = h.service.versions()
    subprocess.run(['adb', 'reverse', 'tcp:%d' % h.service.port, 'tcp:%d' % h.service.port], check=True)
    adb('install', '-r', '-t', 'build/android-record-interop/test-apks/record-interop-ui.apk')
    env = dict(os.environ); env['PYTHONPATH'] = 'tests/reader_android_record_interop'
    subprocess.run([sys.executable, 'build/android-page-theme/candidate/record_sender_only.py', '--fixtures', str(a.fixtures),
                    '--output', str(a.output / 'sender')], env=env, check=True, timeout=1800)
    checked = folder(a.output / 'sender/bundle'); manifest = checked['manifest']
    require(all(manifest['sender'][key] == value for key, value in identity.items()), 'sender source/run/attempt differs')
    adb('install', '-r', '-t', 'build/host-session-android/test-apks/host-sync.apk')
    payload = {'root': 'https://127.0.0.1:%d/dav/' % h.service.port, 'user': USER, 'password': h.secret}
    adb('shell', "run-as %s sh -c 'cat > files/host-ui-input.json'" % package, input=json.dumps(payload).encode())
    command = ['shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', 'interop-send']
    for key, value in identity.items(): command += ['-e', key, value]
    command += [package + '.test/' + package + '.HostSyncTest']
    process = subprocess.run(['adb', *command], capture_output=True, timeout=900)
    (a.output / 'sync-instrumentation.txt').write_bytes(process.stdout + process.stderr)
    raw = adb('exec-out', 'run-as', package, 'cat', 'files/host-ui-interop-send.json')
    (a.output / 'sync-report.json').write_bytes(raw)
    observed = json.loads(raw)
    require(process.returncode == 0 and b'HOST_SYNC_UI_PASS interop-send' in process.stdout and
            b'INSTRUMENTATION_CODE: -1' in process.stdout and observed['passed'] is True and
            all(observed.get(key) == value for key, value in identity.items()), 'actual sync UI failed')
    require([c['name'] for c in observed['checks']] == ['actual_activity_syncs_existing_record_sender', 'actual_session_closes'], 'sync UI checks differ')
    for row in manifest['originals']:
        path = '/dav/exreader-sync-v1/objects/' + row['sha256'][:2] + '/' + row['sha256'] + '.' + row['format']
        status, data = h.client.get(path)
        require(status == 200 and data == (a.output / 'sender/bundle' / row['file']).read_bytes(), 'remote original differs: ' + row['role'])
    for row in manifest['revisions']:
        path = '/dav/exreader-sync-v1/revisions/' + row['id'][:2] + '/' + row['id'] + '-' + row['sha256'] + '.json'
        status, data = h.client.get(path)
        require(status == 200 and data == (a.output / 'sender/bundle' / row['file']).read_bytes(), 'remote revision differs: ' + row['id'])
    report.update(android_activity_sync=True, sender=manifest['sender'], manifest_sha256=checked['manifest_sha256'],
                  originals=len(manifest['originals']), revisions=len(manifest['revisions']), reading_records=len(manifest['reading_records']))
    trust = '/usr/local/share/ca-certificates/exreader-android-gtk-interop.crt'
    subprocess.run(['sudo', 'cp', str(ca), trust], check=True)
    subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)
    gtk_env = dict(os.environ, INTEROP_GTK_OUTPUT=str((a.output / 'gtk').resolve()),
                   INTEROP_ANDROID_BUNDLE=str((a.output / 'sender/bundle').resolve()),
                   INTEROP_ROOT=payload['root'], INTEROP_USER=USER, INTEROP_PASSWORD=h.secret)
    gtk = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1440x1400x24', 'dbus-run-session', '--',
                          'bash', '-euc', 'openbox >/dev/null 2>&1 & exec /usr/bin/python3 tests/reader_android_real_dav/gtk_receive.py'],
                         env=gtk_env, capture_output=True, timeout=1500)
    (a.output / 'gtk-runner.log').write_bytes(gtk.stdout + gtk.stderr)
    require(gtk.returncode == 0, 'actual GTK receiver failed; see gtk/result.json and gtk-runner.log')
    desktop = json.loads((a.output / 'gtk/result.json').read_text())
    require(desktop['accepted'] is True and all(desktop.get(key) == value for key, value in identity.items()), 'GTK report identity differs')
    report.update(accepted=True, actual_desktop_receive=True, gtk_program_sha256=desktop['program_sha256'],
                  gtk_pid=desktop['pid'], gtk_books=desktop['books'])
except Exception as error:
    report['failure'] = str(error); report['trace'] = traceback.format_exc()
finally:
    if hasattr(h, 'service'):
        try: copies = h.service.collect()
        except Exception as error: report['collection_failure'] = str(error); report['accepted'] = False
        h.service.remove()
    found, scanned = h.scrub(copies)
    if found or not scanned: report['credential_scan_matches'] = found; report['accepted'] = False
    # Includes the other evidence directory, which must also never retain test credentials.
    for path in a.output.rglob('*'):
        if path.is_file() and any(secret.encode() in path.read_bytes() for secret in (h.secret, h.admin, h.auth)):
            path.write_text('removed generated credential\n'); report['accepted'] = False; report['credential_leak'] = str(path)
    run(['sudo', 'rm', '-f', '/usr/local/share/ca-certificates/exreader-android-gtk-interop.crt'], check=False)
    run(['sudo', 'update-ca-certificates', '--fresh'], check=False)
    run(['sudo', 'rm', '-rf', str(h.work)], check=False)
    (a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
sys.exit(0 if report['accepted'] else 1)
