"""Read one immutable producer archive. Never execute archive content."""
import hashlib,json,os,pathlib,stat,urllib.request,urllib.parse,zipfile
ROOT=pathlib.Path("build/f03-retained-evidence")
ROOT.mkdir(parents=True,exist_ok=False)
REPO="NoGod3524/EXReader"
RUN=41360729084
ARTIFACT=13104954654
SOURCE="ce45497953e4f54cc253842a153f72f9f00a28bb"
SIZE=234819553
DIGEST="09d290caa818a4679587df4f117d26fc4be6182bf6c877295b49497de3a4904b"
def require(value,message):
    if not value:raise RuntimeError(message)
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if urllib.parse.urlsplit(req.full_url).netloc!=urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected
opener=urllib.request.build_opener(SafeRedirect())
def request(path):
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,
        headers={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    return opener.open(req,timeout=90)
def get(path):
    with request(path) as response:return json.load(response)
producer=get("actions/runs/"+str(RUN))
require(producer["head_sha"]==SOURCE and producer["run_attempt"]==1 and producer["status"]=="completed" and producer["conclusion"]=="failure","producer identity/state mismatch")
artifact=get("actions/artifacts/"+str(ARTIFACT))
require(artifact["id"]==ARTIFACT and artifact["size_in_bytes"]==SIZE and not artifact["expired"],"artifact metadata mismatch")
require(artifact["digest"]=="sha256:"+DIGEST and artifact["workflow_run"]["id"]==RUN and artifact["workflow_run"]["head_sha"]==SOURCE,"artifact provenance mismatch")
archive=ROOT/"producer.zip"
digest=hashlib.sha256();count=0
with request("actions/artifacts/"+str(ARTIFACT)+"/zip") as response,archive.open("xb") as stream:
    while True:
        block=response.read(1024*1024)
        if not block:break
        count+=len(block);require(count<=SIZE,"archive oversized")
        digest.update(block);stream.write(block)
require(count==SIZE and digest.hexdigest()==DIGEST,"archive digest/length mismatch")
def allowed(name):
    if name.startswith("build/"):name=name[6:]
    fixed={"f03-android-original-steps.json","f03-android-retained-driver.json","android-host/gate-review.json","android-host/bounded-gate-review.json","shelf-android/original-result.json","shelf-android/result.json"}
    return name in fixed or name.startswith("android-host/evidence/") and not name.startswith("android-host/evidence/artifacts/") and pathlib.PurePosixPath(name).suffix.lower() in {".json",".txt",".log"}
manifest=[];findings=[];total=0
def scan(value,path,pointer="$"):
    if isinstance(value,dict):
        negative=any(value.get(k) is False for k in ("passed","accepted","success","ok","candidate_validated","bounded_gate_accepted"))
        negative=negative or any(isinstance(value.get(k),(int,float)) and not isinstance(value.get(k),bool) and value[k]>0 for k in ("failed","skipped","failures","errors"))
        negative=negative or str(value.get("status","")).lower() in ("failed","failure","skipped","error")
        if negative:
            short={k:v for k,v in value.items() if not isinstance(v,(dict,list)) or k in ("problems","error","errors")}
            findings.append({"file":path,"pointer":pointer,"value":short})
        for key,item in value.items():scan(item,path,pointer+"/"+str(key))
    elif isinstance(value,list):
        for i,item in enumerate(value):scan(item,path,pointer+"/"+str(i))
with zipfile.ZipFile(archive) as zipped:
    names=zipped.namelist();require(len(names)==len(set(names)),"duplicate archive names")
    (ROOT/"archive-members.json").write_text(json.dumps(names,indent=2))
    for info in zipped.infolist():
        name=info.filename
        path=pathlib.PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts and "\\" not in name,"unsafe archive member")
        require(not stat.S_ISLNK(info.external_attr>>16),"archive symlink")
        if info.is_dir() or not allowed(name):continue
        require(info.file_size<=24*1024*1024,"selected text too large: "+name)
        total+=info.file_size;require(total<=80*1024*1024,"selected evidence budget exceeded")
        raw=zipped.read(info);text=raw.decode("utf-8")
        target=ROOT/"selected"/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        entry={"path":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
        manifest.append(entry)
        if name.endswith(".json"):
            value=json.loads(text);scan(value,name)
        else:
            hits=[{"line":i+1,"text":s[:2000]} for i,s in enumerate(text.splitlines()) if any(k in s.lower() for k in ("assertionerror","assertionfailederror","failures!!!","shortmsg=","test failed","skipped"))]
            if hits:findings.append({"file":name,"text_hits":hits[:30]})
require(manifest,"no allowed evidence found")
require(any("walkthrough" in x["path"].lower() for x in manifest),"walkthrough evidence missing; inspect archive-members")
result={"diagnostic_identity":{"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]},
    "producer_identity":{"run_id":RUN,"attempt":1,"source_sha":SOURCE,"artifact_id":ARTIFACT,"archive_bytes":count,"archive_sha256":digest.hexdigest()},
    "selected_files":manifest,"findings":findings,"producer_conclusion":"failure",
    "rebuild_executed":False,"emulator_executed":False,"tests_reexecuted":False,"product_accepted":False}
(ROOT/"result.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
print(json.dumps(result,ensure_ascii=True))
archive.unlink()
