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
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'c02_completion_audit_20261031'))
from macho_sdk import sdk_pair_diagnostic

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
    sdk_reports = []
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
        sdk_prefix = "installed-sdk/lib/"
        originals = sorted(name for name in seen if name.startswith(sdk_prefix) and name.endswith(".dylib"))
        if originals:
            identity = json.loads(archive.read("installed-sdk/c02-sdk-identity.json"))
            for name in originals:
                original = archive.read(name)
                leaf = name[len(sdk_prefix):]
                require(hashlib.sha256(original).hexdigest() == identity["files"]["lib/"+leaf],
                        "actual original SDK byte identity")
                for kind in ("production","runtime"):
                    framework = "Frameworks/" if request["platform"] == "iphonesimulator" else "Contents/Frameworks/"
                    bundled_name = "bundles/"+kind+".app/"+framework+leaf
                    require(bundled_name in seen,"matching bundled SDK")
                    bundled = archive.read(bundled_name)
                    try:
                        report = sdk_pair_diagnostic(original,bundled)
                    except Exception as error:
                        report = dict(error=type(error).__name__+":"+str(error),
                                      original_header=original[:128].hex(),bundled_header=bundled[:128].hex())
                    report.update(provider=leaf,bundle=kind)
                    sdk_reports.append(report)
        (out/"macho-sdk-diagnostic.json").write_text(json.dumps(sdk_reports,indent=2)+"\n")
        for report in sdk_reports:
            compact = dict(report)
            for key in ("original","bundled"):
                if key in compact:
                    value = compact[key]
                    compact[key] = dict(value,commands=[cmd for cmd in value["commands"] if
                        cmd["kind"] == 0x1d or cmd.get("segment",{}).get("name") == "__LINKEDIT"])
            print(json.dumps(dict(diagnostic="original-sdk-macho-layout",**compact)),flush=True)
    (out/"diagnostic.json").write_text(json.dumps(dict(
        scope="diagnostic-only",full_c02_complete=False,producer=request,reports=reports),indent=2)+"\n")
    for name,record in reports.items():
        print(json.dumps(dict(path=name,**record)),flush=True)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == request["sha256"],"retained original ZIP unchanged")

if __name__ == "__main__":
    main()
