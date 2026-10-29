#!/usr/bin/env python3
"""Actions-only independent native sync detail evidence audit."""
import hashlib, io, json, os, re, subprocess, tempfile, zipfile
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true"
REPO="NoGod3524/EXReader"
RUN=40914421686
SOURCE="6c7d043d416c1ab1075016695ae510c7b23dd2e5"
JOBS={"macos":123590727527,"iphone":123590727120,"ipad":123590727740}
def api(path, binary=False):
    raw=subprocess.check_output(["gh","api","repos/"+REPO+"/"+path])
    return raw if binary else json.loads(raw)
def sha(data): return hashlib.sha256(data).hexdigest()
def one(root, name):
    matches=list(root.rglob(name))
    assert len(matches)==1,(name,len(matches))
    return matches[0]
def origin(value, platform):
    assert value["source_sha"]==SOURCE and str(value["run_id"])==str(RUN)
    assert str(value["attempt"])=="1" and value["platform"]==platform
    assert value["accepted"] is True
def cases(bundle):
    raw=subprocess.check_output(["xcrun","xcresulttool","get","test-results","tests","--path",str(bundle),"--format","json"])
    result=[]
    def walk(n):
        if n.get("nodeType")=="Test Case": result.append((n["name"],n["result"]))
        for child in n.get("children",[]):walk(child)
    for n in json.loads(raw)["testNodes"]:walk(n)
    return dict(result)
run=api("actions/runs/%d/attempts/1"%RUN)
assert run["head_sha"]==SOURCE and run["status"]=="completed" and run["conclusion"]=="success" and run["run_attempt"]==1
artifacts=api("actions/runs/%d/artifacts?per_page=100"%RUN)["artifacts"]
results=[]
with tempfile.TemporaryDirectory() as work:
    for platform,job_id in JOBS.items():
        job=api("actions/jobs/%d"%job_id)
        assert job["run_id"]==RUN and job["head_sha"]==SOURCE and job["conclusion"]=="success"
        name="apple-sync-%s-%d-1"%(platform,RUN)
        found=[a for a in artifacts if a["name"]==name]
        assert len(found)==1
        meta=found[0]
        assert not meta["expired"] and meta["workflow_run"]["head_sha"]==SOURCE
        raw=api("actions/artifacts/%d/zip"%meta["id"],True)
        assert len(raw)==meta["size_in_bytes"] and "sha256:"+sha(raw)==meta["digest"]
        root=Path(work)/platform;root.mkdir()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert len(z.namelist())==len(set(z.namelist()))
            for n in z.namelist():
                assert not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and "\\" not in n
            z.extractall(root)
        summary=json.loads(one(root,"account-ui.json").read_text())
        origin(summary,platform)
        assert summary["network_sync_ui_accepted"] is True and summary["cases"]==3
        assert summary["https"]["actual_shards"]==256 and summary["https"]["minimum_completed_sweeps"]>=3
        main=cases(one(root,platform+".xcresult"))
        expected={"test01RootValidationAnonymousRestartAndUpdate()","test02SeparateAccountLibrariesAndRestart()","test03NativeHTTPSBackgroundCloseAndRetry()"}
        assert set(main)==expected and set(main.values())=={"Passed"}
        path=one(root,"failure-evidence.json");failure=json.loads(path.read_text())
        origin(failure,platform)
        assert failure["case"]["name"]=="testAuthorizationFailurePreservesBookAndRetry()" and failure["case"]["result"]=="Passed"
        assert failure["failure_requests"]>=1 and failure["failed_state_pending_revisions"]==1
        assert failure["recovery_shards"]==256 and failure["outbox_after_retry"]==0
        assert cases(one(root,"failure.xcresult"))=={"testAuthorizationFailurePreservesBookAndRetry()":"Passed"}
        requests=json.loads((path.parent/"https-requests.json").read_text())
        first_good=next(i for i,r in enumerate(requests) if r["authenticated"])
        observations=[i for i,r in enumerate(requests) if r["method"]=="OBSERVE"]
        assert len(observations)==1 and 0<observations[0]<first_good
        assert any(not r["authenticated"] and r["method"]!="OBSERVE" for r in requests[:observations[0]])
        shards={r["path"] for r in requests[first_good:] if r["authenticated"] and r["method"]=="PROPFIND" and re.fullmatch(r"/dav/exreader-sync-v1/revisions/[0-9a-f]{2}/",r["path"])}
        assert len(shards)==256
        boundary=json.loads((path.parent/"failure-boundary.json").read_text())
        failed=json.loads((path.parent/"failed-state-outbox.json").read_text())
        assert len(boundary)==len(failed)==1 and boundary==failed
        assert boundary[0]["local_books"]==1 and len(boundary[0]["pending_revisions"])==1
        results.append({"platform":platform,"run":RUN,"source":SOURCE,"job":job_id,"artifact":meta["id"],"archive_sha256":sha(raw),
                        "accepted":True,"physical_device":False,"main_cases":list(main),"failure_case":failure["case"]["name"],
                        "recovery_shards":len(shards),"failed_state_pending_revisions":1,"program_hash_recorded_by_original_collector":summary["actual_executable_sha256"]})
        print(json.dumps(results[-1]),flush=True)
out=Path("build/apple-sync-details-independent");out.mkdir(parents=True,exist_ok=True)
(out/"result.json").write_text(json.dumps({"results":results,"catalog_changed":False},indent=2)+"\n")
