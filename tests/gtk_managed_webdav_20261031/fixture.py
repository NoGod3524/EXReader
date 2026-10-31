"""Private Actions-only HTTPS DAV service shared by transport and actual GTK tests."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import uuid
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/webdav"))
from cloud_native import trust_fixture_certificates

class Fixture:
 def __init__(self,folder):
  assert os.environ.get("GITHUB_ACTIONS")=="true"
  folder.mkdir(parents=True,exist_ok=True)
  key,cert=folder/"server.key",folder/"server.crt"
  subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1","-keyout",str(key),
   "-out",str(cert),"-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost,IP:127.0.0.1"],check=True,capture_output=True)
  trust_fixture_certificates((cert,),"managed-webdav-")
  self.auth="Basic "+base64.b64encode(("managed:"+uuid.uuid4().hex).encode()).decode()
  self.entries={"/dav/payload":b"managed product staging\n"*128}
  self.directories={"/dav/","/dav/exreader-sync-v1/","/dav/exreader-sync-v1/revisions/","/dav/exreader-sync-v1/objects/"}
  self.directories.update("/dav/exreader-sync-v1/revisions/%02x/"%n for n in range(256))
  self.requests=[];self.pause="";self.http=0;self.disconnect=False
  self.blocked=threading.Event();self.release=threading.Event();self.release.set()
  fixture=self
  class Handler(BaseHTTPRequestHandler):
   protocol_version="HTTP/1.1"
   def log_message(self,*unused):pass
   def authorized(self):
    yes=self.headers.get("Authorization")==fixture.auth
    fixture.requests.append(dict(method=self.command,path=self.path,authenticated=yes))
    if not yes:self.send(401);return False
    return True
   def send(self,code,body=b""):
    self.send_response(code);self.send_header("Content-Length",str(len(body)));self.send_header("Connection","close");self.end_headers();self.close_connection=True
    try:self.wfile.write(body)
    except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
   def do_GET(self):
    if not self.authorized():return
    if fixture.pause and fixture.pause in self.path:
     fixture.blocked.set()
     if not fixture.release.wait(30):self.send(504);return
    if fixture.http:self.send(fixture.http);return
    body=fixture.entries.get(self.path)
    if body is None:self.send(404);return
    if fixture.disconnect:
     self.send_response(200);self.send_header("Content-Length",str(len(body)));self.end_headers()
     self.wfile.write(body[:1]);self.wfile.flush();self.connection.shutdown(socket.SHUT_RDWR);self.close_connection=True;return
    self.send(200,body)
   def do_PROPFIND(self):
    if not self.authorized():return
    if fixture.http:self.send(fixture.http);return
    if self.path not in fixture.directories:self.send(404);return
    def item(path,folder):
     size=0 if folder else len(fixture.entries[path])
     return '<d:response><d:href>'+escape(path)+'</d:href><d:propstat><d:prop><d:resourcetype>'+('<d:collection/>' if folder else '')+'</d:resourcetype><d:getcontentlength>'+str(size)+'</d:getcontentlength><d:getetag>&quot;managed&quot;</d:getetag></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
    body=item(self.path,True)
    for path in sorted(fixture.directories|set(fixture.entries)):
     if path==self.path or not path.startswith(self.path):continue
     tail=path[len(self.path):].rstrip("/")
     if "/" not in tail:body+=item(path,path in fixture.directories)
    self.send(207,('<d:multistatus xmlns:d="DAV:">'+body+'</d:multistatus>').encode())
   def do_MKCOL(self):
    if not self.authorized():return
    exists=self.path in fixture.directories;fixture.directories.add(self.path);self.send(405 if exists else 201)
   def do_PUT(self):
    if not self.authorized():return
    n=int(self.headers.get("Content-Length","0"))
    if not 0<n<=128*1024*1024:self.send(413);return
    data=self.rfile.read(n)
    if self.path in fixture.entries:self.send(412);return
    if self.headers.get("If-None-Match")!="*":self.send(400);return
    fixture.entries[self.path]=data;self.send(201)
  self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler);self.server.daemon_threads=True
  context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
  self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.url="https://127.0.0.1:%d/dav/"%self.server.server_port
 def hold(self,path):
  self.pause=path;self.blocked.clear();self.release.clear()
 def resume(self):
  self.pause="";self.release.set()
 def close(self):
  self.resume();self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
 def book(self):
  data=("Managed crash cleanup book\nA complete HTTPS download opens in the real GTK reader.\n"*60).encode()
  digest=hashlib.sha256(data).hexdigest();key="txt:"+digest
  value=dict(version=1,id="10000000000000000000000000000001",entity_kind="book",entity_key=key,
   operation="put",location_kind="none",parents=[],payload=dict(format="txt",source_sha256=digest,
   source_bytes=len(data),title="Managed crash cleanup book",author="Fixture",favorite=False))
  wire=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode();sha=hashlib.sha256(wire).hexdigest()
  self.entries["/dav/exreader-sync-v1/revisions/10/"+value["id"]+"-"+sha+".json"]=wire
  self.directories.add("/dav/exreader-sync-v1/objects/"+digest[:2]+"/")
  self.entries["/dav/exreader-sync-v1/objects/"+digest[:2]+"/"+digest+".txt"]=data
  return dict(key=key,sha256=digest,data=data,wire=wire,revision=value["id"])
