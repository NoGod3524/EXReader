#!/usr/bin/env python3
"""Bounded read-only inspection of an immutable failed producer artifact."""
import hashlib,json,math,os,pathlib,re,stat,subprocess,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[3]
OUT=ROOT/"build/f05-manifest-inspect"
PARENT="e4bd48c304106275c9f44ac22c4b456c371b84d0"
BRANCH="dot/f05-head-bridge-manifest-inspect-20261103"
RUN=41598794149
JOB=125792416386
ARTIFACT=13213432032
DIGEST="87f8d3657ef39a4e1e1be0b97b15cb6cc4b139dba5263b4a54edb1b8532e43e3"
SIZE=55310493
APKS=["original-owner.apk","host-sync.apk","head-bridge.apk"]
TEXTS=["original-owner.apk.manifest.txt","admission.json","host-native-audit/result.json","host-sync-source-sets.json","bridge-source-sets.json","shadow/java-adapter.json","shadow/source-sets.json","hash-owner.json","hash-proof-calls.jsonl","completion.json"]
HISTORICAL=["packages.json","runtime.json","host-sync.apk.manifest.txt","head-bridge.apk.manifest.txt"]
IDENTITY_TEXTS={"admission.json","host-native-audit/result.json","shadow/java-adapter.json","hash-owner.json","completion.json"}
SCOPE=[".github/workflows/reader-host-session-android.yml","tests/product/f05_android_head_bridge_20261103/inspect_manifest.py"]
RESULT={"producer_source":PARENT,"producer_run":RUN,"producer_attempt":1,"producer_job":JOB,"producer_conclusion":"failure","artifact_id":ARTIFACT,"artifact_sha256":DIGEST,"members":{},"proofs":{},"manifests":{},"errors":[],"apk_executed":False,"devices_started":False,"recompiled":False,"android_readonly_bridge_accepted":False,"formal_accepted":False}
def clean(v):
 if isinstance(v,bytes):v=v.decode("utf-8",errors="replace")
 v=re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]","",str(v))
 v=re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)","[REDACTED]",v)
 return v[-16000:]
def cmd(args,timeout=120):
 try:
  q=subprocess.run([str(x) for x in args],cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
  return q.stdout
 except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
  detail={"operation":str(args[0]),"error":type(e).__name__,"stdout":clean(e.stdout or b""),"stderr":clean(e.stderr or b"")}
  RESULT["errors"].append(detail);print("COMMAND_ERROR "+json.dumps(detail),flush=True);raise
def pairs(items):
 d={}
 for k,v in items:
  if k in d:raise ValueError("Duplicate JSON key: "+k)
  d[k]=v
 return d
def invalid(v):raise ValueError("Nonfinite JSON: "+v)
def finite(v):
 n=float(v)
 if not math.isfinite(n):raise ValueError("Nonfinite numeric JSON: "+v)
 return n
def parse(s):return json.loads(s,object_pairs_hook=pairs,parse_constant=invalid,parse_float=finite)
def api(path):return parse(cmd(["gh","api","repos/NoGod3524/EXReader/"+path]))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,v):
 path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(v,indent=2,ensure_ascii=True,allow_nan=False)+"\n")
def problem(label,e):
 row={"item":label,"type":type(e).__name__,"message":clean(e)}
 RESULT["errors"].append(row);print("ITEM_ERROR "+json.dumps(row),flush=True)
def identity(doc,label,strict=False):
 assert isinstance(doc,dict),label+" is not an object"
 expected={"source_sha":PARENT,"run_id":str(RUN),"attempt":"1"}
 provided=[k for k in expected if k in doc]
 if strict:assert len(provided)==3,label+" required identity field missing"
 assert all(str(doc[k])==expected[k] for k in provided),label+" provided identity differs"
 return {"identity_validated":len(provided)==3,"validated_fields":provided,"fields_not_provided":[k for k in expected if k not in doc],"outer_artifact_identity_validated":True,"product_acceptance_not_reassessed":True}
def inspect():
 assert os.environ["GITHUB_EVENT_NAME"]=="workflow_dispatch"
 assert os.environ["GITHUB_REF"]=="refs/heads/"+BRANCH and os.environ["GITHUB_RUN_ATTEMPT"]=="1"
 head=cmd(["git","rev-parse","HEAD"]).decode().strip()
 assert head==os.environ["GITHUB_SHA"] and cmd(["git","rev-parse","HEAD^"]).decode().strip()==PARENT
 changes=cmd(["git","diff-tree","--no-commit-id","--name-status","-r",PARENT,head]).decode().splitlines()
 assert sorted(changes)==sorted(["M\t"+SCOPE[0],"A\t"+SCOPE[1]])
 RESULT.update(inspection_source=head,inspection_run=os.environ["GITHUB_RUN_ID"],inspection_attempt=1)
 run=api("actions/runs/"+str(RUN));job=api("actions/jobs/"+str(JOB));meta=api("actions/artifacts/"+str(ARTIFACT))
 assert run["id"]==RUN and run["repository"]["full_name"]=="NoGod3524/EXReader"
 assert run["head_sha"]==PARENT and run["head_branch"]=="dot/f05-android-head-bridge-20261103"
 assert run["run_attempt"]==1 and run["event"]=="workflow_dispatch" and run["status"]=="completed" and run["conclusion"]=="failure"
 assert run["path"]==".github/workflows/reader-host-session-android.yml"
 assert job["id"]==JOB and job["run_id"]==RUN and job["run_attempt"]==1 and job["head_sha"]==PARENT
 assert job["name"]=="f05_android" and job["status"]=="completed" and job["conclusion"]=="failure"
 assert job["run_url"]=="https://api.github.com/repos/NoGod3524/EXReader/actions/runs/"+str(RUN)
 assert meta["id"]==ARTIFACT and meta["workflow_run"]["id"]==RUN and meta["workflow_run"]["head_sha"]==PARENT
 assert meta["workflow_run"]["head_branch"]=="dot/f05-android-head-bridge-20261103"
 assert meta["name"]=="f05-android-head-bridge-41598794149-1" and meta["expired"] is False
 assert meta["size_in_bytes"]==SIZE and meta["digest"]=="sha256:"+DIGEST
 receipt={"run":run,"job":job,"artifact":meta,"validated":True}
 save("producer-authentication.json",receipt);RESULT["producer_identity_validated"]=True
 archive=OUT/"producer.zip"
 with archive.open("wb") as f:
  try:
   subprocess.run(["gh","api","--allow-escape-sequences","repos/NoGod3524/EXReader/actions/artifacts/"+str(ARTIFACT)+"/zip"],cwd=ROOT,stdout=f,stderr=subprocess.PIPE,check=True,timeout=120)
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
   problem("download",clean(e.stderr or b""));raise
 assert archive.stat().st_size==SIZE and SIZE<64*1024*1024
 digest=hashlib.sha256()
 with archive.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):digest.update(block)
 assert digest.hexdigest()==DIGEST
 RESULT["archive_digest_validated"]=True
 selected=["apks/"+x for x in APKS]+TEXTS;raw_text={};total=0
 with zipfile.ZipFile(archive) as z:
  infos=z.infolist();assert len(infos)<=20000
  byname={};canonical=set()
  for info in infos:
   name=info.orig_filename
   assert name==info.filename and "\x00" not in name and "\\" not in name and ":" not in name
   path=pathlib.PurePosixPath(name);isdir=info.is_dir();norm=path.as_posix()
   assert name and not path.is_absolute() and ".." not in path.parts
   assert name==norm+("/" if isdir else "") and norm not in canonical,"Noncanonical or aliased ZIP member"
   canonical.add(norm)
   mode=info.external_attr>>16;kind=stat.S_IFMT(mode)
   assert kind in (0,stat.S_IFREG,stat.S_IFDIR) and not (info.flag_bits&1)
   assert not (kind==stat.S_IFDIR and not isdir) and not (kind==stat.S_IFREG and isdir)
   assert name not in byname
   byname[name]=info
  assert "original-owner.apk.manifest.txt" in byname,"Expected unique upload root missing"
  RESULT["historical_report_presence"]={n:n in byname for n in HISTORICAL}
  RESULT["historical_missing_reports"]=[n for n in HISTORICAL if n not in byname]
  assert sum(byname[n].file_size for n in selected if n in byname)<=100*1024*1024
  for name in selected:
   try:
    if name not in byname:raise FileNotFoundError(name)
    info=byname[name];assert not info.is_dir() and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG)
    limit=32*1024*1024 if name.startswith("apks/") else 2*1024*1024
    assert info.file_size<=limit
    chunks=[];count=0
    with z.open(info) as member:
     while True:
      b=member.read(min(65536,limit-count+1))
      if not b:break
      count+=len(b);total+=len(b)
      assert count<=limit and total<=100*1024*1024,"Actual decompression bound exceeded"
      chunks.append(b)
    b=b"".join(chunks);assert len(b)==info.file_size
    RESULT["members"][name]={"sha256":sha(b),"bytes":len(b)}
    if name.startswith("apks/"):
     dest=OUT/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(b)
    else:
     text=b.decode("utf-8");raw_text[name]=text
     dest=OUT/"original-text"/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
     if name in IDENTITY_TEXTS:
      RESULT["proofs"][name]=identity(parse(text),name,strict=name!="shadow/java-adapter.json")
     elif name=="hash-proof-calls.jsonl":
      rows=[parse(x) for x in text.splitlines() if x.strip()];assert rows
      checks=[identity(row,name,strict=True) for row in rows]
      RESULT["proofs"][name]={"identity_validated":all(x["identity_validated"] for x in checks),"rows":len(rows),"row_identity_checks":checks}
     else:RESULT["proofs"][name]={"identity_validated":False,"status":"raw evidence retained; not validated"}
   except Exception as e:problem(name,e)
 aapt=pathlib.Path(os.environ["ANDROID_HOME"])/"build-tools/35.0.0/aapt2"
 for name,expected in zip(APKS,["ProductOwnerTest","HostSyncTest","HeadBridgeTest"]):
  try:
   assert (OUT/"apks"/name).is_file(),"Authenticated APK unavailable"
   raw=cmd([aapt,"dump","xmltree",OUT/"apks"/name,"--file","AndroidManifest.xml"])
   assert len(raw)<=2*1024*1024
   text=raw.decode("utf-8");(OUT/(name+".manifest.txt")).write_text(text)
   nodes=[];active=None
   for line in text.splitlines():
    m=re.match(r"^(\s*)E:\s+(\S+)",line)
    if m:
     depth=len(m.group(1))
     if active is not None and depth<=active["depth"]:active=None
     if m.group(2)=="instrumentation":
      active={"depth":depth,"node":line,"attributes":[]};nodes.append(active)
    elif active is not None and line.lstrip().startswith("A:"):active["attributes"].append(line)
   RESULT["manifests"][name]={"sha256":sha(raw),"expected_runner":"org.exreader.host."+expected,"expected_target":"org.exreader.host","instrumentation_nodes":nodes,"raw_manifest":text,"new_readonly_dump":True}
   print("MANIFEST "+name+"\n"+text,flush=True)
  except Exception as e:problem("aapt2:"+name,e)
 if "original-owner.apk.manifest.txt" in raw_text and "original-owner.apk" in RESULT["manifests"]:
  RESULT["original_owner_manifest_matches_dump"]=raw_text["original-owner.apk.manifest.txt"]==RESULT["manifests"]["original-owner.apk"]["raw_manifest"]
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 try:inspect()
 except Exception as e:problem("inspection",e)
 finally:
  RESULT["inspection_complete"]=not RESULT["errors"] and len(RESULT["manifests"])==3
  save("inspection.json",RESULT)
  print("F05_FIXED_ARTIFACT_INSPECTION "+json.dumps(RESULT,ensure_ascii=True,allow_nan=False),flush=True)
  for p in [OUT/"producer.zip"]+[OUT/"apks"/n for n in APKS]:
   if p.is_file():p.unlink()
 if not RESULT["inspection_complete"]:raise SystemExit(1)
 print("Inspection complete; original failure retained; no runtime acceptance.",flush=True)
if __name__=="__main__":main()
