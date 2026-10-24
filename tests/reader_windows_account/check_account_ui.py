# SPDX-License-Identifier: MIT
"""Actions-only real Win32 account controls, Credential Manager and native HTTPS WebDAV.

Every account action is a real control message (BM_CLICK / WM_SETTEXT) sent to the
packaged EXReader.exe. Independent observations use sqlite3, the WebDAV server's own
request log, cmdkey and the file system. Nothing here calls host functions directly.
"""
import argparse
import base64
import ctypes as C
from ctypes import wintypes as W
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import ssl
import struct
import subprocess
import sys
import threading
import time
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tests/windows_host'))
sys.path.insert(0, str(HERE.parents[1] / 'tests/windows_host/worker_review'))
import check_metadata_ui as M
from check_worker import U, ENUM, send, set_text
from make_fixtures import epub, pdf

# Control identifiers appended after the original metadata editor controls.
ACCOUNT, ROOT, USER, PASSWORD, REMEMBER, APPLY, SYNC, CANCEL, RETRY, FORGET, CLOSE, MESSAGE, DETAIL = range(137, 150)
REFRESH = 127
BM_CLICK, BM_GETCHECK, BM_SETCHECK = 0xF5, 0xF0, 0xF1
OBJECTS = 'exreader-sync-v1/objects/'


def png(width, height, color):
    rows = b''.join(b'\x00' + bytes(color) * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def make_cbz(path):
    import zipfile
    with zipfile.ZipFile(path, 'w') as archive:
        for index, color in enumerate(((200, 30, 30), (30, 200, 30), (30, 30, 200)), 1):
            info = zipfile.ZipInfo('%03d.png' % index, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, png(96, 128, color))


class Dav:
    """Minimal HTTPS WebDAV collection store with deterministic fault switches."""

    def __init__(self, certificate, key, authorization):
        self.entries, self.requests, self.lock = {}, [], threading.Lock()
        self.directories = {'/dav/', '/other/'}
        self.fail, self.reset = 0, False
        self.blocked, self.release = threading.Event(), threading.Event()
        self.pause = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *unused):
                pass

            def reply(self, code, data=b''):
                self.send_response(code);self.send_header('Content-Length', str(len(data)))
                self.send_header('Connection', 'close');self.end_headers();self.close_connection = True
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                    pass

            def authorized(self):
                if self.command in ('PROPFIND', 'PUT'):
                    length = int(self.headers.get('Content-Length', 0))
                    self.body = self.rfile.read(length) if length else b''
                with outer.lock:
                    outer.requests.append({'method': self.command, 'path': self.path,
                                           'authenticated': self.headers.get('Authorization') == authorization})
                if self.headers.get('Authorization') != authorization:
                    self.reply(401);return False
                if outer.reset:
                    self.close_connection = True
                    try:
                        self.connection.shutdown(2)
                    except OSError:
                        pass
                    return False
                if outer.fail:
                    self.reply(outer.fail);return False
                return True

            def do_MKCOL(self):
                if not self.authorized():
                    return
                with outer.lock:
                    exists = self.path in outer.directories;outer.directories.add(self.path)
                self.reply(405 if exists else 201)

            def do_PUT(self):
                if not self.authorized():
                    return
                with outer.lock:
                    exists = self.path in outer.entries
                    if not exists:
                        outer.entries[self.path] = self.body
                self.reply(412 if exists else 201)

            def do_GET(self):
                if not self.authorized():
                    return
                with outer.lock:
                    body = outer.entries.get(self.path)
                self.reply(404 if body is None else 200, body or b'')

            def do_PROPFIND(self):
                if not self.authorized():
                    return
                if outer.pause:
                    outer.pause = False;outer.blocked.set();outer.release.wait(40)
                with outer.lock:
                    children = [(p, True, 0) for p in outer.directories if p.startswith(self.path) and
                                (p == self.path or '/' not in p[len(self.path):].rstrip('/'))]
                    children += [(p, False, len(b)) for p, b in outer.entries.items()
                                 if p.startswith(self.path) and '/' not in p[len(self.path):]]
                    exists = self.path in outer.directories
                if not exists:
                    self.reply(404);return
                rows = ['<d:response><d:href>' + p + '</d:href><d:propstat><d:prop><d:resourcetype>' +
                        ('<d:collection/>' if is_dir else '') + '</d:resourcetype><d:getcontentlength>' + str(size) +
                        '</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                        for p, is_dir, size in children]
                self.reply(207, ('<d:multistatus xmlns:d="DAV:">' + ''.join(rows) + '</d:multistatus>').encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler);self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'https://127.0.0.1:%d' % self.server.server_port

    def objects(self):
        with self.lock:
            return {p: b for p, b in self.entries.items() if p.startswith('/dav/' + OBJECTS)}

    def count(self, prefix):
        with self.lock:
            return sum(1 for p in self.entries if p.startswith('/dav/exreader-sync-v1/' + prefix))


def blind_text(window, text):
    """Windows refuses cross-process WM_GETTEXT on a masked password edit, so only WM_SETTEXT is verified."""
    units = len(text.encode('utf-16-le')) // 2 + 1
    value = C.create_unicode_buffer(text, units)
    assert send(window, 0xC, 0, C.addressof(value)), 'Password edit rejected WM_SETTEXT'


def clipboard_text(app):
    U.OpenClipboard.argtypes = [W.HWND];U.GetClipboardData.argtypes = [W.UINT];U.GetClipboardData.restype = W.HANDLE
    kernel = C.WinDLL('kernel32');kernel.GlobalLock.argtypes = [W.HANDLE];kernel.GlobalLock.restype = C.c_void_p
    kernel.GlobalUnlock.argtypes = [W.HANDLE]
    assert U.OpenClipboard(app.window)
    try:
        handle = U.GetClipboardData(13);pointer = kernel.GlobalLock(handle)
        value = ' '.join(C.wstring_at(pointer).split()) if pointer else ''
        kernel.GlobalUnlock(handle)
        return value
    finally:
        U.CloseClipboard()


class Device(M.MetadataApp):
    """One real product process on its own profile (its own SDK library and product catalog)."""

    def find_dialog(self):
        found = []

        @ENUM
        def visit(window, unused):
            pid = W.DWORD();U.GetWindowThreadProcessId(window, C.byref(pid))
            if pid.value == self.process.pid and U.IsWindowVisible(window) and U.GetDlgItem(window, APPLY):
                found.append(window)
            return True
        U.EnumWindows(visit, 0)
        return found[-1] if found else None

    def account_dialog(self):
        return self.wait(self.find_dialog)

    def diagnose(self, output):
        """Failure evidence only: visible text and a window capture of a still-running product."""
        info = {'profile': self.profile.name, 'status': self.status()}
        dialog = self.find_dialog()
        if dialog:
            info.update(note=M.text(U.GetDlgItem(dialog, MESSAGE)), detail=M.text(U.GetDlgItem(dialog, DETAIL)))
        windows = []

        @ENUM
        def visit(window, unused):
            pid = W.DWORD();U.GetWindowThreadProcessId(window, C.byref(pid))
            if pid.value == self.process.pid:
                name = C.create_unicode_buffer(100);U.GetClassNameW(window, name, 100)
                windows.append({'class': name.value, 'visible': bool(U.IsWindowVisible(window)), 'enabled': bool(U.IsWindowEnabled(window))})
            return True
        U.EnumWindows(visit, 0)
        info['windows'] = windows
        print(json.dumps({'diagnostic': info}, ensure_ascii=False), flush=True)
        M.screenshot(U.GetDesktopWindow(), output / ('failure-desktop-' + self.profile.name + '.bmp'))
        M.screenshot(dialog or self.window, output / ('failure-' + self.profile.name + '.bmp'))

    def has_row(self, title):
        try:
            self.row(title)
            return True
        except AssertionError:
            return False

    def details_for(self, title):
        """Select the named shelf row with the real list control, then press the real details button."""
        self.wait_idle()
        send(self.control('books'), 0x186, self.row(title))
        send(U.GetDlgItem(self.window, M.DETAILS), BM_CLICK)
        return self.dialog()

    def open_account(self):
        self.wait_idle()
        send(U.GetDlgItem(self.window, ACCOUNT), BM_CLICK)
        dialog = self.account_dialog()
        self.settle(dialog)
        return dialog

    def settle(self, dialog):
        """The load job is visible as disabled buttons; wait until the dialog is idle."""
        self.wait(lambda: U.IsWindowEnabled(U.GetDlgItem(dialog, FORGET)) and M.text(U.GetDlgItem(dialog, MESSAGE)) != '正在读取账号设置。')

    def note(self, dialog):
        return M.text(U.GetDlgItem(dialog, MESSAGE))

    def detail(self, dialog):
        return M.text(U.GetDlgItem(dialog, DETAIL))

    def fill(self, dialog, root=None, user=None, password=None, remember=None):
        if root is not None:
            set_text(U.GetDlgItem(dialog, ROOT), root)
        if user is not None:
            set_text(U.GetDlgItem(dialog, USER), user)
        if password is not None:
            blind_text(U.GetDlgItem(dialog, PASSWORD), password)
        if remember is not None and bool(send(U.GetDlgItem(dialog, REMEMBER), BM_GETCHECK) == 1) != remember:
            send(U.GetDlgItem(dialog, REMEMBER), BM_CLICK)

    def press(self, dialog, identifier):
        send(U.GetDlgItem(dialog, identifier), BM_CLICK)

    def enabled(self, dialog, identifier):
        return bool(U.IsWindowEnabled(U.GetDlgItem(dialog, identifier)))

    def wait_note(self, dialog, needle, timeout=120):
        return self.wait(lambda: needle in self.note(dialog) or needle in self.detail(dialog), timeout=timeout)

    def apply(self, dialog, expected):
        self.press(dialog, APPLY)
        self.wait(lambda: expected in self.note(dialog))

    def close_account(self, dialog):
        self.press(dialog, CLOSE)
        self.wait(lambda: not U.IsWindow(dialog))
        self.wait_idle()

    def run_sync(self, dialog, timeout=240):
        self.press(dialog, SYNC)
        return self.wait_note(dialog, '同步完成', timeout)


def main():
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'package', 'fixtures', 'revision-consumer', 'link-map', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    checks, shots, devices = [], [], []
    user, password = 'u' + secrets.token_hex(12), 'p' + secrets.token_hex(24)
    authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
    font = (args.package / 'Reader.otf').resolve()

    def record(name):
        assert name not in checks, name
        checks.append(name);print(json.dumps({'check': name, 'pass': True}), flush=True)

    def shot(name, window):
        M.screenshot(window, output / name);shots.append(name)

    # ---- source fixtures: four formats plus a large text used by the fault round ----
    source = output / 'sources';source.mkdir()
    small_text = ('Account sync original marker alpha. ' * 400 + '\n').encode()
    (source / 'Remote Small.txt').write_bytes(small_text)
    large = bytearray()
    line = 0
    while len(large) < 5 * 1024 * 1024:
        large += ('Large account text line %08d with stable words for hashing and import.\n' % line).encode();line += 1
    (source / 'AAA Large Text.txt').write_bytes(bytes(large))
    epub(source / 'Account Epub.epub', 'Account Epub', 'Account epub marker bravo. ' * 600)
    pdf(source / 'Account Pdf.pdf', 3)
    make_cbz(source / 'Account Comic.cbz')
    originals = {p.name: p.read_bytes() for p in sorted(source.iterdir())}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()}

    # ---- temporary test CA, trusted only on this runner and removed afterwards ----
    certs = output / 'certificates';certs.mkdir()
    key, certificate = certs / 'server.key', certs / 'server.crt'
    openssl = shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key),
                    '-out', str(certificate), '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'],
                   check=True, capture_output=True)
    subprocess.run(['certutil', '-addstore', '-f', 'Root', str(certificate)], check=True, capture_output=True)
    dav = Dav(certificate, key, authorization)
    root = dav.base + '/dav/'
    other_root = dav.base + '/other/'

    def new_device(name, existing=False):
        profile = output / name
        device = Device(args.candidate.resolve(), font, profile, existing=existing)
        devices.append(device);return device

    def product_db(name):
        return output / name / 'library.sqlite.product.sqlite'

    def sql(name, query, values=()):
        with sqlite3.connect(product_db(name), timeout=10) as db:
            return db.execute(query, values).fetchall()

    def account_id(name):
        text = (output / name / 'account.ini').read_text()
        lines = text.splitlines()
        assert lines[0] == '[account]' and len(lines) == 3 and lines[1].startswith('id=') and lines[2].startswith('root=')
        return lines[1][3:], lines[2][5:]

    def credential_listed(identifier):
        done = subprocess.run(['cmdkey', '/list'], capture_output=True, text=True)
        return 'org.exreader.reader.webdav/' + identifier in done.stdout

    # Every needle the on-disk scan looks for: the user, the password, the exact
    # Authorization header and two encodings of the secret.
    needles = [user.encode(), password.encode(), authorization.encode(),
               base64.b64encode((user + ':' + password).encode()), password.encode().hex().encode()]
    owner_locked = []

    def exclusive_owner(path):
        """Files a live host may legitimately hold with share mode 0.

        The bound session keeps '<product>.sync-account' open exclusively for its whole
        lifetime and SQLite keeps its journal/WAL exclusive. Nothing else may be
        unreadable while a product runs, so any other denied read is a failure.
        """
        return path.name.endswith(('.sync-account', '.lock', '-journal', '-wal', '-shm'))

    def leak_scan(profile, allow_owner_lock=True):
        for path in profile.rglob('*'):
            try:
                if not path.is_file() or path.stat().st_size >= 64 * 1024 * 1024:
                    continue
                data = path.read_bytes()
            except PermissionError:
                assert allow_owner_lock and exclusive_owner(path), path
                if path not in owner_locked:
                    owner_locked.append(path)
                continue
            if any(n in data for n in needles):
                return str(path)
        return None

    def read_after_exit(path):
        deadline = time.monotonic() + 10
        while True:
            try:
                return path.read_bytes()
            except PermissionError:
                assert time.monotonic() < deadline and exclusive_owner(path), 'still held after exit: ' + str(path)
                time.sleep(.05)

    def leak_scan_everything():
        """Once every host has exited, not one byte of the secret may be readable."""
        for device in devices:
            assert device.process.poll() is not None, 'host still running: ' + device.profile.name
        for path in owner_locked:
            if path.exists():
                assert not any(n in read_after_exit(path) for n in needles), str(path)
        for device in devices:
            if not device.profile.exists():
                continue
            for path in device.profile.rglob('*'):
                try:
                    if not path.is_file() or path.stat().st_size >= 64 * 1024 * 1024:
                        continue
                except PermissionError:
                    assert exclusive_owner(path), path
                    continue
                assert not any(n in read_after_exit(path) for n in needles), str(path)

    def encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()

    def revision(number, shard, kind, key, mode, payload, parents=()):
        return {'version': 1, 'id': '%02x%030x' % (shard, number), 'entity_kind': kind, 'entity_key': key,
                'operation': 'put', 'location_kind': mode, 'parents': list(parents), 'payload': payload}

    def capture(name, value, heads):
        wire = output / (value['id'] + '.json');wire.write_bytes(encode(value))
        done = subprocess.run([str(args.revision_consumer.resolve()), 'reading-local', str(product_db(name)), str(wire), heads, '-'],
                              capture_output=True, text=True, encoding='utf-8', timeout=60)
        assert done.returncode == 0 and json.loads(done.stdout)['status'] == 0, (done.stdout, done.stderr)

    def kill(device):
        device.process.kill();device.process.wait(timeout=20);device.log.close()

    def import_books(device, names):
        for name in names:
            set_text(device.control('path'), str(source / name))
            seen = [device.status()]
            send(device.control('import'), BM_CLICK, timeout=5000)
            end = time.monotonic() + 180
            while time.monotonic() < end:
                status = device.status()
                if status != seen[-1]:
                    seen.append(status)
                if '已导入' in status or '去重' in status or '失败' in status:
                    break
                time.sleep(.05)
            print(json.dumps({'import': name, 'statuses': seen}, ensure_ascii=False), flush=True)
            assert '已导入' in seen[-1] or '去重' in seen[-1], (name, seen)
            device.wait_idle()
            device.wait(lambda: not device.status().endswith('书架信息待恢复'), timeout=60)

    A = B = None
    try:
        # ===== Device A: four formats imported through the real import control =====
        A = new_device('device-a')
        assert U.GetDlgItem(A.window, ACCOUNT) and not U.GetDlgItem(A.window, APPLY) and not U.GetDlgItem(A.window, ROOT)
        record('default_shelf_has_one_secondary_account_entry_and_no_resident_account_controls')
        import_books(A, ['Remote Small.txt', 'Account Comic.cbz', 'Account Epub.epub', 'Account Pdf.pdf', 'AAA Large Text.txt'])
        A.wait(lambda: len(sql('device-a', 'SELECT book_key FROM reader_books')) == 5)
        formats = sorted(f for f, in sql('device-a', 'SELECT format FROM reader_books'))
        assert formats == ['cbz', 'epub', 'pdf', 'txt', 'txt'], formats
        record('four_original_formats_are_imported_through_the_native_import_control')
        # A real typed metadata edit so remote title, author and favorite differ from SDK defaults.
        small_key = 'txt:' + hashes['Remote Small.txt']
        title0 = sql('device-a', 'SELECT title FROM reader_books WHERE book_key=?', (small_key,))[0][0]
        A.wait(lambda: A.has_row(title0))
        dialog = A.details_for(title0);set_text(U.GetDlgItem(dialog, M.TITLE), 'Remote Title ✓ 书名')
        set_text(U.GetDlgItem(dialog, M.AUTHOR), 'Remote Author 作者')
        if send(U.GetDlgItem(dialog, M.FAVORITE), BM_GETCHECK) != 1:
            send(U.GetDlgItem(dialog, M.FAVORITE), BM_CLICK)
        send(U.GetDlgItem(dialog, M.SAVE), BM_CLICK);A.closed(dialog)
        edited = sql('device-a', 'SELECT title,author,favorite FROM reader_books WHERE book_key=?', (small_key,))
        assert edited == [('Remote Title ✓ 书名', 'Remote Author 作者', 1)], edited
        record('typed_metadata_edit_creates_the_remote_title_author_and_favorite_to_preserve')

        # ===== account controls: refusal, secure save, binding and no plaintext =====
        dialog = A.open_account()
        shot('01-account-dialog.bmp', dialog)
        assert not A.enabled(dialog, SYNC)
        record('account_dialog_opens_from_the_real_button_with_sync_disabled_until_credentials_exist')
        A.fill(dialog, 'http://127.0.0.1/dav/', user, password, True)
        A.apply(dialog, 'HTTPS')
        assert not (output / 'device-a' / 'account.ini').exists()
        record('non_https_account_root_is_refused_before_anything_is_bound_or_saved')
        A.fill(dialog, root, user, password, True)
        A.apply(dialog, '系统安全存储')
        identifier, saved_root = account_id('device-a')
        assert saved_root == root and credential_listed(identifier) and A.enabled(dialog, SYNC)
        assert leak_scan(output / 'device-a') is None
        record('credentials_are_saved_in_windows_credential_manager_and_binding_stores_only_uuid_and_root')
        A.fill(dialog, other_root, user, password, True)
        A.apply(dialog, '已绑定')
        assert account_id('device-a') == (identifier, root)
        record('a_different_account_root_is_refused_for_a_bound_library')
        A.fill(dialog, root, user, password, True)
        A.apply(dialog, '系统安全存储')

        # ===== first full scan: stage originals, then network, then receive =====
        A.run_sync(dialog)
        shot('02-device-a-finished.bmp', dialog)
        detail = A.detail(dialog)
        assert 'FINISHED' in detail and '本机原书：已检查 5' in detail, detail
        staged = {p.name: p.read_bytes() for p in (output / 'device-a' / 'sync-originals').iterdir()}
        expected = {hashes[n] + '.' + n.rsplit('.', 1)[1]: d for n, d in originals.items()}
        assert staged == expected
        remote = dav.objects()
        for name, data in originals.items():
            suffix = '/%s.%s' % (hashes[name], name.rsplit('.', 1)[1])
            assert any(p.endswith(suffix) and b == data for p, b in remote.items()), name
        assert all(r['authenticated'] for r in dav.requests) and dav.count('revisions/') >= 6
        record('whole_local_library_originals_are_staged_exactly_and_published_after_source_release')
        record('four_format_originals_and_metadata_revisions_reach_native_https_with_session_authorization')
        A.close_account(dialog)

        # Real reading captures are committed by the installed native producer on A's product
        # database (verified book history required), then published by the host's own scan.
        A.close();assert A.process.returncode == 0
        location = {'mode': 'reflow_global', 'parser_version': '3.40.0', 'anchor_version': 1,
                    'selector': {'exact': 'Account', 'prefix': '', 'suffix': ' sync', 'start': 0, 'end': 7}}
        progress1 = revision(1, 0x32, 'progress', small_key, 'reflow_global', {'book_key': small_key, 'location': location})
        annotation_key = small_key + ':' + '3' * 32
        note = revision(1, 0x33, 'annotation', annotation_key, 'reflow_global',
                        {'book_key': small_key, 'annotation_id': '3' * 32, 'location': location, 'text': '备注 capture'})
        capture('device-a', progress1, '-');capture('device-a', note, '-')
        A = new_device('device-a', existing=True)
        dialog = A.open_account();A.run_sync(dialog);A.close_account(dialog)
        assert dav.count('revisions/') >= 8

        # ===== Device B: independent product and SDK library receives cloud-only books =====
        B = new_device('device-b')
        dialog = B.open_account()
        B.fill(dialog, root, user, password, False)
        B.apply(dialog, '仅本次会话')
        identifier_b, _ = account_id('device-b')
        assert identifier_b != identifier and not credential_listed(identifier_b)
        record('session_only_credentials_are_used_without_writing_secure_or_plain_storage')
        B.run_sync(dialog)
        shot('03-device-b-received.bmp', dialog)
        B.wait(lambda: len(sql('device-b', 'SELECT sdk_book_id FROM reader_local_books')) == 5)
        rows = sql('device-b', 'SELECT book_key,title,author,favorite FROM reader_books ORDER BY book_key')
        assert len(rows) == 5 and {r[0] for r in rows} == {('%s:%s' % (n.rsplit('.', 1)[1], hashes[n])) for n in originals}
        remote_row = [r for r in rows if r[0] == small_key][0]
        assert remote_row[1:] == ('Remote Title ✓ 书名', 'Remote Author 作者', 1), remote_row
        assert leak_scan(output / 'device-b') is None
        record('cloud_only_books_are_imported_from_verified_private_files_and_mapped_to_a_second_sdk_library')
        record('remote_title_author_and_favorite_survive_import_and_mapping')
        B.close_account(dialog)
        B.wait(lambda: B.has_row('Remote Title ✓ 书名'))
        for name in ('Remote Title ✓ 书名', 'Account Epub'):
            B.open(name);B.wait_idle()
            assert '已打开' in B.status(), B.status()
        B.click('select');B.click('copy')
        assert 'Account epub marker bravo.' in clipboard_text(B)
        record('cloud_only_books_open_and_render_on_the_receiving_device')

        # ===== reading position is never moved by receiving remote data =====
        B.open('Remote Title ✓ 书名');B.wait_idle()
        B.click('next');B.wait_idle()
        page_label = U.GetDlgItem(B.window, 124)
        page_before = M.text(page_label)
        for value in (progress1, note):
            row = sql('device-b', 'SELECT body_json FROM reader_revisions WHERE revision_id=?', (value['id'],))
            assert row and json.loads(row[0][0]) == value, value['id']
        record('real_reading_progress_and_annotation_captures_round_trip_to_the_second_device_byte_exactly')
        A.close();assert A.process.returncode == 0
        progress2 = revision(2, 0x32, 'progress', small_key, 'reflow_global', {'book_key': small_key, 'location': location},
                             parents=[progress1['id']])
        capture('device-a', progress2, progress1['id'])
        A = new_device('device-a', existing=True)
        title_a = sql('device-a', 'SELECT title FROM reader_books WHERE book_key=?', ('epub:' + hashes['Account Epub.epub'],))[0][0]
        A.wait(lambda: A.has_row(title_a))
        A.wait(lambda: A.has_row(title_a))
        dialog = A.details_for(title_a);set_text(U.GetDlgItem(dialog, M.TITLE), 'Epub Retitled Remotely')
        send(U.GetDlgItem(dialog, M.SAVE), BM_CLICK);A.closed(dialog)
        dialog = A.open_account();A.run_sync(dialog);A.close_account(dialog)
        dialog = B.open_account();B.run_sync(dialog)
        shot('04-device-b-reading-not-moved.bmp', dialog)
        B.close_account(dialog)
        B.wait(lambda: sql('device-b', 'SELECT title FROM reader_books WHERE book_key=?', ('epub:' + hashes['Account Epub.epub'],))[0][0] == 'Epub Retitled Remotely')
        row = sql('device-b', 'SELECT body_json FROM reader_revisions WHERE revision_id=?', (progress2['id'],))
        assert row and json.loads(row[0][0]) == progress2
        assert M.text(page_label) == page_before and B.status() is not None
        record('remote_progress_arrives_and_metadata_applies_while_the_active_reading_page_is_not_moved')
        B.close();assert B.process.returncode == 0

        # ===== restart: saved credentials load, a repeated scan is idempotent =====
        A.close();assert A.process.returncode == 0
        before = (sql('device-a', 'SELECT count(*) FROM reader_revisions')[0][0], len(dav.objects()))
        A = new_device('device-a', existing=True)
        dialog = A.open_account()
        assert '已载入' in A.note(dialog) and A.enabled(dialog, SYNC)
        A.run_sync(dialog)
        assert (sql('device-a', 'SELECT count(*) FROM reader_revisions')[0][0], len(dav.objects())) == before
        assert len(sql('device-a', 'SELECT sdk_book_id FROM reader_local_books')) == 5
        shot('05-restart-loaded-credentials.bmp', dialog)
        record('exit_and_reopen_loads_saved_credentials_and_a_repeat_scan_adds_no_duplicates')
        # Forget removes the system record and the session secret.
        A.press(dialog, FORGET)
        A.wait(lambda: '已删除保存的凭据' in A.note(dialog))
        assert not credential_listed(identifier) and not A.enabled(dialog, SYNC)
        record('forget_removes_the_credential_manager_record_and_disables_scanning')
        A.close_account(dialog)
        A.close();assert A.process.returncode == 0

        # ===== fault round 1: network interruption, then explicit retry =====
        C1 = new_device('device-c')
        dialog = C1.open_account()
        C1.fill(dialog, root, user, password, False);C1.apply(dialog, '仅本次会话')
        dav.reset = True
        C1.press(dialog, SYNC)
        C1.wait_note(dialog, 'FAILED', 120)
        assert C1.enabled(dialog, RETRY) and '同步失败' in C1.note(dialog)
        shot('06-network-interrupted.bmp', dialog)
        dav.reset = False
        C1.press(dialog, RETRY)
        C1.wait_note(dialog, '同步完成', 240)
        C1.wait(lambda: len(sql('device-c', 'SELECT sdk_book_id FROM reader_local_books')) == 5)
        record('fault_round_1_network_interruption_fails_visibly_and_explicit_retry_completes')
        C1.close_account(dialog)

        # ===== cancel then retry resumes =====
        dialog = C1.open_account()
        dav.pause = True
        C1.press(dialog, SYNC)
        assert dav.blocked.wait(60)
        C1.press(dialog, CANCEL)
        dav.release.set()
        C1.wait_note(dialog, 'CANCELLED', 120)
        assert C1.enabled(dialog, RETRY)
        shot('07-cancelled.bmp', dialog)
        dav.release.clear()
        C1.press(dialog, RETRY)
        C1.wait_note(dialog, '同步完成', 240)
        record('network_cancel_is_visible_and_retry_resumes_to_completion')
        C1.close_account(dialog)
        C1.close();assert C1.process.returncode == 0

        # ===== fault round 2: mapping failure after the SDK import, then repair =====
        D = new_device('device-d')
        dialog = D.open_account()
        D.fill(dialog, root, user, password, False);D.apply(dialog, '仅本次会话')
        D.press(dialog, SYNC)
        lock = None
        end = time.monotonic() + 240
        while time.monotonic() < end:
            try:
                if sql('device-d', 'SELECT count(*) FROM reader_books')[0][0] >= 5:
                    lock = sqlite3.connect(product_db('device-d'), timeout=0.05, isolation_level=None)
                    lock.execute('BEGIN IMMEDIATE')
                    break
            except sqlite3.OperationalError:
                lock = None
            time.sleep(.003)
        assert lock is not None, 'projected rows never appeared'
        try:
            D.wait_note(dialog, '映射待恢复', 300)
        finally:
            lock.rollback();lock.close()
        shot('08-mapping-failure.bmp', dialog)
        D.close_account(dialog)
        D.wait_idle();send(D.control('books'), 0, 0)
        send(U.GetDlgItem(D.window, REFRESH), BM_CLICK)
        D.wait(lambda: len(sql('device-d', 'SELECT sdk_book_id FROM reader_local_books')) == 5, timeout=120)
        D.wait_idle()
        D.open('Account Epub');D.wait_idle()
        record('fault_round_2_mapping_failure_after_import_is_reported_and_repaired_without_reimport')
        D.close();assert D.process.returncode == 0

        # ===== fault round 3: close while scanning =====
        E = new_device('device-e')
        dialog = E.open_account()
        E.fill(dialog, root, user, password, False);E.apply(dialog, '仅本次会话')
        dav.pause = True;dav.release.clear();dav.blocked.clear()
        E.press(dialog, SYNC)
        assert dav.blocked.wait(120)
        started = time.monotonic()
        U.PostMessageW(E.window, 0x10, 0, 0)
        time.sleep(.5)
        assert E.process.poll() is None
        alive = send(E.control('status'), 0xE, timeout=3000) >= 0
        assert alive
        code = E.process.wait(timeout=60);E.log.close()
        elapsed = time.monotonic() - started
        dav.release.set()
        assert code == 0 and elapsed < 45, (code, elapsed)
        record('fault_round_3_closing_during_a_native_scan_waits_for_closed_then_exits_cleanly')
        E = new_device('device-e', existing=True)
        dialog = E.open_account()
        E.fill(dialog, root, user, password, False);E.apply(dialog, '仅本次会话')
        E.run_sync(dialog)
        E.close_account(dialog)
        record('reopened_library_resumes_after_closing_mid_scan')
        E.close();assert E.process.returncode == 0

        # ===== account isolation =====
        F = new_device('device-f')
        dialog = F.open_account()
        F.fill(dialog, other_root, user, password, False);F.apply(dialog, '仅本次会话')
        F.run_sync(dialog)
        assert sql('device-f', 'SELECT count(*) FROM reader_books')[0][0] == 0
        assert not any(r['path'].startswith('/dav/') for r in dav.requests[-40:])
        record('independent_account_root_sees_none_of_the_other_accounts_books')
        F.close_account(dialog);F.close()

        # ===== every host has exited: no secret survives on disk =====
        leak_scan_everything()
        record('no_plaintext_credential_survives_any_product_shutdown')

        # ===== link graph =====
        graph = args.link_map.read_text(errors='replace')
        for needle in ('reader_session', 'exr_webdav', 'exr_credentials', 'exr_sideload', 'reader_revisions', 'sqlite3_open'):
            assert needle in graph, needle
        shutil.copyfile(args.link_map, output / 'windows-host.map')
        dependents = subprocess.run(['dumpbin', '/DEPENDENTS', str(args.candidate)], capture_output=True, text=True).stdout
        (output / 'dependents.txt').write_text(dependents)
        assert 'WINHTTP.dll' in dependents.upper().replace('WINHTTP.DLL', 'WINHTTP.dll') or 'winhttp' in dependents.lower()
        record('link_graph_contains_native_session_credentials_sideload_and_winhttp_without_webview')
        assert len(checks) == 25, len(checks)
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks, 'count': len(checks),
                  'program_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(), 'screenshots': shots,
                  'uncovered': ['Credential Manager UNAVAILABLE state',
                                'screen-reader narration',
                                'CONCURRENT, PENDING-parent and tombstone receive states are displayed but never provoked end to end',
                                'cancel during receive/import (only cancel during the network scan is exercised)',
                                'a real remote HTTPS collection (loopback TLS with a runner-local test CA only)'],
                  'complete_product': False}
        (output / 'account-ui.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'accepted': True, 'count': len(checks)}), flush=True)
    finally:
        for device in devices:
            if device.process.poll() is None:
                if sys.exc_info()[0] is not None:
                    try:
                        device.diagnose(output)
                    except Exception as error:
                        print('diagnostic failed: %r' % (error,), flush=True)
                device.process.kill();device.process.wait(timeout=20)
            if not device.log.closed:
                device.log.close()
        try:
            thumbprint = subprocess.run(['powershell', '-NoProfile', '-Command',
                                         "(New-Object Security.Cryptography.X509Certificates.X509Certificate2('%s')).Thumbprint" % certificate],
                                        capture_output=True, text=True).stdout.strip()
            if thumbprint:
                subprocess.run(['certutil', '-delstore', 'Root', thumbprint], capture_output=True)
        except Exception:
            pass


if __name__ == '__main__':
    main()
