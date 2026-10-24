#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only TLS fixture, with request traces that never retain Authorization."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import threading
import time


def require_actions():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('Actions only')


def prepare(root):
    require_actions();private=root/'private';private.mkdir(parents=True,exist_ok=True);private.chmod(0o700)
    public=root/'public';public.mkdir(exist_ok=True)
    def openssl(*args):
        result=subprocess.run(['openssl',*map(str,args)],capture_output=True,check=True)
        # OpenSSL progress is not a protocol request trace and contains no credentials.
        (public/'certificate-generation.log').open('ab').write(result.stderr)
    openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',private/'ca.key','-out',public/'ca.crt',
            '-subj','/CN=EXReader Android test-only CA','-addext','basicConstraints=critical,CA:TRUE')
    for name,san in (('server','DNS:localhost,IP:127.0.0.1'),('wrong-host','DNS:wrong.example')):
        openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',private/(name+'.key'),'-out',private/(name+'.csr'),'-subj','/CN='+name)
        ext=private/(name+'.ext');ext.write_text('subjectAltName='+san+'\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n')
        openssl('x509','-req','-in',private/(name+'.csr'),'-CA',public/'ca.crt','-CAkey',private/'ca.key','-CAcreateserial',
                '-out',public/(name+'.crt'),'-days','2','-extfile',ext)
    openssl('req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',private/'untrusted.key','-out',public/'untrusted.crt',
            '-subj','/CN=untrusted','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1')
    return root


class Fixture:
    def __init__(self,root):
        require_actions();self.root=Path(root);self.servers=[];self.requests=[];self.lock=threading.Lock()
    def start(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def record(self):
                headers=[(name,('sha256:'+hashlib.sha256(value.encode()).hexdigest()) if name.lower()=='authorization' else value)
                         for name,value in self.headers.items()]
                with owner.lock:owner.requests.append({'request_line':self.raw_requestline.decode('ascii',errors='replace').strip(),'headers':headers})
            def answer(self,code,body=b'EXReader platform TLS'):
                self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (OSError,ssl.SSLError):pass
            def do_GET(self):
                self.record()
                if self.path=='/probe/slow':time.sleep(2)
                self.answer(200)
            def do_PUT(self):
                self.record()
                if self.path=='/probe/write-block':
                    time.sleep(2);self.close_connection=True;return
                self.answer(201,b'')
        for name in ('server','wrong-host','untrusted'):
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.root/'public'/(name+'.crt'),self.root/'private'/(name+'.key'))
            server.socket=tls.wrap_socket(server.socket,server_side=True);self.servers.append(server)
            threading.Thread(target=server.serve_forever,daemon=True).start()
        return {name:server.server_port for name,server in zip(('trusted','wrong_host','untrusted'),self.servers)}
    def close(self):
        for server in self.servers:server.shutdown();server.server_close()
        with self.lock:(self.root/'requests.json').write_text(json.dumps(self.requests,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare']);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.output)
