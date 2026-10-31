#!/usr/bin/env python3
"""Actions-only synthetic HTTPS store; never stores authentication values in evidence."""
import base64, hashlib, json, os, re, secrets, shutil, ssl, subprocess, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.sax.saxutils import escape
BASE=Path(__file__).resolve().parents[2]
def need(value,message):
    if not value: raise AssertionError(message)
def sha(data): return hashlib.sha256(data).hexdigest()
def identity():
    return dict(source=os.environ["GITHUB_SHA"],run=int(os.environ["GITHUB_RUN_ID"]),attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def body(): return ("F02 cross-platform exact original. 共享原书，不共享本地行号。\n"*160).encode("utf-8")
def safe_path(path):
    return bool(re.fullmatch(r"/dav/(?:[a-zA-Z0-9_.-]+/)*(?:[a-zA-Z0-9_.-]+)?",path)) and ".." not in path.split("/")
class Store:
    def __init__(self,initial=None):
        need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
        self.server=None;self.started=False;self.closed=False;self.trust_installed=False;self.temp=None
        try:self.initialize(initial)
        except BaseException:
            self.close();raise
    def initialize(self,initial):
        self.temp=tempfile.TemporaryDirectory(prefix="f02-tls-")
        self.dir=Path(self.temp.name);self.key=self.dir/"server.key";self.cert=self.dir/"server.crt"
        self.user="u"+secrets.token_hex(12);self.password="p"+secrets.token_hex(24)
        self.auth="Basic "+base64.b64encode((self.user+":"+self.password).encode()).decode()
        self.entries={};self.directories={"/dav/"};self.events=[];self.lock=threading.Lock();self.closed=False
        if initial is not None:
            manifest=json.loads((Path(initial)/"store.json").read_text(encoding="utf-8"))
            need(manifest["identity"]==identity(),"store identity")
            self.directories=set(manifest["directories"])
            need(all(safe_path(p) for p in self.directories),"directory path")
            for item in manifest["entries"]:
                need(safe_path(item["path"]) and re.fullmatch("[0-9a-f]{64}",item["sha256"]),"entry identity")
                data=(Path(initial)/"objects"/item["sha256"]).read_bytes()
                need(len(data)==item["bytes"] and sha(data)==item["sha256"],"store bytes")
                need(item["path"] not in self.entries,"duplicate entry")
                self.entries[item["path"]]=data
        openssl=shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
        subprocess.run([openssl,"req","-x509","-newkey","rsa:2048","-nodes","-days","1","-keyout",str(self.key),"-out",str(self.cert),"-subj","/CN=127.0.0.1","-addext","subjectAltName=IP:127.0.0.1"],check=True,capture_output=True)
        fp=subprocess.check_output([openssl,"x509","-in",str(self.cert),"-noout","-fingerprint","-sha1"],text=True)
        self.thumb=fp.strip().split("=")[-1].replace(":","")
        if os.name=="nt":
            self.trust_installed=True
            subprocess.run(["certutil","-addstore","-f","Root",str(self.cert)],check=True,capture_output=True)
        else:
            self.trust="/usr/local/share/ca-certificates/exreader-f02-"+str(os.getpid())+".crt"
            self.trust_installed=True
            subprocess.run(["sudo","cp",str(self.cert),self.trust],check=True,capture_output=True)
            subprocess.run(["sudo","update-ca-certificates"],check=True,capture_output=True)
        outer=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version="HTTP/1.1"
            def log_message(self,*unused): pass
            def reply(self,code,data=b""):
                with outer.lock:
                    outer.events.append(dict(seq=len(outer.events)+1,method=self.command,path=self.path,status=code,
                        authenticated=self.headers.get("Authorization")==outer.auth,
                        request_bytes=len(getattr(self,"body",b"")),request_sha256=sha(getattr(self,"body",b"")),
                        response_bytes=len(data),response_sha256=sha(data)))
                self.send_response(code);self.send_header("Content-Length",str(len(data)))
                self.send_header("Connection","close");self.end_headers();self.close_connection=True
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
            def authorize(self):
                if not safe_path(self.path):self.reply(400);return False
                length=int(self.headers.get("Content-Length","0"))
                if not 0<=length<=8*1024*1024:self.reply(413);return False
                self.body=self.rfile.read(length) if length else b""
                if len(self.body)!=length:self.reply(400);return False
                if self.headers.get("Authorization")!=outer.auth:self.reply(401);return False
                return True
            def do_MKCOL(self):
                if not self.authorize():return
                with outer.lock:
                    exists=self.path in outer.directories;outer.directories.add(self.path)
                self.reply(405 if exists else 201)
            def do_PUT(self):
                if not self.authorize():return
                with outer.lock:
                    exists=self.path in outer.entries
                    if not exists:outer.entries[self.path]=self.body
                self.reply(412 if exists else 201)
            def do_GET(self):
                if not self.authorize():return
                with outer.lock:data=outer.entries.get(self.path)
                self.reply(404 if data is None else 200,data or b"")
            def do_PROPFIND(self):
                if not self.authorize():return
                with outer.lock:
                    exists=self.path in outer.directories
                    rows=[(p,True,0) for p in outer.directories if p.startswith(self.path) and (p==self.path or "/" not in p[len(self.path):].rstrip("/"))]
                    rows += [(p,False,len(b)) for p,b in outer.entries.items() if p.startswith(self.path) and "/" not in p[len(self.path):]]
                if not exists:self.reply(404);return
                xml=['<d:response><d:href>'+escape(p)+'</d:href><d:propstat><d:prop><d:resourcetype>'+('<d:collection/>' if directory else '')+'</d:resourcetype><d:getcontentlength>'+str(size)+'</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' for p,directory,size in rows]
                self.reply(207,('<d:multistatus xmlns:d="DAV:">'+''.join(xml)+'</d:multistatus>').encode())
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler);self.server.daemon_threads=False
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,self.key)
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.started=True
        self.root="https://127.0.0.1:"+str(self.server.server_port)+"/dav/"
    def snapshot(self,path):
        with self.lock:
            entries=dict(self.entries);directories=sorted(self.directories);events=list(self.events)
        path=Path(path);(path/"objects").mkdir(parents=True,exist_ok=True)
        for data in entries.values():(path/"objects"/sha(data)).write_bytes(data)
        save(path/"store.json",dict(identity=identity(),directories=directories,
            entries=[dict(path=p,bytes=len(b),sha256=sha(b)) for p,b in sorted(entries.items())]))
        save(path/"events.json",events)
        return entries,events
    def stop(self):
        if not self.closed:
            if self.server is not None:
                if self.started:self.server.shutdown()
                self.server.server_close()
            self.closed=True
    def close(self):
        try:
            self.stop()
            if self.trust_installed:
                self.trust_installed=False
                if os.name=="nt":
                    subprocess.run(["certutil","-delstore","Root",self.thumb],check=True,capture_output=True)
                else:
                    subprocess.run(["sudo","rm","-f","--",self.trust],check=True,capture_output=True)
                    subprocess.run(["sudo","update-ca-certificates"],check=True,capture_output=True)
        finally:
            if self.temp is not None:self.temp.cleanup()
    def authorize_upload(self,path):
        self.no_secrets(path)
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as output:
            output.write("safe_upload=true\n")
    def no_secrets(self,path):
        needles=[self.user.encode(),self.password.encode(),self.auth.encode(),self.key.read_bytes()]
        for p in Path(path).rglob("*"):
            if p.is_file():
                data=p.read_bytes()
                need(not any(n in data for n in needles),"evidence credential leak:"+p.name)
