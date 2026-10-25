#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only authentication of real jobs, ZIPs and installed consumers.

Negative tests modify the authenticated Linux bundle in memory in Actions. They
must be refused by the same verifier used for all three real platform grants.
"""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_diagnostic_report import (  # noqa: E402
    ALL_PLATFORMS, COMMON_START, HEADER_CONTRACT, PLATFORM_CASES, REQUIRED_CASES, REVIEW_START)

PLATFORMS = (("Linux", "ubuntu-22.04"), ("Windows", "windows-2022"), ("macOS", "macos-15"))
REPORT_PATH = "diag-evidence/result.json"


def expected_cases(platform):
    return [name for name in REQUIRED_CASES if platform in PLATFORM_CASES.get(name, ALL_PLATFORMS)]


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def verify_bundle(platform, runner, source, run_id, attempt, jobs, artifacts, data):
    artifact_name = "reader-diagnostic-report-%s-%d-%d" % (platform, run_id, attempt)
    job_name = "diagnostic report consumers (%s)" % runner
    matches = [item for item in artifacts if item["name"] == artifact_name]
    require(len(matches) == 1, "missing or duplicate artifact " + artifact_name)
    artifact = matches[0]
    require(sum(item["id"] == artifact["id"] for item in artifacts) == 1,
            "duplicate artifact ID")
    matches = [item for item in jobs if item["name"] == job_name]
    require(len(matches) == 1, "missing or duplicate job " + job_name)
    job = matches[0]
    require(sum(item["id"] == job["id"] for item in jobs) == 1, "duplicate job ID")
    require(job["head_sha"] == source and job["run_attempt"] == attempt and
            job["run_id"] == run_id and job["status"] == "completed" and
            job["conclusion"] == "success", "upstream failed, incomplete or identity differs")
    require(type(artifact["id"]) is int and artifact["id"] > 0 and
            artifact["expired"] is False and artifact["size_in_bytes"] > 0 and
            artifact["workflow_run"]["head_sha"] == source and
            artifact["workflow_run"]["id"] == run_id and
            re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")) and
            timestamp(artifact["expires_at"]) > datetime.now(timezone.utc),
            "artifact identity, expiry or digest differs")
    require(timestamp(job["started_at"]) <= timestamp(artifact["created_at"]) <=
            timestamp(job["completed_at"]), "artifact outside producer job interval")
    require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ")
    require("sha256:" + hashlib.sha256(data).hexdigest() == artifact["digest"],
            "ZIP digest differs")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate ZIP member")
        require(all(not name.startswith("/") and "\\" not in name and
                    ".." not in PurePosixPath(name).parts for name in names), "unsafe ZIP member")
        reports = [name for name in names if PurePosixPath(name).name == "result.json"]
        require(reports == [REPORT_PATH], "missing or duplicate report")
        report = unique_json(archive.read(REPORT_PATH))
        require(report.get("accepted") is True, "%s: report refused" % platform)
        require(report.get("source_sha") == source and report.get("run_id") == run_id and
                report.get("attempt") == attempt and report.get("common_start") == COMMON_START and
                report.get("review_start") == REVIEW_START and report.get("job") == "consumers",
                "%s: report identity differs" % platform)
        require(report.get("platform") == platform and
                report.get("granted_platform") == platform.lower(), "platform differs")
        expected = expected_cases(platform)
        cases = report.get("cases", [])
        require(len(cases) == len(REQUIRED_CASES) and
                len({case["name"] for case in cases}) == len(REQUIRED_CASES) and
                {case["name"] for case in cases} == set(REQUIRED_CASES), "case names differ")
        require(report.get("required_cases") == list(REQUIRED_CASES), "declared contract differs")
        require(all(case.get("ok") is True and
                    case.get("applicable", True) is (case["name"] in expected)
                    for case in cases), "failed or incorrectly skipped case")
        require(sorted(report.get("skipped", [])) == sorted(set(REQUIRED_CASES) - set(expected)),
                "skipped case set differs")
        require(report.get("checks") == len(expected) and report.get("failed") == [],
                "case count or failures differ")
        require(report.get("limits") == HEADER_CONTRACT, "installed contract limits differ")
        require(report.get("host_ui_accepted") is False and report.get("auto_upload") is False,
                "report claims a scope it does not own")
        suffix = ".exe" if platform == "Windows" else ""
        binaries = {"diag-consumer/diagnostic-" + stem + suffix
                    for stem in ("c-consumer", "cpp-consumer", "worker", "audit-consumer")}
        entries = report.get("binaries", []) + report.get("installed_files", [])
        require(len(entries) == len({entry["path"] for entry in entries}), "duplicate manifest entry")
        require({entry["path"] for entry in report.get("binaries", [])} == binaries,
                "missing consumer identity")
        installed = {name for name in names if name.startswith("diag-stage/") and
                     not name.endswith("/")}
        require(installed and {entry["path"] for entry in report.get("installed_files", [])} ==
                installed, "installed package manifest differs")
        require("diag-stage/include/reader_diagnostic_report.h" in installed and
                any(name.endswith((".a", ".lib")) for name in installed), "installed package missing")
        for entry in entries:
            raw = archive.read(entry["path"])
            require(type(entry["bytes"]) is int and entry["bytes"] > 0 and
                    len(raw) == entry["bytes"] and
                    re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) and
                    hashlib.sha256(raw).hexdigest() == entry["sha256"],
                    "installed file or consumer identity differs")
    return report, job, artifact


def mutate_zip(data, transform):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [(item.filename, archive.read(item)) for item in archive.infolist()]
    members = transform(members)
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, raw in members:
                archive.writestr(name, raw)
    return output.getvalue()


def refusal_tests(source, run_id, attempt, jobs, artifacts, data, artifact_id):
    tests = []
    def refused(name, change):
        changed_jobs, changed_artifacts, changed_data = copy.deepcopy(jobs), copy.deepcopy(artifacts), data
        changed_jobs, changed_artifacts, changed_data = change(changed_jobs, changed_artifacts, changed_data)
        try:
            verify_bundle("Linux", "ubuntu-22.04", source, run_id, attempt,
                          changed_jobs, changed_artifacts, changed_data)
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile):
            tests.append({"name": name, "ok": True})
            return
        raise ValueError("negative case accepted: " + name)

    def job_change(field, value):
        def change(js, ars, raw):
            next(j for j in js if j["name"] == "diagnostic report consumers (ubuntu-22.04)")[field] = value
            return js, ars, raw
        return change

    def artifact_change(field, value):
        def change(js, ars, raw):
            next(a for a in ars if a["id"] == artifact_id)[field] = value
            return js, ars, raw
        return change

    def archive_change(transform):
        def change(js, ars, raw):
            raw = mutate_zip(raw, transform)
            a = next(a for a in ars if a["id"] == artifact_id)
            a["size_in_bytes"] = len(raw)
            a["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
            return js, ars, raw
        return change

    def report_change(field, value):
        def transform(members):
            report = unique_json(next(raw for name, raw in members if name == REPORT_PATH))
            report[field] = value
            return [(name, json.dumps(report).encode() if name == REPORT_PATH else raw)
                    for name, raw in members]
        return archive_change(transform)

    for field, value in (("status", "in_progress"), ("conclusion", "failure"),
                         ("head_sha", "0" * 40), ("run_id", run_id + 1),
                         ("run_attempt", attempt + 1)):
        refused("reject-job-" + field, job_change(field, value))
    refused("reject-missing-job", lambda js, ars, raw: (
        [j for j in js if j["name"] != "diagnostic report consumers (ubuntu-22.04)"], ars, raw))
    refused("reject-duplicate-job", lambda js, ars, raw: (
        js + [next(j for j in js if j["name"] == "diagnostic report consumers (ubuntu-22.04)")], ars, raw))
    refused("reject-missing-artifact", lambda js, ars, raw: (
        js, [a for a in ars if a["id"] != artifact_id], raw))
    refused("reject-duplicate-artifact", lambda js, ars, raw: (
        js, ars + [next(a for a in ars if a["id"] == artifact_id)], raw))
    refused("reject-expired-artifact", artifact_change("expired", True))
    refused("reject-stale-expiry", artifact_change("expires_at", "2000-01-01T00:00:00Z"))
    refused("reject-artifact-source", artifact_change("workflow_run", {"id": run_id, "head_sha": "0" * 40}))
    refused("reject-artifact-run", artifact_change("workflow_run", {"id": run_id + 1, "head_sha": source}))
    refused("reject-empty-artifact", artifact_change("size_in_bytes", 0))
    refused("reject-zip-digest", artifact_change("digest", "sha256:" + "0" * 64))
    refused("reject-zip-size", artifact_change("size_in_bytes", len(data) + 1))
    refused("reject-duplicate-member", archive_change(lambda members: members + [members[0]]))
    refused("reject-duplicate-report", archive_change(lambda members: members + [
        ("extra/result.json", next(raw for name, raw in members if name == REPORT_PATH))]))
    refused("reject-missing-report", archive_change(lambda members: [
        (name, raw) for name, raw in members if name != REPORT_PATH]))
    refused("reject-tampered-consumer", archive_change(lambda members: [
        (name, raw + b"tampered" if name == "diag-consumer/diagnostic-c-consumer" else raw)
        for name, raw in members]))
    refused("reject-missing-consumer", archive_change(lambda members: [
        (name, raw) for name, raw in members if name != "diag-consumer/diagnostic-c-consumer"]))
    refused("reject-missing-binary-identity", report_change("binaries", []))
    refused("reject-report-source", report_change("source_sha", "0" * 40))
    refused("reject-report-attempt", report_change("attempt", attempt + 1))
    refused("reject-missing-cases", report_change("cases", []))
    refused("reject-changed-limit", report_change("limits", {}))
    return tests


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id, attempt = int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"])
    source = os.environ["GITHUB_SHA"]
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {"accepted": False, "package": "EXReaderDiagnosticReport 0.1.0",
               "common_start": COMMON_START, "review_start": REVIEW_START, "source_sha": source,
               "run_id": run_id, "attempt": attempt, "artifacts": [], "jobs": [], "problems": [],
               "granted_platforms": [], "contract_limits": {}, "negative_cases": [], "binaries": {},
               "host_ui_accepted": False, "auto_upload": False, "performance_claimed": False,
               "complete_product": False, "sdk_changed": False, "schema_changed": False}
    try:
        run = fetch("actions/runs/%d" % run_id)
        require(run["head_sha"] == source and run["run_attempt"] == attempt and run["id"] == run_id,
                "caller identity differs")
        require(run["path"] == ".github/workflows/reader-diagnostic-report.yml", "wrong workflow")
        jobs = pages("actions/runs/%d/attempts/%d/jobs" % (run_id, attempt), "jobs")
        artifacts = pages("actions/runs/%d/artifacts" % run_id, "artifacts")
        outcomes = {}
        for platform, runner in PLATFORMS:
            artifact_name = "reader-diagnostic-report-%s-%d-%d" % (platform, run_id, attempt)
            matches = [item for item in artifacts if item["name"] == artifact_name]
            require(len(matches) == 1, "missing or duplicate artifact " + artifact_name)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(matches[0]["id"], stream)
                stream.seek(0)
                data = stream.read()
            report, job, artifact = verify_bundle(platform, runner, source, run_id, attempt,
                                                  jobs, artifacts, data)
            if platform == "Linux":
                summary["negative_cases"] = refusal_tests(source, run_id, attempt, jobs,
                                                          artifacts, data, artifact["id"])
            outcomes[platform] = expected_cases(platform)
            summary["artifacts"].append({key: artifact[key] for key in
                ("id", "name", "size_in_bytes", "digest", "created_at", "expires_at")})
            summary["jobs"].append({key: job[key] for key in
                ("id", "name", "status", "conclusion", "head_sha", "run_id", "run_attempt")})
            summary["granted_platforms"].append(platform.lower())
            summary["binaries"][platform] = report["binaries"]
        require(set().union(*(set(items) for items in outcomes.values())) == set(REQUIRED_CASES),
                "platform union does not cover contract")
        summary["contract_limits"] = HEADER_CONTRACT
        summary["accepted"] = True
    except Exception as error:  # noqa: BLE001 - preserve refusals, including unexpected defects
        summary["problems"].append(str(error))
    (out / "result.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary["accepted"] else 1)


if __name__ == "__main__":
    main()
