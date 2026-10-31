#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only original POSIX ZIP diagnostics; never a qualification result."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess

from audit import zip_files, git_bytes, package_identity, semantic_diagnostic
from posix_owner import audit_posix_owner
from protocols import need, sha, json_value

REPO = "NoGod3524/EXReader"
WORKFLOW = ".github/workflows/dot-c02-posix-migration-20261031.yml"

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "actions-only-original-diagnostics")
    request = json.loads(os.environ["C02_POSIX_DIAGNOSTIC"])
    out = Path("audit-diagnostic")
    out.mkdir(exist_ok=False)
    (out / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    for key in ("run", "attempt", "job", "artifact", "bytes"):
        need(type(request[key]) is int and request[key] > 0, "positive-diagnostic-id:" + key)
    need(re.fullmatch(r"[0-9a-f]{40}", request["source"]) and
         re.fullmatch(r"[0-9a-f]{64}", request["sha256"]) and
         request["os"] in ("ubuntu-22.04", "macos-15") and
         request["bytes"] <= 512 * 1024 * 1024, "bounded-original-diagnostic-request")
    def api(path, name):
        data = subprocess.check_output(["gh", "api", "repos/" + REPO + "/" + path])
        (out / name).write_bytes(data)
        return json_value(data)
    run = api(f"actions/runs/{request['run']}/attempts/{request['attempt']}", "run.json")
    jobs = api(f"actions/runs/{request['run']}/attempts/{request['attempt']}/jobs?per_page=100", "jobs.json")
    artifact = api(f"actions/artifacts/{request['artifact']}", "artifact.json")
    need(run["head_sha"] == request["source"] and run["run_attempt"] == request["attempt"] and
         run["path"] == WORKFLOW and run["status"] == "completed" and
         run["repository"]["full_name"] == REPO, "exact-original-producer-run")
    need(jobs["total_count"] == len(jobs["jobs"]), "complete-original-job-page")
    selected = [job for job in jobs["jobs"] if job["id"] == request["job"]]
    need(len(selected) == 1, "one-exact-original-job")
    job = selected[0]
    need(job["run_id"] == request["run"] and job["status"] == "completed" and
         job["conclusion"] == "success" and job["name"] == "migration (" + request["os"] + ")",
         "successful-original-migration-job")
    name = "c02-posix-migration-" + request["os"] + "-" + request["source"]
    need(artifact["name"] == name and artifact["size_in_bytes"] == request["bytes"] and
         artifact["digest"] == "sha256:" + request["sha256"] and not artifact["expired"] and
         artifact["workflow_run"]["id"] == request["run"] and
         artifact["workflow_run"]["head_sha"] == request["source"], "exact-original-artifact-api")
    instant = lambda value: datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(instant(job["started_at"]) <= instant(artifact["created_at"]) <= instant(job["completed_at"]),
         "original-artifact-exact-job-window")
    original = out / "original.zip"
    with original.open("xb") as stream:
        subprocess.run(["gh", "api", f"repos/{REPO}/actions/artifacts/{request['artifact']}/zip"],
                       stdout=stream, check=True)
    raw = original.read_bytes()
    need(len(raw) == request["bytes"] and sha(raw) == request["sha256"], "retained-original-zip-digest")
    files = zip_files(raw)
    (out / "members.json").write_text(json.dumps([
        dict(path=name, bytes=len(data), sha256=sha(data)) for name, data in sorted(files.items())
    ], indent=2) + "\n")
    selected_names = [name for name in sorted(files) if
        name.endswith(("migration-result.json", "repair-result.json", "legacy-result.json", "pc02-provider-inputs.txt",
                       "exreader-c02-migrate", "exreader-c02-migrate-controls", "exreader-c02-admission")) or
        "/preserved-binaries/" in name or name.endswith("source-observations.json")]
    print("C02-POSIX-ORIGINAL-MEMBERS " + json.dumps(selected_names), flush=True)
    reports = {}
    for name, data in sorted(files.items()):
        chosen_case = "/process-kill-900-any/" in name or "/process-kill-1603-" in name
        if not (name.endswith(("migration-result.json", "repair-result.json", "legacy-result.json", "source-observations.json")) or
                chosen_case and name.endswith(".json") and "/native/" not in name):
            continue
        value = json_value(data)
        reports[name] = value
        shown = value
        if name.endswith("legacy-result.json"):
            shown = {key:val for key,val in value.items() if key not in ("results", "cases")}
        if name.endswith("source-observations.json") and isinstance(value, list):
            shown = [row for row in value if
                     "process-kill-900-any" in str(row) or "process-kill-1603-" in str(row)][:32]
        text = json.dumps(dict(path=name, bytes=len(data), value=shown))
        print("C02-POSIX-ORIGINAL-JSON " + text[:48000], flush=True)
    (out / "selected-json.json").write_text(json.dumps(reports, indent=2) + "\n")
    repair_diagnostics(files, out)
    need(original.stat().st_size == request["bytes"] and sha(original.read_bytes()) == request["sha256"],
         "original-zip-unchanged-after-diagnostics")
    receipt = dict(scope="diagnostic-only", full_c02_complete=False, producer=request,
                   producer_workflow_conclusion=run["conclusion"], original_zip_unchanged=True,
                   members=len(files))
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("C02-POSIX-DIAGNOSTIC " + json.dumps(receipt), flush=True)
    if "owner_spec" in request:
        spec = request["owner_spec"]
        need(spec["run"] == request["run"] and spec["attempt"] == request["attempt"] and
             spec["job"] == request["job"] and spec["artifact"] == dict(id=request["artifact"],
                  name=artifact["name"],bytes=request["bytes"],sha256=request["sha256"]),
             "diagnostic-owner-spec-exact-original")
        package_identity(spec,request["source"])
        try:
            details = audit_posix_owner(files,spec,request["source"],git_bytes)
        except Exception as error:
            diagnostic = semantic_diagnostic(files,spec,error)
            (out / "owner-failure.json").write_text(json.dumps(diagnostic,indent=2)+"\n")
            print("C02-POSIX-OWNER-FAILURE " + json.dumps({
                key:value for key,value in diagnostic.items() if key != "files"}),flush=True)
            raise
        (out / "owner-independent.json").write_text(json.dumps(details,indent=2)+"\n")
        print("C02-POSIX-OWNER-INDEPENDENT " + json.dumps({
            key:value for key,value in details.items() if key != "cases"}),flush=True)


def repair_diagnostics(files, out):
    import struct
    cases = ("partial-begin-actual", "partial-clean-actual", "partial-head-actual",
             "two-sequential-interruptions", "selected-complete-clean-restored",
             "protected-applied-floor-rollback-refused")
    report = {}
    for case in cases:
        members = []
        for name, data in sorted(files.items()):
            if "/" + case + "/" not in name:
                continue
            leaf = name.rsplit("/", 1)[-1]
            if not (leaf.startswith(("repair-", "proof-")) or leaf == "repair.guard" or
                    "/repair-archive-" in name or leaf.endswith("-observation.json")):
                continue
            row = dict(path=name, bytes=len(data), sha256=sha(data))
            if data[:8] == b"PC02R001" and len(data) >= 112:
                row.update(zip(("kind", "sequence", "payload_bytes"), struct.unpack_from("<QQQ", data, 8)))
            members.append(row)
        report[case] = members
        print("C02-REPAIR-MEMBERS " + json.dumps(dict(case=case, count=len(members), members=members)), flush=True)
    samples = {}
    for name, data in sorted(files.items()):
        if name.endswith("native-source-observations.json"):
            observations = json_value(data)
            for case in cases:
                matches = [row for row in observations if case in json.dumps(row)]
                chosen = []
                for marker in ("state", "repair-archive-", "proof-"):
                    chosen.extend([row for row in matches if marker in json.dumps(row)][:3])
                samples[case] = chosen
                print("C02-REPAIR-FSTAT " + json.dumps(dict(case=case, rows=chosen)), flush=True)
        if "/partial-head-actual/" not in name:
            continue
        if name.endswith("process-repair-plan-1-observation.json"):
            value = json_value(data)
            samples[name] = value
            print("C02-REPAIR-PROCESS " + json.dumps(dict(path=name, value=value)), flush=True)
        if name.endswith((".stdout", ".log", ".txt")) and b"repair_" in data and len(data) < 200000:
            value = data.decode("utf-8", "strict")
            samples[name] = value
            print("C02-REPAIR-SDK-LOG " + json.dumps(dict(path=name, text=value)), flush=True)
    (out / "repair-diagnostic.json").write_text(json.dumps(dict(members=report, samples=samples), indent=2) + "\n")

if __name__ == "__main__":
    main()
