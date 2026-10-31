"""Separate Actions job: authenticate same-run artifacts, recompute disk evidence."""
import copy,hashlib,io,json,os,stat,subprocess,sys,zipfile,zlib
from pathlib import Path,PurePosixPath
OUT=Path("build/gtk-managed-verification")
def need(value,why):
 if not value:raise AssertionError(why)
def sha(b):return hashlib.sha256(b).hexdigest()
def api(path):return subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path],timeout=60)
def locate(files,suffix):
 rows=[n for n in files if n==suffix or n.endswith("/"+suffix)]
 need(len(rows)==1,"member "+suffix);return rows[0]
def obj(files,suffix):return json.loads(files[locate(files,suffix)])
def unpack(data):
 files={};seen=set()
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  need(len(z.infolist())<=8192 and sum(i.file_size for i in z.infolist())<=512*1024**2,"ZIP bounds")
  for i in z.infolist():
   n=i.filename;p=PurePosixPath(n)
   need(n and not p.is_absolute() and ".." not in p.parts and "\\" not in n and ":" not in n and "\0" not in n,"ZIP path")
   need(n.rstrip("/")==str(p) and n.casefold() not in seen,"ZIP duplicate");seen.add(n.casefold())
   need(stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not i.flag_bits&1,"ZIP type")
   need(i.file_size<=256*1024**2,"ZIP member bound")
   if not i.is_dir():files[n]=z.read(i)
 return files
def disk(rows):
 for path,r in rows.items():
  need(r["uid"]!=0 and r["kind"] in ("file","dir","symlink","other"),"raw owner/type")
  if r["kind"]!="file":continue
  if "bytes_hex" in r:
   b=bytes.fromhex(r["bytes_hex"]);need(len(b)==r["size"] and sha(b)==r["sha256"],"raw bytes")
  if path.endswith("/.receipt"):
   b=bytes.fromhex(r["bytes_hex"]);zero=b[:60]+b"\0"*4+b[64:]
   need(len(b)==4160 and b[:8]==b"EXRWCRCT" and zlib.crc32(zero)==int.from_bytes(b[60:64],"little"),"receipt CRC")
   need(int.from_bytes(b[24:32],"little")==rows[str(PurePosixPath(path).parent)]["ino"],"receipt inode")
   count=int.from_bytes(b[12:16],"little");need(count<=64,"receipt count")
   for i in range(64):
    part=b[64+i*64:128+i*64]
    if i>=count:need(not any(part),"unused slots")
    else:need(1<=int.from_bytes(part[:4],"little")<=6 and not any(part[4:8]+part[48:64]),"receipt slots")
def check_linux(files):
 build=obj(files,"build.json");matrix=obj(files,"matrix/results.json");ui=obj(files,"ui/results.json")
 source=os.environ["GITHUB_SHA"]
 need(build["source"]==matrix["source"]==ui["source"]==source,"producer source")
 for p,meta in build["files"].items():
  if p.startswith("build/gtk-managed/sdk-source/"):continue
  b=files[locate(files,p.removeprefix("build/gtk-managed/"))]
  need(sha(b)==meta["sha256"] and len(b)==meta["bytes"],"installed binary hash")
  if p.endswith((".a","exreader-linux","managed-consumer")):
   need(b"exr_wc_test_hook" not in b and b"exr_webdav_managed_test_hook" not in b,"installed hook")
 need(build["installed_only"] and build["no_installed_hooks"],"installed source distinction")
 cases=matrix["cases"];need(len(cases)==25 and len({c["name"] for c in cases})==25,"product case set")
 kills=0
 for i,c in enumerate(cases,1):
  need(c["name"].startswith("%02d-"%i) and c["passed"] and c["euid"]!=0,"case failure")
  need(len({p["pid"] for p in c["processes"]})==len(c["processes"]),"process identities")
  for p in c["processes"]:
   need(p["pid"]>0 and p["pid"]!=c["observer_pid"],"actual child")
   text=files[locate(files,"matrix/"+p["log"])].decode()
   observations=[json.loads(x[4:]) for x in text.splitlines() if x.startswith("OBS ")]
   need(observations==p.get("observations",[]),"raw transcript binding")
   if p["kill_sent"]:
    kills+=1;need(p["signal_sent"]==9 and p["returncode"]==-9 and "HELD " in text,"actual SIGKILL")
   else:need(p["returncode"]==0 and p["signal_sent"] is None,"normal process exit")
  snapshots={s["label"]:s["entries"] for s in c["snapshots"]}
  need(len(snapshots)==len(c["snapshots"]) and "final" in snapshots,"snapshot set")
  for rows in snapshots.values():disk(rows)
  if "held" in snapshots:need(snapshots["held"]==snapshots["after-death"],"death preserved held image")
  if "recovery-1" in snapshots:need(snapshots["recovery-1"]==snapshots["recovery-2"],"idempotent raw recovery")
  for first,last in (("before-recovery","recovery-2"),("before-existing","after-existing")):
   if first not in snapshots or last not in snapshots:continue
   for path,r in snapshots[first].items():
    if not path.startswith("dest/") or r["kind"]!="file":continue
    a=snapshots[last].get(path)
    need(a and all(r[k]==a[k] for k in ("dev","ino","size","sha256")),"published target preserved")
  if "before-refusal" in snapshots:need(snapshots["before-refusal"]==snapshots["after-refusal"],"refused namespace unchanged")
  if i==6:
   p=c["processes"][0];canary=p["canaries"][0]
   need(canary["euid"]!=0 and canary["mode"]==0o500 and canary["rc"]==-1 and canary["errno"]==13,"real EACCES")
   r=p["observations"][-1];need(r["status"]==0 and r["published"]==1 and r["pending"]==1 and r["errno"]==13,"published pending")
  if i==23:
   r=c["processes"][0]["observations"][-1];need(r["published"]==1 and r["status"]==0 and r["uncertain"]==1,"published uncertain fact")
  if i==25:
   r=c["processes"][0]["observations"][-1]
   need(r["status"]==8 and r["published"]==0 and r["exhausted"]==1 and len(r["roots"])==16,"capacity refusal")
   need(all(r["slots"]==64 for r in r["roots"]),"1024 lifetime slots")
 need(kills==11,"fixed observed death count")
 need(ui["accepted"] and ui["real_gtk"] and ui["binary_sha256"]==build["files"]["build/gtk-managed/host/gtk-host/exreader-linux"]["sha256"],"actual installed GTK")
 rows={r["name"]:r for r in ui["records"]}
 for name in ("gtk-https-session-sync-dav","gtk-downloaded-book-open","gtk-normal-reopen","gtk-eacces-visible-pending",
  "gtk-cleanup-only-retry","gtk-sigkill-owned","gtk-offline-reading-with-pending","gtk-cancel-disconnect-close",
  "gtk-window-close-during-transfer","gtk-24-root-rotation-and-mixed-restart","gtk-25-pool-exhaustion","gtk-offline-reading-bad-registry"):
  need(name in rows,"GTK scenario "+name)
 r=rows["gtk-cleanup-only-retry"];need(r["request_count_before"]==r["request_count_after"] and r["target_before"]==r["target_after"],"cleanup retry only")
 r=rows["gtk-sigkill-owned"];need(r["actual_exit"]==-9 and r["signal_sent"]==9 and r["receipt_before"]==r["receipt_after"],"actual GTK death")
 for r in ui["records"]:
  need(r["pid"]>0,"GTK PID")
  if "actual_exit" in r:need(r["actual_exit"]==(-9 if r["name"]=="gtk-sigkill-owned" else 0),"GTK lifecycle exit")
  if "screenshot" in r:
   p=r["screenshot"];need(sha(files[locate(files,"ui/"+p["path"])])==p["sha256"],"screenshot bytes")
 need(all(x["authenticated"] for x in ui["requests"]) and any(x["method"]=="GET" and "/objects/" in x["path"] for x in ui["requests"]),"GTK HTTPS observations")
 return dict(transport_cases=25,observed_process_deaths=kills,gtk_records=len(ui["records"]),accepted=True)
def controls(files):
 results=[]
 for name in ("signal","target","capacity","gtk"):
  changed=dict(files)
  if name=="gtk":
   n=locate(files,"ui/results.json");r=json.loads(files[n]);row=next(x for x in r["records"] if x["name"]=="gtk-cleanup-only-retry");row["request_count_after"]+=1
  else:
   n=locate(files,"matrix/results.json");r=json.loads(files[n])
   if name=="signal":next(p for p in r["cases"][6]["processes"] if p["kill_sent"])["returncode"]=0
   elif name=="target":
    next(s for s in r["cases"][5]["snapshots"] if s["label"]=="recovery-2")["entries"]["dest/book.txt"]["ino"]+=1
   else:
    p=r["cases"][24]["processes"][0];p["observations"][-1]["published"]=1
    log=locate(changed,"matrix/"+p["log"]);lines=changed[log].decode().splitlines();index=max(i for i,x in enumerate(lines) if x.startswith("OBS "))
    lines[index]="OBS "+json.dumps(p["observations"][-1]);changed[log]=("\n".join(lines)+"\n").encode()
  changed[n]=(json.dumps(r)+"\n").encode()
  try:check_linux(changed)
  except AssertionError as e:results.append(dict(name=name,rejected=True,reason=str(e)))
  else:raise AssertionError("negative control accepted "+name)
 return results
def main():
 need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only");OUT.mkdir(parents=True,exist_ok=True)
 result=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],accepted=False,artifacts=[],errors=[])
 try:
  run,attempt=os.environ["GITHUB_RUN_ID"],os.environ["GITHUB_RUN_ATTEMPT"]
  meta=json.loads(api("actions/runs/"+run+"/artifacts?per_page=100"))["artifacts"]
  for platform in ("Linux","Windows","macOS"):
   name="gtk-managed-"+platform+"-"+run+"-"+attempt
   rows=[a for a in meta if a["name"]==name];need(len(rows)==1,"producer artifact "+platform);a=rows[0]
   need(not a["expired"] and a["workflow_run"]["head_sha"]==os.environ["GITHUB_SHA"],"artifact source")
   data=api("actions/artifacts/"+str(a["id"])+"/zip")
   need(len(data)==a["size_in_bytes"] and "sha256:"+sha(data)==a["digest"],"original ZIP identity")
   (OUT/(platform+".zip")).write_bytes(data);files=unpack(data)
   admission=obj(files,"admission.json");need(admission["source"]==os.environ["GITHUB_SHA"] and admission["upstream_accepted"],"admission")
   if platform=="Linux":out=check_linux(files);out["negative_controls"]=controls(files)
   else:
    c=obj(files,"compat.json")
    need(c["source"]==os.environ["GITHUB_SHA"] and c["legacy_default"] and c["tls"]["accepted"] and c["session"]["accepted"],"legacy compatibility")
    need(c["tls"]["count"]==(76 if platform=="Windows" else 77) and c["session"]["count"]==20,"original case counts")
    out=dict(legacy_tls=c["tls"]["count"],legacy_session=20,accepted=True)
   result["artifacts"].append(dict(platform=platform,id=a["id"],digest=a["digest"],size=a["size_in_bytes"],result=out))
  result["accepted"]=True
 except Exception as e:result["errors"].append(type(e).__name__+": "+str(e))
 finally:
  (OUT/"summary.json").write_text(json.dumps(result,indent=2)+"\n");print("MANAGED-PRODUCT-VERIFIED "+json.dumps(result),flush=True)
 return 0 if result["accepted"] else 1
if __name__=="__main__":sys.exit(main())
