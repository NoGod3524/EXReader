"""Real Android Activity/HTTPS chain over the authenticated archived Windows PUT store."""
import base64,hashlib,json,os,re,secrets,sqlite3,subprocess,sys,tempfile,threading,time
from fetch_sender import *
PACKAGE='org.exreader.host'
def main():
 actions();OUT.mkdir(parents=True,exist_ok=True)
 raw=(INPUT/'sender.zip').read_bytes();need(sha(raw)==LOCK['sender']['sha256'],'downloaded Windows original ZIP')
 frozen=old_verifier();files=frozen.unpack(raw);sender=frozen.verify_sender(files)
 receipt=json.loads((INPUT/'sender-receipt.json').read_text());need(receipt['consumer']==identity(),'input consumer')
 sys.path.insert(0,str(ROOT/'tests/reader_session_android'));from run_roundtrip import Dav
 user='f02-'+secrets.token_hex(16);password=secrets.token_hex(32)
 authorization='Basic '+base64.b64encode((user+':'+password).encode()).decode()
 secret_bytes=[v.encode() for v in (user,password,authorization)]
 events=[];errors=[];server=None;reports=[];observations={};success=False
 report=dict(identity=identity(),accepted=False,sender_artifact=receipt,book_key=sender['book_key'],
  original_bytes=sender['original_bytes'],original_sha256=sender['original_sha256'],sdk_version='3.42.0',
  F02_accepted=False,formal='95/108',phases=reports,processes=observations)
 def command(args,timeout=90,input=None,check=True):
  p=subprocess.run(list(map(str,args)),input=input,capture_output=True,timeout=timeout)
  if check:need(p.returncode==0,'Android command '+str(args[0]))
  return p
 def adb(*args,timeout=90,input=None,check=True):
  return command(['adb',*map(str,args)],timeout,input,check)
 def private(name):return adb('exec-out','run-as',PACKAGE,'cat','files/'+name).stdout
 def exists(name):return adb('shell','run-as',PACKAGE,'test','-f','files/'+name,check=False).returncode==0
 def write(name,data):adb('shell',f"run-as {PACKAGE} sh -c 'cat > files/{name}'",input=data)
 def safe_save(name,data):
  need(not any(x in data for x in secret_bytes),'generated credential in evidence')
  p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 def filemeta(name):
  if not exists(name):return dict(exists=False)
  native=adb('shell',f"run-as {PACKAGE} stat -c '%d %i %h %u %s %a' files/{name}").stdout.decode().strip().split()
  need(len(native)==6,'native file metadata')
  data=private(name)
  return dict(exists=True,dev=int(native[0]),ino=int(native[1]),nlink=int(native[2]),uid=int(native[3]),size=int(native[4]),mode=native[5],sha256=sha(data))
 def instrument(phase):
  payload=dict(root=root,user=user,password=password,title=sender['title'],book_key=sender['book_key'],sha256=sender['original_sha256'],bytes=sender['original_bytes'])
  write('f02-input.json',json.dumps(payload,ensure_ascii=False).encode())
  args=['adb','shell','am','instrument','-w','-r','-e','phase',phase]
  for k,v in identity().items():args+=['-e',k,str(v)]
  args+=[PACKAGE+'.test/'+PACKAGE+'.F02ReceiveTest']
  p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  end=time.monotonic()+600;native=None
  while p.poll() is None and time.monotonic()<end:
   if native is None:
    found=adb('shell','pidof',PACKAGE,timeout=10,check=False).stdout.decode().strip()
    if re.fullmatch(r'[0-9]+',found):
     q=adb('exec-out','run-as',PACKAGE,'cat','/proc/'+found+'/status',timeout=10,check=False)
     if q.returncode==0:
      lines=[l for l in q.stdout.splitlines() if l.startswith((b'Name:',b'Pid:',b'Uid:'))]
      native=b'\n'.join(lines)+b'\n';safe_save('proc-'+phase+'.txt',native)
   time.sleep(.15)
  if p.poll() is None:p.kill();p.wait(timeout=10);raise AssertionError('instrumentation timeout')
  output=p.communicate(timeout=15)[0];safe_save(phase+'-instrumentation.txt',output)
  need(p.returncode==0 and b'Process crashed' not in output,'actual instrumentation process')
  data=private('f02-report-'+phase+'.json');safe_save(phase+'-report.json',data);value=json.loads(data)
  reports.append(value)
  need(native is not None and value['passed'],'actual '+phase+' checks')
  pid=int(re.search(rb'^Pid:\s+([0-9]+)',native,re.M)[1]);uid=int(re.search(rb'^Uid:\s+([0-9]+)',native,re.M)[1])
  need(value['pid']==pid and value['uid']==uid,'observed process identity');observations[phase]=dict(pid=pid,uid=uid)
  safe_save('sdk-'+phase+'.txt',private('f02-sdk-'+phase+'.txt'))
  safe_save(phase+'.png',private('f02-captures/'+phase+'.png'))
  print('F02_ANDROID_PHASE '+json.dumps(dict(phase=phase,pid=pid,uid=uid,count=value['count'],passed=value['passed'])),flush=True)
 def apk_identity(package,label):
  line=adb('shell','pm','path',package).stdout.decode().strip().splitlines()
  need(len(line)==1 and line[0].startswith('package:'),'installed package path')
  path=line[0].split(':',1)[1]
  expected=json.loads((OUT/'build.json').read_text())['files'][label+'.apk']['sha256']
  return dict(package=package,path=path,expected_sha256=expected)
 try:
  fixture=ROOT/'build/wave3/network-fixture'
  secret_bytes.append((fixture/'private/server.key').read_bytes())
  server=Dav(fixture,authorization)
  manifest=frozen.load(files['store.json'])
  with server.lock:
   server.entries={r['path']:files['objects/'+r['sha256']] for r in manifest['entries']}
   server.dirs=set(manifest['directories'])
  root='https://127.0.0.1:'+str(server.server.server_port)+'/dav/'
  object_path=sender['object_path'];original=server.entries[object_path];base=server.server.RequestHandlerClass
  def event(handler,code,data,declared=None):
   trace=getattr(handler,'trace',{})
   with server.lock:
    events.append(dict(seq=len(events)+1,method=handler.command,path=handler.path,status=code,
     authenticated=handler.headers.get('Authorization')==authorization,request_bytes=trace.get('body_bytes',0),
     request_sha256=trace.get('body_sha256',sha(b'')),response_bytes=len(data),response_sha256=sha(data),
     declared_bytes=len(data) if declared is None else declared))
  class EvidenceHandler(base):
   def send(self,code,data=b''):
    event(self,code,data);return super().send(code,data)
   def do_GET(self):
    try:
     if self.path==object_path and exists('f02-get-mode'):
      mode=private('f02-get-mode').decode().strip();adb('shell','run-as',PACKAGE,'rm','files/f02-get-mode')
      if not self.authorized():return
      if mode=='corrupt':self.send(200,bytes([original[0]^1])+original[1:]);return
      if mode=='truncate':
       partial=original[:len(original)//2];event(self,200,partial,len(original))
       self.trace['response']=200;self.send_response(200);self.send_header('Content-Length',str(len(original)));self.send_header('Connection','close');self.end_headers();self.close_connection=True
       try:self.wfile.write(partial);self.wfile.flush()
       except (OSError,ssl.SSLError):pass
       return
      if mode=='block':
       write('f02-get-blocked',b'1');end=time.monotonic()+45
       while time.monotonic()<end and not exists('f02-get-release'):time.sleep(.05)
       need(exists('f02-get-release'),'actual cancel release');self.send(200,original);return
      raise AssertionError('unknown transport control')
     super().do_GET()
    except Exception as exc:
     errors.append(type(exc).__name__);self.close_connection=True
  # ssl is a module in the frozen Dav producer; use it only for expected broken sockets.
  import ssl
  server.server.RequestHandlerClass=EvidenceHandler
  adb('install','-r','-t',OUT/'artifacts/host.apk')
  adb('install','-r','-t',OUT/'artifacts/test.apk')
  report['runtime_apks']=dict(host=apk_identity(PACKAGE,'host'),test=apk_identity(PACKAGE+'.test','test'))
  need(adb('shell','pm','clear',PACKAGE).stdout.strip()==b'Success','fresh application profile')
  adb('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
  adb('shell','am','force-stop',PACKAGE)
  adb('reverse','tcp:'+str(server.server.server_port),'tcp:'+str(server.server.server_port))
  instrument('online')
  # All host owners were joined by the instrumentation before these database reads.
  with tempfile.TemporaryDirectory(prefix='f02-closed-product-') as scratch:
   path=Path(scratch)/'product.db';path.write_bytes(private('reader-catalog.db'))
   for suffix in ('-wal','-shm'):
    if exists('reader-catalog.db'+suffix):(Path(str(path)+suffix)).write_bytes(private('reader-catalog.db'+suffix))
   wire=[]
   with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
    for row in sender['book_revisions']:
     got=db.execute('SELECT CAST(body_json AS BLOB) FROM reader_revisions WHERE revision_id=?',(row['id'],)).fetchall()
     need(len(got)==1 and got[0][0]==files['objects/'+row['sha256']],'actual received Windows wire')
     name='wire-'+row['id']+'.json';safe_save(name,got[0][0]);wire.append(dict(id=row['id'],path=name,bytes=len(got[0][0]),sha256=sha(got[0][0])))
   report['wire']=wire
  cache='sync-cache/'+sender['original_sha256']+'.txt'
  before=filemeta(cache);need(before.get('sha256')==sender['original_sha256'],'real downloaded cache before removal')
  need(not exists('reader-originals/'+sender['original_sha256']+'.txt'),'reader copy not preseeded')
  adb('shell','run-as',PACKAGE,'rm','files/'+cache);after=filemeta(cache);need(not after['exists'],'cache removal')
  report['eviction']=dict(before=before,after=after)
  with server.lock:before_requests=len(events)
  server.server.shutdown();server.server.server_close()
  report['offline']=dict(server_stopped=True,requests_before=before_requests)
  adb('reverse','--remove','tcp:'+str(server.server.server_port))
  for phase in ('offline','reopen'):
   adb('shell','am','force-stop',PACKAGE);instrument(phase)
  report['reader_copy']=filemeta('reader-originals/'+sender['original_sha256']+'.txt')
  safe_save('reader-original.txt',private('reader-originals/'+sender['original_sha256']+'.txt'))
  report['offline']['requests_after']=len(events)
  need(len(events)==before_requests and not errors,'offline/transport integrity')
  need(len({p['pid'] for p in reports})==3,'three actual process identities')
  report['accepted']=True;success=True
 except Exception as exc:
  report['error_type']=type(exc).__name__
  try:safe_save('failure-logcat.txt',adb('logcat','-d','-v','threadtime','-t','1500',check=False).stdout)
  except Exception:pass
  raise
 finally:
  try:
   if server is not None:
    server.release.set()
    if not report.get('offline',{}).get('server_stopped'):server.server.shutdown();server.server.server_close()
  finally:
   save(OUT/'events.json',events);save(OUT/'report.json',report)
   safe=True
   for path in OUT.rglob('*'):
    if path.is_file():
     data=path.read_bytes()
     if any(secret in data for secret in secret_bytes):safe=False
   save(ROOT/'build/f02-android-status/status.json',dict(identity=identity(),accepted=success,safe_upload=safe,error_type=report.get('error_type'),F02_accepted=False))
   if safe:
    with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('safe_upload=true\n')
   print('F02_ANDROID_RESULT '+json.dumps(dict(identity=identity(),accepted=success,safe_upload=safe,phases=len(reports),F02_accepted=False)),flush=True)
   need(safe,'no generated credentials in uploaded evidence')
if __name__=='__main__':main()
