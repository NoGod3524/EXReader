"""Actions-only HTTPS DAV relay. Each phase starts a separate local server."""
import base64, hashlib, json, os, shutil, ssl, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
OBJECTS = 'exreader-sync-v1/objects/'
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


def start(folder, previous=None):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cert,key=folder/'cert.pem',folder/'key.pem'
    openssl=shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe'
    subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
    if os.name=='nt': subprocess.run(['certutil','-addstore','-f','Root',str(cert)],check=True,capture_output=True)
    else:
        subprocess.run(['sudo','cp',str(cert),'/usr/local/share/ca-certificates/exr-relay.crt'],check=True)
        subprocess.run(['sudo','update-ca-certificates'],check=True,capture_output=True)
    user='relay-fixture';password='relay-'+os.urandom(24).hex()
    auth='Basic '+base64.b64encode((user+':'+password).encode()).decode()
    dav=Dav(cert,key,auth);dav.certificate_sha256=hashlib.sha256(cert.read_bytes()).hexdigest()
    dav.prior_entries={};dav.prior_directories=set();dav.previous_sha256=None
    if previous:
        prior_bytes=Path(previous).read_bytes();saved=json.loads(prior_bytes);dav.previous_sha256=hashlib.sha256(prior_bytes).hexdigest()
        assert saved['schema']==1 and saved['source_sha']==os.environ['GITHUB_SHA'] and saved['run_id']==os.environ['GITHUB_RUN_ID'] and saved['attempt']==os.environ['GITHUB_RUN_ATTEMPT']
        dav.directories=set(saved['directories']);dav.entries={}
        for path,value in saved['entries'].items():
            body=base64.b64decode(value['body'],validate=True)
            assert hashlib.sha256(body).hexdigest()==value['sha256']
            dav.entries[path]=body
        dav.prior_entries=dict(dav.entries);dav.prior_directories=set(dav.directories)
    return dav,user,password

def save(dav, folder, phase, data):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    assert dav.prior_directories.issubset(dav.directories)
    assert all(dav.entries.get(path)==body for path,body in dav.prior_entries.items())
    snapshot={'schema':1,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
      'phase':phase,'previous_sha256':dav.previous_sha256,'server':{'base':dav.base,'certificate_sha256':dav.certificate_sha256,'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},'directories':sorted(dav.directories),'entries':{p:{'sha256':hashlib.sha256(b).hexdigest(),'body':base64.b64encode(b).decode()} for p,b in sorted(dav.entries.items())},'data':data}
    assert all(r['authenticated'] for r in dav.requests)
    (folder/'state.json').write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
    (folder/'requests.json').write_text(json.dumps(dav.requests),encoding='utf-8')
    dav.server.shutdown();dav.server.server_close()
    (folder/'key.pem').unlink(missing_ok=True)
