"""Fail-closed F03 convergence audit; preparatory/local evidence can never award F03."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from identity import SCOPE, TABLES, canonical, digest, identity, require, same_identity, write_json

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
def file_record(root, item):
    path = (root / item["path"]).resolve(strict=True)
    require(path.is_relative_to(root.resolve()), "evidence path escape")
    require(path.stat().st_size == item["bytes"] and digest(path) == item["sha256"],
            "evidence bytes differ: " + item["path"])
    return path
def projection(value, selected):
    result = {}
    for table, columns in TABLES.items():
        rows = value[table]
        require(all(set(row) == set(columns) for row in rows), "wrong projection columns")
        ids = selected[table]
        key = columns[0]
        result[table] = sorted([row for row in rows if row[key] in ids],
                               key=lambda row: canonical(row))
    return result

def retained_binding(root, manifest, host, stamp):
    """Keep original schema; bind its real bytes to successful same-run producer evidence."""
    report = read(file_record(root, manifest["retained"][host]))
    same_identity(report, stamp)
    require(report.get("accepted") is True and report.get("failed", 0) == 0 and
            report.get("skipped", 0) == 0 and not report.get("problems", []),
            "retained host failure: " + host)
    binding = manifest["producer_evidence"][host]
    job = read(file_record(root, binding["job_metadata"]))
    require(str(job.get("run_id")) == stamp["run_id"] and
            str(job.get("run_attempt")) == stamp["attempt"] and
            job.get("head_sha") == stamp["source_sha"] and
            job.get("status") == "completed" and job.get("conclusion") == "success",
            "producer job not successful at this source/run/attempt: " + host)
    artifact = read(file_record(root, binding["artifact_metadata"]))
    origin = artifact.get("workflow_run", {})
    require(str(origin.get("id")) == stamp["run_id"] and
            origin.get("head_sha") == stamp["source_sha"] and not artifact.get("expired"),
            "artifact provenance differs: " + host)
    archive = file_record(root, binding["archive"])
    require(archive.stat().st_size == artifact.get("size_in_bytes") and
            artifact.get("digest") == "sha256:" + digest(archive),
            "original artifact bytes differ: " + host)
    build = read(file_record(root, binding["build"]))
    same_identity(build, stamp)
    require(build.get("operation_completed") is True and
            build.get("sdk_source") == SCOPE["sdk_source"] and
            build.get("sdk_version") == SCOPE["sdk_version"],
            "SDK build provenance incomplete: " + host)
    program = file_record(root, binding["program"])
    require(digest(program) == manifest["programs"][host], "actual program bytes differ: " + host)
    fields = {"windows": "consumer_sha256", "gtk": "program_sha256",
              "macos": "executable_sha256", "iphone": "executable_sha256",
              "ipad": "executable_sha256"}
    if host == "android":
        driver = read(file_record(root, binding["installed_apk_receipt"]))
        same_identity(driver, stamp)
        require(driver.get("mode") == "retained" and driver.get("native_lifecycle_passed") is True and
                driver.get("apk_sha256", {}).get("host_apk") == digest(program),
                "actual retained installed APK differs")
        # The original checker validates its native/UI/XML/recovery cases and all-exits.
        require(report.get("native_checks") == 8 and report.get("real_ui_checks") == 8 and
                report.get("real_process_retry_checks") == 1 and
                report.get("original_owner_checks") == 17 and
                report.get("original_typed_kill_checks") == 2 and
                report.get("original_functional_checks") == 112 and
                report.get("original_gate_checks") == 87 and
                report.get("original_owner_altered_evidence_checks") == 19,
                "original Android all-exits coverage incomplete")
    else:
        require(report.get(fields[host]) == digest(program), "retained native executable differs: " + host)
    # Archive member identity must be established by the Actions extraction admission,
    # not by adding nonexistent fields to the preserved original report.
    members = read(file_record(root, binding["archive_members"]))
    same_identity(members, stamp)
    require(members.get("archive_sha256") == digest(archive) and
            members.get("artifact_id") == artifact.get("id") and
            members.get("producer_job_id") == job.get("id"),
            "artifact member admission provenance differs")
    for role, record in (("retained-report", manifest["retained"][host]),
                         ("build-identity", binding["build"]), ("program", binding["program"])):
        archive_member = record.get("archive_member")
        require(isinstance(archive_member, str) and archive_member and
                not archive_member.startswith("/") and "\\" not in archive_member and
                ":" not in archive_member and ".." not in archive_member.split("/"), "artifact member path invalid")
        matches = [m for m in members.get("members", []) if m.get("path") == archive_member]
        require(len(matches) == 1 and matches[0].get("role") == role and
                matches[0].get("sha256") == record["sha256"] and
                matches[0].get("bytes") == record["bytes"], "original artifact member missing/wrong role")

def audit(root, manifest, stamp):
    same_identity(manifest, stamp)
    require(manifest.get("sdk_version") == SCOPE["sdk_version"], "SDK version differs")
    require(manifest.get("producer_kind") == "actual-native-hosts", "not actual host producer")
    require(manifest.get("hosts") == SCOPE["hosts"], "missing or reordered host set")
    require(manifest.get("same_source") is True, "not one source")
    require(manifest.get("synthesized_revisions") is False, "synthetic revisions refused")
    require(manifest.get("retained_suites_complete") is True, "original suites not complete")
    # Historical red runs remain evidence; they do not fulfill current mandatory retained suites.
    for host in SCOPE["hosts"]:
        retained_binding(root, manifest, host, stamp)
    rounds = manifest["rounds"]
    require(rounds and all(r["author"] in SCOPE["hosts"] for r in rounds), "invalid author rounds")
    covered_operations = set()
    previous_wire = {}
    previous_wire_digest = None
    for round_number, round_record in enumerate(rounds):
        author = round_record["author"]
        operations = round_record["operations"]
        require(operations and set(operations).issubset(SCOPE["operations"]), "unknown lifecycle operation")
        covered_operations.update(operations)
        wire_path = file_record(root, round_record["wire"])
        wire = read(wire_path)
        restart_only = set(operations) == {"restart"}
        if restart_only:
            require(previous_wire_digest is not None and
                    round_record.get("previous_wire_sha256") == previous_wire_digest,
                    "restart lacks preceding authentic author wire")
        same_identity(wire, stamp)
        bodies = {}
        for key, record in wire["entries"].items():
            body = base64.b64decode(record["body"], validate=True)
            require(hashlib.sha256(body).hexdigest() == record["sha256"], "wire digest mismatch")
            bodies[key] = body
        require(all(bodies.get(k) == v for k, v in previous_wire.items()),
                "immutable wire history overwritten")
        previous_wire = bodies
        receipts = round_record["receipts"]
        require(set(receipts) == set(SCOPE["hosts"]), "six receivers required in each round")
        expected_projection = None
        required_revisions = set(round_record["revision_ids"])
        require(required_revisions, "no actual lifecycle revisions")
        wire_revisions = {}
        for key, body in bodies.items():
            if "/revisions/" not in key:
                continue
            value = json.loads(body)
            if isinstance(value, dict) and value.get("id") in required_revisions:
                require(value["id"] not in wire_revisions, "duplicate revision identity")
                wire_revisions[value["id"]] = value
        require(set(wire_revisions) == required_revisions, "missing authored wire revisions")
        operation_evidence = round_record["operation_evidence"]
        require(set(operation_evidence) == set(operations), "UI operations unproven")
        for operation, item in operation_evidence.items():
            raw = file_record(root, item)
            event = read(raw)
            same_identity(event, stamp)
            require(event.get("host") == author and event.get("operation") == operation and
                    event.get("passed") is True and event.get("native_ui") is True,
                    "missing native operation witness")
            require(event.get("program_sha256") == manifest["programs"][author], "wrong author program")
            require(set(event.get("revision_ids", [])).issubset(required_revisions),
                    "operation revision not on authentic wire")
            original = event.get("original_assertion_files", [])
            require(original, "native original assertion evidence missing")
            for original_file in original:
                file_record(root, original_file)
            # A new screenshot filename/role is NOT an original acceptance requirement.
            # Native original logs/results can evidence the operation without a new PNG.
        for host, record in receipts.items():
            receipt = read(file_record(root, record))
            same_identity(receipt, stamp)
            require(receipt.get("host") == host and receipt.get("sdk_version") == SCOPE["sdk_version"],
                    "receiver identity differs")
            require(receipt.get("program_sha256") == manifest["programs"][host], "receiver program differs")
            if not restart_only:
                require(receipt.get("native_sync_completed") is True, "receiver bypassed native sync")
            require(receipt.get("restart_verified") is True, "receiver persistence unverified")
            snapshot = receipt["snapshot"]
            require(hashlib.sha256(canonical(snapshot)).hexdigest() == receipt["snapshot_sha256"],
                    "snapshot digest mismatch")
            local = {r["id"]: r["body"] for r in snapshot["revisions"]}
            require(all(local.get(rid) == body for rid, body in wire_revisions.items()),
                    "receiver lacks exact wire revision bodies")
            actual = projection(snapshot, round_record["selected"])
            if expected_projection is None:
                expected_projection = actual
            require(actual == expected_projection, "cross-host organization diverges")
            requests = read(file_record(root, receipt["requests"]))
            require(isinstance(requests, list) and (restart_only or requests) and
                    all(r.get("authenticated") is True for r in requests),
                    "network authenticity absent")
            if not restart_only:
                method = "PUT" if host == author else "GET"
                require(any(r.get("method") == method and "/revisions/" in r.get("path", "")
                            for r in requests), "required native revision transport absent")
        previous_wire_digest = digest(wire_path)
    require(covered_operations == set(SCOPE["operations"]), "lifecycle coverage incomplete")
    require(SCOPE["complete"] is True and SCOPE["ci_authorized"] is True,
            "preparation_only: final acceptance disabled by current authorization")
    return {**stamp, "accepted": True, "preparation_only": False,
            "requirement": "F03", "sdk_version": SCOPE["sdk_version"],
            "hosts": SCOPE["hosts"], "author_rounds": len(rounds),
            "scope": "same-source six-host organization lifecycle consistency",
            "physical_device_accepted": False}


def collect_original_archives(root, stamp):
    """Fetch current-attempt API metadata and original ZIP bytes on Actions, never accept supplied metadata."""
    import os, urllib.request, urllib.parse, zipfile, io
    from datetime import datetime
    repository=os.environ["GITHUB_REPOSITORY"]
    require(repository=="NoGod3524/EXReader","wrong repository")
    token=os.environ["GITHUB_TOKEN"]
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            result=super().redirect_request(req,fp,code,msg,headers,newurl)
            if urllib.parse.urlsplit(newurl).netloc != "api.github.com":
                result.remove_header("Authorization")
            return result
    opener=urllib.request.build_opener(Redirect())
    def fetch(path):
        request=urllib.request.Request("https://api.github.com/repos/"+repository+path,
            headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
                     "X-GitHub-Api-Version":"2022-11-28"})
        with opener.open(request,timeout=180) as response:return response.read()
    run=json.loads(fetch("/actions/runs/"+stamp["run_id"]+"/attempts/"+stamp["attempt"]))
    require(run["head_sha"]==stamp["source_sha"] and str(run["run_attempt"])==stamp["attempt"],
            "current attempt API source mismatch")
    jobs=json.loads(fetch("/actions/runs/"+stamp["run_id"]+"/attempts/"+stamp["attempt"]+"/jobs?per_page=100"))
    artifacts=[]
    page=1
    while True:
        values=json.loads(fetch("/actions/runs/"+stamp["run_id"]+"/artifacts?per_page=100&page="+str(page)))
        artifacts+=values["artifacts"]
        if len(values["artifacts"])<100:break
        page+=1
    proof=root/"api-originals";proof.mkdir(parents=True,exist_ok=False)
    write_json(proof/"run.json",run);write_json(proof/"jobs.json",jobs)
    receipts={}
    for host in ("gtk","android"):
        name="reader-suite-f03-"+host+"-"+stamp["run_id"]+"-"+stamp["attempt"]
        matches=[a for a in artifacts if a["name"]==name]
        require(len(matches)==1,"missing/duplicate current-attempt artifact: "+host)
        artifact=matches[0]
        selected=[j for j in jobs["jobs"] if j["name"]==host]
        require(len(selected)==1 and selected[0]["conclusion"]=="success" and
                selected[0]["status"]=="completed" and selected[0]["head_sha"]==stamp["source_sha"],
                "producer job not successful: "+host)
        job=selected[0]
        require(job["started_at"]<=artifact["created_at"]<=job["completed_at"],
                "artifact outside producer job lifetime")
        require(not artifact.get("expired") and artifact["workflow_run"]["head_sha"]==stamp["source_sha"],
                "expired/different-source artifact")
        body=fetch("/actions/artifacts/"+str(artifact["id"])+"/zip")
        require(len(body)==artifact["size_in_bytes"] and
                "sha256:"+hashlib.sha256(body).hexdigest()==artifact["digest"],
                "original ZIP differs from API")
        (proof/(host+".zip")).write_bytes(body)
        write_json(proof/(host+"-artifact.json"),artifact)
        members={}
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            for entry in archive.infolist():
                if entry.is_dir():continue
                name=entry.filename
                require(name not in members and not name.startswith("/") and "\\" not in name and
                        ":" not in name and ".." not in name.split("/"),"unsafe/duplicate ZIP member")
                raw=archive.read(entry)
                local=root/host/name
                require(not local.exists(),"refuse preexisting artifact member")
                local.parent.mkdir(parents=True,exist_ok=True)
                local.write_bytes(raw)
                require(local.stat().st_size==len(raw) and digest(local)==hashlib.sha256(raw).hexdigest(),
                        "extracted evidence differs from original ZIP")
                members[name]={"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
        receipts[host]={"artifact_id":artifact["id"],"job_id":job["id"],
            "archive_sha256":hashlib.sha256(body).hexdigest(),"members":members}
    write_json(proof/"admission.json",{**stamp,"api_fetched":True,"archives":receipts})
    return receipts

def partial_observations(root, stamp):
    """Audit the exact two-host candidate; never grants six-host F03 completion."""
    def checked(path):
        value=read(root/path);same_identity(value,stamp);return value
    builds={h:checked(Path(h)/("f03-"+h+"-build.json")) for h in ("gtk","android")}
    for host,report in builds.items():
        require(report["operation_completed"] is True and report["sdk_source"]==SCOPE["sdk_source"] and
                report["sdk_version"]==SCOPE["sdk_version"],"build identity/SDK mismatch")
    gtk=checked(Path("gtk/f03-retained-gtk/collections-ui.json"))
    require(gtk["accepted"] is True and gtk["count"]==27,"original GTK organization cases incomplete")
    apk=root/"android/android-host/artifacts/app-debug.apk"
    program=root/"gtk/package/EXReader-Linux/bin/exreader-linux"
    require(gtk["program_sha256"]==digest(program),"GTK original/actual program mismatch")
    android=checked(Path("android/organization-android/result.json"))
    require(android["accepted"] is True and not android["problems"] and
        android["native_checks"]==8 and android["real_ui_checks"]==8 and
        android["real_process_retry_checks"]==1 and android["original_owner_checks"]==17 and
        android["original_typed_kill_checks"]==2 and android["original_functional_checks"]==112 and
        android["original_gate_checks"]==87 and android["original_owner_altered_evidence_checks"]==19,
        "original Android all-exits incomplete")
    original=checked(Path("android/f03-android-original-steps.json"))
    require(original["accepted"] is True and original["steps"] and
            all(s["exit_code"]==0 for s in original["steps"]),"original Android gate execution failed")
    require(digest(root/"android/owner-android/apks/app-debug.apk")==digest(apk) and
            digest(root/"android/organization-android/apks/app-debug.apk")==digest(apk),
            "retained owner/organization APK mismatch")
    phases=["create","delete","restore","member-remove","member-restore","restart"]
    observations=[];previous={};previous_digest=None;coverage=set()
    for phase in phases:
        author_path=Path("gtk/f03-author")/phase
        receiver_path=Path("android/f03-android")/phase
        author=checked(author_path/"projection.json");receiver=checked(receiver_path/"projection.json")
        require(author["host"]=="gtk" and receiver["host"]=="android","host slot mismatch")
        require(author["program_sha256"]==digest(program) and receiver["program_sha256"]==digest(apk),
                "actual phase executable mismatch")
        for receipt in (author,receiver):
            require(receipt["sdk_version"]==SCOPE["sdk_version"] and receipt["restart_verified"] is True and
                    receipt["native_sync_completed"] is True,"native synchronization/restart missing")
            require(hashlib.sha256(canonical(receipt["snapshot"])).hexdigest()==receipt["snapshot_sha256"],
                    "snapshot digest mismatch")
        for table in TABLES:require(author["snapshot"][table]==receiver["snapshot"][table],
                                    "two-host organization differs: "+table)
        wire=checked(author_path/"wire/state.json")
        require(wire.get("previous_sha256")==previous_digest,"author wire lineage mismatch")
        bodies={}
        for key,value in wire["entries"].items():
            raw=base64.b64decode(value["body"],validate=True)
            require(hashlib.sha256(raw).hexdigest()==value["sha256"],"wire body digest mismatch")
            bodies[key]=raw
        require(all(bodies.get(k)==v for k,v in previous.items()),"immutable authored wire overwritten")
        expected={r["id"]:r["body"] for r in author["snapshot"]["revisions"]}
        actual={r["id"]:r["body"] for r in receiver["snapshot"]["revisions"]}
        require(expected and all(actual.get(k)==v for k,v in expected.items()),"received revisions differ")
        wire_revisions={json.loads(v)["id"]:json.loads(v) for k,v in bodies.items() if "/revisions/" in k}
        require(all(wire_revisions.get(k)==v for k,v in expected.items()),"snapshot revision absent on real wire")
        for operation in wire["data"]["events"]:
            event=checked(author_path/(operation+".json"))
            require(event["operation"]==operation and event["passed"] is True and event["native_ui"] is True and
                    event["program_sha256"]==digest(program),"actual native operation missing")
            require(all(r in expected for r in event["revision_ids"]),"event revision absent from author")
            coverage.add(operation)
        for host,path,method in (("gtk",author_path,"PUT"),("android",receiver_path,"GET")):
            requests=read(root/path/"wire/requests.json")
            require(all(r["authenticated"] is True for r in requests),"unauthenticated wire evidence")
            if phase!="restart" or host=="android":
                require(any(r["method"]==method and "/revisions/" in r["path"] for r in requests),
                        "actual native revision transport missing")
        native=checked(receiver_path/"received/result.json")
        require(native["accepted"] is True and native["restart_verified"] is True and
                native["native_sync_completed"] is True,"Android UI receipt incomplete")
        driver=checked(receiver_path/"driver-result.json")
        require(driver["mode"]=="receive" and driver["native_lifecycle_passed"] is True and
                driver["apk_sha256"]["host_apk"]==digest(apk),"installed Android phase mismatch")
        # This exact read-only snapshot was taken from the stopped real app by adb run-as.
        from identity import read_snapshot
        require(read_snapshot(root/receiver_path/"native-catalog/reader-catalog.db")==receiver["snapshot"],
                "retained native database differs from projection receipt")
        previous=bodies;previous_digest=digest(root/author_path/"wire/state.json")
        observations.append({"phase":phase,"author_wire_sha256":previous_digest,
                             "projection_sha256":receiver["snapshot_sha256"]})
    require(coverage==set(SCOPE["operations"]),"lifecycle operation coverage incomplete")
    return {**stamp,"accepted":True,"acceptance_mode":"two-host-partial",
        "active_hosts":["gtk","android"],"phases":observations,"full_f03_accepted":False,
        "formal_count_credit":0,"not_run":["windows","macos","iphone","ipad","F04","F05"],
        "sdk_source":SCOPE["sdk_source"],"historical_owner_guard_reexecuted":False}

def partial(root, output, stamp):
    archives=collect_original_archives(root,stamp)
    result=partial_observations(root,stamp)
    result["original_archives"]={k:{x:y for x,y in v.items() if x!="members"} for k,v in archives.items()}
    # Exact field counterexamples use separate copies, never rewrite original ZIP or producer files.
    import shutil, tempfile
    negatives=[]
    cases=[
        ("source", "android/f03-android/create/projection.json", ["source_sha"],"0"*40,"identity mismatch"),
        ("run", "android/f03-android/create/projection.json", ["run_id"],"0","identity mismatch"),
        ("attempt", "android/f03-android/create/projection.json", ["attempt"],"0","identity mismatch"),
        ("sdk", "android/f03-android/create/projection.json", ["sdk_version"],"0.0","native synchronization"),
        ("apk", "android/f03-android/create/projection.json", ["program_sha256"],"0"*64,"actual phase executable"),
        ("restart", "android/f03-android/create/projection.json", ["restart_verified"],False,"native synchronization"),
        ("old-gate", "android/organization-android/result.json", ["original_gate_checks"],86,"original Android all-exits"),
        ("original-failure", "gtk/f03-retained-gtk/collections-ui.json", ["accepted"],False,"original GTK"),
        ("host", "android/f03-android/create/projection.json", ["host"],"gtk","host slot"),
    ]
    for name,path,keys,value,reason in cases:
        with tempfile.TemporaryDirectory(prefix="f03-audit-negative-",dir=root.parent) as tmp:
            copy=Path(tmp)/"evidence"
            # Link originals read-only for efficiency; replace only the changed JSON inode.
            shutil.copytree(root,copy,copy_function=__import__("os").link,
                            ignore=shutil.ignore_patterns("api-originals"))
            target=copy/path;raw=target.read_bytes();data=json.loads(raw);cursor=data
            for key in keys[:-1]:cursor=cursor[key]
            cursor[keys[-1]]=value
            target.unlink();target.write_bytes(canonical(data))
            try:
                partial_observations(copy,stamp)
            except (AssertionError,KeyError,ValueError) as error:
                require(reason in str(error),"negative rejected for wrong reason: "+name)
                negatives.append({"name":name,"expected_reason":reason,"actual_reason":str(error),
                    "original_sha256":hashlib.sha256(raw).hexdigest(),"altered_sha256":digest(target),"rejected":True})
            else:raise AssertionError("counterexample wrongly accepted: "+name)
    from identity import check_candidate_fields
    admission_cases=[
        ("sdk-as-product",SCOPE["sdk_source"],SCOPE["sdk_source"],[],False,"product baseline mismatch"),
        ("wrong-sdk",SCOPE["baseline"],"0"*40,[],False,"SDK freeze mismatch"),
        ("false-old-owner",SCOPE["baseline"],SCOPE["sdk_source"],[],True,"historical owner guard"),
        ("product-edit",SCOPE["baseline"],SCOPE["sdk_source"],["examples/android/app/build.gradle"],False,"outside authorized"),
        ("old-test-edit",SCOPE["baseline"],SCOPE["sdk_source"],["tools/check_reader_owner_android.py"],False,"outside authorized"),
    ]
    for name,base,sdk,paths,historical,reason in admission_cases:
        try:check_candidate_fields(base,sdk,paths,historical)
        except AssertionError as error:
            require(reason in str(error),"admission negative wrong reason")
            negatives.append({"name":name,"expected_reason":reason,"actual_reason":str(error),"rejected":True})
        else:raise AssertionError("admission negative accepted: "+name)
    result["audit_negatives"]=negatives
    write_json(output,result)


def diagnose_original(output, stamp):
    """Read the single approved failed artifact; never rerun or accept product checks."""
    import os, urllib.request, urllib.parse, zipfile, io, stat
    run_id, attempt, job_id = 41258793317, 1, 124707556530
    artifact_id, expected_size = 13064700805, 22383312
    source = "211615ebea4985405c8dfa2f5c70fad0e2d2ad11"
    expected_digest = "6fd133347aa6b4fc9c4138c0b94a5c76bb909eecd87b38530d2281fef362da62"
    expected_png = "6db331a569b7048cc4f900d72047771c1f975f34feb28d6b2579e68079b2f1cb"
    require(os.environ.get("GITHUB_ACTIONS") == "true", "diagnostic Actions only")
    require(os.environ["GITHUB_REPOSITORY"] == "NoGod3524/EXReader", "wrong repository")
    folder = output.parent / "original-round2"
    folder.mkdir(parents=True, exist_ok=False)
    result = {**stamp, "diagnostic_only": True, "product_reexecuted": False,
              "accepted": False, "full_F03_accepted": False,
              "original_run": run_id, "original_attempt": attempt, "original_source": source,
              "original_job": job_id, "original_artifact": artifact_id, "problems": []}
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            value = super().redirect_request(req, fp, code, msg, headers, newurl)
            if value is not None and urllib.parse.urlsplit(newurl).netloc != "api.github.com":
                value.remove_header("Authorization")
            return value
    opener = urllib.request.build_opener(Redirect())
    def fetch(path, limit=2*1024*1024):
        request = urllib.request.Request("https://api.github.com/repos/NoGod3524/EXReader"+path,
            headers={"Authorization": "Bearer "+os.environ["GITHUB_TOKEN"],
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with opener.open(request, timeout=120) as response:
            value = response.read(limit+1)
        require(len(value) <= limit, "diagnostic response exceeds fixed bound")
        return value
    try:
        run = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}"))
        jobs = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"))
        artifact = json.loads(fetch(f"/actions/artifacts/{artifact_id}"))
        for name, value in (("run.json", run), ("jobs.json", jobs), ("artifact.json", artifact)):
            write_json(folder/name, value)
        require(run["head_sha"] == source and run["run_attempt"] == attempt and
                run["status"] == "completed" and run["conclusion"] == "failure",
                "fixed failed run identity differs")
        matches = [j for j in jobs["jobs"] if j["id"] == job_id]
        require(len(matches) == 1, "fixed job missing")
        job = matches[0]
        require(job["name"] == "gtk" and job["head_sha"] == source and
                job["status"] == "completed" and job["conclusion"] == "failure",
                "fixed failed GTK job differs")
        require(artifact["id"] == artifact_id and
                artifact["name"] == f"reader-suite-f03-gtk-{run_id}-{attempt}" and
                artifact["size_in_bytes"] == expected_size and
                artifact["digest"] == "sha256:"+expected_digest and not artifact["expired"] and
                artifact["workflow_run"]["id"] == run_id and
                artifact["workflow_run"]["head_sha"] == source and
                job["started_at"] <= artifact["created_at"] <= job["completed_at"],
                "fixed original artifact metadata differs")
        body = fetch(f"/actions/artifacts/{artifact_id}/zip", expected_size)
        require(len(body) == expected_size and hashlib.sha256(body).hexdigest() == expected_digest,
                "fixed original ZIP digest/size differs")
        (folder/"original.zip").write_bytes(body)
        wanted = {"application.log", "window-tree.txt", "state.ini", "collections-ui.json",
                  "f03-retained-openbox.log", "failure-native-desktop.png"}
        found, inventory = {}, {}
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            require(len(entries) <= 1000 and sum(x.file_size for x in entries) <= 1024**3,
                    "original ZIP expansion exceeds diagnostic bound")
            for entry in entries:
                name = entry.filename
                require(name not in inventory and not name.startswith("/") and
                        "\\" not in name and ":" not in name and ".." not in name.split("/") and
                        not stat.S_ISLNK(entry.external_attr >> 16),
                        "unsafe/duplicate original ZIP member")
                inventory[name] = {"bytes": entry.file_size, "compressed_bytes": entry.compress_size}
                if entry.is_dir() or Path(name).name not in wanted:
                    continue
                require(entry.file_size <= 8*1024*1024, "selected evidence too large")
                raw = archive.read(entry)
                destination = folder/"selected"/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                record = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                found.setdefault(Path(name).name, []).append(record)
                if name.endswith(".png"):
                    require(raw.startswith(b"\x89PNG\r\n\x1a\n") and
                            record["sha256"] == expected_png, "fixed failure screenshot differs")
                    print("F03_DIAGNOSTIC_PNG_BASE64_BEGIN", flush=True)
                    print(base64.b64encode(raw).decode("ascii"), flush=True)
                    print("F03_DIAGNOSTIC_PNG_BASE64_END", flush=True)
                else:
                    require(len(raw) <= 512*1024, "selected text exceeds diagnostic print bound")
                    print("F03_ORIGINAL_TEXT_BEGIN "+name, flush=True)
                    print(raw.decode("utf-8", errors="replace"), flush=True)
                    print("F03_ORIGINAL_TEXT_END "+name, flush=True)
        require(all(len(found.get(name, [])) == 1 for name in
                    ("application.log", "collections-ui.json", "failure-native-desktop.png")),
                "required fixed diagnostic evidence absent or ambiguous")
        report_path = folder/"selected"/found["collections-ui.json"][0]["path"]
        report = read(report_path)
        require(report["source_sha"] == source and str(report["run_id"]) == str(run_id) and
                str(report["attempt"]) == str(attempt) and report["accepted"] is False and
                report["count"] == 0, "original failure report differs")
        result.update(original_zip_verified=True, selected=found,
                      missing=sorted(wanted-set(found)), original_inventory=inventory,
                      diagnostic_extraction_completed=True)
        print(json.dumps({k:v for k,v in result.items() if k!="original_inventory"}), flush=True)
    except BaseException as error:
        result["problems"].append(type(error).__name__+": "+str(error))
        raise
    finally:
        write_json(output, result)


def diagnose_gtk_ready_original(output, stamp):
    """Read the single approved failed artifact; never rerun or accept product checks."""
    import os, urllib.request, urllib.parse, zipfile, io, stat
    run_id, attempt, job_id = 41311869249, 1, 124863751211
    artifact_id, expected_size = 13086111887, 22830839
    source = "e84c4c5db2b242b61990cca9ee7917fa39fa43e9"
    expected_digest = "acbbe4e93421e927bf9661d2325c7fd4ef870d470281b53d5616ee8bbbc42e9b"
    require(os.environ.get("GITHUB_ACTIONS") == "true", "diagnostic Actions only")
    require(os.environ["GITHUB_REPOSITORY"] == "NoGod3524/EXReader", "wrong repository")
    folder = output.parent / "original-gtk-ready"
    folder.mkdir(parents=True, exist_ok=False)
    result = {**stamp, "diagnostic_only": True, "product_reexecuted": False,
              "accepted": False, "full_F03_accepted": False,
              "original_run": run_id, "original_attempt": attempt, "original_source": source,
              "original_job": job_id, "original_artifact": artifact_id, "problems": []}
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            value = super().redirect_request(req, fp, code, msg, headers, newurl)
            if value is not None and urllib.parse.urlsplit(newurl).netloc != "api.github.com":
                value.remove_header("Authorization")
            return value
    opener = urllib.request.build_opener(Redirect())
    def fetch(path, limit=2*1024*1024):
        request = urllib.request.Request("https://api.github.com/repos/NoGod3524/EXReader"+path,
            headers={"Authorization": "Bearer "+os.environ["GITHUB_TOKEN"],
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with opener.open(request, timeout=120) as response:
            value = response.read(limit+1)
        require(len(value) <= limit, "diagnostic response exceeds fixed bound")
        return value
    try:
        run = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}"))
        jobs = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"))
        artifact = json.loads(fetch(f"/actions/artifacts/{artifact_id}"))
        for name, value in (("run.json", run), ("jobs.json", jobs), ("artifact.json", artifact)):
            write_json(folder/name, value)
        require(run["id"] == run_id and run["head_sha"] == source and run["run_attempt"] == attempt and
                run["status"] == "completed" and run["conclusion"] == "failure",
                "fixed failed readiness run identity differs")
        matches = [j for j in jobs["jobs"] if j["id"] == job_id]
        require(len(matches) == 1, "fixed readiness job missing")
        job = matches[0]
        require(job["name"] == "f03_gtk_ready_diagnostic" and job["head_sha"] == source and
                job["run_id"] == run_id and job["run_attempt"] == attempt and
                job["status"] == "completed" and job["conclusion"] == "failure",
                "fixed failed readiness GTK job differs")
        require(artifact["id"] == artifact_id and
                artifact["name"] == f"reader-suite-f03-gtk-ready-diagnostic-{run_id}-{attempt}" and
                artifact["size_in_bytes"] == expected_size and
                artifact["digest"] == "sha256:"+expected_digest and not artifact["expired"] and
                artifact["workflow_run"]["id"] == run_id and
                artifact["workflow_run"]["head_sha"] == source and
                job["started_at"] <= artifact["created_at"] <= job["completed_at"],
                "fixed readiness artifact metadata differs")
        body = fetch(f"/actions/artifacts/{artifact_id}/zip", expected_size)
        require(len(body) == expected_size and hashlib.sha256(body).hexdigest() == expected_digest,
                "fixed readiness ZIP digest/size differs")
        (folder/"original.zip").write_bytes(body)
        wanted = {"collections-ui.json"}
        for prefix in ("f03-retained", "f03-author"):
            wanted.update(prefix+suffix for suffix in (
                "-openbox.log", "-window-tree-before.txt", "-window-tree-exit.txt",
                "-root-properties-exit.txt", "-wm-observations.txt", "-window-samples.txt"))
        found, inventory, refused_selected = {}, {}, {}
        printed = 0
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            require(len(entries) <= 1000 and sum(x.file_size for x in entries) <= 1024**3,
                    "readiness ZIP expansion exceeds fixed bound")
            for entry in entries:
                name = entry.filename
                require(name not in inventory and name and not name.startswith("/") and
                        "\\" not in name and ":" not in name and
                        not any(x in ("", ".", "..") for x in name.rstrip("/").split("/")) and
                        not entry.flag_bits & 1,
                        "unsafe/duplicate/encrypted readiness ZIP member")
                mode = stat.S_IFMT(entry.external_attr >> 16)
                inventory[name] = {"bytes": entry.file_size, "compressed_bytes": entry.compress_size,
                                   "unix_file_type": mode, "symlink": stat.S_ISLNK(entry.external_attr >> 16)}
                if entry.is_dir() or Path(name).name not in wanted:
                    continue
                if mode not in (0, stat.S_IFREG):
                    refused_selected[name] = "selected member is not a regular file; never followed"
                    continue
                require(entry.file_size <= 1024*1024, "selected readiness evidence too large")
                raw = archive.read(entry)
                printed += len(raw)
                require(printed <= 3*1024*1024, "total readiness text exceeds print bound")
                destination = folder/"selected"/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                record = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                found.setdefault(Path(name).name, []).append(record)
                print("F03_GTK_READY_ORIGINAL_TEXT_BEGIN "+name, flush=True)
                print(raw.decode("utf-8", errors="replace"), flush=True)
                print("F03_GTK_READY_ORIGINAL_TEXT_END "+name, flush=True)
        require(all(len(items) == 1 for items in found.values()), "selected readiness name ambiguous")
        require(len(found.get("collections-ui.json", [])) == 1, "original retained report absent")
        item = found["collections-ui.json"][0]
        require(item["sha256"] == "e251716ee24b70c87842713b1b510e8bcf0ac186539944b191b9ed7030a351e1",
                "original 27-check report bytes differ")
        report = read(folder/"selected"/item["path"])
        require(report["source_sha"] == source and str(report["run_id"]) == str(run_id) and
                str(report["attempt"]) == str(attempt) and report["accepted"] is True and
                report["count"] == 27 and report["program_sha256"] ==
                "d0a5032dbc8af40ce1a0cba276f2c27a1a2807667c5f2bb7327fdb6be90a6846",
                "original retained report identity/count differs")
        profile_expected = ("f03-author-profile/application.log", "f03-author-profile/state.ini")
        profile_presence = {p: [n for n in inventory if n == p or n.endswith("/"+p)]
                            for p in profile_expected}
        result.update(original_zip_verified=True, selected=found,
                      missing_selected=sorted(wanted-set(found)), refused_selected=refused_selected,
                      author_profile_presence=profile_presence,
                      missing_author_profile=sorted(p for p, names in profile_presence.items() if not names),
                      original_inventory=inventory, diagnostic_extraction_completed=True)
        print(json.dumps({k:v for k,v in result.items() if k!="original_inventory"}), flush=True)
    except BaseException as error:
        result["problems"].append(type(error).__name__+": "+str(error))
        raise
    finally:
        write_json(output, result)



def diagnose_owner_original(output):
    """Authenticate and inspect one fixed archive; never execute or accept its products."""
    import os, re, subprocess, urllib.request, urllib.parse, zipfile, io, stat
    from identity import ROOT
    import xml.etree.ElementTree as ET
    base = "99d1b754690fec199f41de2f0edb7070558b285a"
    branch = "refs/heads/dot/f03-owner-artifact-20261101"
    require(os.environ.get("GITHUB_ACTIONS") == "true" and
            os.environ.get("GITHUB_REPOSITORY") == "NoGod3524/EXReader" and
            os.environ.get("GITHUB_REF") == branch and
            os.environ.get("F03_OWNER_ARTIFACT_CASE") == "f03/owner-fixed-artifact",
            "fixed owner diagnostic controller route differs")
    stamp = {key: os.environ[env] for key, env in (
        ("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}
    require(re.fullmatch(r"[0-9a-f]{40}", stamp["source_sha"]) and
            stamp["run_id"].isdigit() and stamp["attempt"] == "1", "controller identity malformed")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() ==
            stamp["source_sha"], "controller checkout differs")
    subprocess.run(["git", "merge-base", "--is-ancestor", base, stamp["source_sha"]], cwd=ROOT, check=True)
    paths = set(subprocess.check_output(["git", "diff", "--name-only", base, stamp["source_sha"]],
                                      cwd=ROOT, text=True).splitlines())
    require(paths == {
        "tests/dot_f03_same_source_20261031/verify.py",
        ".github/workflows/dot-f03-same-source-20261031.yml",
        "tests/dot_f03_same_source_20261031/scope.json",
        "docs/reader-total-progress/DOT_F03_SAME_SOURCE_20261031.md"},
        "controller changed outside four approved paths")
    run_id, attempt, job_id = 41328199296, 1, 124912497495
    source = "e21331513a84cc225daa99f672b4c79384e1f34b"
    artifact_id, expected_size = 13093186163, 193531993
    expected_digest = "e8b2d81a33a62a6d47c718bfdea2e49d5075b9eb8de27048eaf3023b33f8f17f"
    expected_identity = {"source_sha": source, "run_id": str(run_id), "attempt": str(attempt)}
    names = {
        "actualInstalledProviderAndJson", "persistedNativeCreateIds", "strictUtf16AndEmoji",
        "staleObservedHeadsAreAtomic", "explicitDeleteAndRestore", "metadataFailureRollsBackAndRetries",
        "outboxFailureRollsBackAndRetries", "membershipNeedsExplicitBookBootstrap",
        "publicSdkBootstrapKeepsCurrentProductTitle", "shelfAndSeriesMembershipOrder",
        "missingAndDeletedDependenciesRefused", "mapFailureKeepsSdkAndCommittedBookCommand",
        "nativeRejectsWrongOwner", "nativeRejectsClosedHandle", "twoNativeOwnersCompeteOnOneObservedHead",
        "sdkDatabaseRefusedWithoutModification", "opensClosedLegacySystemCatalog",
        "finalizeImportAutomaticallyBootstrapsOnce"}
    wanted = {"source.txt", "device-api.txt", "device-abi.txt", "device-report.json",
              "owner-instrumentation.txt", "result.json"}
    wanted.update(prefix+"-"+phase+".txt" for prefix in ("seed", "recover", "witness")
                  for phase in ("before", "after"))
    result = {"controller": stamp, "controller_base": base, "diagnostic_only": True,
              "product_reexecuted": False, "accepted": False, "full_F03_accepted": False,
              "provider_fully_authenticated": False, "formal_count_credit": 0,
              "original": {**expected_identity, "job_id": job_id, "artifact_id": artifact_id},
              "problems": [], "missing": [], "invalid": [], "selected": {}, "observations": {}}
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            value = super().redirect_request(req, fp, code, msg, headers, newurl)
            if value is not None and urllib.parse.urlsplit(newurl).netloc != "api.github.com":
                value.remove_header("Authorization")
            return value
    opener = urllib.request.build_opener(Redirect())
    def fetch(path, limit=2*1024*1024):
        request = urllib.request.Request("https://api.github.com/repos/NoGod3524/EXReader"+path,
            headers={"Authorization": "Bearer "+os.environ["GITHUB_TOKEN"],
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with opener.open(request, timeout=120) as response:
            raw = response.read(limit+1)
        require(len(raw) <= limit, "fixed diagnostic response too large")
        return raw
    def observe(key, value):
        result["observations"][key] = bool(value)
        if not value: result["invalid"].append(key)
    try:
        run = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}"))
        jobs = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"))
        artifact = json.loads(fetch(f"/actions/artifacts/{artifact_id}"))
        require(run["id"] == run_id and run["head_sha"] == source and run["run_attempt"] == attempt and
                run["status"] == "completed" and run["conclusion"] == "failure", "fixed failed run differs")
        matches = [j for j in jobs["jobs"] if j["id"] == job_id]
        require(len(matches) == 1, "fixed job missing")
        job = matches[0]
        require(job["name"] == "f03_android_importmapping_retained" and job["head_sha"] == source and
                job["run_id"] == run_id and job["run_attempt"] == attempt and
                job["status"] == "completed" and job["conclusion"] == "failure", "fixed failed job differs")
        require(artifact["id"] == artifact_id and artifact["name"] ==
                f"reader-suite-f03-android-importmapping-{run_id}-{attempt}" and
                artifact["size_in_bytes"] == expected_size and not artifact["expired"] and
                artifact["digest"] == "sha256:"+expected_digest and
                artifact["workflow_run"]["id"] == run_id and
                artifact["workflow_run"]["head_sha"] == source and
                job["started_at"] <= artifact["created_at"] <= job["completed_at"],
                "fixed artifact metadata differs")
        body = fetch(f"/actions/artifacts/{artifact_id}/zip", expected_size)
        require(len(body) == expected_size and hashlib.sha256(body).hexdigest() == expected_digest,
                "fixed archive digest/size differs")
        selected, inventory, total_selected = {}, set(), 0
        organization_present = False
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            require(len(entries) <= 20000 and sum(e.file_size for e in entries) <= 2*1024**3,
                    "archive expansion exceeds diagnostic bound")
            for entry in entries:
                name = entry.filename
                parts = name.rstrip("/").split("/")
                require(name and name not in inventory and not name.startswith("/") and
                        "\\" not in name and ":" not in name and
                        not any(x in ("", ".", "..") for x in parts) and not entry.flag_bits & 1,
                        "unsafe duplicate encrypted archive member")
                inventory.add(name)
                if parts[-2:] == ["organization-android", "device-report.json"]: organization_present = True
                logical = None
                if "owner-android" in parts:
                    index = parts.index("owner-android")
                    tail = "/".join(parts[index+1:])
                    if tail in wanted or tail.startswith("owner-reports/") and tail.endswith(".xml"):
                        logical = "owner/"+tail
                elif parts[-1] == "f03-android-original-steps.json":
                    logical = "original-steps"
                if logical is None or entry.is_dir(): continue
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if mode not in (0, stat.S_IFREG):
                    result["invalid"].append("nonregular:"+logical); continue
                require(logical not in selected and entry.file_size <= 2*1024*1024,
                        "ambiguous or oversized selected evidence")
                raw = archive.read(entry); total_selected += len(raw)
                require(total_selected <= 16*1024*1024, "selected text exceeds diagnostic bound")
                selected[logical] = raw
                result["selected"][logical] = {"path": name, "bytes": len(raw),
                                               "sha256": hashlib.sha256(raw).hexdigest()}
        result["archive_verified"] = True
        result["inventory_member_count"] = len(inventory)
        result["organization_device_report_present"] = organization_present
        result["missing"] = sorted("owner/"+x for x in wanted if "owner/"+x not in selected)
        def text(key): return selected[key].decode("utf-8")
        def parsed(key):
            try: return json.loads(text(key))
            except (ValueError, UnicodeError):
                result["invalid"].append("json:"+key); return None
        for label, expected in (("source.txt", source), ("device-api.txt", "34"), ("device-abi.txt", "x86_64")):
            key = "owner/"+label
            if key in selected: observe(label, text(key).strip() == expected)
        key = "owner/device-report.json"
        if key in selected:
            device = parsed(key)
            if isinstance(device, dict):
                observe("device_identity", all(device.get(k) == v for k,v in expected_identity.items()))
                observe("device_api_abi", device.get("api") == 34 and device.get("abi") == "x86_64")
                checks = device.get("checks", [])
                ids = [x.get("id") for x in checks if isinstance(x, dict)] if isinstance(checks, list) else []
                observe("device_18_checks", device.get("count") == 18 and device.get("failed") == 0 and
                        isinstance(checks, list) and len(checks) == len(ids) == 18 and set(ids) == names and
                        all(x.get("pass") is True for x in checks))
                result["device"] = {"api": device.get("api") if type(device.get("api")) is int else "invalid",
                                    "abi": device.get("abi") if device.get("abi") == "x86_64" else "unexpected",
                                    "count": device.get("count") if type(device.get("count")) is int else "invalid",
                                    "failed": device.get("failed") if type(device.get("failed")) is int else "invalid",
                                    "known_checks": [{"id": x["id"], "pass": x.get("pass") is True}
                                     for x in checks if isinstance(x, dict) and x.get("id") in names]
                                     if isinstance(checks, list) else [],
                                    "unexpected_check_count": len([x for x in ids if x not in names])}
        key = "owner/owner-instrumentation.txt"
        if key in selected:
            raw = text(key); status = {}; completed = []; bad = []; safe = []
            for line in raw.splitlines():
                if line.startswith("INSTRUMENTATION_STATUS: "):
                    k,_,v = line[len("INSTRUMENTATION_STATUS: "):].partition("=")
                    if k in ("class", "test", "numtests", "current"): status[k] = v
                elif line.startswith("INSTRUMENTATION_STATUS_CODE: "):
                    try: code = int(line.split(":",1)[1])
                    except ValueError: code = None
                    if code not in (0,1): bad.append("failure_or_skip")
                    if code == 0:
                        valid = (status.get("class") == "org.exreader.host.ProductOwnerTest" and
                                 status.get("numtests") == "18" and status.get("test") in names)
                        if not valid: bad.append("status_identity")
                        completed.append(status.get("test"))
                        safe.append({"test":status.get("test") if status.get("test") in names else "unexpected",
                                     "status_code":code,"identity_valid":valid})
                    status = {}
            observe("manual_18", len(completed) == 18 and set(completed) == names and not bad and
                    re.search(r"^INSTRUMENTATION_CODE: -1\s*$", raw, re.M) and "OK (18 tests)" in raw and
                    "FAILURES" not in raw)
            result["manual_protocol"] = safe
            ending = re.findall(r"^INSTRUMENTATION_CODE: (-?[0-9]+)\s*$", raw, re.M)
            result["manual_summary"] = {"completion_count": len(completed),
                "ending_codes": [int(x) for x in ending], "ok_18_present": "OK (18 tests)" in raw,
                "failures_marker_present": "FAILURES" in raw,
                "failure_or_skip_status_count": bad.count("failure_or_skip"),
                "invalid_status_identity_count": bad.count("status_identity")}
        xml_names = []; xml_bad = []; xml_files = []
        for key in sorted(selected):
            if key.startswith("owner/owner-reports/") and key.endswith(".xml"):
                xml_files.append(key)
                try:
                    raw = selected[key]
                    require(b"<!DOCTYPE" not in raw and b"<!ENTITY" not in raw, "XML declarations forbidden")
                    tree = ET.fromstring(raw)
                    for suite in tree.iter("testsuite"):
                        if any(int(suite.get(k,"0")) for k in ("failures","errors","skipped")): xml_bad.append("suite")
                    for case in tree.iter("testcase"):
                        if case.get("classname") != "org.exreader.host.ProductOwnerTest" or any(
                                case.find(k) is not None for k in ("failure","error","skipped")): xml_bad.append("case")
                        xml_names.append(case.get("name"))
                except (ValueError, ET.ParseError, AssertionError): xml_bad.append("invalid_xml")
        if not xml_files: result["missing"].append("owner/owner-reports/*.xml")
        observe("xml_18", bool(xml_files) and len(xml_names) == 18 and set(xml_names) == names and not xml_bad)
        result["xml_known_names"] = sorted(x for x in xml_names if x in names)
        for phase in ("before","after"):
            keys = ["owner/"+x+"-"+phase+".txt" for x in ("seed","recover","witness")]
            if all(k in selected for k in keys):
                seed, recovery, witness = [text(k) for k in keys]
                observe("kill_"+phase,
                        "INSTRUMENTATION_RESULT: shortMsg=Process crashed." in seed and
                        "EXR_OWNER_RECOVERED recover-"+phase in recovery and
                        re.search(r"^INSTRUMENTATION_CODE: -1\s*$", recovery, re.M) and
                        "EXR_OWNER_PHASE_FAILED" not in recovery and
                        witness == ("1,1,0" if phase == "before" else "1,1,1"))
        if "owner/result.json" in selected:
            old = parsed("owner/result.json")
            if isinstance(old, dict):
                observe("old_owner_gate_identity", all(old.get(k) == v for k,v in expected_identity.items()))
                observe("old_owner_rejection_retained", old.get("accepted") is False and
                        "owner device execution failed" in old.get("problems", []))
                result["old_owner_gate"] = {"accepted": old.get("accepted") is True,
                    "identity_matches": all(old.get(k) == v for k,v in expected_identity.items()),
                    "reported_owner_device_failure": "owner device execution failed" in old.get("problems",[]),
                    "problem_count": len(old.get("problems",[]))}
        if "original-steps" in selected:
            steps = parsed("original-steps")
            result["original_steps_shape"] = type(steps).__name__
            if isinstance(steps, dict):
                observe("original_steps_identity", all(steps.get(k) == v for k,v in expected_identity.items()))
                fixed_workflow = ".github/workflows/reader-organization-android.yml"
                workflow_hash = steps.get("original_workflow_sha256", "")
                observe("original_steps_workflow", steps.get("original_workflow") == fixed_workflow and
                        isinstance(workflow_hash, str) and re.fullmatch(r"[0-9a-f]{64}", workflow_hash))
                observe("original_steps_failure_retained", steps.get("accepted") is False and
                        steps.get("historical_owner_guard_reexecuted") is False)
                receipt_steps = steps.get("steps", [])
                valid_steps = isinstance(receipt_steps, list) and bool(receipt_steps) and all(
                    isinstance(x, dict) and type(x.get("exit_code")) is int and
                    isinstance(x.get("original_command_sha256"), str) and
                    re.fullmatch(r"[0-9a-f]{64}", x["original_command_sha256"]) for x in receipt_steps)
                observe("original_steps_records", valid_steps)
                result["original_steps"] = {"workflow": fixed_workflow if steps.get("original_workflow") == fixed_workflow else "unexpected",
                    "workflow_sha256": workflow_hash if isinstance(workflow_hash, str) and re.fullmatch(r"[0-9a-f]{64}", workflow_hash) else "invalid",
                    "accepted": steps.get("accepted") is True,
                    "historical_owner_guard_reexecuted": steps.get("historical_owner_guard_reexecuted") is True,
                    "steps": [{"index":index, "exit_code":item["exit_code"],
                               "command_sha256":item["original_command_sha256"]}
                              for index,item in enumerate(receipt_steps)] if valid_steps else []}
        else: result["missing"].append("f03-android-original-steps.json")
        result["diagnostic_completed"] = True
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as error:
        result["problems"].append(type(error).__name__)
        raise
    finally:
        write_json(output, result)


def diagnose_owner_core(output):
    """Authenticate and inspect one fixed archive; never execute or accept its products."""
    import os, re, subprocess, urllib.request, urllib.parse, zipfile, io, stat
    from identity import ROOT
    import xml.etree.ElementTree as ET
    base = "21ffb3ef36a2daedf20b7a2ca4d0b78cadfad932"
    branch = "refs/heads/dot/f03-owner-core-20261101"
    require(os.environ.get("GITHUB_ACTIONS") == "true" and
            os.environ.get("GITHUB_REPOSITORY") == "NoGod3524/EXReader" and
            os.environ.get("GITHUB_REF") == branch and
            os.environ.get("F03_OWNER_CORE_CASE") == "f03/owner-core-original",
            "fixed owner diagnostic controller route differs")
    stamp = {key: os.environ[env] for key, env in (
        ("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}
    require(re.fullmatch(r"[0-9a-f]{40}", stamp["source_sha"]) and
            stamp["run_id"].isdigit() and stamp["attempt"] == "1", "controller identity malformed")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() ==
            stamp["source_sha"], "controller checkout differs")
    subprocess.run(["git", "merge-base", "--is-ancestor", base, stamp["source_sha"]], cwd=ROOT, check=True)
    paths = set(subprocess.check_output(["git", "diff", "--name-only", base, stamp["source_sha"]],
                                      cwd=ROOT, text=True).splitlines())
    require(paths == {
        "tools/check_reader_owner_android.py",
        "tests/dot_f03_same_source_20261031/verify.py",
        ".github/workflows/dot-f03-same-source-20261031.yml",
        "tests/dot_f03_same_source_20261031/scope.json",
        "docs/reader-total-progress/DOT_F03_SAME_SOURCE_20261031.md"},
        "controller changed outside five approved paths")
    run_id, attempt, job_id = 41328199296, 1, 124912497495
    source = "e21331513a84cc225daa99f672b4c79384e1f34b"
    artifact_id, expected_size = 13093186163, 193531993
    expected_digest = "e8b2d81a33a62a6d47c718bfdea2e49d5075b9eb8de27048eaf3023b33f8f17f"
    expected_identity = {"source_sha": source, "run_id": str(run_id), "attempt": str(attempt)}
    names = {
        "actualInstalledProviderAndJson", "persistedNativeCreateIds", "strictUtf16AndEmoji",
        "staleObservedHeadsAreAtomic", "explicitDeleteAndRestore", "metadataFailureRollsBackAndRetries",
        "outboxFailureRollsBackAndRetries", "membershipNeedsExplicitBookBootstrap",
        "publicSdkBootstrapKeepsCurrentProductTitle", "shelfAndSeriesMembershipOrder",
        "missingAndDeletedDependenciesRefused", "mapFailureKeepsSdkAndCommittedBookCommand",
        "nativeRejectsWrongOwner", "nativeRejectsClosedHandle", "twoNativeOwnersCompeteOnOneObservedHead",
        "sdkDatabaseRefusedWithoutModification", "opensClosedLegacySystemCatalog",
        "finalizeImportAutomaticallyBootstrapsOnce"}
    wanted = {"source.txt", "device-api.txt", "device-abi.txt", "device-report.json",
              "owner-instrumentation.txt", "result.json"}
    wanted.update(prefix+"-"+phase+".txt" for prefix in ("seed", "recover", "witness")
                  for phase in ("before", "after"))
    result = {"controller": stamp, "controller_base": base, "diagnostic_only": True,
              "product_reexecuted": False, "accepted": False, "full_F03_accepted": False,
              "provider_fully_authenticated": False, "formal_count_credit": 0,
              "original": {**expected_identity, "job_id": job_id, "artifact_id": artifact_id},
              "problems": [], "missing": [], "invalid": [], "selected": {}, "observations": {}}
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            value = super().redirect_request(req, fp, code, msg, headers, newurl)
            if value is not None and urllib.parse.urlsplit(newurl).netloc != "api.github.com":
                value.remove_header("Authorization")
            return value
    opener = urllib.request.build_opener(Redirect())
    def fetch(path, limit=2*1024*1024):
        request = urllib.request.Request("https://api.github.com/repos/NoGod3524/EXReader"+path,
            headers={"Authorization": "Bearer "+os.environ["GITHUB_TOKEN"],
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with opener.open(request, timeout=120) as response:
            raw = response.read(limit+1)
        require(len(raw) <= limit, "fixed diagnostic response too large")
        return raw
    def observe(key, value):
        result["observations"][key] = bool(value)
        if not value: result["invalid"].append(key)
    try:
        run = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}"))
        jobs = json.loads(fetch(f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"))
        artifact = json.loads(fetch(f"/actions/artifacts/{artifact_id}"))
        require(run["id"] == run_id and run["head_sha"] == source and run["run_attempt"] == attempt and
                run["status"] == "completed" and run["conclusion"] == "failure", "fixed failed run differs")
        matches = [j for j in jobs["jobs"] if j["id"] == job_id]
        require(len(matches) == 1, "fixed job missing")
        job = matches[0]
        require(job["name"] == "f03_android_importmapping_retained" and job["head_sha"] == source and
                job["run_id"] == run_id and job["run_attempt"] == attempt and
                job["status"] == "completed" and job["conclusion"] == "failure", "fixed failed job differs")
        require(artifact["id"] == artifact_id and artifact["name"] ==
                f"reader-suite-f03-android-importmapping-{run_id}-{attempt}" and
                artifact["size_in_bytes"] == expected_size and not artifact["expired"] and
                artifact["digest"] == "sha256:"+expected_digest and
                artifact["workflow_run"]["id"] == run_id and
                artifact["workflow_run"]["head_sha"] == source and
                job["started_at"] <= artifact["created_at"] <= job["completed_at"],
                "fixed artifact metadata differs")
        body = fetch(f"/actions/artifacts/{artifact_id}/zip", expected_size)
        require(len(body) == expected_size and hashlib.sha256(body).hexdigest() == expected_digest,
                "fixed archive digest/size differs")

        import tempfile, importlib.util, sys
        allowed_owner = wanted | {"native/inventory.json","native/debug.map","native/debug.so",
            "native/debug.symbols.txt","native/debug.dynamic.txt","native/release.map","native/release.so",
            "native/release.symbols.txt","native/release.dynamic.txt","native/sqlite3.h",
            "apks/app-debug.apk","apks/app-debug-androidTest.apk"}
        extra = {"android-host/build.json","android-host/gate-review.json",
                 "android-host/bounded-gate-review.json","shelf-android/shelf-result.json",
                 "shelf-android/shelf-gate-review.json"}
        selected, inventory = {}, set()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries=archive.infolist()
            require(len(entries)<=20000 and sum(x.file_size for x in entries)<=2*1024**3,"archive expansion bound")
            for entry in entries:
                name=entry.filename;parts=name.rstrip("/").split("/")
                require(name and name not in inventory and not name.startswith("/") and "\\" not in name and
                        ":" not in name and not any(x in ("",".","..") for x in parts) and not entry.flag_bits&1,
                        "unsafe archive member")
                inventory.add(name);logical=None
                if "owner-android" in parts:
                    tail="/".join(parts[parts.index("owner-android")+1:])
                    if tail in allowed_owner or tail.startswith("owner-reports/") and tail.endswith(".xml"):
                        logical="build/owner-android/"+tail
                else:
                    for group in ("android-host","shelf-android"):
                        if group in parts:
                            tail="/".join(parts[parts.index(group):])
                            if tail in extra:logical="build/"+tail
                if logical is None or entry.is_dir():continue
                require(stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG),"selected member not regular")
                require(logical not in selected and entry.file_size<=256*1024**2,"selected bound or ambiguity")
                selected[logical]=archive.read(entry)
        require(sum(map(len,selected.values()))<=512*1024**2,"selected total bound")
        result["selected"]={k:{"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
                            for k,raw in sorted(selected.items())}
        required={"build/owner-android/"+x for x in allowed_owner} | {"build/"+x for x in extra}
        result["missing"]=sorted(required-set(selected))
        require(not result["missing"],"required fixed evidence missing")
        require(any(x.startswith("build/owner-android/owner-reports/") and x.endswith(".xml") for x in selected),
                "required XML missing")
        checker_path=ROOT/"tools/check_reader_owner_android.py"
        checker_text=checker_path.read_text()
        previous=subprocess.check_output(["git","show",base+":tools/check_reader_owner_android.py"],cwd=ROOT,text=True)
        restored=checker_text.replace("'opensClosedLegacySystemCatalog','finalizeImportAutomaticallyBootstrapsOnce'}",
                                      "'opensClosedLegacySystemCatalog'}").replace("OK (18 tests)","OK (17 tests)")
        require(restored==previous,"checker changed beyond two authorized edits")
        spec=importlib.util.spec_from_file_location("f03_fixed_owner_checker",checker_path)
        checker=importlib.util.module_from_spec(spec)
        saved_sys_path=list(sys.path)
        original_identity=None
        saved_cwd=Path.cwd()
        try:
            sys.path.insert(0,str(ROOT/"tools"));spec.loader.exec_module(checker)
            require(checker.NAMES==names,"core checker name set differs")
            original_identity=checker.identity
            checker.identity=lambda:dict(expected_identity)
            result["identity_binding"]="fixed producer injected into inspect only; controller environment unchanged"
            result["checker_sha256"]=hashlib.sha256(checker_path.read_bytes()).hexdigest()
            checks=[];result["checks"]=checks
            saved_cwd=Path.cwd()
            with tempfile.TemporaryDirectory(prefix="f03-owner-core-") as temporary:
                sandbox=Path(temporary)
                for logical,raw in selected.items():
                    dest=sandbox/logical;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
                root=sandbox/"build/owner-android"
                def invoke(name,expected):
                    actual=False;error_type=None
                    try:
                        value=checker.inspect(root,False)
                        actual=value.get("accepted") is True
                    except (ValueError,OSError,KeyError,TypeError,IndexError,ET.ParseError) as error:
                        error_type=type(error).__name__
                    passed=actual is expected
                    checks.append({"id":name,"expected_accepted":expected,"actual_accepted":actual,
                                   "passed":passed,"error_type":error_type})
                    require(passed,"core control differs: "+name)
                def alter(path,change,name):
                    raw=path.read_bytes();changed=change(raw)
                    require(changed!=raw,"mutation did not alter input: "+name)
                    try:path.write_bytes(changed);invoke(name,False)
                    finally:path.write_bytes(raw)
                def edit(path,name,change):
                    def replace(raw):
                        value=json.loads(raw);change(value);return json.dumps(value).encode()
                    alter(path,replace,name)
                try:
                    os.chdir(sandbox)
                    invoke("positive",True);device=root/"device-report.json"
                    edit(device,"old_device_source",lambda v:v.update(source_sha="0"*40))
                    edit(device,"missing_device_case",lambda v:v["checks"].pop())
                    edit(device,"duplicate_device_case",lambda v:v["checks"].append(v["checks"][0]))
                    edit(device,"failed_device_case",lambda v:v["checks"][0].update({"pass":False}))
                    edit(device,"wrong_native_runtime_provider",lambda v:v["provider"].__setitem__(3,"/system/lib64/libsqlite.so"))
                    edit(device,"wrong_actual_sqlite_source",lambda v:v["provider"].__setitem__(1,"wrong"))
                    edit(device,"missing_provider_option",lambda v:v["provider"].__setitem__(4,""))
                    alter(root/"owner-instrumentation.txt",lambda raw:raw.replace(b"INSTRUMENTATION_STATUS_CODE: 0",b"INSTRUMENTATION_STATUS_CODE: -3",1),"skipped_manual_owner_case")
                    alter(root/"apks/app-debug.apk",lambda raw:raw+b"altered APK","different_reinstalled_application")
                    xml=next((root/"owner-reports").rglob("*.xml"))
                    def skipped(raw):
                        tree=ET.fromstring(raw);ET.SubElement(next(tree.iter("testcase")),"skipped");return ET.tostring(tree)
                    alter(xml,skipped,"skipped_owner_xml")
                    alter(root/"native/release.symbols.txt",lambda raw:raw+b"0000 T Java_org_exreader_host_ProductFixture_injected\n","fixture_in_release")
                    alter(root/"native/debug.map",lambda raw:b"","missing_link_provider_proof")
                    alter(root/"witness-before.txt",lambda raw:b"0,0,0","wrong_three_write_crash_boundary")
                    alter(root/"recover-after.txt",lambda raw:b"","missing_successful_retry_after_kill")
                    alter(root/"seed-before.txt",lambda raw:b"OK","process_not_killed")
                    new_name="finalizeImportAutomaticallyBootstrapsOnce"
                    alter(root/"owner-instrumentation.txt",
                          lambda raw:raw.replace(("test="+new_name).encode(),b"test=missing_18th"),
                          "missing_18th_manual")
                    def remove_new(raw):
                        tree=ET.fromstring(raw)
                        for parent in tree.iter():
                            for child in list(parent):
                                if child.tag=="testcase" and child.get("name")==new_name:parent.remove(child)
                        return ET.tostring(tree)
                    matches=[p for p in (root/"owner-reports").rglob("*.xml") if new_name.encode() in p.read_bytes()]
                    require(len(matches)==1,"18th XML ambiguous")
                    alter(matches[0],remove_new,"missing_18th_xml")
                    invoke("restored_positive",True)
                    require(len(checks)==19 and all(x["passed"] for x in checks),"fixed 19 controls incomplete")
                    all_exits_accepted=False;all_exits_error=None;all_exits_reason=None
                    try:all_exits_accepted=checker.inspect(root,True).get("accepted") is True
                    except (ValueError,OSError,KeyError,TypeError,IndexError,ET.ParseError) as error:
                        all_exits_error=type(error).__name__
                        all_exits_reason="original shelf acceptance missing" if str(error)=="original shelf acceptance missing" else "unexpected_refusal"
                    result["old_all_exits"]={"expected_accepted":False,"actual_accepted":all_exits_accepted,
                                              "error_type":all_exits_error,"reason":all_exits_reason}
                    require(not all_exits_accepted and all_exits_error=="ValueError" and all_exits_reason=="original shelf acceptance missing","old all exits refusal differs")
                    result["core_controls_passed"]=True
                    result["historical_core_provider_authenticated"]=True
                    result["diagnostic_completed"]=True
                finally:
                    os.chdir(saved_cwd)
        finally:
            os.chdir(saved_cwd)
            if original_identity is not None:checker.identity=original_identity
            sys.path[:]=saved_sys_path
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException as error:
        result["problems"].append(type(error).__name__)
        raise
    finally:
        write_json(output,result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    p.add_argument("--partial", action="store_true")
    p.add_argument("--diagnose-original", action="store_true")
    p.add_argument("--diagnose-owner-original", action="store_true")
    p.add_argument("--diagnose-owner-core", action="store_true")
    p.add_argument("--diagnose-gtk-ready-original", action="store_true")
    p.add_argument("--evidence", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.diagnose_owner_core:
        require(not a.diagnose_owner_original and not a.diagnose_original and not a.diagnose_gtk_ready_original and not a.partial and a.manifest is None and a.evidence is None, "core diagnostic cannot mix audits")
        diagnose_owner_core(a.output)
        return
    if a.diagnose_owner_original:
        require(not a.diagnose_original and not a.diagnose_gtk_ready_original and not a.partial
                and a.manifest is None and a.evidence is None, "owner diagnostic cannot mix audits")
        diagnose_owner_original(a.output)
        return
    stamp = identity()
    if a.diagnose_gtk_ready_original:
        require(not a.diagnose_original and not a.partial and a.manifest is None and a.evidence is None, "readiness diagnosis cannot mix audits")
        diagnose_gtk_ready_original(a.output, stamp)
        return
    if a.diagnose_original:
        require(not a.partial and a.manifest is None and a.evidence is None, "diagnosis cannot mix product audits")
        diagnose_original(a.output, stamp)
        return
    result = {**stamp, "accepted": False, "preparation_only": not SCOPE["complete"], "requirement": "F03", "problems": []}
    try:
        if a.partial:
            require(a.evidence is not None and a.manifest is None,"partial evidence root required")
            partial(a.evidence,a.output,stamp)
            return
        require(a.manifest is not None,"six-host manifest required")
        result = audit(a.manifest.parent, read(a.manifest), stamp)
    except Exception as error:
        result["problems"].append(type(error).__name__ + ": " + str(error))
        write_json(a.output, result)
        raise
    write_json(a.output, result)
if __name__ == "__main__":
    main()
