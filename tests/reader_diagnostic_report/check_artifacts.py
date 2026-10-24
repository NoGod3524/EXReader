#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three diagnostic-report jobs.

Each platform ZIP is authenticated against the Actions API (id, name, size,
digest, expiry, source) and then opened here; the named per-platform outcomes are
compared with the exact expected set. A missing, duplicated, cross-source,
expired or edited artifact fails the run.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_diagnostic_report import (  # noqa: E402
    ALL_PLATFORMS, COMMON_START, PLATFORM_CASES, REQUIRED_CASES)

PLATFORMS = (("Linux", "ubuntu-22.04"), ("Windows", "windows-2022"), ("macOS", "macos-15"))


def expected_cases(platform):
    return [name for name in REQUIRED_CASES if platform in PLATFORM_CASES.get(name, ALL_PLATFORMS)]


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    source = os.environ["GITHUB_SHA"]
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "accepted": False,
        "package": "EXReaderDiagnosticReport 0.1.0",
        "common_start": COMMON_START,
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "artifacts": [],
        "jobs": [],
        "problems": [],
        "granted_platforms": [],
        "contract_limits": {},
        "host_ui_accepted": False,
        "auto_upload": False,
        "performance_claimed": False,
        "complete_product": False,
        "sdk_changed": False,
        "schema_changed": False,
    }
    try:
        run = fetch("actions/runs/%d" % run_id)
        require(run["head_sha"] == source and run["run_attempt"] == attempt,
                "caller identity differs")
        require(run["path"] == ".github/workflows/reader-diagnostic-report.yml",
                "wrong workflow")
        jobs = pages("actions/runs/%d/attempts/%d/jobs" % (run_id, attempt), "jobs")
        artifacts = pages("actions/runs/%d/artifacts" % run_id, "artifacts")
        outcomes = {}
        limits = []
        for platform, runner in PLATFORMS:
            artifact_name = "reader-diagnostic-report-%s-%d-%d" % (platform, run_id, attempt)
            job_name = "diagnostic report consumers (%s)" % runner
            matches = [item for item in artifacts if item["name"] == artifact_name]
            require(len(matches) == 1, "missing or duplicate artifact " + artifact_name)
            artifact = matches[0]
            matches = [item for item in jobs if item["name"] == job_name]
            require(len(matches) == 1, "missing or duplicate job " + job_name)
            job = matches[0]
            require(job["head_sha"] == source and job["run_attempt"] == attempt and
                    job["conclusion"] == "success", "upstream failed or different source")
            require(not artifact["expired"] and artifact["size_in_bytes"] > 0 and
                    artifact["workflow_run"]["head_sha"] == source,
                    "artifact identity differs")
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact["id"], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ")
            require("sha256:" + hashlib.sha256(data).hexdigest() == artifact["digest"],
                    "ZIP digest differs")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                report = json.loads(archive.read("diag-evidence/result.json"))
            require(report.get("accepted") is True, "%s: report refused" % platform)
            require(report.get("source_sha") == source and
                    int(report.get("run_id", 0)) == run_id and
                    int(report.get("attempt", 0)) == attempt,
                    "%s: report identity differs" % platform)
            require(report.get("granted_platform") == platform.lower(),
                    "%s: platform grant differs" % platform)
            expected = expected_cases(platform)
            observed = {case["name"] for case in report.get("cases", [])
                        if case["ok"] and case.get("applicable", True)}
            require(len(report.get("cases", [])) == len(REQUIRED_CASES),
                    "%s: case list is not the full contract" % platform)
            require(observed == set(expected),
                    "%s: applicable case set differs: %r" % (platform, sorted(observed ^ set(expected))))
            require(sorted(report.get("skipped", [])) ==
                    sorted(set(REQUIRED_CASES) - set(expected)),
                    "%s: skipped case set differs" % platform)
            require(int(report.get("checks", 0)) == len(expected),
                    "%s: applicable case count differs" % platform)
            require(not report.get("failed"), "%s: a named case failed" % platform)
            require(report.get("host_ui_accepted") is False and
                    report.get("auto_upload") is False,
                    "%s: report claims a scope it does not own" % platform)
            outcomes[platform] = sorted(observed)
            limits.append(report.get("limits", {}))
            summary["artifacts"].append({
                key: artifact[key]
                for key in ("id", "name", "size_in_bytes", "digest", "expires_at")})
            summary["jobs"].append({key: job[key] for key in ("id", "name", "conclusion")})
            summary["granted_platforms"].append(platform.lower())
        require(len(outcomes) == 3, "missing platform outcomes")
        union = set()
        for observed in outcomes.values():
            union |= set(observed)
        require(union == set(REQUIRED_CASES),
                "the three platforms do not cover the contract: %r" %
                sorted(set(REQUIRED_CASES) - union))
        require(limits[0] == limits[1] == limits[2] and limits[0],
                "installed contract limits differ across platforms")
        summary["contract_limits"] = limits[0]
        summary["accepted"] = True
    except Exception as error:  # noqa: BLE001 - refusal is evidence
        summary["problems"].append(str(error))
    (out / "result.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary["accepted"] else 1)


if __name__ == "__main__":
    main()