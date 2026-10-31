# SPDX-License-Identifier: MIT
"""Runner-local authenticated HTTPS store; no revision/database injection."""
import hashlib
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

class Store:
    def __init__(self, certificate, key, authorization):
        self.entries, self.requests = {}, []
        self.directories = {"/dav/"}
        self.lock = threading.Lock()
        self.offline = False
        self.hold_put = False
        self.put_committed, self.release = threading.Event(), threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_):
                pass
            def reply(self, code, data=b""):
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                try:
                    self.wfile.write(data)
                except (OSError, ssl.SSLError):
                    pass
            def authorized(self):
                self.body = b""
                size = int(self.headers.get("Content-Length", "0"))
                if size > 8 * 1024 * 1024:
                    self.reply(413)
                    return False
                if size:
                    self.body = self.rfile.read(size)
                good = self.headers.get("Authorization") == authorization
                with outer.lock:
                    outer.requests.append({"method": self.command, "path": self.path,
                                           "authenticated": good,
                                           "body_sha256": hashlib.sha256(self.body).hexdigest()})
                if not good or outer.offline:
                    self.reply(401 if not good else 503)
                    return False
                return True
            def do_MKCOL(self):
                if not self.authorized(): return
                with outer.lock:
                    exists = self.path in outer.directories
                    outer.directories.add(self.path)
                self.reply(405 if exists else 201)
            def do_PUT(self):
                if not self.authorized(): return
                if self.headers.get("If-None-Match") != "*":
                    self.reply(428)
                    return
                with outer.lock:
                    exists = self.path in outer.entries
                    if not exists: outer.entries[self.path] = self.body
                    held = outer.hold_put and "/revisions/" in self.path
                    if held: outer.hold_put = False
                if held:
                    outer.put_committed.set()
                    outer.release.wait(60)
                self.reply(412 if exists else 201)
            def do_GET(self):
                if not self.authorized(): return
                with outer.lock: body = outer.entries.get(self.path)
                self.reply(404 if body is None else 200, body or b"")
            def do_PROPFIND(self):
                if not self.authorized(): return
                with outer.lock:
                    if self.path not in outer.directories:
                        rows = None
                    else:
                        children = [(p, True, 0) for p in outer.directories
                                    if p.startswith(self.path) and
                                    (p == self.path or "/" not in p[len(self.path):].rstrip("/"))]
                        children += [(p, False, len(v)) for p, v in outer.entries.items()
                                     if p.startswith(self.path) and "/" not in p[len(self.path):]]
                        rows = "".join("<d:response><d:href>" + escape(p) +
                            "</d:href><d:propstat><d:prop><d:resourcetype>" +
                            ("<d:collection/>" if directory else "") +
                            "</d:resourcetype><d:getcontentlength>" + str(size) +
                            "</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status>"
                            "</d:propstat></d:response>" for p, directory, size in children)
                self.reply(404 if rows is None else 207,
                    b"" if rows is None else ('<d:multistatus xmlns:d="DAV:">' + rows + "</d:multistatus>").encode())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = "https://127.0.0.1:%d/dav/" % self.server.server_port
    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
