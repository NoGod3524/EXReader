"""Independent retained-artifact audit. Execute only in GitHub Actions."""
import os,json,hashlib,io,zipfile,urllib.request,urllib.error,re,copy,stat
from pathlib import Path
SOURCE="af851ee7a7d3c04fd4905785a51e6fc9a1226327"
RUN=41085869945
JOB=124166761142
ART=12991273158
SIZE=341928
DIGEST="5880b88ee98dfefe2c3a697054e475df06cfd176fb9089a4964b4acf15fa52fb"
REPO="NoGod3524/EXReader"
class Rejected(Exception): pass
def need(ok,code):
 if not ok: raise Rejected(code)
def sha(b): return hashlib.sha256(b).hexdigest()
class StripOnRedirect(urllib.request.HTTPRedirectHandler):
 """Artifact zips redirect to signed blob storage; the API token must not follow.
  Sending it there yields HTTP 401 and would also disclose it to a second host."""
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  r=super().redirect_request(req,fp,code,msg,headers,newurl)
  if r is not None:
   for k in [k for k in r.headers if k.lower()=="authorization"]: r.headers.pop(k,None)
   for k in [k for k in r.unredirected_hdrs if k.lower()=="authorization"]: r.unredirected_hdrs.pop(k,None)
  return r
OPENER=urllib.request.build_opener(StripOnRedirect())
def api(path,raw=False):
 req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"})
 with OPENER.open(req,timeout=120) as r: data=r.read(8*1024*1024)
 return data if raw else json.loads(data)
def pairs(items):
 d={}
 for k,v in items:
  need(k not in d,"duplicate-json-key");d[k]=v
 return d
def js(b): return json.loads(b,object_pairs_hook=pairs)
def archive(data):
 need(len(data)==SIZE,"zip-size");need(sha(data)==DIGEST,"zip-digest")
 files={};total=0
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  names=set()
  for n in z.infolist():
   path=n.filename
   need(not path.startswith(("/", "\\")) and "\\" not in path and ":" not in path and ".." not in path.split("/"),"unsafe-path")
   need(path.lower() not in names,"duplicate-member");names.add(path.lower())
   need(not n.flag_bits&1 and not stat.S_ISLNK(n.external_attr>>16),"unsafe-member")
   need(n.file_size<=16*1024*1024,"member-limit");total+=n.file_size;need(total<=64*1024*1024,"total-limit")
   if not n.is_dir():
    with z.open(n) as f: b=f.read(n.file_size+1)
    need(len(b)==n.file_size,"member-size");files[path]=b
 return files
def one(v,suffix):
 keys=[k for k in v if k==suffix or k.endswith("/"+suffix)]
 need(len(keys)==1,"missing-or-ambiguous:"+suffix);return keys[0]
def read(v,s):return v[one(v,s)]
def obj(v,s):return js(read(v,s))
def bind(d):
 need(d.get("source")==SOURCE,"source")
 need(str(d.get("run"))==str(RUN) and str(d.get("attempt"))=="1","run-attempt")
def false(d,k):need(d.get(k) is False,"forbidden-claim:"+k)
def inspect(v):
 rec=obj(v,"bridge-evidence/receipt.json");bind(rec)
 need(rec.get("passed") is True and rec.get("live_bridge_only") is True,"bridge-receipt")
 for k in ("restart_reader","full_p0_acceptance","physical_power_loss"):false(rec,k)
 rows=rec["results"];need(len(rows)==5,"mode-count")
 modes=["normal","before","record","published","after"]
 # Native normal result has no mode key. Remaining modes are explicit and unique.
 need([r.get("mode") for r in rows[1:]]==modes[1:],"mode-order")
 for mode,r in zip(modes,rows):
  prefix=one(v,"bridge-evidence/"+mode+"/stdout.txt").rsplit("/",1)[0]+"/"
  stdout=v[prefix+"stdout.txt"].decode()
  if mode=="normal":
   native=js(stdout)
   need(native.get("source")==SOURCE and native.get("checks")==26 and native.get("failed")==0 and native.get("passed") is True,"bridge-26")
   need(r.get("checks")==26 and r.get("failed")==0 and r.get("passed") is True,"bridge-26")
   need(native.get("sdk_open_attempts")==0,"sdk-open")
   for k in ("commit_acknowledged","recovery_admission"):false(native,k)
  else:
   need(stdout.splitlines()[0]=="ready-"+mode and r.get("terminated") is True,"death-cut")
  for k in ("commit_acknowledged","recovery_admission"):false(r,k)
  inventory={k[len(prefix):]:b for k,b in v.items() if k.startswith(prefix)}
  manifest={k.replace("\\","/"):x for k,x in r["files"].items()}
  need(set(inventory)==set(manifest),"inventory")
  for p,b in inventory.items():
   need(manifest[p]["bytes"]==len(b) and manifest[p]["sha256"]==sha(b),"manifest-bytes")
  public=mode in ("normal","published","after")
  need(("published.bin" in inventory)==public and ("private/target.bin" in inventory)!=public,"publication-layout")
  payload=inventory["published.bin" if public else "private/target.bin"]
  need(payload==b"bridge payload\n","payload")
  need(not any("ack" in p.lower() for p in inventory),"unexpected-ack")
  records=[]
  for i in range(2):
   raw=inventory["private/bridge-slot-%02d.rec"%i]
   valid=(i==0 and mode!="before") or (i==1 and mode in ("normal","after"))
   if not valid:need(raw==bytes(4096),"reservation");continue
   d=js(raw);need(d.get("magic")=="EXRWINRECOVERY1" and d.get("version")==1,"codec")
   need(d.get("source")==SOURCE and d.get("run")=="a"*32,"record-binding")
   for k in ("root","parent","target"):
    need(isinstance(d.get(k),str) and re.fullmatch("[0-9a-f]{48}",d[k]),"full-identity")
   need(d.get("ordinal")==i and d.get("phase")==i,"phase")
   seal=d["seal"];body={k:x for k,x in d.items() if k!="seal"}
   need(sha(json.dumps(body,separators=(",",":")).encode()+b"\n")==seal,"seal")
   need(d["payload_sha"]==sha(payload),"payload-sha")
   records.append(d)
  if len(records)==2:
   for k in ("source","run","root","parent","target","payload_sha"):need(records[0][k]==records[1][k],"chain-binding")
   need(re.fullmatch("[0-9a-f]{48}",records[1]["previous_id"]) is not None,"previous-id")
   need(records[1]["previous_sha"]==sha(inventory["private/bridge-slot-00.rec"]),"previous-sha")
 # Original Windows record evidence and its retained bytes.
 old=obj(v,"record-evidence/receipt.json")
 need(old["source"]==SOURCE and str(old["run"])==str(RUN),"old-binding")
 false(old,"full_p0_acceptance")
 n=obj(v,"record-evidence/native.json")
 need(n["source"]==SOURCE and n["checks"]==n["expected"]==27 and n["passed"] is True and n["identity_bytes"]==49 and n["sdk_open_attempts"]==0,"record-27")
 false(n,"recovery_admission")
 for leaf,meta in old["files"].items():
  b=read(v,"record-evidence/private-state/"+leaf.replace("\\","/"));need(meta["bytes"]==len(b) and meta["sha256"]==sha(b),"old-file")
 d=obj(v,"record-evidence/private-state/record-00.json")
 need(d["target"]==n["target"] and d["source"]==SOURCE,"old-target")
 # Original publisher controls, including retained original bytes.
 pub=obj(v,"publish-evidence/receipt.json");bind(pub)
 need(pub["passed"] is True and len(pub["results"])==3,"publisher-receipt")
 false(pub,"full_p0_acceptance");false(pub,"physical_power_loss")
 p=pub["results"][0];need(p["source"]==SOURCE and p["checks"]==28 and p["failed"]==0 and p["passed"] is True and p["sdk_open_attempts"]==0,"publisher-28");false(p,"recovery_admission")
 need(read(v,"publish-evidence/normal/collision.bin")==b"retain","collision")
 need(sha(read(v,"publish-evidence/normal/published.bin"))==p["sha256"],"published-sha")
 for mode in ("before","after"):
  suffix="private/source.bin" if mode=="before" else "published.bin"
  need(read(v,"publish-evidence/"+mode+"/"+suffix)==b"private-to-public complete bytes\n","publisher-death")
  r=pub["results"][1 if mode=="before" else 2];need(r["mode"]==mode and r["terminated"] is True and r["retained"] is True,"publisher-death")
  false(r,"commit_acknowledged");false(r,"recovery_admission")
 refusal=obj(v,"recovery-integration/evidence.json")
 need(refusal.get("passed") is True and len(refusal["cases"])==8 and all(c.get("passed") is True for c in refusal["cases"]),"refusal-8")
 need(len({json.dumps(c,sort_keys=True) for c in refusal["cases"]})==8,"duplicate-refusal")
 # Unlike the older publisher ZIP, this producer retains BOTH archive copies.
 installed=obj(v,"bridge-evidence/installed.json");bind(installed)
 for short,stem,stage,build in (("bridge","windows-record-bridge","bridge-stage","bridge"),("publish","windows-publish","publish-stage","publish"),("record","windows-record","migration-stage","migration")):
  lib="exreader-migration-"+stem+".lib"
  a=read(v,"build/"+build+"/Release/"+lib);b=read(v,stage+"/lib/"+lib)
  need(a==b,"built-installed:"+short)
  need(installed["libraries"][short]=={"sha256":sha(b),"bytes":len(b)},"library-receipt")
  m=read(v,short+"-consumer.map").decode(errors="replace")
  need(lib[:-4].lower() in m.lower(),"map-library:"+short)
 need(old["installed_library_sha256"]==sha(read(v,"migration-stage/lib/exreader-migration-windows-record.lib")),"record-install-hash")
 return {"bridge":26,"death_cuts":4,"original_record":27,"original_publisher":28,"original_refusals":8,"installed_pairs":3}
def changed(v,suffix,fn):
 w=dict(v);k=one(w,suffix);d=js(w[k]);fn(d);w[k]=json.dumps(d,separators=(",",":")).encode();return w
def main():
 need(os.environ.get("GITHUB_ACTIONS")=="true","actions-only")
 out=Path("audit-evidence");out.mkdir(exist_ok=True)
 try:
  body(out)
 except BaseException as exc:
  # A failing audit must still leave evidence instead of an empty upload.
  detail="http-%d"%exc.code if isinstance(exc,urllib.error.HTTPError) else str(exc)
  (out/"error.json").write_text(json.dumps({"rejected_or_failed":detail,"audit_source":os.environ.get("GITHUB_SHA"),"independent_validator":True},indent=2)+"\n")
  raise
def body(out):
 meta=api("actions/artifacts/"+str(ART));job=api("actions/jobs/"+str(JOB));run=api("actions/runs/"+str(RUN))
 need(meta["id"]==ART and meta["size_in_bytes"]==SIZE and meta["digest"]=="sha256:"+DIGEST and meta["expired"] is False,"artifact")
 need(meta["name"]=="windows-record-bridge-"+SOURCE and meta["workflow_run"]["head_sha"]==SOURCE and meta["workflow_run"]["id"]==RUN,"artifact-owner")
 need(job["run_id"]==RUN and job["run_attempt"]==1 and job["head_sha"]==SOURCE and job["conclusion"]=="success","job")
 need(run["head_sha"]==SOURCE and run["run_attempt"]==1 and run["conclusion"]=="success","run")
 raw=api("actions/artifacts/"+str(ART)+"/zip",True);v=archive(raw);positive=inspect(v)
 negatives=[]
 def reject(name,view,expected):
  try:inspect(view)
  except Rejected as e:
   need(str(e)==expected,"wrong-negative:"+name+":"+str(e));negatives.append({"name":name,"rule":str(e)});return
  raise Rejected("accepted-negative:"+name)
 def mutation(name,suffix,fn,expected):reject(name,changed(v,suffix,fn),expected)
 b="bridge-evidence/receipt.json"
 mutation("wrong-source",b,lambda d:d.update(source="0"*40),"source")
 mutation("wrong-attempt",b,lambda d:d.update(attempt="2"),"run-attempt")
 mutation("fake-completion",b,lambda d:d.update(full_p0_acceptance=True),"forbidden-claim:full_p0_acceptance")
 mutation("drop-mode",b,lambda d:d["results"].pop(),"mode-count")
 mutation("duplicate-mode",b,lambda d:d["results"][1].update(mode="after"),"mode-order")
 mutation("wrong-normal-count",b,lambda d:d["results"][0].update(checks=25),"bridge-26")
 mutation("death-not-terminated",b,lambda d:d["results"][1].update(terminated=False),"death-cut")
 mutation("fake-ack",b,lambda d:d["results"][1].update(commit_acknowledged=True),"forbidden-claim:commit_acknowledged")
 mutation("record-count","record-evidence/native.json",lambda d:d.update(checks=26),"record-27")
 mutation("publisher-count","publish-evidence/receipt.json",lambda d:d["results"][0].update(checks=27),"publisher-28")
 mutation("drop-refusal","recovery-integration/evidence.json",lambda d:d["cases"].pop(),"refusal-8")
 mutation("duplicate-refusal","recovery-integration/evidence.json",lambda d:d["cases"].__setitem__(1,d["cases"][0]),"duplicate-refusal")
 for short,stem in (("bridge","windows-record-bridge"),("publish","windows-publish"),("record","windows-record")):
  w=dict(v);k=one(w,"build/"+("migration" if short=="record" else short)+"/Release/exreader-migration-"+stem+".lib");w[k]=w[k]+b"x"
  reject("tamper-built-"+short,w,"built-installed:"+short)
 # Deep byte mutations update only the producer manifest, so semantic checks—not
 # the outer archive hash or manifest check—must reject each corruption.
 def deep(name,mode,leaf,edit,rule):
  w=dict(v);k=one(w,"bridge-evidence/"+mode+"/"+leaf);w[k]=edit(w[k])
  receipt=js(read(w,b));idx=["normal","before","record","published","after"].index(mode)
  receipt["results"][idx]["files"][leaf]={"bytes":len(w[k]),"sha256":sha(w[k])};w[one(w,b)]=json.dumps(receipt).encode()
  reject(name,w,rule)
 deep("payload-bytes","normal","published.bin",lambda x:b"wrong\n","payload")
 deep("reserved-byte","before","private/bridge-slot-00.rec",lambda x:b"x"+x[1:],"reservation")
 def reseal(raw,key,value):
  d=js(raw);d[key]=value;d.pop("seal");d["seal"]=sha(json.dumps(d,separators=(",",":")).encode()+b"\n");return json.dumps(d,separators=(",",":")).encode()+b"\n"
 deep("sealed-wrong-run","normal","private/bridge-slot-01.rec",lambda x:reseal(x,"run","b"*32),"record-binding")
 deep("sealed-wrong-phase","normal","private/bridge-slot-01.rec",lambda x:reseal(x,"phase",9),"phase")
 deep("sealed-root-tail","normal","private/bridge-slot-01.rec",lambda x:reseal(x,"root","0"*48),"chain-binding")
 deep("sealed-predecessor","normal","private/bridge-slot-01.rec",lambda x:reseal(x,"previous_sha","0"*64),"previous-sha")
 need(inspect(v)==positive,"baseline-changed")
 report={"producer_source":SOURCE,"producer_run":RUN,"attempt":1,"job":JOB,"artifact":ART,"archive_bytes":SIZE,"archive_sha256":DIGEST,"positive":positive,"negative_controls":negatives,"independent_validator":True,"full_p0_acceptance":False,"restart_reader":False,"physical_power_loss":False,"limits":["26 checks are aggregate producer output, not 26 independent re-executions","original NTFS record file ID cannot be remeasured from ZIP; previous_id syntax only","process kill is not physical power loss"],"audit_source":os.environ["GITHUB_SHA"]}
 (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
 (out/"producer-metadata.json").write_text(json.dumps({"artifact":meta,"job":job,"run":run},indent=2))
 print(json.dumps(report))
if __name__=="__main__":main()
