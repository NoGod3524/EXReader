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
    def __init__(self,root,authorization=None):
        require_actions();self.root=Path(root);self.servers=[];self.requests=[];self.lock=threading.Lock();self.authorization=authorization
        self.payload=bytes(n%251 for n in range(524288));self.objects={};self.collections=set();self.committed=threading.Event();self.foreign_port=0
    def start(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def record(self):
                headers=[(name,('sha256:'+hashlib.sha256(value.encode()).hexdigest()) if name.lower()=='authorization' else value)
                         for name,value in self.headers.items()]
                self.trace={'request_line':self.raw_requestline.decode('ascii',errors='replace').strip(),'headers':headers,'port':self.server.server_port}
                with owner.lock:owner.requests.append(self.trace)
                if self.path.startswith('/probe/'):return True
                if self.server.server_port==owner.foreign_port:return True
                if self.headers.get('Authorization')!=owner.authorization:
                    self.answer(401,b'');return False
                return True
            def answer(self,code,body=b'EXReader platform TLS',headers=()):
                self.trace['response_status']=code
                self.send_response(code)
                for name,value in headers:self.send_header(name,value)
                self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (OSError,ssl.SSLError):pass
            def redirect(self):
                targets={'same.bin':'/dav/book.bin','loop.bin':'/dav/loop.bin','outside.bin':'/outside.bin',
                         'foreign.bin':f'https://127.0.0.1:{owner.foreign_port}/dav/book.bin','downgrade.bin':'http://127.0.0.1/dav/book.bin',
                         'redirected/':'/dav/folder/','write-redirect/':'/dav/folder/','write-redirect.bin':'/dav/book.bin'}
                target=targets.get(self.path.removeprefix('/dav/'))
                if target:self.answer(307,b'',(('Location',target),));return True
                return False
            def chunked(self,body,delay=0):
                self.trace['response_status']=200;self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
                try:
                    for offset in range(0,len(body),8192):
                        chunk=body[offset:offset+8192];self.wfile.write(f'{len(chunk):x}\r\n'.encode()+chunk+b'\r\n');self.wfile.flush()
                        if delay:time.sleep(delay)
                    self.wfile.write(b'0\r\n\r\n')
                except (OSError,ssl.SSLError):pass
            def do_GET(self):
                if not self.record():return
                if self.path.startswith('/probe/'):
                    if self.path=='/probe/slow':time.sleep(2)
                    self.answer(200);return
                if self.redirect():return
                if self.path=='/dav/delayed.bin':time.sleep(.35)
                if self.path=='/dav/header-timeout.bin':time.sleep(2)
                if self.path in ('/dav/chunked.bin','/dav/slow.bin','/dav/trickle.bin'):
                    self.chunked(owner.payload,.04 if self.path!='/dav/chunked.bin' else 0);return
                if self.path=='/dav/broken.bin':
                    self.trace['response_status']=200;self.send_response(200);self.send_header('Content-Length',str(len(owner.payload)));self.end_headers()
                    self.wfile.write(owner.payload[:65536]);self.close_connection=True;return
                if self.path=='/dav/ceiling.bin':
                    self.trace['response_status']=200;self.send_response(200);self.send_header('Content-Length',str(128*1024*1024+1));self.end_headers();self.close_connection=True;return
                if self.path.startswith('/dav/error'):
                    self.answer(int(self.path.removeprefix('/dav/error')),b'');return
                self.answer(200,owner.objects.get(self.path,owner.payload))
            def do_PROPFIND(self):
                length=int(self.headers.get('Content-Length','0'));body=self.rfile.read(length)
                if not self.record():return
                self.trace['request_body_sha256']=hashlib.sha256(body).hexdigest()
                if self.headers.get('Depth')!='1':self.answer(400,b'');return
                if self.redirect():return
                def row(href,folder=False,extra='',missing=False):
                    return ('<d:response><d:href>'+href+'</d:href><d:propstat><d:prop>'
                            +('' if missing else '<d:displayname>书 &amp; Book &#x1F4D6;</d:displayname>')
                            +'<d:resourcetype>'+('<d:collection/>' if folder else '')+'</d:resourcetype><d:getcontentlength>524288</d:getcontentlength>'
                            +'<d:getetag>&quot;immutable&quot;</d:getetag>'+extra+'</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>'
                            +('<d:propstat><d:prop><d:displayname/></d:prop><d:status>HTTP/1.1 404 Not Found</d:status></d:propstat>' if missing else '')+'</d:response>')
                def xml(rows):return ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'+''.join(rows)+'</d:multistatus>').encode()
                path=self.path
                rows=[row(path,True),row(path+'book.bin'),row(path+'folder/',True),row(path+'%E4%B9%A6.bin')]
                if path.endswith('folder/'):rows=[row('child.bin')]
                cases={
                    'invalid-escape/':xml([row('/outside.bin')]),'invalid-origin/':xml([row(f'https://127.0.0.1:{owner.foreign_port}/dav/a.bin')]),
                    'invalid-traversal/':xml([row(path+'%2e%2e/a.bin')]),'invalid-depth/':xml([row(path+'a/b.bin')]),
                    'invalid-duplicate/':xml([row(path+'a.bin')]*2),'invalid-xml/':b'<d:multistatus xmlns:d="DAV:"><d:response>',
                    'invalid-dtd/':b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///unused">]><d:multistatus xmlns:d="DAV:">&x;</d:multistatus>',
                    'external-entity/':f'<!DOCTYPE a [<!ENTITY x SYSTEM "https://127.0.0.1:{owner.foreign_port}/entity">]><d:multistatus xmlns:d="DAV:">&x;</d:multistatus>'.encode(),
                    'internal-entity/':b'<!DOCTYPE a [<!ENTITY x "text">]><d:multistatus xmlns:d="DAV:">&x;</d:multistatus>',
                    'unknown-entity/':b'<d:multistatus xmlns:d="DAV:">&unknown;</d:multistatus>',
                    'invalid-namespace/':xml([]).replace(b'DAV:',b'urn:other'),
                    'missing-href/':xml([row(path+'a.bin')]).replace(('<d:href>'+path+'a.bin</d:href>').encode(),b''),
                    'namespace-limit/':('<d:multistatus xmlns:d="DAV:"><a:item xmlns:a="'+'x'*2048+'"/></d:multistatus>').encode(),
                    'names/':xml([row(path+'a%20b.txt',missing=True),row(path+'100%25.txt',missing=True)]),
                    'unicode/':xml([row(path+'%E4%B9%A6%20%2B%25.txt',missing=True)]),
                    'root%25/':xml([row(path+'child.txt',missing=True)]),
                    'ceiling/':xml([row(path+f'{n:04d}.bin',missing=True) for n in range(2000)]),
                    'overflow/':xml([row(path+f'{n:04d}.bin',missing=True) for n in range(2001)]),
                    'response-flood/':xml([row(path+'a.bin',extra='<d:x/>'*33)]),'outside-flood/':xml(['<d:x/>'*129]),
                    'deep/':xml(['<d:x>'*33+'</d:x>'*33]),'invalid-utf8/':xml([row(path+'%FF.bin',missing=True)]),
                    'listing-ceiling/':b' '*(4*1024*1024+1),
                }
                output=cases.get(path.removeprefix('/dav/'),xml(rows))
                if path=='/dav/alias/':output=output.replace(b'd:',b'x:').replace(b'xmlns:d',b'xmlns:x')
                if path=='/dav/default/':output=output.replace(b'd:',b'').replace(b'xmlns:d',b'xmlns')
                self.answer(207,output)
            def do_MKCOL(self):
                if not self.record():return
                if self.redirect():return
                with owner.lock:
                    exists=self.path in owner.collections;owner.collections.add(self.path)
                self.answer(405 if exists else 201,b'')
            def do_PUT(self):
                if not self.record():return
                if self.path=='/probe/write-block':
                    time.sleep(2);self.close_connection=True;return
                if self.path=='/dav/write-block.bin':
                    time.sleep(2);self.close_connection=True;return
                if self.redirect():return
                length=int(self.headers.get('Content-Length','0'))
                if length>128*1024*1024 or self.headers.get('If-None-Match')!='*':self.answer(400,b'');return
                try:body=self.rfile.read(length)
                except (OSError,ssl.SSLError):return
                if len(body)!=length:self.close_connection=True;return
                self.trace['request_body_sha256']=hashlib.sha256(body).hexdigest();self.trace['request_body_bytes']=len(body)
                with owner.lock:
                    exists=self.path in owner.objects
                    if not exists:owner.objects[self.path]=body
                if exists:self.answer(412,b'');return
                if self.path=='/dav/process.bin':owner.committed.set();time.sleep(10)
                self.answer(201,b'')
        for name in ('server','wrong-host','untrusted','server'):
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.root/'public'/(name+'.crt'),self.root/'private'/(name+'.key'))
            server.socket=tls.wrap_socket(server.socket,server_side=True);self.servers.append(server)
            threading.Thread(target=server.serve_forever,daemon=True).start()
        ports={name:server.server_port for name,server in zip(('trusted','wrong_host','untrusted','foreign'),self.servers)}
        self.foreign_port=ports['foreign'];return ports
    def close(self):
        for server in self.servers:server.shutdown();server.server_close()
        with self.lock:(self.root/'requests.json').write_text(json.dumps(self.requests,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare']);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.output)
