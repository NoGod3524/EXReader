"""Actions-only inspection of four pinned b2f failure-evidence ZIPs; no product acceptance."""
import hashlib, io, json, os, stat, subprocess, sys, traceback, zipfile
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_parallel_integration import fetch, download_artifact_zip
SOURCE = "b2f4e6e1363d0ee20fcb87a6acef548e0624318a"
RUN, ATTEMPT = 41093873914, 1
PINS = [
 ("authentication",124237468776,"Team24 Apple original ZIP authentication",13001905243,"team24-apple-authentication",7869,"2ca6e800b6d6472957caae775ecc630ce1c2e7b34e12111d0f8b2a950e839bb8"),
 ("summary",124237948220,"full-host-summary",13001118263,"apple-sdk342-full-summary",661,"cc1bf59d59a40ed06c9cc8e2dbe9ca0d1a4ed4d41a78b9b9f2de1a308151092a"),
 ("iphone",124197382353,"Team24 Apple native iphone",13000480037,"team24-apple-native-iphone",429525947,"6df5cee057d608ae96f3cf14193ed546606cba78c7f362362c8af5691e7f5cae"),
 ("font-ipad",124197382630,"Apple 3.42 font ipad",12998390637,"apple-sdk342-supplemental-font-ipad",117806346,"c91eb0db5e0b63c2e1f17711d69a0e45bf06ca128b5ebcdacd8f535314e45c4e"),
]
OUT = ROOT / "build/dot-apple-b2f-diagnose"
OUT.mkdir(parents=True, exist_ok=True)
receipt = dict(producer_source=SOURCE, run=RUN, attempt=ATTEMPT, inspection_source=os.environ["GITHUB_SHA"], diagnostic_only=True, product_acceptance=False, artifacts=[], errors=[])
def save(path, obj):
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(obj, indent=2) + "\n")
def inspect(pin):
 label, jid, jname, aid, stem, size, digest = pin
 dest = OUT / label
 dest.mkdir(parents=True, exist_ok=True)
 job, meta = fetch(f"actions/jobs/{jid}"), fetch(f"actions/artifacts/{aid}")
 save(dest/"job.json", job); save(dest/"metadata.json",meta)
 assert (job["head_sha"],job["run_id"],job["run_attempt"],job["name"],job["status"],job["conclusion"]) == (SOURCE,RUN,ATTEMPT,jname,"completed","failure")
 assert (meta["workflow_run"]["head_sha"],meta["workflow_run"]["id"],meta["name"],meta["size_in_bytes"],meta["digest"],meta["expired"]) == (SOURCE,RUN,f"{stem}-{RUN}-{ATTEMPT}",size,"sha256:"+digest,False)
 raw = download_artifact_zip(aid)
 assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
 entry=dict(label=label,job=jid,artifact=aid,bytes=size,sha256=digest,raw_zip_verified=True)
 receipt["artifacts"].append(entry)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist(); names=[x.filename for x in infos]
  assert len(names)==len(set(names)) and sum(x.file_size for x in infos)<4*1024**3
  canonical=set()
  for item in infos:
   p=PurePosixPath(item.filename)
   assert not p.is_absolute() and ".." not in p.parts and "\\" not in item.filename and ":" not in item.filename
   key=str(p); assert key not in canonical; canonical.add(key)
   assert stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR) and not item.flag_bits&1
  save(dest/"members.json",[dict(name=i.filename,bytes=i.file_size) for i in infos])
  selected=[]
  for item in infos:
   if item.is_dir(): continue
   name=item.filename
   bundle = any(part.endswith(".xcresult") and ((label=="iphone" and part=="wave3.xcresult") or (label=="font-ipad" and part=="font.xcresult")) for part in PurePosixPath(name).parts)
   regular = name.endswith((".log",".json",".txt")) and ".xcresult/" not in name
   if not (bundle or regular): continue
   assert item.file_size < 256*1024**2
   data=z.read(name); target=dest/"extracted"/name
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
   selected.append(dict(name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
   if regular and name.endswith(".json"):
    try:
     obj=json.loads(data)
     if isinstance(obj,dict) and ("failures" in obj or "accepted" in obj):
      print("PRODUCER_REPORT "+label+" "+name+" "+json.dumps({k:obj[k] for k in ("accepted","failures","failure","source_sha","run_id","attempt") if k in obj}),flush=True)
    except (ValueError,UnicodeError): pass
   if regular and name.endswith(".log"):
    lines=data.decode("utf-8","replace").splitlines()
    matches=[]
    for n,line in enumerate(lines):
     if any(s in line for s in ("error:","XCTAssert","Assertion Failure","Exceeded","Restarting after","Test Case","Timed out")):
      matches.append(dict(line=n+1,context=lines[max(0,n-15):min(len(lines),n+25)]))
    save(dest/("contexts-"+hashlib.sha256(name.encode()).hexdigest()[:12]+".json"),matches)
  save(dest/"extracted-hashes.json",selected)
 if label in ("iphone","font-ipad"):
  bundles=list((dest/"extracted").rglob("wave3.xcresult" if label=="iphone" else "font.xcresult"))
  assert len(bundles)==1,("expected one original xcresult",bundles)
  bundle=bundles[0]
  for kind in ("summary","tests"):
   result=subprocess.run(["xcrun","xcresulttool","get","test-results",kind,"--path",str(bundle),"--format","json"],capture_output=True,text=True,timeout=120)
   (dest/(kind+".json")).write_text(result.stdout);(dest/(kind+".stderr.txt")).write_text(result.stderr)
   assert result.returncode==0,(kind,result.returncode)
  result=subprocess.run(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--format","json"],capture_output=True,text=True,timeout=120)
  assert result.returncode==0,result.stderr
  obj=json.loads(result.stdout);save(dest/"legacy.json",obj)
  print("FIRST_ISSUES "+label+" "+json.dumps(obj.get("issues",{})),flush=True)
  pending=[]; seen=set()
  def refs(value):
   if isinstance(value,dict):
    for key,val in value.items():
     if key in ("testsRef","summaryRef") and isinstance(val,dict):
      ident=val.get("id",{}).get("_value")
      if ident and ident not in seen and ident not in pending: pending.append(ident)
     refs(val)
   elif isinstance(value,list):
    for val in value: refs(val)
  refs(obj)
  while pending:
   ident=pending.pop(0)
   if ident in seen: continue
   assert len(seen)<64,"bounded xcresult reference traversal exceeded"
   seen.add(ident)
   result=subprocess.run(["xcrun","xcresulttool","get","object","--legacy","--path",str(bundle),"--id",ident,"--format","json"],capture_output=True,text=True,timeout=120)
   assert result.returncode==0,result.stderr
   node=json.loads(result.stdout)
   save(dest/"activities"/(hashlib.sha256(ident.encode()).hexdigest()+".json"),node)
   refs(node)
  entry["xcresult_reference_objects"]=len(seen)
  result=subprocess.run(["xcrun","xcresulttool","export","attachments","--path",str(bundle),"--output-path",str(dest/"attachments")],capture_output=True,text=True,timeout=120)
  save(dest/"attachment-export.json",dict(exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
  assert result.returncode==0,result.stderr
for pin in PINS:
 try: inspect(pin)
 except Exception as error:
  receipt["errors"].append(dict(label=pin[0],type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
  save(OUT/"receipt.json",receipt)
save(OUT/"receipt.json",receipt)
print("DIAGNOSTIC_RECEIPT "+json.dumps(receipt),flush=True)
assert not receipt["errors"],"Retain diagnostic errors; no product acceptance"
