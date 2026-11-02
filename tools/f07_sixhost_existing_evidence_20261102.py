#!/usr/bin/env python3
"""Fixed historical artifact observations only; never execute payloads."""
import hashlib,io,json,os,pathlib,re,stat,subprocess,sys,time,urllib.request,urllib.error,zipfile
REPO="NoGod3524/EXReader"
SOURCE="ec11cf862ca3b44483d7e8c4726ae748ab438337"
RUN=41306566948
MARKER="[F07-EXISTING-ARTIFACTS-ONE-RUN]"
PATHS=("tools/f07_sixhost_existing_evidence_20261102.py",".github/workflows/f07-sixhost-existing-evidence-20261102.yml","docs/reader-total-progress/F07_SIXHOST_EXISTING_EVIDENCE_20261102.md")
LOCK=json.loads('[{"id":13082734165,"name":"f04-build-windows-41306566948-1","size_in_bytes":53053366,"digest":"sha256:b83dbe7c451b4cd0d706d830f4bd20d315a5324065528890466d66f2bcad18f9","target":"windows","role":"build","related_job_ids":[124848056376]},{"id":13083886661,"name":"f04-build-android-41306566948-1","size_in_bytes":39939060,"digest":"sha256:ff84cb321c80ef3ac53dc17ae03343f127d0f6b3a76602273fabd7033064700a","target":"android","role":"build","related_job_ids":[124849056530]},{"id":13083942264,"name":"f04-build-gtk-41306566948-1","size_in_bytes":42096020,"digest":"sha256:e84f29c61d0ccf746f1c7cc2cd427850a160b1fd9faf3f87641251ca07ce83cc","target":"gtk","role":"build","related_job_ids":[124850367810]},{"id":13083581922,"name":"f04-build-macos-41306566948-1","size_in_bytes":22475890,"digest":"sha256:2c45e5de5aebdb7aecd4284043251250ddbcea3a8ac4a73cd4a486845ddaf58b","target":"macos","role":"sdk_build","related_job_ids":[124848056231]},{"id":13083354773,"name":"f04-build-iphonesimulator-41306566948-1","size_in_bytes":22468633,"digest":"sha256:0a604b5db02b5c812efbf04845cf1aafb97e6efa9040467b4d6b5100c900f38e","target":"ios","role":"sdk_build","related_job_ids":[124848056440]},{"id":13083193632,"name":"f04-windows-seed-41306566948-1","size_in_bytes":4201186,"digest":"sha256:1a9fc4859ab4a0b51468c0d3ee594f16ec5ce7447329c909a676d7977e5522f4","target":"windows","role":"seed","related_job_ids":[124848056376]},{"id":13083881725,"name":"f04-android-peer-41306566948-1","size_in_bytes":20043430,"digest":"sha256:4b98652ca3a72a5473640bc8d067fd70b5c35b7fed6da41bf59dbfc3a12a0488","target":"android","role":"peer","related_job_ids":[124849056530]},{"id":13083892632,"name":"f04-gtk-peer-41306566948-1","size_in_bytes":5165508,"digest":"sha256:48e61868a5546bad38df90098859d08b3f6c9f4f59506e884fe4796177780612","target":"gtk","role":"peer","related_job_ids":[124850367810]},{"id":13083986989,"name":"f04-macos-peer-41306566948-1","size_in_bytes":3419395,"digest":"sha256:5b52dbf637fc764bcb028b5ecee2f9533fdf97661ae841eb5fe5553eca44cb26","target":"macos","role":"peer","related_job_ids":[124850367899]},{"id":13084032549,"name":"f04-iphone-peer-41306566948-1","size_in_bytes":3412241,"digest":"sha256:cc4f59d193561194d762e609a382c22d5e0ce4d0672133e24cb43fdb080c33c2","target":"iphone","role":"peer","related_job_ids":[124850367757]},{"id":13083873210,"name":"f04-ipad-peer-41306566948-1","size_in_bytes":3412241,"digest":"sha256:552c8ffd99ff159619d34eef3424eef793f70d80268fafff5915c7a432141192","target":"ipad","role":"peer","related_job_ids":[124850367715]}]')
START=time.monotonic()
TEXT_TOTAL=0
OUT=pathlib.Path("f07-existing-evidence")
OUT.mkdir(exist_ok=True)
report={"source":SOURCE,"producer_run":RUN,"attempt":1,"accepted":False,"artifacts":[],"errors":[],
        "private_entry_absence_proven":False,"runtime_provider_verified":False}
def tick():
    if time.monotonic()-START>540: raise TimeoutError("audit deadline")
def sha(b): return hashlib.sha256(b).hexdigest()
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=True,indent=2),encoding="utf-8")
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
def api(path):
    tick()
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json",
                 "X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
def download(a):
    tick()
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/actions/artifacts/"+str(a["id"])+"/zip",
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json"})
    try:
        urllib.request.build_opener(NoRedirect()).open(req,timeout=30)
        raise ValueError("expected signed redirect")
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308): raise ValueError("redirect status") from None
        url=e.headers.get("Location","")
    if not url.startswith("https://"): raise ValueError("non-HTTPS signed URL")
    chunks=[]; n=0
    with urllib.request.urlopen(urllib.request.Request(url),timeout=30) as r:
        while True:
            tick(); b=r.read(1024*1024)
            if not b: break
            n+=len(b)
            if n>a["size_in_bytes"]: raise ValueError("archive size limit")
            chunks.append(b)
    data=b"".join(chunks)
    if n!=a["size_in_bytes"] or "sha256:"+sha(data)!=a["digest"]: raise ValueError("archive identity mismatch")
    return data
def safe_infos(z):
    infos=z.infolist()
    if len(infos)>20000: raise ValueError("member count limit")
    seen=set(); total=0
    for i in infos:
        name=i.filename; parts=name.rstrip("/").split("/")
        if i.orig_filename!=name or any(ord(ch)<32 or ord(ch)==127 for ch in name):
            raise ValueError("control character member")
        canonical=name.rstrip("/")
        mode_type=stat.S_IFMT(i.external_attr>>16)
        if mode_type not in (0,stat.S_IFREG,stat.S_IFDIR):
            raise ValueError("nonregular member")
        if (mode_type==stat.S_IFDIR and not i.is_dir()) or (mode_type==stat.S_IFREG and i.is_dir()):
            raise ValueError("member mode directory mismatch")
        if not name or name.startswith("/") or "\\" in name or ":" in name or any(p in ("",".","..") for p in parts):
            raise ValueError("unsafe member")
        if canonical in seen: raise ValueError("duplicate member")
        seen.add(canonical)
        if stat.S_ISLNK(i.external_attr>>16) or i.flag_bits&1: raise ValueError("symlink/encrypted member")
        if i.file_size>256*1024*1024: raise ValueError("member size limit")
        total+=i.file_size
        if total>2*1024**3: raise ValueError("uncompressed size limit")
    return infos
def kind(name):
    b=pathlib.PurePosixPath(name).name.lower()
    if b=="program.bin": return "program"
    if b in ("build-receipt.json","installed-identity.json","sdk342-installed-identity.json",
             "wave3-packages.json","sdk-identity.json","raw-identity.json","report.json","result.json",
             "manifest.json","commands.json"): return "identity_or_report"
    if b.endswith(".json") and re.search(r"(?:^|[-_])(receipt|identity|report)(?:[-_.]|$)",b): return "identity_or_report"
    if b.endswith((".map",".rsp")) or b in ("link.txt","link.command","link-command.txt"): return "link_text"
    if re.search(r"(symbols?|imports?|exports?|dependencies|private.entry|linker|link.report)",b) and b.endswith((".txt",".json",".log")):
        return "module_or_link_report"
    return None
def identity_fields(obj,prefix="",depth=0):
    if depth>8: return []
    result=[]
    allowed={"source","source_sha","head_sha","commit","commit_sha","sdk_source","sdk_source_sha","sdk_sha",
             "program_sha256","sha256","digest","run_id","run_attempt","artifact_id","job_id"}
    if isinstance(obj,dict):
        for k,v in obj.items():
            if not isinstance(k,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}",k): continue
            key=prefix+"."+k if prefix else k
            if k in allowed and isinstance(v,str) and re.fullmatch(r"(?:sha256:)?[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?",v):
                result.append({"field":key,"value":v})
            elif k in {"run_id","run_attempt","artifact_id","job_id"} and isinstance(v,int) and not isinstance(v,bool):
                result.append({"field":key,"value":v})
            elif isinstance(v,(dict,list)): result.extend(identity_fields(v,key,depth+1))
            if len(result)>=100: break
    elif isinstance(obj,list):
        for i,v in enumerate(obj[:32]):
            result.extend(identity_fields(v,prefix+"["+str(i)+"]",depth+1))
    return result[:100]
def compact(x):
    r={k:v for k,v in x.items() if k not in ("text","json","sqlite_lines")}
    if "json" in x: r["identity_fields"]=identity_fields(x["json"])
    if "sqlite_lines" in x:
        # Never echo arbitrary log text/URLs/connection strings; only identifier matches.
        matches=[]
        for row in x["sqlite_lines"]:
            tokens=re.findall(r"\b(?:sqlite3_[A-Za-z0-9_]+|exr_vendor_exr_sqlite(?:\.lib)?|reader_catalog_sqlite(?:\.lib)?)\b",row["text"])
            if tokens: matches.append({"line":row["line"],"identifiers":tokens[:20]})
            if len(matches)>=100: break
        r["sqlite_identifier_observations"]=matches
    return r
def verify_consumer():
    def git(*args): return subprocess.check_output(["git",*args],text=True).strip()
    head=git("rev-parse","HEAD")
    if head!=os.environ.get("GITHUB_SHA"): raise ValueError("consumer HEAD mismatch")
    subprocess.run(["git","merge-base","--is-ancestor",SOURCE,head],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if MARKER not in git("log","-1","--format=%B"): raise ValueError("consumer marker mismatch")
    changes=git("diff","--name-status","--no-renames",SOURCE,head).splitlines()
    if sorted(changes)!=sorted("A\t"+p for p in PATHS): raise ValueError("consumer exact three-addition scope mismatch")
    return {"source_sha":head,"run_id":os.environ.get("GITHUB_RUN_ID"),"attempt":1,"producer_source":SOURCE,"exact_added_paths":list(PATHS)}
def inspect(a,data):
    global TEXT_TOTAL
    result={"id":a["id"],"name":a["name"],"target":a["target"],"role":a["role"],"sha256":sha(data),
            "size_in_bytes":len(data),"inventory":[],"selected":[],"gaps":[]}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for i in safe_infos(z):
            tick()
            result["inventory"].append({"path":i.filename,"bytes":i.file_size,"crc":i.CRC,"directory":i.is_dir()})
            k=kind(i.filename)
            if not k or i.is_dir(): continue
            entry={"path":i.filename,"kind":k,"bytes":i.file_size}
            if k!="program" and (i.file_size>8*1024*1024 or TEXT_TOTAL+i.file_size>64*1024*1024):
                entry["skipped"]="text budget"; result["selected"].append(entry); continue
            with z.open(i) as f:
                h=hashlib.sha256(); chunks=[]; n=0
                while True:
                    tick(); b=f.read(1024*1024)
                    if not b: break
                    n+=len(b); h.update(b)
                    if n>i.file_size: raise ValueError("expanded size mismatch")
                    if k!="program": chunks.append(b)
            if n!=i.file_size: raise ValueError("member size mismatch")
            entry["sha256"]=h.hexdigest()
            if k!="program":
                raw=b"".join(chunks); TEXT_TOTAL+=len(raw)
                try: text=raw.decode("utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig")
                except UnicodeDecodeError: entry["skipped"]="unsupported encoding; retained inventory/hash"
                else:
                    entry["text"]=text
                    if k=="identity_or_report":
                        try: entry["json"]=json.loads(text)
                        except ValueError: entry["parse"]="not JSON"
                    if k in ("link_text","module_or_link_report"):
                        entry["sqlite_lines"]=[{"line":n,"text":s} for n,s in enumerate(text.splitlines(),1)
                                               if re.search(r"sqlite|exr_vendor|reader_catalog",s,re.I)][:2000]
                        entry["interpretation"]="observation only; not proof of unique provider/no private dependencies"
            result["selected"].append(entry)
    for k in ("program","identity_or_report","link_text","module_or_link_report"):
        if not any(x["kind"]==k and "skipped" not in x for x in result["selected"]):
            result["gaps"].append(k+": no readable matching member; artifact role may not require it")
    save(str(a["id"])+".json",result)
    return {k:v for k,v in result.items() if k not in ("inventory","selected")} | {
        "members":len(result["inventory"]),"selected":[compact(x) for x in result["selected"]]}
def controls():
    results=[]
    def archive(names):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            for n in names: z.writestr(n,b"{}")
        return zipfile.ZipFile(io.BytesIO(b.getvalue()))
    for label,names in [("traversal",["../x"]),("absolute",["/x"]),("backslash",["a\\x"]),("drive",["C:x"]),("duplicate",["x","x"])]:
        with archive(names) as z:
            try: safe_infos(z)
            except ValueError: results.append(label+"_rejected")
            else: raise AssertionError("unsafe ZIP accepted")
    with archive(["a/build-receipt.json","a/link.rsp"]) as z: assert len(safe_infos(z))==2
    assert kind("a/link.rsp")=="link_text" and kind("a/program.bin")=="program"
    assert kind("a/app.exe") is None and kind("a/arbitrary.py") is None
    results.append("selection_and_safe_members")
    return results
try:
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")==REPO
    assert os.environ.get("GITHUB_REF")=="refs/heads/audit/f07-sixhost-existing-evidence-20261102"
    assert os.environ.get("GITHUB_RUN_ATTEMPT")=="1"
    assert len(LOCK)==11 and sum(a["size_in_bytes"] for a in LOCK)==219686970 and len({a["id"] for a in LOCK})==11
    report["stage"]="consumer_scope"
    report["consumer"]=verify_consumer()
    report["controls"]=controls()
    report["stage"]="producer_run"
    run=api("actions/runs/"+str(RUN))
    assert run["head_sha"]==SOURCE and run["run_attempt"]==1 and run["status"]=="completed" and run["conclusion"]=="success"
    report["producer"]={k:run.get(k) for k in ("id","head_sha","run_attempt","status","conclusion","html_url")}
    report["stage"]="producer_jobs"
    jobs=api("actions/runs/"+str(RUN)+"/attempts/1/jobs?per_page=100")["jobs"]
    byid={j["id"]:j for j in jobs}
    report["related_successful_jobs"]=[]
    for jid in sorted({j for a in LOCK for j in a["related_job_ids"]}):
        j=byid[jid]
        assert j["run_id"]==RUN and j["head_sha"]==SOURCE and j["status"]=="completed" and j["conclusion"]=="success"
        report["related_successful_jobs"].append({k:j.get(k) for k in ("id","name","run_id","head_sha","status","conclusion")})
    for a in LOCK:
        tick(); report["stage"]="artifact_metadata"; report["current_artifact"]=a["id"]
        actual=api("actions/artifacts/"+str(a["id"]))
        for k in ("id","name","size_in_bytes","digest"): assert actual[k]==a[k],k
        assert not actual["expired"] and actual["workflow_run"]["id"]==RUN and actual["workflow_run"]["head_sha"]==SOURCE
        report["stage"]="artifact_download"
        data=download(a)
        report["stage"]="artifact_inventory_text"
        report["artifacts"].append(inspect(a,data)); del data
        save("summary.json",report)
    report["audit_complete"]=True
except Exception as e:
    report["audit_complete"]=False
    safe_errors={"audit deadline","expected signed redirect","redirect status","non-HTTPS signed URL","archive size limit",
                 "archive identity mismatch","member count limit","unsafe member","duplicate member","symlink/encrypted member",
                 "member size limit","uncompressed size limit","expanded size mismatch","member size mismatch",
                 "unsafe ZIP accepted","control character member","nonregular member","member mode directory mismatch",
                 "consumer HEAD mismatch","consumer marker mismatch","consumer exact three-addition scope mismatch"}
    detail=str(e) if str(e) in safe_errors else ("identity/assertion mismatch" if isinstance(e,AssertionError) else "operation failed; detail suppressed")
    report["errors"].append({"type":type(e).__name__,"message":detail,"artifact_id":report.get("current_artifact"),
                             "stage":report.get("stage"),"http_status":e.code if isinstance(e,urllib.error.HTTPError) else None})
finally:
    report["elapsed_seconds"]=time.monotonic()-START
    save("summary.json",report)
    print("F07_EXISTING_SUMMARY="+json.dumps(report,ensure_ascii=True,separators=(",",":")))
sys.exit(0 if report.get("audit_complete") else 1)
