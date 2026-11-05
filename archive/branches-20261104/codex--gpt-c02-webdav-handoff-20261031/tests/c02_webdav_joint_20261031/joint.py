import hashlib,json,os,pwd,select,signal,struct,subprocess,sys,time
from common import *
import ui
def main():
 actions();assert os.geteuid()!=0
 U=ui.load();J=OUT/'cross';J.mkdir(parents=True,exist_ok=True)
 adm=(OUT/'c02-prefix/bin/exreader-c02-admission').resolve()
 owner=(OUT/'c02-prefix/bin/exreader-c02-migrate').resolve()
 controls=(OUT/'c02-owner/exreader-c02-migrate-controls').resolve()
 sys.path.insert(0,str(ROOT/'tests/migration'));import legacy_data as L
 books,notes=L.dataset();pack=J/'input.exrpack'
 pack.write_bytes(L.build_pack(books[:1],[n for n in notes if n['bookId']=='b-txt']))
 authority=Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve()/'.exreader-c02-admission'
 rows=[];commands=[];hosts=[];server=None
 def call(args,expected):
  p=subprocess.Popen(list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:out,err=p.communicate(timeout=120)
  except subprocess.TimeoutExpired:
   p.kill();out,err=p.communicate(timeout=10);raise
  row=dict(argv=list(map(str,args)),pid=p.pid,returncode=p.returncode,stdout=out.decode(errors='replace'),stderr=err.decode(errors='replace'))
  commands.append(row);assert p.returncode in expected,row;return row
 def route(target):
  parent=target.parent.stat();found=[]
  for p in authority.glob('*/binding'):
   raw=p.read_bytes()
   if len(raw)==304 and raw[:8]==b'PC02B001' and struct.unpack_from('<QQ',raw,24)==(parent.st_dev,parent.st_ino):found.append(p.parent)
  assert len(found)==1,found;return found[0]
 def authority_image(target):
  result={}
  for p in sorted(route(target).iterdir()):
   if p.is_file():
    s=p.stat();raw=p.read_bytes();result[p.name]=dict(dev=s.st_dev,ino=s.st_ino,nlink=s.st_nlink,uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&511,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),bytes_hex=raw.hex())
  return result
 def add(name,**details):
  rows.append(dict(name=name,passed=True,**details))
  save(J/'result.json',dict(source=os.environ['GITHUB_SHA'],uid=os.geteuid(),authority=str(authority),rows=rows,commands=commands,passed=False))
 def make(name,enroll=True):
  folder=J/name;folder.mkdir(parents=True);(folder/'profile').mkdir(mode=0o700)
  h=U.host_for(name,folder) if enroll else U.Session((U.PAYLOAD/'bin/exreader-linux').resolve(),(U.PAYLOAD/'Reader.otf').resolve(),folder)
  hosts.append(h);return h,folder/'profile/library.sqlite'
 def refused(h):
  h.launch();v=U.wait(h,lambda v:v.get('host',{}).get('error') not in (None,'0'))
  assert v.get('managed',{}).get('started') in (None,'0'),v
  assert not (h.folder/'profile/webdav-managed-v1').exists()
  h.close();return v
 try:
  h,target=make('unregistered',False)
  add('01-refuse-before-recovery',observed=refused(h),managed_namespace_absent=True)
  h,target=make('reader-first');h.launch();U.ready(h)
  before=authority_image(target);target_before=U.identity(target)
  denied=call([owner,'migrate',target,pack],(2,))
  assert authority_image(target)==before and U.identity(target)==target_before
  add('02-reader-excludes-migrator',holder_pid=h.process.pid,refusal=denied,before=before,after=authority_image(target),target_before=target_before,target_after=U.identity(target))
  server=U.Fixture(J/'tls');server.book();server.hold('/revisions/')
  U.open_account(h,server);assert server.blocked.wait(15)
  denied=call([owner,'migrate',target,pack],(2,))
  observed=U.read(h)
  h.key('alt+c','alt+d','alt+F4');server.resume()
  closed=U.wait(h,lambda v:v['account']['visible']=='0' and v['account']['session_present']=='0')
  assert closed['account']['session_generation']==closed['account']['closed_generation']
  idle_denied=call([owner,'migrate',target,pack],(2,))
  h.close();assert h.process.returncode==0
  completed=call([owner,'migrate',target,pack],(0,))
  call([adm,'check',target],(0,))
  add('03-network-and-close-retain-lease',holder_pid=h.process.pid,network_observed=observed,closed_observed=closed,
      active_refusal=denied,idle_refusal=idle_denied,exit=h.process.returncode,after_final_join=completed,
      authority_after=authority_image(target),target_after=U.identity(target))
  server.close();server=None
  h,target=make('migrator-first')
  rr,rw=os.pipe();gr,gw=os.pipe();env=dict(os.environ,EXR_PC02_PHASE='1603',EXR_PC02_READY_FD=str(rw),EXR_PC02_GO_FD=str(gr))
  output=open(J/'owner.stdout','wb');error=open(J/'owner.stderr','wb')
  p=subprocess.Popen([str(controls),'migrate',str(target),str(pack)],stdout=output,stderr=error,env=env,pass_fds=(rw,gr))
  os.close(rw);os.close(gr)
  try:
   assert select.select([rr],[],[],60)[0] and os.read(rr,1)==b'r',('owner barrier',p.poll())
   pending=authority_image(target);call([adm,'check',target],(2,))
   live=refused(h);os.kill(p.pid,signal.SIGKILL);rc=p.wait(timeout=10);assert rc==-9
   call([adm,'check',target],(2,))
   dead=refused(h);after_death=authority_image(target);assert after_death==pending
   recovered=call([owner,'recover',target],(0,));call([adm,'check',target],(0,))
   h.launch();U.ready(h);h.close()
   add('04-migrator-pending-survives-death',owner_pid=p.pid,signal_sent=9,returncode=rc,
       pending_before=pending,pending_after_death=after_death,live_refusal=live,dead_refusal=dead,
       recovery=recovered,authority_final=authority_image(target))
  finally:
   if p.poll() is None:p.kill();p.wait(timeout=10)
   os.close(rr);os.close(gw);output.close();error.close()
  original=json.loads((ROOT/'build/gtk-managed/ui/results.json').read_text())
  assert original['accepted'] and len(original['records'])==21
  for name in ('normal','eacces','process-death'):
   call([adm,'check',ROOT/'build/gtk-managed/ui'/name/'profile/library.sqlite'],(0,))
  add('05-cleanup-pending-never-grants-migration-clean',original_gtk_records=21,
      records=[r for r in original['records'] if r['name'] in ('gtk-cleanup-only-retry','gtk-sigkill-owned','gtk-eacces-visible-pending')],
      authorities={name:authority_image(ROOT/'build/gtk-managed/ui'/name/'profile/library.sqlite') for name in ('normal','eacces','process-death')})
  assert (OUT/'gtk-native-audit').exists()
  add('06-last-sdk-borrow-regression',original_host_evidence='gtk-original',independent_raw_audit='gtk-native-audit',untouched_driver=True)
  save(J/'result.json',dict(source=os.environ['GITHUB_SHA'],uid=os.geteuid(),authority=str(authority),rows=rows,commands=commands,passed=True,power_loss=False,scope=M['scope']))
  print('JOINT-CROSS passed=true groups=6',flush=True)
 except Exception:
  save(J/'result.json',dict(source=os.environ['GITHUB_SHA'],uid=os.geteuid(),authority=str(authority),rows=rows,commands=commands,passed=False,error=__import__('traceback').format_exc()))
  raise
 finally:
  if server:server.close()
  for h in hosts:
   if h.process and h.process.poll() is None:h.process.kill();h.process.wait(timeout=10)
   if h.log and not h.log.closed:h.log.close()
if __name__=='__main__':main()
