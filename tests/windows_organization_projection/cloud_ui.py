"""Normal Windows cloud import UI only; run on GitHub Actions."""
import base64
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('import_organize_ui', ROOT / 'tests/reader_windows_import_organize/check_ui.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
App, ACCOUNT, A, U, send, text, M = (driver.App, driver.ACCOUNT, driver.A, driver.U, driver.send, driver.text, driver.M)
CLOUD, ROWS, MESSAGE, GO, CANCEL, CLOSE, INPUTS = (driver.CLOUD, driver.ROWS, driver.MESSAGE, driver.GO, driver.CANCEL, driver.CLOSE, driver.INPUTS)

out = ROOT / 'build/cloud-ui'
out.mkdir(parents=True, exist_ok=False)
candidate = ROOT / 'build/c09/package/EXReader/EXReader.exe'
font = ROOT / 'build/c09/package/EXReader/Reader.otf'
probe = ROOT / 'build/cloud-readback/cloud-probe.exe'
fixtures = ROOT / 'tests/fixtures'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
checks, problems = [], []
report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
              attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=checks, problems=problems,
              scope='normal cloud UI only', inputs={name: sha(fixtures / fixture) for name, fixture in INPUTS})
report['installed_libraries'] = {str(path.relative_to(ROOT / 'build')).replace('\\', '/'): sha(path)
                                 for stage in ('raw-stage', 'product-stage', 'sdk-stage')
                                 for path in (ROOT / 'build/c09' / stage).rglob('*.lib')}
app = dav = None
phase = 'setup'

def record(name, condition):
    assert condition, name
    checks.append(name)
    print(name, flush=True)

def settle(d):
    app.wait(lambda: not U.IsWindowEnabled(U.GetDlgItem(d, CANCEL)), timeout=120)

def press(d, control):
    send(U.GetDlgItem(d, control), 0xF5)
    settle(d)
    return text(U.GetDlgItem(d, MESSAGE))

def labels(d):
    box = U.GetDlgItem(d, ROWS)
    values = []
    for i in range(send(box, 0x18B)):
        n = send(box, 0x18A, i)
        buf = C.create_unicode_buffer(n + 1)
        send(box, 0x189, i, C.addressof(buf))
        values.append(buf.value)
    return values

def choose(d, label):
    row = next(i for i, value in enumerate(labels(d)) if label in value)
    send(U.GetDlgItem(d, ROWS), 0x186, row)

def show():
    app.wait_idle()
    U.SetForegroundWindow(app.window)
    A.tap(ord('I'), (A.VK_CONTROL, A.VK_SHIFT))
    d = app.io_dialog()
    settle(d)
    return d

def close(d):
    send(U.GetDlgItem(d, CLOSE), 0xF5)
    app.wait(lambda: not U.IsWindow(d))
    app.wait_idle()

def count():
    with sqlite3.connect(str(app.db)) as db:
        return db.execute('SELECT count(*) FROM books').fetchone()[0]

try:
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    assert report['installed_libraries'], 'no installed library identities'
    certs = out / 'certificates'; certs.mkdir()
    key, cert = certs / 'server.key', certs / 'server.crt'
    openssl = shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(cert), '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(cert)], check=True, capture_output=True)
    user, password = 'fixture-user', 'fixture-secret-' + uuid.uuid4().hex
    auth = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
    dav = ACCOUNT.Dav(cert, key, auth)
    report['server'] = dict(base=dav.base, certificate_sha256=sha(cert), implementation_sha256=sha(ROOT / 'tests/reader_windows_account/check_account_ui.py'))
    dav.directories.add('/dav/books/')
    for name, fixture in INPUTS:
        dav.entries['/dav/books/' + name.replace(' ', '%20')] = (fixtures / fixture).read_bytes()
    app = App(candidate, font, out / 'profile'); app.wait_initial_shelf(); app.wait_idle()
    phase = 'account'
    d = app.open_account(); app.fill(d, root=dav.base + '/dav/', user=user, password=password, remember=False); app.apply(d, '仅本次会话'); app.close_account(d)
    phase = 'listing'; d = show()
    record('authenticated-https-listing', any(r['method'] == 'PROPFIND' and r['authenticated'] for r in dav.requests) and any('books' in x for x in labels(d)))
    before = count()
    record('no-implicit-selection', C.c_ssize_t(send(U.GetDlgItem(d, ROWS), 0x188)).value == -1 and 'committed=1' not in press(d, GO) and count() == before)
    choose(d, 'books'); press(d, GO)
    record('directory-navigation', len(labels(d)) == len(INPUTS))
    for name, fixture in INPUTS:
        phase = 'import-' + fixture
        choose(d, name); message = press(d, GO)
        record('import-' + fixture, all(v in message for v in ('committed=1', 'created=1', 'mapped=1', 'staging_removed=1')))
    M.screenshot(d, out / 'cloud-receipts.bmp'); close(d)
    phase = 'readback'; readback = out / 'readback'; readback.mkdir()
    spec = out / 'readback.spec'; spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n' % (app.db, readback), encoding='utf-8')
    value = subprocess.run([str(probe), str(spec)], capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert value.returncode == 0, value.stderr
    audit = json.loads(value.stdout); report['public_readback'] = audit
    actual = {sha(readback / ('book-%d.bin' % book['id'])) for book in audit['books']}
    record('public-sdk-original-readback', audit['ok'] == 1 and len(audit['books']) == len(INPUTS) and actual == set(report['inputs'].values()) and all(book['read_ok'] == 1 for book in audit['books']))
    d = show(); choose(d, 'books'); press(d, GO); choose(d, INPUTS[0][0]); message = press(d, GO)
    record('duplicate-preserves-state', 'committed=1' in message and 'created=0' in message and count() == len(INPUTS))
    dav.fail = 500; message = press(d, GO); dav.fail = 0
    receipt = (out / 'profile/cloud-import.receipts').read_text()
    record('http-failure-preserves-state', 'HTTP=500' in message and 'http=500' in receipt and count() == len(INPUTS) and not list((out / 'profile/cloud-import').glob('cloud-*')))
    close(d); dav.pause = True
    U.SetForegroundWindow(app.window); A.tap(ord('I'), (A.VK_CONTROL, A.VK_SHIFT)); d = app.io_dialog()
    app.wait(lambda: dav.blocked.is_set()); send(U.GetDlgItem(d, CLOSE), 0xF5); dav.release.set()
    app.wait(lambda: not U.IsWindow(d)); app.wait_idle()
    record('cancel-listing-preserves-state', count() == len(INPUTS) and U.IsWindowEnabled(app.window))
    phase = 'unauthorized'; d = app.open_account(); app.fill(d, password='wrong-password'); app.apply(d, '仅本次会话'); app.close_account(d)
    d = show(); record('unauthorized-preserves-state', 'HTTP=401' in text(U.GetDlgItem(d, MESSAGE)) and not labels(d) and count() == len(INPUTS)); close(d)
    phase = 'readback-after-failure-cancel'; readback2 = out / 'readback-after'; readback2.mkdir()
    spec.write_text('cmd=readback\nlibrary=%s\nout=%s\n' % (app.db, readback2), encoding='utf-8')
    value = subprocess.run([str(probe), str(spec)], capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert value.returncode == 0, value.stderr
    after = json.loads(value.stdout); report['public_readback_after'] = after
    record('originals-survive-failure-and-cancel', after['ok'] == 1 and len(after['books']) == len(INPUTS) and all(book['read_ok'] == 1 for book in after['books']) and {sha(readback2 / ('book-%d.bin' % book['id'])) for book in after['books']} == set(report['inputs'].values()))
    record('authenticated-downloads', sum(r['method'] == 'GET' and r['authenticated'] for r in dav.requests) >= len(INPUTS))
    record('fixtures-unchanged', all(sha(fixtures / fixture) == report['inputs'][name] for name, fixture in INPUTS))
    report['accepted'] = True
except Exception as error:
    problems.append(phase + ': ' + type(error).__name__ + ': ' + str(error)); traceback.print_exc()
    try: M.screenshot(U.GetDesktopWindow(), out / 'failure-desktop.bmp')
    except Exception: pass
finally:
    if app:
        if app.process.poll() is None: app.process.kill(); app.process.wait(timeout=20)
        if not app.log.closed: app.log.close()
    if dav:
        dav.release.set(); dav.server.shutdown(); dav.server.server_close(); report['requests'] = dav.requests
    for item in out.glob('certificates/*.key'): item.unlink()
    for name, path in [('program', candidate), ('probe', probe), ('font', font)]:
        if path.exists(): report[name + '_sha256'] = sha(path)
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)
if not report['accepted']:
    raise SystemExit('Normal cloud UI checks failed')
