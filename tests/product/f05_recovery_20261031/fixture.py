# SPDX-License-Identifier: MIT
"""Runner-local authenticated HTTPS store; no revision/database injection."""
import hashlib
import json
import os
from pathlib import Path
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

class Store:
    def __init__(self, certificate, key, authorization):
        self.entries, self.requests, self.commits = {}, [], []
        self.inherited_commits = []
        self.directories = {"/dav/"}
        self.lock = threading.Lock()
        self.offline = False
        self.hold_put = False
        self.hold_get = False
        self.get_blocked = threading.Event()
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
                    if not exists:
                        outer.entries[self.path] = self.body
                        outer.commits.append({"sequence": len(outer.commits),
                            "path": self.path, "bytes": len(self.body),
                            "sha256": hashlib.sha256(self.body).hexdigest(),
                            "authenticated_native_put": True})
                    held = outer.hold_put and "/revisions/" in self.path
                    if held: outer.hold_put = False
                if held:
                    outer.put_committed.set()
                    outer.release.wait(60)
                self.reply(412 if exists else 201)
            def do_GET(self):
                if not self.authorized(): return
                with outer.lock:
                    body = outer.entries.get(self.path)
                    held = outer.hold_get and "/objects/" in self.path
                    if held: outer.hold_get = False
                if held:
                    outer.get_blocked.set()
                    outer.release.wait(60)
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
    def checkpoint(self, directory, author):
        """Persist only actual committed PUT bytes, for same-run offline peers."""
        if os.environ.get("GITHUB_ACTIONS") != "true": raise RuntimeError("Actions only")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        with self.lock:
            entries, commits, requests = dict(self.entries), list(self.commits) + list(self.inherited_commits), list(self.requests)
            directories = sorted(self.directories)
        files = {}
        for index, (path, body) in enumerate(sorted(entries.items())):
            name = str(index) + ".body"
            digest = hashlib.sha256(body).hexdigest()
            if not any(c["path"] == path and c["sha256"] == digest for c in commits):
                raise AssertionError("checkpoint entry lacks actual authenticated PUT")
            (directory / name).write_bytes(body)
            files[path] = {"file": name, "bytes": len(body), "sha256": digest}
        manifest = {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
            "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "author": author,
            "sdk": "8357eafa28423a7ab93ba08b823af80f01ad1505",
            "files": files, "directories": directories, "commits": commits,
            "requests": requests, "simultaneous_online_peers": False}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest

    def expose_checkpoint(self, directory):
        """Expose unchanged producer bytes; never modify receiver DB/revisions."""
        directory = Path(directory)
        data = json.loads((directory / "manifest.json").read_text())
        for key, env in (("source", "GITHUB_SHA"), ("run", "GITHUB_RUN_ID"),
                         ("attempt", "GITHUB_RUN_ATTEMPT")):
            if str(data[key]) != os.environ[env]: raise AssertionError("foreign producer identity")
        if data["sdk"] != "8357eafa28423a7ab93ba08b823af80f01ad1505":
            raise AssertionError("foreign SDK producer")
        verified = {}
        for path, item in data["files"].items():
            file = directory / item["file"]
            if file.parent != directory or not path.startswith("/dav/exreader-sync-v1/"):
                raise AssertionError("producer path escape")
            body = file.read_bytes()
            if len(body) != item["bytes"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise AssertionError("producer immutable bytes differ")
            if not any(c["path"] == path and c["sha256"] == item["sha256"]
                       and c["authenticated_native_put"] for c in data["commits"]):
                raise AssertionError("producer PUT identity absent")
            verified[path] = body
        with self.lock:
            for path, body in verified.items():
                if path in self.entries and self.entries[path] != body:
                    raise AssertionError("immutable peer path collision")
            for commit in data["commits"]:
                self.inherited_commits.append({**commit, "inherited_from": {
                    "author": data["author"], "source": data["source"],
                    "run": data["run"], "attempt": data["attempt"]}})
            self.entries.update(verified)
            self.directories.update(data["directories"])
        return data

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
