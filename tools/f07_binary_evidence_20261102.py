#!/usr/bin/env python3
"""Read pinned binaries as data with preinstalled LLVM; no builds or payload execution."""
import hashlib,io,json,os,pathlib,re,shutil,stat,subprocess,sys,tempfile,time,urllib.request,urllib.error,zipfile
REPO="NoGod3524/EXReader"
SOURCE="ec11cf862ca3b44483d7e8c4726ae748ab438337"
PARENT="fb67403e042890d75bc28b48c00d20e83d1c90e8"
CONSUMER_PARENT="68a86723b4e19b8c1498e3f846c554cbfd5ece62"
MODIFIED_PATH="tools/f07_binary_evidence_20261102.py"
PRODUCER=41306566948
AUDIT_RUN=41495920766
AUDIT_ARTIFACT=13167080517
BRANCH="audit/f07-sixhost-binary-evidence-20261102"
MARKER="[F07-BINARY-EVIDENCE-ONE-RUN]"
PATHS=("tools/f07_binary_evidence_20261102.py",".github/workflows/f07-binary-evidence-20261102.yml","docs/reader-total-progress/F07_BINARY_EVIDENCE_20261102.md")
LOCK=json.loads('[{"id":13083193632,"name":"f04-windows-seed-41306566948-1","size_in_bytes":4201186,"digest":"sha256:1a9fc4859ab4a0b51468c0d3ee594f16ec5ce7447329c909a676d7977e5522f4","target":"windows","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"2bf178b4c284f5cd68ed6d15c448b308df75f8c85e8898256edace349b46080c"},{"id":13083881725,"name":"f04-android-peer-41306566948-1","size_in_bytes":20043430,"digest":"sha256:4b98652ca3a72a5473640bc8d067fd70b5c35b7fed6da41bf59dbfc3a12a0488","target":"android","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"6395d7431342e40567e68b88ee292a82f352a97f852d415e34b3cad2d231acb0"},{"id":13083892632,"name":"f04-gtk-peer-41306566948-1","size_in_bytes":5165508,"digest":"sha256:48e61868a5546bad38df90098859d08b3f6c9f4f59506e884fe4796177780612","target":"gtk","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"814f08a660d42c1c659bbfd4e691d4cf8c7e67f2b8a793f7ec859de9b4c6b4cd"},{"id":13083986989,"name":"f04-macos-peer-41306566948-1","size_in_bytes":3419395,"digest":"sha256:5b52dbf637fc764bcb028b5ecee2f9533fdf97661ae841eb5fe5553eca44cb26","target":"macos","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"f897162e4c1b83ab5396e7da3554426a167fe9c38f222df081a7115801d94a3f"},{"id":13084032549,"name":"f04-iphone-peer-41306566948-1","size_in_bytes":3412241,"digest":"sha256:cc4f59d193561194d762e609a382c22d5e0ce4d0672133e24cb43fdb080c33c2","target":"iphone","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"68c06e80a9173b681f79789e7ee3cdd0ab1f76325a5fe30d5ae036197d986ca0"},{"id":13083873210,"name":"f04-ipad-peer-41306566948-1","size_in_bytes":3412241,"digest":"sha256:552c8ffd99ff159619d34eef3424eef793f70d80268fafff5915c7a432141192","target":"ipad","run_id":41306566948,"source_sha":"ec11cf862ca3b44483d7e8c4726ae748ab438337","program_sha256":"6219512f607b78d89819ae8de1bbbb4d6a34e2c7c63709183041939e46af28fb"},{"id":13167080517,"name":"f07-existing-sixhost-41495920766-1","size_in_bytes":473328,"digest":"sha256:9cc435d2d24b6a9c3751ef7a1714c3713f1e0afed787432d46bb1422848f3efb","target":"prior_audit","run_id":41495920766,"source_sha":"fb67403e042890d75bc28b48c00d20e83d1c90e8"}]')
START=time.monotonic()
OUT=pathlib.Path("f07-binary-evidence"); OUT.mkdir(exist_ok=True)
report={"source":SOURCE,"parent":PARENT,"scope":"offline binary observations","acceptance_assessed":False,
"unique_static_archive_origin_proven":False,"private_entry_absence_proven":False,"runtime_loading_assessed":False,
"artifacts":[],"binaries":[],"gaps":[],"errors":[]}
def tick():
    if time.monotonic()-START>540: raise TimeoutError("audit deadline")
def sha(b): return hashlib.sha256(b).hexdigest()
def save(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=True,indent=2),encoding="utf-8")
def consumer():
    def git(*args): return subprocess.check_output(["git",*args],text=True).strip()
    head=git("rev-parse","HEAD")
    assert head==os.environ["GITHUB_SHA"]
    assert git("rev-parse","HEAD^")==CONSUMER_PARENT
    assert MARKER in git("log","-1","--format=%B")
    assert git("diff","--no-renames","--name-status",CONSUMER_PARENT,head).splitlines()==["M\t"+MODIFIED_PATH]
    return {"source_sha":head,"run_id":os.environ["GITHUB_RUN_ID"],"attempt":1,"parent_sha":CONSUMER_PARENT,"modified_paths":[MODIFIED_PATH]}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
def api(path):
    tick()
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
def download(a):
    tick()
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/actions/artifacts/"+str(a["id"])+"/zip",
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"})
    try:
        urllib.request.build_opener(NoRedirect()).open(req,timeout=30)
        raise ValueError("expected redirect")
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308): raise ValueError("redirect status") from None
        url=e.headers.get("Location","")
    if not url.startswith("https://"): raise ValueError("non HTTPS redirect")
    chunks=[]; n=0
    with urllib.request.urlopen(urllib.request.Request(url),timeout=30) as r:
        while True:
            tick(); b=r.read(1024*1024)
            if not b: break
            n+=len(b)
            if n>a["size_in_bytes"]: raise ValueError("archive size exceeded")
            chunks.append(b)
    data=b"".join(chunks)
    if n!=a["size_in_bytes"] or "sha256:"+sha(data)!=a["digest"]: raise ValueError("archive digest mismatch")
    return data
def members(z):
    infos=z.infolist(); seen=set(); total=0
    if len(infos)>20000: raise ValueError("member count exceeded")
    for i in infos:
        n=i.filename; canonical=n.rstrip("/")
        if i.orig_filename!=n or any(ord(c)<32 or ord(c)==127 for c in n): raise ValueError("control member")
        if not canonical or n.startswith("/") or "\\" in n or ":" in n or any(p in ("",".","..") for p in canonical.split("/")): raise ValueError("unsafe member")
        if canonical in seen: raise ValueError("duplicate member")
        seen.add(canonical)
        typ=stat.S_IFMT(i.external_attr>>16)
        if typ not in (0,stat.S_IFREG,stat.S_IFDIR) or i.flag_bits&1: raise ValueError("nonregular encrypted member")
        if (typ==stat.S_IFDIR and not i.is_dir()) or (typ==stat.S_IFREG and i.is_dir()): raise ValueError("member mode mismatch")
        if i.file_size>128*1024*1024: raise ValueError("member byte limit")
        total+=i.file_size
        if total>512*1024*1024: raise ValueError("archive expansion limit")
    return infos
def read(z,i):
    tick()
    with z.open(i) as f: b=f.read(i.file_size+1)
    if len(b)!=i.file_size: raise ValueError("member size mismatch")
    return b
def fmt(data):
    if data[:2]==b"MZ": return "PE"
    if data[:4]==b"\x7fELF": return "ELF"
    if data[:4] in (b"\xfe\xed\xfa\xce",b"\xce\xfa\xed\xfe",b"\xfe\xed\xfa\xcf",b"\xcf\xfa\xed\xfe",
                    b"\xca\xfe\xba\xbe",b"\xbe\xba\xfe\xca",b"\xca\xfe\xba\xbf",b"\xbf\xba\xfe\xca"): return "MachO"
    if data[:4] in (b"PK\x03\x04",b"PK\x05\x06"): return "ZIP"
    return "unknown"
def controls():
    results=[]
    def zmake(names):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            for n in names: z.writestr(n,b"{}")
        return zipfile.ZipFile(io.BytesIO(b.getvalue()))
    for label,names in [("traversal",["../x"]),("absolute",["/x"]),("backslash",["a\\x"]),("drive",["C:x"]),("canonical_duplicate",["a","a/"])]:
        with zmake(names) as z:
            try: members(z)
            except ValueError: results.append(label)
            else: raise AssertionError("unsafe zip accepted")
    with zmake(["report.json"]) as z: assert len(members(z))==1
    results.append("safe_zip")
    assert fmt(b"PK\x03\x04")=="ZIP" and fmt(b"\x7fELF")=="ELF" and fmt(b"MZ")== "PE"
    results.append("APK_not_ELF")
    assert fmt(b"\xcf\xfa\xed\xfe")=="MachO" and fmt(b"plain")=="unknown"
    results.append("MachO_and_unknown")
    return results
def tools_available():
    required={"nm":["--defined-only","--extern-only","--format","--undefined-only"],
              "readobj":["--file-header","--symbols","--coff-imports","--coff-exports",
                         "--dyn-symbols","--needed-libs","--macho-dysymtab"]}
    for suffix in ("","-20","-19","-18","-17","-16","-15","-14"):
        nm=shutil.which("llvm-nm"+suffix); ro=shutil.which("llvm-readobj"+suffix)
        if nm and ro:
            versions={}; preflight=[]; parsed=[]
            for key,path in (("nm",nm),("readobj",ro)):
                tick()
                r=subprocess.run([path,"--version"],capture_output=True,text=True,timeout=10)
                match=re.search(r"version\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)",r.stdout,re.I)
                version=match.group(1) if match else None
                versions[key]={"path":path,"returncode":r.returncode,"version":r.stdout.splitlines()[:3],"parsed_version":version}
                h=subprocess.run([path,"--help"],capture_output=True,text=True,timeout=10)
                missing=[flag for flag in required[key] if flag not in h.stdout]
                preflight.append({"tool":key,"help_returncode":h.returncode,"missing_options":missing})
                parsed.append(version)
            report["tool_preflight"]={"versions":versions,"options":preflight}
            good=all(v["returncode"]==0 for v in versions.values()) and all(parsed) and len(set(parsed))==1
            good=good and all(x["help_returncode"]==0 and not x["missing_options"] for x in preflight)
            if not good:
                report["gaps"].append("LLVM version/help preflight failed; no binary reader invocation")
                return None
            return {"nm":nm,"readobj":ro,"versions":versions,"option_preflight":preflight}
    return None
def command(tool,args,path,key):
    tick()
    # Tools only receive controlled numeric local filenames, not artifact-provided options.
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        try:
            p=subprocess.Popen([tool,*args,str(path)],stdout=out,stderr=err)
            deadline=min(START+540,time.monotonic()+30)
            while p.poll() is None:
                if time.monotonic()>deadline:
                    p.kill(); p.wait(); return {"operation":key,"timeout":True}
                if os.fstat(out.fileno()).st_size>16*1024*1024 or os.fstat(err.fileno()).st_size>1024*1024:
                    p.kill(); p.wait(); return {"operation":key,"output_limit_exceeded":True}
                time.sleep(0.1)
            rc=p.returncode
        except OSError: return {"operation":key,"launch_failed":True}
        out.seek(0,2); olen=out.tell(); err.seek(0,2); elen=err.tell()
        out.seek(0); ob=out.read(8*1024*1024); err.seek(0); eb=err.read(1024*1024)
    text=ob.decode("utf-8",errors="replace")
    result={"operation":key,"returncode":rc,"stdout_bytes":olen,"stderr_bytes":elen,
            "stdout_truncated":olen>len(ob),"stderr_truncated":elen>len(eb),
            "stdout_sha256_of_retained_bytes":sha(ob),"stderr_sha256_of_retained_bytes":sha(eb)}
    result["sqlite_identifiers"]=sorted(set(re.findall(r"\b_?sqlite3_[A-Za-z0-9_]+\b",text)))[:300]
    result["sdk_product_identifiers"]=sorted(set(re.findall(r"\b_?(?:exr|reader)_[A-Za-z0-9_]+\b",text)))[:300]
    result["dependency_name_observations"]=sorted(set(re.findall(r"\b[A-Za-z0-9_+.-]+\.(?:dll|dylib|so(?:\.[0-9]+)*)\b",text,re.I)))[:200]
    result["identifier_lists_bounded"]=True
    result["no_symbols_diagnostic"]="no symbols" in (text+eb.decode("utf-8",errors="replace")).lower()
    # Full textual tool observations remain in the authorized evidence artifact, never raw stdout.
    save(key+".json",{"result":result,"stdout":text,"stderr":eb.decode("utf-8",errors="replace")})
    return result
def scan_binary(data,target,label,toolset,folder):
    tick(); f=fmt(data); index=len(report["binaries"])
    row={"target":target,"member":label,"format":f,"bytes":len(data),"sha256":sha(data),"operations":[]}
    report["binaries"].append(row)
    expected={"windows":"PE","gtk":"ELF","android":"ELF","macos":"MachO","iphone":"MachO","ipad":"MachO"}[target]
    row["expected_format"]=expected
    if f!=expected:
        row["gap"]="target format mismatch; no reader invocation"; return
    if not toolset:
        row["gap"]="preinstalled LLVM pair missing; no install permitted"; return
    path=folder/("payload-"+str(index)+".bin"); path.write_bytes(data)
    plans=[("defined",toolset["nm"],["--defined-only","--extern-only","--format=posix"]),
           ("undefined",toolset["nm"],["--undefined-only","--format=posix"])]
    extra={"PE":["--file-header","--symbols","--coff-imports","--coff-exports"],
           "ELF":["--file-header","--symbols","--dyn-symbols","--needed-libs"],
           "MachO":["--file-header","--symbols","--needed-libs","--macho-dysymtab"]}[f]
    plans.append(("object",toolset["readobj"],extra))
    for name,tool,args in plans:
        row["operations"].append(command(tool,args,path,"binary-"+str(index)+"-"+name))
    path.unlink()
def handle_program(data,a,toolset,folder):
    if sha(data)!=a["program_sha256"]: raise ValueError("program hash mismatch")
    if a["target"]!="android":
        scan_binary(data,a["target"],"program.bin",toolset,folder); return
    if fmt(data)!="ZIP": raise ValueError("Android program not APK")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=members(z)
        selected=[i for i in infos if not i.is_dir() and re.fullmatch(r"lib/[A-Za-z0-9_-]+/[^/]+\.so",i.filename)]
        if len(selected)>64: raise ValueError("APK native count limit")
        report["android_apk"]={"sha256":sha(data),"members":len(infos),"native_members":[i.filename for i in selected]}
        if not selected: report["gaps"].append("APK contains no matching native .so member")
        for i in selected: scan_binary(read(z,i),"android",i.filename,toolset,folder)
try:
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")==REPO
    assert os.environ.get("GITHUB_REF")=="refs/heads/"+BRANCH and os.environ.get("GITHUB_RUN_ATTEMPT")=="1"
    assert len(LOCK)==7 and len({x["id"] for x in LOCK})==7 and sum(x["size_in_bytes"] for x in LOCK)==40127329
    report["stage"]="consumer"; report["consumer"]=consumer(); report["controls"]=controls()
    for rid,source in ((PRODUCER,SOURCE),(AUDIT_RUN,PARENT)):
        r=api("actions/runs/"+str(rid))
        assert r["head_sha"]==source and r["run_attempt"]==1 and r["status"]=="completed" and r["conclusion"]=="success"
    toolset=tools_available()
    report["tools"]=toolset
    if not toolset: report["gaps"].append("preinstalled LLVM unavailable; no binary tool observations")
    old=None
    with tempfile.TemporaryDirectory(prefix="f07-readonly-") as tmp:
        folder=pathlib.Path(tmp)
        for a in sorted(LOCK,key=lambda x:0 if x["id"]==AUDIT_ARTIFACT else 1):
            report["current_artifact"]=a["id"]; report["stage"]="metadata"
            m=api("actions/artifacts/"+str(a["id"]))
            for k in ("id","name","size_in_bytes","digest"): assert m[k]==a[k],k
            assert not m["expired"] and m["workflow_run"]["id"]==a["run_id"] and m["workflow_run"]["head_sha"]==a["source_sha"]
            report["stage"]="download"; data=download(a)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos=members(z)
                report["artifacts"].append({"id":a["id"],"name":a["name"],"size":len(data),"sha256":sha(data),"members":len(infos)})
                report["stage"]="selected_members"
                if a["id"]==AUDIT_ARTIFACT:
                    entries=[i for i in infos if i.filename=="summary.json"]
                    assert len(entries)==1
                    old=json.loads(read(z,entries[0]))
                    assert old["audit_complete"] and not old["errors"] and old["source"]==SOURCE and old["consumer"]["source_sha"]==PARENT
                    assert old["producer_run"]==PRODUCER and old["attempt"]==1 and len(old["artifacts"])==11
                    report["prior_audit"]={"run":AUDIT_RUN,"artifact":AUDIT_ARTIFACT,"link_text_files":sum(
                        x["kind"]=="link_text" for v in old["artifacts"] for x in v["selected"])}
                else:
                    assert old is not None
                    prior=next(v for v in old["artifacts"] if v["id"]==a["id"])
                    observed=next(x for x in prior["selected"] if x["kind"]=="program" and x["path"]=="program.bin")
                    assert observed["sha256"]==a["program_sha256"]
                    entries=[i for i in infos if i.filename=="program.bin"]
                    assert len(entries)==1
                    handle_program(read(z,entries[0]),a,toolset,folder)
            del data
            save("summary.json",report)
    operations=[op for b in report["binaries"] for op in b["operations"]]
    counts={
        "nonzero":sum("returncode" in op and op["returncode"]!=0 for op in operations),
        "timeout":sum(bool(op.get("timeout")) for op in operations),
        "launch_failed":sum(bool(op.get("launch_failed")) for op in operations),
        "output_limit":sum(bool(op.get("output_limit_exceeded")) for op in operations),
        "truncated":sum(bool(op.get("stdout_truncated") or op.get("stderr_truncated")) for op in operations),
        "no_symbols":sum(bool(op.get("no_symbols_diagnostic")) for op in operations)}
    report["operation_counts"]=counts
    report["targets_observed"]=sorted({b["target"] for b in report["binaries"]})
    report["binary_observations_complete"]=bool(toolset) and not any(counts.values()) and not any("gap" in b for b in report["binaries"]) and report["targets_observed"]==["android","gtk","ipad","iphone","macos","windows"]
    report["binary_observations_complete"]=report["binary_observations_complete"] and all(len(b["operations"])==3 for b in report["binaries"])
    report["audit_complete"]=bool(toolset)
    if not toolset: report["errors"].append({"type":"MissingOrIncompatibleTool","message":"preinstalled LLVM version/help not usable; no install or retry"})
except Exception as e:
    report["audit_complete"]=False
    report["binary_observations_complete"]=False
    safe={"audit deadline","expected redirect","redirect status","non HTTPS redirect","archive size exceeded","archive digest mismatch",
          "member count exceeded","control member","unsafe member","duplicate member","nonregular encrypted member","member mode mismatch",
          "member byte limit","archive expansion limit","member size mismatch","unsafe zip accepted","program hash mismatch",
          "Android program not APK","APK native count limit"}
    report["errors"].append({"type":type(e).__name__,"message":str(e) if str(e) in safe else "identity or operation failure",
        "stage":report.get("stage"),"artifact":report.get("current_artifact"),"http_status":e.code if isinstance(e,urllib.error.HTTPError) else None})
finally:
    report["elapsed_seconds"]=time.monotonic()-START
    save("summary.json",report)
    print("F07_BINARY_SUMMARY="+json.dumps(report,ensure_ascii=True,separators=(",",":")))
sys.exit(0 if report.get("audit_complete") else 1)
