#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only read-only diagnostics of an explicitly bound original Apple ZIP."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

REPO = "NoGod3524/EXReader"
WORKFLOW = ".github/workflows/dot-c02-apple-host-20261031.yml"

def require(value,label):
    if not value:
        raise ValueError(label)

def api(path,out):
    result = subprocess.run(["gh","api","repos/"+REPO+"/"+path],capture_output=True,check=True)
    out.write_bytes(result.stdout)
    return json.loads(result.stdout)

def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true","Actions-only original ZIP diagnostics")
    request = json.loads(os.environ["C02_DIAGNOSTIC"])
    out = Path("build/apple-c02-original-diagnostic")
    out.mkdir(parents=True,exist_ok=False)
    (out/"request.json").write_text(json.dumps(request,indent=2)+"\n")
    for key in ("run","attempt","job","artifact","bytes"):
        require(type(request[key]) is int and request[key] > 0,"positive-id:"+key)
    require(re.fullmatch(r"[0-9a-f]{40}",request["source"]) and
            re.fullmatch(r"[0-9a-f]{64}",request["sha256"]),"qualified producer hashes")
    require(request["platform"] in ("macos","iphonesimulator") and request["bytes"] <= 256*1024*1024,
            "bounded known Apple artifact")
    run = api(f"actions/runs/{request['run']}/attempts/{request['attempt']}",out/"run.json")
    jobs = api(f"actions/runs/{request['run']}/attempts/{request['attempt']}/jobs?per_page=100",out/"jobs.json")
    artifact = api(f"actions/artifacts/{request['artifact']}",out/"artifact.json")
    require(run["head_sha"] == request["source"] and run["run_attempt"] == request["attempt"] and
            run["path"] == WORKFLOW and run["status"] == "completed" and
            run["repository"]["full_name"] == REPO,"producer run binding")
    require(jobs["total_count"] == len(jobs["jobs"]),"unresolved job pagination")
    selected = [row for row in jobs["jobs"] if row["id"] == request["job"]]
    require(len(selected) == 1,"producer job")
    job = selected[0]
    require(job["status"] == "completed" and job["run_id"] == request["run"] and
            job["name"] == "Actual C02 Apple app UID "+request["platform"],"producer runtime job")
    expected_name = f"c02-apple-runtime-{request['platform']}-{request['run']}-{request['attempt']}"
    require(artifact["name"] == expected_name and artifact["size_in_bytes"] == request["bytes"] and
            artifact["digest"] == "sha256:"+request["sha256"] and artifact["expired"] is False and
            artifact["workflow_run"]["id"] == request["run"] and
            artifact["workflow_run"]["head_sha"] == request["source"],"original artifact API binding")
    instant = lambda value: datetime.datetime.fromisoformat(value.replace("Z","+00:00"))
    require(instant(job["started_at"]) <= instant(artifact["created_at"]) <= instant(job["completed_at"]),
            "artifact exact attempt job window")
    path = out/"original.zip"
    with path.open("xb") as stream:
        subprocess.run(["gh","api",f"repos/{REPO}/actions/artifacts/{request['artifact']}/zip"],stdout=stream,check=True)
    raw = path.read_bytes()
    require(len(raw) == request["bytes"] and hashlib.sha256(raw).hexdigest() == request["sha256"],
            "unchanged original ZIP bytes")
    wanted = ("receipt.json","admission.json","baseline.log","enrollment-crash.log","pending-crash.log",
              "runtime/baseline/failure.json","runtime/baseline/baseline.json",
              "native/baseline/model/host-log.txt","runtime/fresh/failure.json")
    reports = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        seen = set()
        for info in archive.infolist():
            name = info.filename
            require(name not in seen and not name.startswith("/") and
                    all(part not in (".","..") for part in name.split("/")) and
                    not stat.S_ISLNK(info.external_attr >> 16),"unambiguous original archive paths")
            seen.add(name)
            if name in wanted:
                require(info.file_size <= 1024*1024,"bounded diagnostic text")
                data = archive.read(info)
                reports[name] = dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                                     text=data.decode("utf-8","backslashreplace")[-24000:])
    (out/"diagnostic.json").write_text(json.dumps(dict(
        scope="diagnostic-only",full_c02_complete=False,producer=request,reports=reports),indent=2)+"\n")
    for name,record in reports.items():
        print(json.dumps(dict(path=name,**record)),flush=True)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == request["sha256"],"retained original ZIP unchanged")

if __name__ == "__main__":
    main()
