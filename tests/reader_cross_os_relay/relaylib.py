# SPDX-License-Identifier: MIT
"""Actions-only helpers for the cross-OS artifact relay: identity, a file-backed
HTTPS WebDAV service, independent tree/inventory checks and process runners.
Never run locally."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'webdav'))
ROLES = ('txt', 'epub', 'pdf', 'cbz')
DIRECTIONS = {'linux-to-windows': ('Linux', 'Windows'), 'windows-to-linux': ('Windows', 'Linux'),
              'linux-to-macos': ('Linux', 'macOS'), 'macos-to-linux': ('macOS', 'Linux')}
SYSTEM_TO_RUNNER = {'Linux': 'Linux', 'Windows': 'Windows', 'Darwin': 'macOS'}
INVENTORY_FORMAT = 'exr-relay-inventory-1'
SYNC = 'exreader-sync-v1'
MAX_REQUEST_BODY = 128 * 1024 * 1024


class Refused(Exception):
    pass


def need(condition, message):
    if not condition:
        raise Refused(message)


def exe(name):
    return name + ('.exe' if os.name == 'nt' else '')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_path(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def current_os():
    return SYSTEM_TO_RUNNER[platform.system()]


def run_identity():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    return {'source_sha': os.environ['GITHUB_SHA'], 'run_id': str(os.environ['GITHUB_RUN_ID']),
            'attempt': str(os.environ['GITHUB_RUN_ATTEMPT'])}


def same_identity(record, identity):
    return all(str(record.get(k)) == identity[k] for k in identity)


def load_expected():
    value = json.loads((HERE / 'expected.json').read_text(encoding='utf-8'))
    s = value['strings']
    for role in ROLES:
        s['sort_' + role] = unicodedata.normalize('NFC', s['title_' + role])
    s['return_sort_epub'] = unicodedata.normalize('NFC', s['return_title_epub'])
    s['return_quote_hex'] = s['return_quote'].encode('utf-8').hex()
    return value


def pinned(expected):
    for role, item in expected['originals'].items():
        need(item['sha256'] and item['bytes'], 'original digest for %s is not pinned in expected.json' % role)
    return {role: item['sha256'] for role, item in expected['originals'].items()}


def write_plan(expected, path, font):
    rows = []
    for key, value in expected['strings'].items():
        need('\t' not in value and '\n' not in value, 'plan value has a separator')
        rows.append('str\t%s\t%s' % (key, value))
    for case in expected['cases']:
        rows.append('case\t%s\t%s\t%s' % (case['id'], case['state'], case['quote'].encode('utf-8').hex() or '-'))
    Path(path).write_text('\n'.join(rows) + '\n', encoding='utf-8', newline='\n')


def read_transport(path):
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line:
            rows.append(line.split('\t'))
    return rows


# ---------- independent inventory ----------
def canonical_inventory(root):
    root = Path(root)
    records = []
    total = 0
    for current, dirs, files in os.walk(root):
        for name in dirs:
            records.append((str((Path(current) / name).relative_to(root).as_posix()), None))
        for name in files:
            p = Path(current) / name
            need(not p.is_symlink(), 'symlink in tree')
            records.append((p.relative_to(root).as_posix(), p))
    records.sort(key=lambda r: r[0].encode('utf-8'))
    dirs = [r for r in records if r[1] is None]
    files = []
    for path, p in records:
        if p is not None:
            data = p.read_bytes()
            files.append((path, len(data), sha256_bytes(data)))
            total += len(data)
    digest = hashlib.sha256()
    for path, _ in dirs:
        digest.update(('D\t%s\n' % path).encode('utf-8'))
    for path, size, sha in files:
        digest.update(('F\t%d\t%s\t%s\n' % (size, sha, path)).encode('utf-8'))
    out = '{"format":"%s",\n' % INVENTORY_FORMAT
    out += '"file_count":%d,"dir_count":%d,"total_bytes":%d,"digest":"%s",\n' % (len(files), len(dirs), total, digest.hexdigest())
    out += '"dirs":[\n' + ''.join('"%s"%s\n' % (p, ',' if i + 1 < len(dirs) else '') for i, (p, _) in enumerate(dirs))
    out += '],\n"files":[\n' + ''.join('{"path":"%s","bytes":%d,"sha256":"%s"}%s\n' % (p, n, h, ',' if i + 1 < len(files) else '')
                                       for i, (p, n, h) in enumerate(files)) + ']}\n'
    return out.encode('utf-8')


def inventory_files(inventory_bytes):
    value = json.loads(inventory_bytes.decode('utf-8'))
    need(value['format'] == INVENTORY_FORMAT, 'inventory format')
    return {f['path']: (f['bytes'], f['sha256']) for f in value['files']}, value


def tool(tool_path, *args):
    return subprocess.run([str(tool_path), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=120)


def native_inventory(tool_path, tree, output):
    done = tool(tool_path, 'inventory', tree, output)
    need(done.returncode == 0, 'native inventory refused: ' + done.stderr)
    native = Path(output).read_bytes()
    need(native == canonical_inventory(tree), 'native component inventory differs from the independent Python inventory')
    return native


# ---------- certificates and the file-backed HTTPS WebDAV service ----------
def make_certificate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    key, cert = directory / 'server.key', directory / 'server.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(cert),
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], check=True, capture_output=True)
    from cloud_native import trust_fixture_certificates
    trust_fixture_certificates([cert], 'reader-cross-os-relay-')
    return key, cert


class Service:
    """Immutable-publication WebDAV directory service rooted at /dav/ over one tree."""

    def __init__(self, tree, key, cert):
        self.tree = Path(tree)
        self.secret = uuid.uuid4().hex
        self.auth = 'Basic ' + base64.b64encode(('relay:' + self.secret).encode()).decode()
        self.requests = []
        self.lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def reply(self, code, body=b'', extra=None):
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.close_connection = True
                with service.lock:
                    service.requests.append({'method': self.command, 'path': self.path, 'status': code,
                                             'authenticated': self.headers.get('Authorization') == service.auth,
                                             'depth': self.headers.get('Depth'), 'if_none_match': self.headers.get('If-None-Match')})
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

            def target(self):
                path = urllib.parse.unquote(self.path.split('?', 1)[0])
                if not (path == '/dav' or path.startswith('/dav/')):
                    return None
                parts = [p for p in path[len('/dav'):].split('/') if p]
                if any(p in ('.', '..') or '\\' in p or ':' in p for p in parts):
                    return None
                return service.tree.joinpath(*parts)

            def authorized(self):
                if self.headers.get('Authorization') == service.auth:
                    return True
                self.reply(401)
                return False

            def drain(self):
                count = int(self.headers.get('Content-Length', 0))
                need(0 <= count <= MAX_REQUEST_BODY, 'request body too large')
                return self.rfile.read(count) if count else b''

            def do_MKCOL(self):
                self.drain()
                if not self.authorized():
                    return
                target = self.target()
                if target is None:
                    return self.reply(403)
                with service.lock:
                    if target.exists():
                        code = 405
                    elif not target.parent.is_dir():
                        code = 409
                    else:
                        target.mkdir()
                        code = 201
                self.reply(code)

            def do_PUT(self):
                body = self.drain()
                if not self.authorized():
                    return
                target = self.target()
                if target is None or self.headers.get('If-None-Match') != '*':
                    return self.reply(400 if target is not None else 403)
                with service.lock:
                    if target.exists():
                        code = 412
                    elif not target.parent.is_dir():
                        code = 409
                    else:
                        temporary = target.with_name('.upload-' + uuid.uuid4().hex)
                        temporary.write_bytes(body)
                        os.replace(temporary, target)
                        code = 201
                self.reply(code)

            def do_GET(self):
                if not self.authorized():
                    return
                target = self.target()
                if target is None or not target.is_file():
                    return self.reply(404)
                self.reply(200, target.read_bytes())

            def do_PROPFIND(self):
                self.drain()
                if not self.authorized():
                    return
                target = self.target()
                if target is None or self.headers.get('Depth') != '1':
                    return self.reply(400)
                if not target.is_dir():
                    return self.reply(404)
                base = self.path.split('?', 1)[0]
                if not base.endswith('/'):
                    base += '/'
                rows = [(base, True, 0)]
                for child in sorted(target.iterdir(), key=lambda p: p.name.encode('utf-8')):
                    rows.append((base + urllib.parse.quote(child.name) + ('/' if child.is_dir() else ''), child.is_dir(),
                                 0 if child.is_dir() else child.stat().st_size))
                xml = ''.join('<d:response><d:href>%s</d:href><d:propstat><d:prop><d:resourcetype>%s</d:resourcetype>'
                              '<d:getcontentlength>%d</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                              % (href, '<d:collection/>' if directory else '', size) for href, directory, size in rows)
                self.reply(207, ('<d:multistatus xmlns:d="DAV:">' + xml + '</d:multistatus>').encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def root_url(self):
        return 'https://localhost:%d/dav/' % self.server.server_port

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def assert_hygiene(self):
        need(self.requests and all(r['authenticated'] for r in self.requests), 'unauthenticated or no requests')
        need(all(r['if_none_match'] == '*' for r in self.requests if r['method'] == 'PUT'), 'unconditional PUT')
        need(all(r['depth'] == '1' for r in self.requests if r['method'] == 'PROPFIND'), 'PROPFIND without Depth: 1')
        need(not any(r['status'] == 403 for r in self.requests), 'traversal-shaped request')


def run_probe(probe, args, secret_env, log):
    done = subprocess.run([str(probe)] + [str(a) for a in args], capture_output=True, text=True, encoding='utf-8', timeout=600,
                          env=dict(os.environ, READER_TEST_AUTH=secret_env))
    Path(log).write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
    print(done.stdout)
    print(done.stderr)
    return done


def scan_for_secret(directory, *needles):
    for path in Path(directory).rglob('*'):
        if path.is_file() and path.suffix != '.key':
            data = path.read_bytes()
            for n in needles:
                need(n.encode() not in data, 'secret found in %s' % path)


def parse_no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        need(k not in out, 'duplicate JSON key ' + k)
        out[k] = v
    return out


# ---------- independent checks of the relayed service tree ----------
def load_revisions(tree):
    revs = {}
    base = Path(tree) / SYNC / 'revisions'
    for path in sorted(base.rglob('*.json')):
        m = re.fullmatch(r'([0-9a-f]{32})-([0-9a-f]{64})\.json', path.name)
        need(m and path.parent.name == m.group(1)[:2], 'revision leaf name ' + path.name)
        body = path.read_bytes()
        need(sha256_bytes(body) == m.group(2), 'revision bytes do not match their leaf digest ' + path.name)
        value = json.loads(body.decode('utf-8'), object_pairs_hook=parse_no_duplicates)
        need(value['id'] == m.group(1) and value['version'] == 1, 'revision envelope ' + path.name)
        revs[m.group(1)] = (value, m.group(2), len(body))
    return revs


def entity_heads(revs, kind, key):
    members = {i: v for i, (v, _, _) in revs.items() if v['entity_kind'] == kind and v['entity_key'] == key}
    parents = {p for v in members.values() for p in v['parents']}
    return members, sorted(i for i in members if i not in parents)


def verify_originals(tree, expected):
    pins = pinned(expected)
    for role, item in expected['originals'].items():
        path = Path(tree) / SYNC / 'objects' / pins[role][:2] / (pins[role] + '.' + role)
        need(path.is_file(), 'original object missing for ' + role)
        data = path.read_bytes()
        need(sha256_bytes(data) == pins[role] and len(data) == item['bytes'], 'original object bytes differ from the pin for ' + role)


def verify_tree(tree, expected, rows, returned):
    """rows: parsed transport.tsv rows (from the sender). Independent of any probe report."""
    s = expected['strings']
    verify_originals(tree, expected)
    revs = load_revisions(tree)
    need(len(revs) == (35 if returned else 31), 'revision count %d' % len(revs))
    labels = {r[1]: r for r in rows if r[0] == 'rev'}
    pins = pinned(expected)
    for role in ROLES:
        value = revs[labels['book-' + role][4]][0]
        p = value['payload']
        need(value['entity_key'] == '%s:%s' % (role, pins[role]) and value['operation'] == 'put', 'book key ' + role)
        need(p['title'] == s['title_' + role] and p['author'] == s['author_' + role] and p['favorite'] is True, 'book metadata not byte exact ' + role)
        need(p['source_sha256'] == pins[role] and p['source_bytes'] == expected['originals'][role]['bytes'], 'book identity ' + role)
    need(unicodedata.is_normalized('NFC', s['title_txt']) and not unicodedata.is_normalized('NFC', s['title_epub']), 'pinned NFC/NFD classes')
    cases = [r for r in rows if r[0] == 'case']
    need([c[1] for c in cases] == [c['id'] for c in expected['cases']], 'capture ids/order differ from the pin')
    for c, pin in zip(cases, expected['cases']):
        value, sha, _ = revs[c[5]]
        need(sha == c[6], 'capture digest ' + c[1])
        loc = value['payload']['location']
        need(loc['anchor_version'] == 2 and loc['mode'] == c[2], 'capture anchor v2/mode ' + c[1])
        need(loc['selector']['exact'] == pin['quote'], 'capture quote ' + c[1])
    ck = labels['conflict-root'][3]
    members, heads = entity_heads(revs, 'tag', ck)
    a, b = labels['conflict-a'][4], labels['conflict-b'][4]
    if not returned:
        need(len(members) == 3 and heads == sorted([a, b]), 'concurrent heads')
    else:
        merge = labels['return-tag-merge'][4]
        need(heads == [merge] and sorted(revs[merge][0]['parents']) == sorted([a, b]) and revs[merge][0]['payload']['name'] == s['tag_merge'], 'conflict merge')
    t = labels['tomb-delete'][4]
    need(revs[t][0]['operation'] == 'delete' and revs[t][0]['payload'] is None and revs[t][0]['parents'] == [labels['tomb-put'][4]], 'tombstone')
    child, parent = labels['pending-child'][4], labels['pending-parent'][4]
    need(revs[child][0]['parents'] == [parent] and child[:2] != parent[:2], 'pending-parent shape (different shards)')
    need(revs[labels['shelf'][4]][0]['payload']['name'] == s['shelf_name'], 'shelf name')
    need(revs[labels['membership'][4]][0]['payload']['collection_id'] == labels['shelf'][3], 'membership shelf')
    if returned:
        ret = {r[1]: r for r in rows if r[0] == 'rev'}
        edit = revs[ret['return-book-edit'][4]][0]
        need(edit['parents'] == [labels['book-epub'][4]] and edit['payload']['title'] == s['return_title_epub'] and edit['payload']['favorite'] is False, 'returned book edit')
        mem = revs[ret['return-membership-delete'][4]][0]
        need(mem['operation'] == 'delete' and mem['parents'] == [labels['membership'][4]], 'returned membership tombstone')
        hl = [r for r in rows if r[0] == 'retcase'][0]
        loc = revs[hl[4]][0]['payload']['location']
        need(loc['anchor_version'] == 2 and loc['selector']['exact'] == s['return_quote'], 'returned highlight')
    return revs


def clone_tree(source, destination):
    if Path(destination).exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, symlinks=False)


def temp_dir(prefix):
    return Path(tempfile.mkdtemp(prefix=prefix))
