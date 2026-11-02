"""Read one immutable producer archive. Never execute archive content."""
import hashlib,json,os,pathlib,stat,urllib.request,urllib.parse,zipfile,re
ROOT=pathlib.Path("build/f03-candidate-contract")
ROOT.mkdir(parents=True,exist_ok=False)
REPO="NoGod3524/EXReader"
RUN=41367420320
ARTIFACT=13109295042
SOURCE="39600d0d3a3a5e4bc2599a92e94e494a542f06f1"
SIZE=234959087
DIGEST="88e9af8020ff5fb2057a6525dcc1400a67c935949a0ef414db0eba76ef87543a"
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
job=get("actions/jobs/125030446752")
require(job["id"]==125030446752 and job["run_id"]==RUN and job["status"]=="completed" and job["conclusion"]=="failure","producer job mismatch")
if "run_attempt" in job:require(job["run_attempt"]==1,"producer job attempt mismatch")
require(job.get("head_sha",SOURCE)==SOURCE,"producer job source mismatch")
artifact=get("actions/artifacts/"+str(ARTIFACT))
require(artifact["name"]=="reader-suite-f03-bootstrap-recovery-41367420320-1","artifact name mismatch")
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

# This adapter checks an authenticated producer contract, not a product rerun.
import copy,subprocess
BASE="94fb236a4a2da87dfbaf4f1dd2a47885d615a230"
def git_bytes(path):
    return subprocess.check_output(["git","show",SOURCE+":"+path])
def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
gate_paths=["tests/android_host/check_evidence_gate.py","tests/android_host/check_bounded_evidence_gate.py"]
gate_blobs=["25bd472866a3ea1c98131fe2e43b34bf9d1dcd49","cd44337313dad579e450a5b709d1cf143d5ea31d"]
gate_sha=[]
for path,pin in zip(gate_paths,gate_blobs):
    raw=git_bytes(path);require(git_blob(raw)==pin,"frozen gate source mismatch")
    require(pathlib.Path(path).read_bytes()==raw,"consumer checkout gate changed")
    gate_sha.append(hashlib.sha256(raw).hexdigest())
WALK="cold_start_shelf picker_cancel import_epub open_epub page_next page_prev font_increase font_decrease touch_select copy_selection note_add notes_read note_edit note_navigate rotate_landscape rotate_portrait activity_rebuild background_resume process_restart_reflow notes_after_restart note_delete import_txt open_txt import_pdf open_pdf pdf_next pdf_prev pdf_zoom pdf_select_copy pdf_note_add pdf_process_restart pdf_note_delete import_bigchapter open_bigchapter bigchapter_next import_ambiguous ambiguous_restore corrupt_import retry_import duplicate_import too_large cancel_large_import book_switch accessibility_semantics native_metrics".split()
REVIEW="duplicate_cancel_keeps_original new_copy_cancel_cleans_file late_insert_cancel_rolls_back_new_book duplicate_late_cancel_keeps_original late_cancel_after_commit_reports_success failed_open_preserves_reader failed_progress_preserves_frame selection_invalidated_while_busy unicode_comment_round_trip destroyed_activity_releases_worker".split()
BOUNDED="bounded_source_delete_restore bounded_cross_chapter_font bounded_note_domain_restart bounded_duplicate_spine bounded_legacy_dedup bounded_schema6_upgrade bounded_progress_write_reject bounded_external_commit_reopen bounded_damaged_next_preserves_frame bounded_budget_limit_preserves_frame bounded_empty_next_explicit_error".split()
MUTATIONS="missing_case duplicate_case reordered_case unknown_case skipped_case summary_skipped case_json missing_shot empty_shot changed_shot reused_shot escaping_shot".split()
GATES=[["positive"]+[s+":"+m for s in ("walkthrough","review") for m in MUTATIONS]+"source run attempt app_apk test_apk installed_apk sdk native font fixture device_fixture missing_log failed_instrumentation missing_review sequence suite_identity skipped_build source_inventory log_hash failed_build cancelled_emulator skipped_static missing_emulator".split(),
 ["positive"]+["bounded:"+m for m in MUTATIONS]+"missing_bounded_report missing_bounded_log changed_bounded_log missing_restart_frame_observation changed_restart_drawn_token changed_frame_png pdf_turn_reused_bitmap".split()]
FIXED={"shelf-android/original-result.json","android-host/build.json","android-host/gate-review.json","android-host/bounded-gate-review.json"}
for folder in ("device","review","bounded"):
    FIXED.add("android-host/evidence/"+folder+"/validation.json")
def wanted(name):
    return name in FIXED or any(name.startswith("android-host/evidence/"+f+"/cases/") and name.endswith(".json") for f in ("device","review","bounded"))
records={};raw_hash={};manifest=[];errors=[];checks=[];total=0
with zipfile.ZipFile(archive) as zipped:
    seen=set();logical_seen=set()
    for info in zipped.infolist():
        name=info.filename;path=pathlib.PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts and "\\" not in name,"unsafe archive path")
        require(":" not in name and "\x00" not in info.orig_filename and name.rstrip("/")==path.as_posix(),"noncanonical archive path")
        canonical=path.as_posix();require(canonical not in seen,"duplicate archive path");seen.add(canonical)
        require(not info.flag_bits&1,"encrypted archive member")
        require(stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),"nonregular archive member")
        if info.is_dir():continue
        logical=name.removeprefix("build/")
        require(logical not in logical_seen,"logical duplicate archive path");logical_seen.add(logical)
        if not wanted(logical):continue
        require(info.file_size<=24*1024*1024,"selected member too large")
        total+=info.file_size;require(total<=80*1024*1024,"selected evidence budget exceeded")
        raw=zipped.read(info);raw_hash[logical]=hashlib.sha256(raw).hexdigest()
        manifest.append({"path":logical,"bytes":len(raw),"sha256":raw_hash[logical]})
        try:records[logical]=json.loads(raw.decode("utf-8"))
        except (UnicodeError,ValueError,RecursionError):errors.append({"path":logical,"error":"invalid UTF-8/JSON"})
missing=sorted(FIXED-records.keys())
def identity(value):
    require(value.get("source_sha")==SOURCE and str(value.get("run_id"))==str(RUN) and str(value.get("attempt"))=="1","source/run/attempt mismatch")
def validate(data):
    require(not (FIXED-data.keys()),"required evidence missing")
    original=data["shelf-android/original-result.json"]
    require(original.get("schema")==2 and original.get("accepted") is False and original.get("ok") is True and original.get("candidate_only") is True and original.get("candidate_validated") is True and original.get("problems")==[],"candidate-only report contract mismatch")
    summary=original["summary"]
    require(summary.get("source_sha")==SOURCE and str(summary["run"]["id"])==str(RUN) and str(summary["run"]["attempt"])=="1","original identity mismatch")
    build=data["android-host/build.json"];identity(build)
    require(summary["build"]==build,"producer build report mismatch")
    owner=build["ownership"]
    require(owner.get("sdk_base")==BASE and owner.get("review_base")==BASE and owner.get("ownership_head")==BASE and owner.get("tested_source")==SOURCE and owner.get("candidate_only") is True,"candidate SDK identity mismatch")
    require(build.get("sdk_built") is True and build.get("apk_built") is True and build.get("sdk_files_sha256") and build.get("source_files_sha256"),"SDK/source inventory missing")
    for folder,ids,key in (("device",WALK,None),("review",REVIEW,"review"),("bounded",BOUNDED,"bounded")):
        report=data["android-host/evidence/"+folder+"/validation.json"];identity(report)
        expected={"total":len(ids),"passed":len(ids),"failed":0,"skipped":0}
        require(report.get("summary")==expected,"suite summary mismatch")
        cases=report["cases"];require([c.get("id") for c in cases]==ids,"suite case identity/order mismatch")
        require(all(c.get("status")=="pass" for c in cases),"suite case not passed")
        require(report.get("apk_sha256")==build["artifacts"]["app-debug.apk"]["sha256"] and report.get("test_apk_sha256")==build["artifacts"]["uitest-debug-androidTest.apk"]["sha256"],"suite APK identity mismatch")
        require(report.get("physical_device_execution") is False and report.get("device_is_emulator") is True and report.get("api")==34 and report.get("abi")=="x86_64","suite device scope mismatch")
        host=summary if key is None else summary[key]
        require(host["summary"]==expected and host["cases"]==cases,"host versus original suite mismatch")
        case_prefix="android-host/evidence/"+folder+"/cases/"
        expected_paths=[case_prefix+(str(index+1).zfill(2)+"-" if folder=="device" else "")+case["id"]+".json" for index,case in enumerate(cases)]
        require({p for p in data if p.startswith(case_prefix)}==set(expected_paths),"original case file set mismatch")
        for case,path in zip(cases,expected_paths):
            require(data[path]==case,"original case file mismatch")
    for index,(path,field) in enumerate((("android-host/gate-review.json","gate_review_sha256"),("android-host/bounded-gate-review.json","bounded_gate_review_sha256"))):
        gate=data[path];identity(gate)
        require(gate.get("accepted") is True and gate.get("script_sha256")==gate_sha[index],"strict gate identity mismatch")
        require(summary.get(field)==raw_hash[path],"strict gate report hash mismatch")
        require([c.get("name") for c in gate["checks"]]==GATES[index] and all(c.get("passed") is True for c in gate["checks"]),"strict gate count/order/pass mismatch")
    return {"candidate_only":True,"candidate_contract_validated":True,"product_accepted":False,"formal_accepted":False,"producer_conclusion":"failure","original_accepted":False,"counts":{"walkthrough":45,"review":10,"bounded":11,"strict_gate":48,"bounded_gate":20}}
def negative(name,mutate):
    changed=copy.deepcopy(records)
    mutate(changed)
    try:validate(changed)
    except (RuntimeError,KeyError,TypeError,ValueError):checks.append({"name":name,"rejected":True})
    else:raise RuntimeError("negative control incorrectly accepted: "+name)
result={"consumer_identity":{"source_sha":os.environ["GITHUB_SHA"],"run_id":os.environ["GITHUB_RUN_ID"],"attempt":os.environ["GITHUB_RUN_ATTEMPT"]},
 "producer_identity":{"source_sha":SOURCE,"run_id":str(RUN),"attempt":"1","artifact_id":ARTIFACT,"bytes":SIZE,"sha256":DIGEST},
 "missing":missing,"inspection_errors":errors,"selected_files":manifest,"negative_controls":checks,
 "producer_conclusion":"failure","product_accepted":False,"tests_reexecuted":False,"build_executed":False,"emulator_executed":False}
try:
    require(not missing and not errors,"missing or invalid selected evidence")
    result["positive"]=validate(records)
    original="shelf-android/original-result.json"
    for field,value in (("accepted",True),("ok",False),("candidate_only",False),("candidate_validated",False),("problems",["controlled"])):
        negative("candidate_"+field,lambda d,f=field,v=value:d[original].update({f:v}))
    negative("wrong_source",lambda d:d[original]["summary"].update(source_sha="0"*40))
    negative("wrong_run",lambda d:d[original]["summary"]["run"].update(id="0"))
    negative("wrong_attempt",lambda d:d[original]["summary"]["run"].update(attempt="2"))
    negative("SDK_baseline",lambda d:d["android-host/build.json"]["ownership"].update(sdk_base="0"*40))
    negative("SDK_inventory",lambda d:d["android-host/build.json"].update(sdk_files_sha256={}))
    for folder in ("device","review","bounded"):
        path="android-host/evidence/"+folder+"/validation.json"
        negative(folder+"_missing",lambda d,p=path:d.pop(p))
        negative(folder+"_extra_case",lambda d,f=folder:d.update({"android-host/evidence/"+f+"/cases/unexpected.json":{}}))
        negative(folder+"_missing_case",lambda d,p=path:d[p]["cases"].pop())
        negative(folder+"_failed",lambda d,p=path:d[p]["cases"][0].update(status="fail"))
        negative(folder+"_skipped",lambda d,p=path:d[p]["summary"].update(skipped=1))
        negative(folder+"_wrong_source",lambda d,p=path:d[p].update(source_sha="0"*40))
    for path,field in (("android-host/gate-review.json","gate_review_sha256"),("android-host/bounded-gate-review.json","bounded_gate_review_sha256")):
        name=path.split("/")[-1]
        negative(name+"_missing",lambda d,p=path:d.pop(p))
        negative(name+"_hash",lambda d,f=field:d[original]["summary"].update({f:"0"*64}))
        negative(name+"_script",lambda d,p=path:d[p].update(script_sha256="0"*64))
        negative(name+"_missing_check",lambda d,p=path:d[p]["checks"].pop())
        negative(name+"_failed_check",lambda d,p=path:d[p]["checks"][0].update(passed=False))
        negative(name+"_wrong_run",lambda d,p=path:d[p].update(run_id="0"))
    require(len(checks)==40 and all(x["rejected"] for x in checks),"negative control set incomplete")
    result["contract_regression_passed"]=True
except Exception as error:
    result["contract_regression_passed"]=False
    result["contract_error"]=type(error).__name__+": "+str(error)[:500]
(ROOT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
archive.unlink()
require(result["contract_regression_passed"],"candidate contract regression failed; original producer failure preserved")
