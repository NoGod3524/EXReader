"""Drive the installed GTK binary through native controls; no product hooks."""
import base64,configparser,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import gi
gi.require_version("Atspi","2.0")
from gi.repository import Atspi
from fixture import Fixture
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"build/gtk-managed";UI=OUT/"ui"
sys.path.insert(0,str(ROOT/"tools"))
from check_linux_host import Session,command
PAYLOAD=OUT/"package/EXReader-Linux"
RECORDS=[]
def require(ok,reason):
 if not ok:raise AssertionError(reason)
def read(host):
 c=configparser.ConfigParser(interpolation=None);c.read(host.observe);return {g:dict(c[g]) for g in c.sections()}
def wait(host,predicate,seconds=45):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  require(host.process.poll() is None,"GTK process exited")
  v=read(host)
  if predicate(v):return v
  time.sleep(.05)
 raise TimeoutError(json.dumps(read(host)))
def ready(host):
 return wait(host,lambda v:v.get("managed",{}).get("started")=="1" and v["managed"]["recovering"]=="0" and v.get("host",{}).get("busy")=="0")
def record(label,host,**extra):
 value=dict(name=label,pid=host.process.pid,returncode=host.process.poll(),observed=read(host),**extra)
 RECORDS.append(value);(UI/"results.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
  run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],records=RECORDS),indent=2)+"\n")
def widget(host,needle,role=None):
 end=time.monotonic()+10
 while time.monotonic()<end:
  desktop=Atspi.get_desktop(0)
  def scan(node,depth=0):
   if depth>16:return None
   try:
    name=node.get_name() or "";r=node.get_role_name()
    if needle in name and (role is None or r==role):
     ext=node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
     if ext.width>0 and ext.height>0:return node
    for i in range(node.get_child_count()):
     found=scan(node.get_child_at_index(i),depth+1)
     if found:return found
   except Exception:pass
  for i in range(desktop.get_child_count()):
   app=desktop.get_child_at_index(i)
   if app.get_process_id()==host.process.pid:
    found=scan(app)
    if found:return found
  time.sleep(.1)
 raise AssertionError("AT-SPI widget missing: "+needle)
def click(host,needle,role=None):
 node=widget(host,needle,role)
 try:
  action=node.get_action_iface()
  if action.get_n_actions()>0 and action.do_action(0):return
 except Exception:pass
 r=node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
 command("xdotool","mousemove","--sync",r.x+r.width//2,r.y+r.height//2,"click",1)
def shot(host,name):
 path=UI/(name+".png");command("import","-window",host.window,path)
 return dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def open_account(host,server,start=True):
 host.key("ctrl+shift+a")
 wait(host,lambda v:v.get("account",{}).get("visible")=="1" and v["account"]["owner_busy"]=="0")
 dialog=command("xdotool","search","--onlyvisible","--all","--pid",host.process.pid,"--name","^Account and Sync$").splitlines()[-1]
 command("xdotool","windowactivate","--sync",dialog)
 user,password=base64.b64decode(server.auth.split(" ",1)[1]).decode().split(":",1)
 for key,value in (("w",server.url),("u",user),("p",password)):
  host.key("alt+"+key,"ctrl+a");host.paste(value)
 host.key("alt+h")
 if start:host.key("alt+s")
def synced(host):
 return wait(host,lambda v:v.get("account",{}).get("session_state") in ("4","5") and v["account"]["preparing"]=="0",120)
def identity(path):
 s=path.stat();b=path.read_bytes()
 return dict(dev=s.st_dev,ino=s.st_ino,nlink=s.st_nlink,size=s.st_size,sha256=hashlib.sha256(b).hexdigest())
def roots(profile):
 return {p.parent.name:dict(identity(p),bytes_hex=p.read_bytes().hex()) for p in (profile/"webdav-managed-v1").glob("root-*/.receipt")}
def host_for(name,folder=None):
 folder=folder or UI/name;folder.mkdir(parents=True,exist_ok=True)
 return Session((PAYLOAD/"bin/exreader-linux").resolve(),(PAYLOAD/"Reader.otf").resolve(),folder)
def close(host,name):
 host.close();record(name,host,actual_exit=host.process.returncode)
def main():
 require(os.environ.get("GITHUB_ACTIONS")=="true" and os.geteuid()!=0,"Actions nonroot")
 UI.mkdir(parents=True,exist_ok=True);server=Fixture(OUT/"gtk-tls-private");book=server.book();hosts=[]
 def launch(name,folder=None):
  h=host_for(name,folder);hosts.append(h);h.launch();ready(h);return h
 try:
  end=time.monotonic()+30
  while time.monotonic()<end:
   if "window id #" in command("xprop","-root","_NET_SUPPORTING_WM_CHECK"):break
   time.sleep(.1)
  h=launch("normal");open_account(h,server);v=synced(h)
  require(v["account"]["session_state"]=="4" and int(v["account"]["pulled"])==1,"actual session completed")
  require(v["managed"]["enabled"]=="1" and v["managed"]["pending"]=="0" and int(v["managed"]["roots"])>=1,"real managed chain")
  profile=h.folder/"profile";cached=profile/"sync-work"/(book["sha256"]+".txt")
  require(cached.read_bytes()==book["data"],"verified cached original")
  import sqlite3
  with sqlite3.connect(profile/"library.sqlite.product.sqlite") as db:
   wire=db.execute("SELECT CAST(body_json AS BLOB) FROM reader_revisions WHERE revision_id=?",(book["revision"],)).fetchone()[0]
  require(wire==book["wire"],"original raw wire retained")
  record("gtk-https-session-sync-dav",h,receipt=roots(profile),target=identity(cached),wire_sha256=hashlib.sha256(wire).hexdigest())
  h.key("alt+r");wait(h,lambda v:v["account"]["preparing"]=="0" and int(v["account"]["projected"])>=1)
  h.key("alt+F4");wait(h,lambda v:v["account"]["visible"]=="0" and v["account"]["session_present"]=="0")
  click(h,"Managed crash cleanup book")
  v=wait(h,lambda v:int(v["host"]["book"])>0 and int(v["host"]["end"])>0 and v["host"]["busy"]=="0",60)
  require(v["host"]["error"]=="0","downloaded book opens")
  record("gtk-downloaded-book-open",h,screenshot=shot(h,"book-open"))
  oldroots=roots(profile);oldtarget=identity(cached);close(h,"gtk-normal-close")
  h.launch();ready(h);h.wait(lambda v:v["book"]>0 and v["end"]>0)
  require(roots(profile)==oldroots and identity(cached)==oldtarget,"restart identity and target")
  record("gtk-normal-reopen",h,receipt=roots(profile),target=identity(cached));close(h,"gtk-reopen-close")
  # Real production process, external permission change while HTTPS GET waits.
  h=launch("eacces");server.hold("/revisions/");open_account(h,server)
  require(server.blocked.wait(15),"actual GTK GET reached")
  tx=next((h.folder/"profile/webdav-managed-v1").glob("root-*/tx-*"));tx.chmod(0o500)
  canary=h.folder/"canary";canary.mkdir(mode=0o700);(canary/"c").write_bytes(b"c");canary.chmod(0o500)
  error=None
  try:(canary/"c").unlink()
  except OSError as e:error=e.errno
  require(error==13 and (canary/"c").exists(),"actual nonroot permission canary")
  record("gtk-eacces-held",h,errno=error,euid=os.geteuid(),mode=tx.stat().st_mode&0o777,receipt=roots(h.folder/"profile"))
  canary.chmod(0o700);(canary/"c").unlink();canary.rmdir();server.resume();v=synced(h)
  require(v["account"]["session_state"]=="4" and int(v["managed"]["pending"])>=1 and v["managed"]["native_error"]=="13","UI published-pending")
  widget(h,"Temporary downloads need cleanup")
  record("gtk-eacces-visible-pending",h,screenshot=shot(h,"pending"),receipt=roots(h.folder/"profile"))
  cached=h.folder/"profile/sync-work"/(book["sha256"]+".txt");before=identity(cached);tx.chmod(0o700)
  count=len(server.requests);click(h,"Retry cleanup","push button")
  wait(h,lambda v:v["managed"]["pending"]=="0" and v["managed"]["recovering"]=="0")
  require(len(server.requests)==count and identity(cached)==before,"cleanup retry did not transfer or alter book")
  record("gtk-cleanup-only-retry",h,request_count_before=count,request_count_after=len(server.requests),target_before=before,target_after=identity(cached))
  h.key("alt+F4");wait(h,lambda v:v["account"]["visible"]=="0" and v["account"]["session_present"]=="0");close(h,"gtk-eacces-close")
  # Installed GTK SIGKILL while its actual managed transaction owns staging.
  h=launch("process-death");server.hold("/revisions/");open_account(h,server)
  require(server.blocked.wait(15),"GTK death barrier");before=roots(h.folder/"profile")
  h.process.kill();rc=h.process.wait(timeout=10);h.log.close();require(rc==-9,"GTK SIGKILL")
  record("gtk-sigkill-owned",h,signal_sent=9,actual_exit=rc,receipt_before=before,receipt_after=roots(h.folder/"profile"))
  server.resume();h.launch();v=ready(h)
  require(int(v["managed"]["pending"])>=1,"startup retains owned pending")
  local=UI/"offline.txt";local.write_text("Offline reading remains available.\n"*100)
  h.dialog(local.resolve());h.wait(lambda v:v["book"]>0 and v["end"]>0)
  record("gtk-offline-reading-with-pending",h,screenshot=shot(h,"offline-pending"));close(h,"gtk-death-reopen-close")
  # Cancel, Disconnect, close-dialog and close-window share the existing drain.
  h=launch("close-race");server.hold("/revisions/");open_account(h,server)
  require(server.blocked.wait(15),"close race barrier")
  h.key("alt+c","alt+d","alt+F4");server.resume()
  v=wait(h,lambda v:v["account"]["visible"]=="0" and v["account"]["session_present"]=="0")
  require(v["account"]["session_generation"]==v["account"]["closed_generation"],"one acknowledged owner close")
  record("gtk-cancel-disconnect-close",h);close(h,"gtk-close-race-exit")
  h=launch("window-close");server.hold("/revisions/");open_account(h,server)
  require(server.blocked.wait(15),"window close barrier")
  command("wmctrl","-ic",hex(int(h.window)));server.resume();rc=h.process.wait(timeout=20);h.log.close()
  require(rc==0,"asynchronous window exit");record("gtk-window-close-during-transfer",h,actual_exit=rc)
  # Existing capacity/mixed fixtures retain their canonical profile binding.
  for label in ("24-root-rotation-and-mixed-restart","25-pool-exhaustion"):
   h=launch(label,OUT/"matrix"/label);v=read(h)
   if label.startswith("24"):
    require(v["managed"]["roots"]=="3" and v["managed"]["pending"]=="1","bounded mixed restart")
   else:
    require(v["managed"]["roots"]=="16" and v["managed"]["exhausted"]=="1","GTK capacity refusal")
    h.dialog(local.resolve());h.wait(lambda v:v["book"]>0 and v["end"]>0)
   record("gtk-"+label,h,screenshot=shot(h,label));close(h,"gtk-"+label+"-close")
  # Corrupt registry cannot disable reading an already saved library.
  h=hosts[0];registry=h.folder/"profile/webdav-managed-v1/registry";original=registry.read_bytes();registry.write_bytes(b"corrupt registry")
  h.launch();v=ready(h);require(v["managed"]["status"]=="4","bad registry user-visible refusal")
  h.wait(lambda v:v["book"]>0 and v["end"]>0)
  record("gtk-offline-reading-bad-registry",h,screenshot=shot(h,"bad-registry"));close(h,"gtk-bad-registry-close");registry.write_bytes(original)
  require(all(r["authenticated"] for r in server.requests),"all real GTK HTTPS requests authenticated")
  require(any(r["method"]=="GET" and "/objects/" in r["path"] for r in server.requests),"GTK original GET")
  result=dict(accepted=True,source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],
   attempt=os.environ["GITHUB_RUN_ATTEMPT"],binary_sha256=hashlib.sha256((PAYLOAD/"bin/exreader-linux").read_bytes()).hexdigest(),
   real_gtk=True,records=RECORDS,requests=server.requests)
  (UI/"results.json").write_text(json.dumps(result,indent=2)+"\n")
  print("MANAGED-GTK "+json.dumps(dict(accepted=True,records=len(RECORDS),requests=len(server.requests))),flush=True)
 finally:
  server.close()
  for h in hosts:
   if h.process and h.process.poll() is None:
    h.process.kill();h.process.wait(timeout=10)
   if h.log and not h.log.closed:h.log.close()
if __name__=="__main__":main()
