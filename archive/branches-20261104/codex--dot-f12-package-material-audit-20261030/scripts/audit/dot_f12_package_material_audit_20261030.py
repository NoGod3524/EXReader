#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only retained-package materials audit. Execute ONLY in Actions."""
import copy, hashlib, importlib.util, io, json, os, re, stat, subprocess, sys
import urllib.request, zipfile
from pathlib import Path, PurePosixPath

SOURCE = "8f8acf3234cba747165f001c0c96efe1b911e6ad"
RUN = 40678657371
ATTEMPT = 1
REPO = "NoGod3524/EXReader"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "f12-evidence"
MIB = 1024 * 1024
PINS = {
"windows": (12812276328,17696295,"0206e54988ca50e3feae37d7f83457ab959d052ef350fb55eb9269007c2c9cd2","6c4719028b0ff76a4ec09334cb3a91423e9e5655e2956cadbd82a1744194b490"),
"linux": (12811449234,18545727,"be3a91161939b3b61bce041feaa06679d03120af9f53abea02bab141d5665641","64e457ea504a1472c575eb11f944cfde58e430ad19600ef9ccc21e074a940286"),
"macos": (12811976629,27507961,"f480b2a8489f8b21aa00c795b38fbd4a85261200a654cb2daf6c880bb538b599","b44172354029995d7a47dd25804d4913f12f0761c66d00725d5c50fdea28e3dd"),
"android": (12812325830,19702584,"e120fb8a3d73aafb19578aed9d114788177ae104a00f1f754b2cb413c174760e","4533e63c20c9f248beb6afc7690dd5da54eda5b8360aea899e99522b7a6a0e53"),
"iphone": (12813015622,27511670,"c56a913aca689f4290a4d66787666e3b22617c39308c3acfc45bd1b3794f3c3b","35f810de9ee9af6113d04c97e300eb7ea95aa2eea01cf29cc37b823281cf0502"),
"ipad": (12812242328,27511644,"34cb0a2b9b56f5b6cd4f3347f08505aac3abe128aba59e982cf208e93829acf9","f3b0d84946f4fd3390fdbb0998e63fc8d69b5dd77446b8d2cee410c0fe167d4c")}
TOPICS = {
"installation": ("install","安装","怎么运行"),
"import": ("import","导入"),
"sync": ("webdav","同步"),
"conflict_recovery": ("conflict","冲突","重试"),
"backup": ("backup","备份"),
"upgrade": ("upgrade","升级","旧库")}
OFL = "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"
class Reject(Exception): pass
def need(ok, rule):
    if not ok: raise Reject(rule)
def sha(b): return hashlib.sha256(b).hexdigest()
def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def unique(pairs):
    d={}
    for k,v in pairs:
        need(k not in d,"json.duplicate")
        d[k]=v
    return d
def js(b): return json.loads(b.decode("utf-8"),object_pairs_hook=unique)
def pathkey(s):
    need(isinstance(s,str) and s and "\x00" not in s,"zip.path")
    need(not s.startswith(("/","\\")) and not re.match(r"^[A-Za-z]:",s),"zip.absolute")
    need("\\" not in s,"zip.backslash")
    parts=s.rstrip("/").split("/")
    need(".." not in parts,"zip.traversal")
    return "/".join(x for x in parts if x not in ("","."))
def charge(n, used, limit):
    used[0]+=n
    need(used[0]<=limit,"zip.stream_budget")
def scan_zip(data, budget, label):
    """Never extract. Validate all central entries before reading any member."""
    need(len(data)<=128*MIB,"zip.archive_budget")
    result={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist()
        need(len(infos)<=20000,"zip.member_count")
        raw=set(); normalized=set(); declared=0
        for inf in infos:
            need(inf.filename not in raw,"zip.duplicate")
            raw.add(inf.filename)
            key=pathkey(inf.filename)
            need(key not in normalized,"zip.collision")
            normalized.add(key)
            mode=inf.external_attr>>16
            kind=stat.S_IFMT(mode)
            need(kind in (0,stat.S_IFREG,stat.S_IFDIR),"zip.type")
            need(not (inf.flag_bits&1),"zip.encrypted")
            need(inf.file_size<=128*MIB,"zip.declared_budget")
            declared+=inf.file_size
        need(declared<=512*MIB,"zip.declared_budget")
        for inf in infos:
            if inf.is_dir(): continue
            chunks=[]; count=0
            with z.open(inf) as stream:
                while True:
                    b=stream.read(MIB)
                    if not b: break
                    count+=len(b)
                    need(count<=128*MIB,"zip.stream_budget")
                    charge(len(b),budget,512*MIB)
                    chunks.append(b)
            need(count==inf.file_size,"zip.size")
            result[pathkey(inf.filename)]=b"".join(chunks)
    return result
def meta_check(meta,target):
    aid,size,digest,_=PINS[target]
    need(meta.get("id")==aid,"identity.artifact")
    need(meta.get("name")==f"f06-{target}-{RUN}-{ATTEMPT}","identity.name")
    need(meta.get("size_in_bytes")==size,"identity.bytes")
    need(meta.get("digest")=="sha256:"+digest,"identity.digest")
    need(meta.get("expired") is False,"identity.expired")
    wr=meta.get("workflow_run",{})
    need(wr.get("id")==RUN,"identity.run")
    need(wr.get("head_sha")==SOURCE,"identity.source")
def manifest_check(files,target,expected_archive=None):
    need("manifest.json" in files,"manifest.missing")
    m=js(files["manifest.json"])
    need(m.get("source_sha")==SOURCE,"identity.source")
    need(m.get("target")==target and m.get("sdk_version")=="3.42.0","identity.target_sdk")
    p=m.get("provenance",{})
    need(str(p.get("run_id"))==str(RUN),"identity.run")
    need(str(p.get("attempt"))==str(ATTEMPT),"identity.attempt")
    declared=m.get("files")
    need(isinstance(declared,dict),"manifest.files")
    metadata=m.get("metadata_files")
    need(metadata==["manifest.json","SHA256SUMS"],"manifest.metadata")
    need(set(files)==set(declared)|set(metadata),"manifest.inventory")
    for name,row in declared.items():
        need(pathkey(name)==name,"manifest.path")
        need(type(row.get("bytes")) is int and row["bytes"]==len(files[name]),"manifest.bytes")
        need(row.get("sha256")==sha(files[name]),"manifest.hash")
    need("SHA256SUMS" in files,"manifest.sums")
    sums="".join(declared[n]["sha256"]+"  "+n+"\n" for n in sorted(declared))
    need(files["SHA256SUMS"]==sums.encode(),"manifest.sums")
    entry=m.get("entry")
    need(entry in declared,"manifest.entry")
    if expected_archive is not None:
        need(sha(expected_archive)==PINS[target][3],"manifest.inner_hash")
    return m
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        need(newurl.startswith("https://"),"download.https")
        nxt=super().redirect_request(req,fp,code,msg,headers,newurl)
        if nxt:
            nxt.remove_header("Authorization")
            nxt.unredirected_hdrs.pop("Authorization",None)
        return nxt
def get(url, limit, accept="application/vnd.github+json"):
    need(url.startswith("https://api.github.com/"),"download.api")
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],
        "Accept":accept,"User-Agent":"EXReader-F12-material-audit"})
    chunks=[]; n=0
    with urllib.request.build_opener(Redirect()).open(req,timeout=60) as r:
        while True:
            b=r.read(MIB)
            if not b: break
            n+=len(b);need(n<=limit,"download.bytes");chunks.append(b)
    return b"".join(chunks)
def obligations():
    spec=importlib.util.spec_from_file_location("f12_registry",ROOT/"tools/check_reading_licenses.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    rows=[]
    for component in mod.COMPONENTS:
        for file in component["files"]:
            if component["id"]=="exreader": continue
            expected=file.get("sha256")
            if file["origin"]=="repository":
                expected=sha((ROOT/file["path"]).read_bytes())
            rows.append({"component":component["id"],"source":file["path"],
                "installed":file["installed"],"expected_sha256":expected,
                "condition":file.get("when") if file.get("when") is not None else component.get("when","")})
    return rows
def material_row(files, obligation, applicable=None):
    expected=obligation.get("expected_sha256")
    installed=obligation["installed"].removeprefix("share/exreader/")
    candidates=[n for n in files if n==installed or n.endswith("/"+installed)]
    matches=[n for n in candidates if expected and sha(files[n])==expected]
    if applicable is False:
        state="not_applicable"
    elif matches: state="present_verified"
    elif candidates: state="mismatch" if expected else "unresolved"
    elif applicable is True: state="missing_required"
    else: state="unresolved"
    return dict(obligation,state=state,applicability=applicable,paths=[
        {"path":n,"bytes":len(files[n]),"sha256":sha(files[n])} for n in candidates],matched=matches)
def require_material(files,ob,applicable=True):
    r=material_row(files,ob,applicable)
    need(r["state"] in ("present_verified","not_applicable"),"materials.required")
    return r
def instruction_check(files, name):
    need(name in files,"instructions.missing")
    text=files[name].decode("utf-8")
    need(SOURCE in text,"instructions.source")
    return text
def recipe_applicability(condition,target):
    # Source-recipe classification only, NOT a new observed build-cache result.
    if not condition: return True
    switches={"EXR_ENABLE_PDF":True,"EXR_ENABLE_LIBRARY":True,"EXR_BUILD_TEXT_INDEX":False,
      "EXR_ENABLE_ICC":True,"EXR_ENABLE_PDF_JPX":True,"EXR_ENABLE_AAC":False,
      "EXR_ENABLE_AUDIO":target not in ("windows","linux"),
      "EXR_ENABLE_MP3":target not in ("windows","linux"),
      "EXR_ENABLE_IMAGE_WEBP":target!="android","EXR_ENABLE_IMAGE_TIFF":target!="android",
      "EXR_ENABLE_IMAGE_AVIF":target!="android","EXR_ENABLE_PDF_CRYPTO":target!="android"}
    terms=[part.split("&") for part in condition.split("|")]
    if any(key not in switches for group in terms for key in group): return None
    return any(all(switches[key] for key in group) for group in terms)

def materials(files, m, registry):
    rows=[]
    for ob in registry:
        # Unconditional components are required. Do NOT infer optional OFF from missing files.
        app=recipe_applicability(ob["condition"],m["target"])
        row=material_row(files,ob,app)
        row["applicability_basis"]="source recipe, not observed cache; actual full dependency closure unresolved"
        rows.append(row)
    for name,pathnames in (("first_party",("LICENSE","LICENSE.txt","EXReader-LICENSE.txt")),
                           ("notice",("THIRD_PARTY_NOTICES.md",))):
        expected=sha((ROOT/("LICENSE" if name=="first_party" else "THIRD_PARTY_NOTICES.md")).read_bytes())
        paths=[n for n,b in files.items() if PurePosixPath(n).name in pathnames]
        good=[n for n in paths if sha(files[n])==expected]
        rows.append({"component":name,"state":"present_verified" if good else "missing_required",
                     "matched":good,"paths":paths,"expected_sha256":expected})
    fonts=[n for n in files if n.endswith("/Reader.otf") or n=="Reader.otf"]
    if fonts:
        paths=[n for n,b in files.items() if PurePosixPath(n).name in ("OFL.txt","Noto-OFL.txt")]
        good=[n for n in paths if sha(files[n])==OFL]
        rows.append({"component":"host_noto_font","fonts":fonts,"paths":paths,
            "state":"present_verified" if good else "missing_required","expected_sha256":OFL})
    else:
        rows.append({"component":"host_noto_font","state":"unresolved","reason":"No recognized font path; not evidence of absence from runtime"})
    text=instruction_check(files,m["instructions"])
    notes={}
    for topic,terms in TOPICS.items():
        lines=[{"line":i+1,"text":s} for i,s in enumerate(text.splitlines())
               if any(term in s.lower() for term in terms)]
        notes[topic]={"state":"text_candidate" if lines else "missing_from_installation_notes","lines":lines}
    docpaths=[n for n in files if n.lower().endswith((".md",".txt")) and
              any(k in n.lower() for k in ("readme","install","upgrade","sync","backup","说明"))]
    return {"materials":rows,"installation_notes":notes,"additional_document_paths":docpaths,
        "registered_materials_complete":all(r["state"] in ("present_verified","not_applicable") for r in rows),
        "materials_complete":False,
        "instructions_complete":False,
        "instructions_limit":"Keyword locations are candidates only, not validated procedures. Other document paths retained for review.",
        "runtime_dependency_completeness":"unresolved: retained package bytes do not establish every linked/system dependency",
        "legal_compliance_assessed":False,"F12_promoted":False}
def merge_apk(files,nested):
    incoming={"APK/"+n:b for n,b in nested.items()}
    need(not (set(files)&set(incoming)),"apk.namespace_collision")
    return dict(files,**incoming)

def make_zip(pairs):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
        for name,data in pairs: z.writestr(name,data)
    return b.getvalue()
def fixture(target):
    files={"app":b"program","licenses/test/LICENSE":b"fixed license",
           "assets/OFL.txt":b"font license","notice":b"component notice",
           "notes.md":(SOURCE+"\ninstall import sync backup upgrade conflict").encode()}
    if target=="android": files["app.apk"]=make_zip([("assets/OFL.txt",b"font license")])
    return seal(files,target)
def seal(files,target):
    files={k:v for k,v in files.items() if k not in ("manifest.json","SHA256SUMS")}
    rows={n:{"bytes":len(b),"sha256":sha(b),"mode":420} for n,b in files.items()}
    m={"source_sha":SOURCE,"target":target,"sdk_version":"3.42.0","entry":"app",
       "provenance":{"run_id":RUN,"attempt":ATTEMPT},"files":rows,
       "metadata_files":["manifest.json","SHA256SUMS"],"instructions":"notes.md"}
    files["SHA256SUMS"]="".join(rows[n]["sha256"]+"  "+n+"\n" for n in sorted(rows)).encode()
    files["manifest.json"]=json.dumps(m).encode()
    return files
def controls():
    results=[]
    for target in PINS:
        f=fixture(target); parsed=scan_zip(make_zip(list(f.items())),[0],"positive")
        manifest_check(parsed,target)
        require_material(parsed,{"installed":"licenses/test/LICENSE","expected_sha256":sha(b"fixed license")})
        require_material(parsed,{"installed":"licenses/disabled/LICENSE","expected_sha256":sha(b"absent")},False)
        instruction_check(parsed,"notes.md")
        if target=="android": scan_zip(parsed["app.apk"],[0],"apk")
        results.append({"name":"positive."+target,"passed":True})
    ob={"installed":"licenses/test/LICENSE","expected_sha256":sha(b"fixed license")}
    tests=[]
    def add(name,rule,fn): tests.append((name,rule,fn))
    base=fixture("linux")
    def mutate_manifest(key,value):
        f=copy.deepcopy(base);m=js(f["manifest.json"]);m[key]=value;f["manifest.json"]=json.dumps(m).encode()
        return manifest_check(f,"linux")
    add("wrong_source","identity.source",lambda:mutate_manifest("source_sha","0"*40))
    add("wrong_run","identity.run",lambda:mutate_manifest("provenance",{"run_id":1,"attempt":1}))
    add("wrong_attempt","identity.attempt",lambda:mutate_manifest("provenance",{"run_id":RUN,"attempt":2}))
    meta={"id":PINS["linux"][0],"name":f"f06-linux-{RUN}-1","size_in_bytes":PINS["linux"][1],
          "digest":"sha256:"+PINS["linux"][2],"expired":False,"workflow_run":{"id":RUN,"head_sha":SOURCE}}
    add("wrong_artifact","identity.artifact",lambda:meta_check(dict(meta,id=1),"linux"))
    add("wrong_outer_digest","identity.digest",lambda:meta_check(dict(meta,digest="sha256:"+"0"*64),"linux"))
    for label,pairs,rule in [
      ("duplicate",[("a",b"x"),("a",b"y")],"zip.duplicate"),
      ("canonical_collision",[("a",b"x"),("./a",b"y")],"zip.collision"),
      ("traversal",[("../a",b"x")],"zip.traversal"),
      ("absolute",[("/a",b"x")],"zip.absolute"),
      ("drive",[("C:/a",b"x")],"zip.absolute")]:
        add(label,rule,lambda pairs=pairs:scan_zip(make_zip(pairs),[0],"negative"))
    link=zipfile.ZipInfo("link");link.external_attr=(stat.S_IFLNK|0o777)<<16
    add("symlink","zip.type",lambda:scan_zip(make_zip([(link,b"target")]),[0],"negative"))
    def declared():
        z=bytearray(make_zip([("a",b"x")]));p=z.index(b"PK\x01\x02")
        z[p+24:p+28]=(128*MIB+1).to_bytes(4,"little")
        return scan_zip(bytes(z),[0],"negative")
    add("declared_size","zip.declared_budget",declared)
    add("stream_budget","zip.stream_budget",lambda:scan_zip(make_zip([("a",b"xx")]),[512*MIB-1],"negative"))
    add("json_duplicate","json.duplicate",lambda:js(b'{"x":1,"x":2}'))
    add("extra_member","manifest.inventory",lambda:manifest_check(dict(base,extra=b"x"),"linux"))
    add("member_hash","manifest.hash",lambda:manifest_check(dict(base,app=b"changed"),"linux"))
    # Keep size equal so the intended hash rule is reached.
    tests[-1]=("member_hash","manifest.hash",lambda:manifest_check(dict(base,app=b"PROGRAM"),"linux"))
    add("inner_hash","manifest.inner_hash",lambda:manifest_check(base,"linux",b"wrong inner"))
    def material_mutation(kind):
        f=copy.deepcopy(base)
        if kind=="deleted": del f["licenses/test/LICENSE"]
        elif kind=="changed": f["licenses/test/LICENSE"]=b"changed"
        elif kind=="font": f["assets/OFL.txt"]=b"wrong font"
        elif kind in ("notice_only","unknown_missing"): del f["licenses/test/LICENSE"]
        f=seal(f,"linux")
        # Semantic controls reseal and parse full ZIP before testing obligations.
        f=scan_zip(make_zip(list(f.items())),[0],"resealed")
        manifest_check(f,"linux")
        if kind=="font":
            return require_material(f,{"installed":"assets/OFL.txt","expected_sha256":sha(b"font license")})
        if kind=="unknown_missing":
            return require_material(f,ob,None)
        return require_material(f,ob)
    for name in ("deleted","changed","font","notice_only"):
        add("material_"+name,"materials.required",
            lambda name=name:material_mutation(name))
    add("apk_namespace","apk.namespace_collision",lambda:merge_apk({"APK/a":b"outer"},{"a":b"nested"}))
    def notes_mutation(missing):
        f=copy.deepcopy(base)
        if missing: del f["notes.md"]
        else: f["notes.md"]=b"another source"
        f=seal(f,"linux");f=scan_zip(make_zip(list(f.items())),[0],"resealed")
        manifest_check(f,"linux")
        return instruction_check(f,"notes.md")
    add("notes_missing","instructions.missing",lambda:notes_mutation(True))
    add("notes_wrong_source","instructions.source",lambda:notes_mutation(False))
    need(len(tests)==24,"controls.count")
    for name,rule,fn in tests:
        actual=None
        try: fn()
        except Reject as e: actual=str(e)
        results.append({"name":name,"expected":rule,"actual":actual,"passed":actual==rule})
    dump(OUT/"controls.json",{"positive":6,"negative":24,"results":results})
    need(all(x["passed"] for x in results),"controls.failure")
def audit_target(target,registry):
    aid,size,digest,inner_digest=PINS[target]
    meta=js(get(f"https://api.github.com/repos/{REPO}/actions/artifacts/{aid}",MIB))
    dump(OUT/target/"artifact-metadata.json",meta);meta_check(meta,target)
    raw=get(f"https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip",size,"application/vnd.github+json")
    need(len(raw)==size and sha(raw)==digest,"download.identity")
    path=OUT/"original"/(target+".zip");path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    budget=[0];outer=scan_zip(raw,budget,"outer")
    names=[n for n in outer if PurePosixPath(n).name=="manifest.json"]
    need(len(names)==1,"outer.manifest_count")
    m=js(outer[names[0]])
    need(m.get("source_sha")==SOURCE and m.get("target")==target,"outer.identity")
    archives=[n for n in outer if n==m["archive"]["name"] or n.endswith("/"+m["archive"]["name"])]
    need(len(archives)==1,"outer.archive_count")
    package=outer[archives[0]]
    need(sha(package)==inner_digest and m["archive"]["sha256"]==inner_digest,"manifest.inner_hash")
    need(type(m["archive"]["bytes"]) is int and m["archive"]["bytes"]==len(package),"outer.archive_bytes")
    files=scan_zip(package,budget,"package")
    im=manifest_check(files,target,package)
    need(m["files"]==im["files"] and m["producer"]==im["producer"],"outer.inner_identity")
    inventory={n:{"bytes":len(b),"sha256":sha(b)} for n,b in files.items()}
    if target=="android":
        need(im["entry"]=="artifacts/app-debug.apk","apk.entry")
        nested=scan_zip(files[im["entry"]],budget,"apk")
        files=merge_apk(files,nested)
        inventory.update({"APK/"+n:{"bytes":len(b),"sha256":sha(b)} for n,b in nested.items()})
    dump(OUT/target/"inventory.json",inventory)
    result=materials(files,im,registry)
    result.update(target=target,source=SOURCE,run=RUN,attempt=ATTEMPT,artifact_id=aid,
        original_zip_sha256=digest,inner_zip_sha256=inner_digest,uncompressed_bytes=budget[0],
        casefold_collisions=sorted(n for n,c in __import__("collections").Counter(x.lower() for x in inventory).items() if c>1))
    dump(OUT/target/"materials.json",result)
    return result
def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true","actions_only")
    OUT.mkdir(exist_ok=True)
    controls()
    run=js(get(f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}/attempts/{ATTEMPT}",4*MIB))
    need(run["head_sha"]==SOURCE and run["run_attempt"]==ATTEMPT,"run.identity")
    dump(OUT/"producer-run.json",run)
    registry=obligations();dump(OUT/"obligations.json",registry)
    results=[];errors=[]
    for target in PINS:
        try: results.append(audit_target(target,registry))
        except Exception as e:
            errors.append({"target":target,"error":str(e),"type":type(e).__name__})
            dump(OUT/target/"error.json",errors[-1])
    need(sum(r["uncompressed_bytes"] for r in results)<=3*1024*MIB,"all_targets.budget")
    summary={"audit_completed":len(results)==6 and not errors,"targets":len(results),"errors":errors,
      "materials_complete":len(results)==6 and all(r["materials_complete"] for r in results),
      "instructions_complete":False,"legal_compliance_assessed":False,"F12_promoted":False,
      "formal_acceptance":"95/108 unchanged","source":SOURCE,"run":RUN,"attempt":ATTEMPT,
      "scope":"Retained development-package materials only; no product rebuild, execution or upgrade-safety acceptance"}
    dump(OUT/"summary.json",summary);print(json.dumps(summary))
    return 0 if summary["audit_completed"] else 1
if __name__=="__main__":
    try: sys.exit(main())
    except Exception as e:
        dump(OUT/"fatal.json",{"error":str(e),"type":type(e).__name__})
        raise
