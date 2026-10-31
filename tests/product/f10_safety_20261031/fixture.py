# SPDX-License-Identifier: MIT
"""Actions-only native HTTPS fixture. Never serializes Authorization or key."""
import hashlib
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

class Fixture:
    def __init__(self, cert, key, authorization):
        self.entries={}
        self.dirs={'/dav/'}
        self.requests=[]
        self.authorization=authorization
        self.gate_method=None
        self.gate_fragment=None
        self.arrived=threading.Event()
        self.release=threading.Event()
        self.lock=threading.RLock()
        outer=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args): pass
            def send(self,code,data=b''):
                self.send_response(code)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Connection','close')
                self.end_headers()
                self.close_connection=True
                try: self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ssl.SSLError): pass
            def record(self):
                good=self.headers.get('Authorization')==outer.authorization
                with outer.lock:
                    outer.requests.append({'method':self.command,'path':self.path,'authenticated':good})
                if not good:
                    self.send(401)
                    return False
                if self.command==outer.gate_method and outer.gate_fragment in self.path:
                    outer.arrived.set()
                    if not outer.release.wait(20):
                        self.send(504)
                        return False
                return True
            def do_MKCOL(self):
                if not self.record(): return
                with outer.lock:
                    existed=self.path in outer.dirs
                    outer.dirs.add(self.path)
                self.send(405 if existed else 201)
            def do_PROPFIND(self):
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                if not self.record(): return
                def entry(p,d=False):
                    size=0 if d else len(outer.entries[p])
                    return '<d:response><d:href>'+escape(p)+'</d:href><d:propstat><d:prop><d:resourcetype>'+('<d:collection/>' if d else '')+'</d:resourcetype><d:getcontentlength>'+str(size)+'</d:getcontentlength><d:getetag>&quot;f10&quot;</d:getetag></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                with outer.lock:
                    if self.path not in outer.dirs:
                        self.send(404);return
                    rows=[entry(self.path,True)]
                    rows += [entry(p,True) for p in sorted(outer.dirs) if p!=self.path and p.startswith(self.path) and '/' not in p[len(self.path):].rstrip('/')]
                    rows += [entry(p) for p in sorted(outer.entries) if p.startswith(self.path) and '/' not in p[len(self.path):]]
                self.send(207,('<d:multistatus xmlns:d="DAV:">'+''.join(rows)+'</d:multistatus>').encode())
            def do_PUT(self):
                data=self.rfile.read(int(self.headers.get('Content-Length','0')))
                if not self.record(): return
                with outer.lock:
                    if self.path in outer.entries:
                        self.send(412);return
                    outer.entries[self.path]=data
                self.send(201)
            def do_GET(self):
                if not self.record(): return
                with outer.lock: data=outer.entries.get(self.path)
                self.send(404 if data is None else 200,data or b'')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert),str(key))
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url='https://127.0.0.1:'+str(self.server.server_port)+'/dav/'
    def add(self,path,data):
        with self.lock:
            self.entries[path]=data
            parts=path.strip('/').split('/')[:-1]
            for n in range(1,len(parts)+1): self.dirs.add('/'+'/'.join(parts[:n])+'/')
    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
