"""Independent same-run artifact audit. Inspect original binaries; never execute them."""
import copy,hashlib,json,os,re,stat,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/"build/f07-audit"
LOCK=json.loads((HERE/"source_lock.json").read_text())
class Invalid(Exception):pass
def need(v,why):
 if not v:raise Invalid(why)
def sha(v):return hashlib.sha256(v).hexdigest()
def api(path):
 return json.loads(subprocess.check_output(["gh","api","repos/NoGod3524/EXReader/"+path],timeout=120))
def providers(text):
 need("Archive member included" in text and "Discarded input sections" in text,"map_format")
 included=text.split("Discarded input sections",1)[0]
 return sorted(set(re.findall(r"(?m)^(\S+\.a)\(([^)]+sqlite[^)]*|sqlite[^)]*)\)",included)))
def text(files,name):return files[name].decode("utf-8")
def check(files,identity):
 need("host.map" in files,"missing_map")
 b=json.loads(files["binding.json"])
 need(all(b.get(k)==v for k,v in identity.items()),"identity")
 need(b["product"]==LOCK["product"] and b["sdk"]==LOCK["sdk"] and b["core"]==LOCK["core"],"sources")
 for name,record in b["files"].items():
  need(name in files and len(files[name])==record["bytes"] and sha(files[name])==record["sha256"],"file_hash")
 need(files["host"]==files["package-host"],"package_identity")
 prefix=b["product_prefix"];sdk=b["sdk_prefix"]
 need(prefix.startswith("/") and sdk.startswith("/") and "/../" not in prefix+sdk,"prefix")
 need(prefix+"/include/exreader-product/sqlite3.h" in text(files,"sdk-header-deps.txt"),"sqlite_header_origin")
 need("#define SQLITE_VERSION " in text(files,"sqlite3-installed.h"),"sqlite_header")
 targets=b["targets"]
 need(targets["product"]==prefix+"/lib/libreader_catalog_sqlite.a" and targets["sdk"]==sdk+"/lib/exreader/libexr_vendor_exr_sqlite.a" and targets["core"]==sdk+"/lib/libexr_core.a","target_prefix")
 need('EXR_VERSION "3.42.0"' in text(files,"sdk-header.h") and re.search(r"#define EXR_ABI_VERSION\s+1u",text(files,"sdk-header.h")),"sdk_version_abi")
 cache=text(files,"host-cache.txt")
 for key in ("EXR_READER_GTK_MANAGED","EXR_READER_GTK_RAW3","EXR_READER_GTK_ACCOUNT","EXR_READER_GTK_READING_RECORDS"):
  need(key+":BOOL=ON" in cache,"managed_flags")
 need("EXR_SDK_VERSION:STRING=3.42.0" in cache,"sdk_cache")
 for key in ("READER_METADATA_PREFIX","READER_ACCOUNT_PREFIX","READER_READING_RECORDS_PREFIX","READER_GTK_RAW3_PREFIX"):
  need(re.search(r"(?m)^"+key+r":[^=]+="+re.escape(prefix)+r"$",cache),"family_prefix")
 commands=json.loads(files["host-commands.json"])
 hostcommands=[x["command"] for x in commands if x["file"].endswith("/examples/linux/reader.c")]
 need(len(hostcommands)==1 and "EXR_READER_GTK_MANAGED=1" in hostcommands[0],"host_compile")
 need(not any("TEST_HOOK" in x["command"] for x in commands),"test_hook")
 hostmap=text(files,"host.map");p=providers(hostmap)
 need(len(p)==1,"provider_ambiguous")
 need(p[0][0]==targets["product"],"host_provider")
 for symbol in ("sqlite3_open","sqlite3_sourceid","sqlite3_compileoption_get"):
  need(symbol in hostmap,"map_symbol")
  lines=[x for x in text(files,"host.nm").splitlines() if x.split() and x.split()[-1]==symbol]
  need(len(lines)==1,"symbol_definition")
 need("test_hook" not in text(files,"host.nm"),"test_hook")
 need(not re.search(r"\bUND\b[^\n]*\bsqlite3_",text(files,"host.dynsym")),"dynamic_sqlite_reference")
 need("Dynamic section" in text(files,"host.dynamic") and "libgtk-3" in text(files,"host.ldd"),"dynamic_inventory")
 build=text(files,"host-build.log")
 need("gtk-host/exreader-linux" in build and "--trace-symbol=sqlite3_open" in build and targets["product"] in build,"link_command")
 cp=providers(text(files,"codec.map"));sp=providers(text(files,"sdk.map"))
 need(len(cp)==1 and cp[0][0]==targets["product"],"codec_provider")
 need("libexr_library.a" not in text(files,"codec.map") and "libexr_vendor_exr_sqlite.a" not in text(files,"codec.map"),"codec_sdk_leak")
 need(len(sp)==1 and sp[0][0]==targets["sdk"],"aux_sdk_provider")
 for key in ("codec-runtime.txt","sdk-runtime.txt"):
  t=text(files,key)
  need("version=3.42.0\n" in t and "abi=1\n" in t and "sourceid=" in t and "option=" in t,"aux_runtime")
 need(json.loads(files["negative-prefix.json"])==dict(refused=True,reason="F07_SDK_PREFIX"),"prefix_control")
 return dict(host_provider=p,codec_provider=cp,auxiliary_sdk_provider=sp,host_runtime_provider_observed=False,dynamic_dependency_inventory_retained=True,sourceid_compile_options_scope="independent consumers only",F07_accepted=False,formal="95/108")
def controls(files,identity):
 cases=[]
 def reseal(d):
  b=json.loads(d["binding.json"])
  b["files"]={n:dict(bytes=len(v),sha256=sha(v)) for n,v in d.items() if n!="binding.json"}
  d["binding.json"]=json.dumps(b).encode()
 def missing(d):d.pop("host.map")
 def ambiguous(d):
  d["host.map"]=d["host.map"].replace(b"Discarded input sections",b"/foreign/libsqlite.a(sqlite3.c.o)\nDiscarded input sections",1)
 def prefix(d):
  b=json.loads(d["binding.json"]);b["targets"]["sdk"]="/wrong/libsqlite.a";d["binding.json"]=json.dumps(b).encode()
 def version(d):d["sdk-header.h"]=d["sdk-header.h"].replace(b'EXR_VERSION "3.42.0"',b'EXR_VERSION "3.40.0"')
 def hook(d):d["host.nm"]+=b"000000 T exr_wc_test_hook\n"
 def wronghash(d):d["product.a"]+=b"x"
 for name,fn,reason,seal in (("missing-map",missing,"missing_map",True),("ambiguous-provider",ambiguous,"provider_ambiguous",True),("wrong-prefix",prefix,"target_prefix",True),("wrong-version",version,"sdk_version_abi",True),("hook",hook,"test_hook",True),("archive-hash",wronghash,"file_hash",False)):
  d=dict(files);fn(d)
  if seal:reseal(d)
  try:check(d,identity)
  except Invalid as e:need(str(e)==reason,"control_reason");cases.append(dict(name=name,reason=reason,refused=True))
  else:raise Invalid("control_accepted")
 return dict(positive=1,negative=len(cases),cases=cases)
def main():
 need(os.environ.get("GITHUB_ACTIONS")=="true","actions_only")
 OUT.mkdir(parents=True,exist_ok=True)
 result=dict(audit_completed=False,audit_passed=False,F07_accepted=False,errors=[])
 try:
  runid=os.environ["GITHUB_RUN_ID"];attempt=os.environ["GITHUB_RUN_ATTEMPT"];source=os.environ["GITHUB_SHA"]
  r=api("actions/runs/"+runid)
  need(r["head_sha"]==source and str(r["run_attempt"])==attempt,"run_identity")
  jobs=api("actions/runs/"+runid+"/attempts/"+attempt+"/jobs")["jobs"]
  need(len([j for j in jobs if j["name"]=="linux" and j["conclusion"]=="success"])==1,"producer_job")
  arts=api("actions/runs/"+runid+"/artifacts")["artifacts"]
  matches=[a for a in arts if a["name"]=="f07-provider-"+runid+"-"+attempt]
  need(len(matches)==1,"artifact_count");a=matches[0]
  need(not a["expired"] and a["workflow_run"]["head_sha"]==source and a["size_in_bytes"]<256*1024**2,"artifact_identity")
  original=OUT/"original.zip"
  with original.open("wb") as stream:subprocess.run(["gh","api","repos/NoGod3524/EXReader/actions/artifacts/"+str(a["id"])+"/zip"],stdout=stream,check=True,timeout=180)
  raw=original.read_bytes();need(len(raw)==a["size_in_bytes"] and "sha256:"+sha(raw)==a["digest"],"outer_hash")
  files={};seen=set()
  with zipfile.ZipFile(original) as z:
   need(0<len(z.infolist())<=100,"zip_count")
   need(sum(i.file_size for i in z.infolist())<512*1024**2,"zip_total")
   for i in z.infolist():
    p=PurePosixPath(i.filename)
    need(not p.is_absolute() and len(p.parts)==1 and p.name==i.filename and ":" not in i.filename and "\\" not in i.filename and p.name not in (".",".."),"zip_path")
    need(p.name.casefold() not in seen,"zip_duplicate");seen.add(p.name.casefold())
    need(not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG) and i.file_size<128*1024**2,"zip_kind_size")
    need(i.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),"zip_method")
    files[p.name]=z.read(i)
  identity=dict(source=source,run=runid,attempt=attempt)
  report=check(files,identity)
  # Recompute actual host symbols independently, never run the binary.
  host=OUT/"host-inspection.bin";host.write_bytes(files["host"])
  actual=subprocess.check_output(["nm","-g","--defined-only",host],text=True,timeout=30)
  need(actual==text(files,"host.nm"),"independent_nm")
  result.update(audit_completed=True,audit_passed=True,report=report,controls=controls(files,identity),artifact=dict(id=a["id"],bytes=len(raw),sha256=sha(raw)),source=source,run=runid,attempt=attempt)
 except Exception as e:
  result["errors"].append(str(e) if isinstance(e,Invalid) else type(e).__name__)
 (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
 print("F07_AUDIT "+json.dumps(result),flush=True)
 return 0 if result["audit_passed"] else 1
if __name__=="__main__":sys.exit(main())
