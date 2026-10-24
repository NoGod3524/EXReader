#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only strict same-source evidence for the three account-profile jobs.

Downloads every same-run artifact through the authenticated API, recomputes the
ZIP SHA-256, refuses mismatched ids/bytes/digests/expiry, and requires the same
named case set and all-pass outcome on every platform. Mutated reports must be
refused by the same validator.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_account_profiles import REQUIRED_CASES  # noqa: E402

PLATFORMS = (("Linux", "ubuntu-22.04"), ("Windows", "windows-2022"), ("macOS", "macos-15"))
WORKFLOW = ".github/workflows/reader-account-profiles.yml"


def download(artifact_id):
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(artifact_id, stream)
        stream.seek(0)
        return stream.read()


def verify_report(report, source, run_id, attempt, platform):
    require(isinstance(report, dict), "report is not an object")
    require(report.get("accepted") is True, "report refused")
    require(report.get("source_sha") == source, "report source differs")
    require(str(report.get("run_id")) == run_id and str(report.get("attempt")) == attempt,
            "report run identity differs")
    require(report.get("platform") == platform, "report platform differs")
    require(report.get("checks") == len(REQUIRED_CASES), "report check count differs")
    require(report.get("required_checks") == len(REQUIRED_CASES),
            "report required count differs")
    for key in ("sdk_changed", "schema_changed", "product_sql_written", "host_ui_accepted",
                "product_integration_accepted", "android_apple_accepted"):
        require(report.get(key) is False, "report claim %s is not false" % key)
    cases = report.get("cases")
    require(isinstance(cases, list) and len(cases) == len(REQUIRED_CASES), "case count differs")
    names = [case.get("name") for case in cases]
    require(len(set(names)) == len(names), "case names repeat")
    require(set(names) == set(REQUIRED_CASES), "case identity differs")
    require(all(case.get("status") == "pass" and case.get("ok") is True and
                case.get("detail") == "" for case in cases), "a named case did not pass")


def negative_controls():
    good = {
        "accepted": True, "source_sha": "a" * 40, "run_id": "1", "attempt": "1",
        "platform": "Linux", "checks": len(REQUIRED_CASES),
        "required_checks": len(REQUIRED_CASES), "sdk_changed": False, "schema_changed": False,
        "product_sql_written": False, "host_ui_accepted": False,
        "product_integration_accepted": False, "android_apple_accepted": False,
        "cases": [{"name": name, "status": "pass", "ok": True, "detail": ""}
                  for name in REQUIRED_CASES],
    }
    verify_report(good, "a" * 40, "1", "1", "Linux")
    mutations = []
    for key, value in (("accepted", False), ("source_sha", "b" * 40), ("checks", 1),
                       ("platform", "Windows"), ("sdk_changed", True)):
        altered = json.loads(json.dumps(good))
        altered[key] = value
        mutations.append(altered)
    altered = json.loads(json.dumps(good))
    altered["cases"][0]["status"] = "fail"
    mutations.append(altered)
    altered = json.loads(json.dumps(good))
    altered["cases"][0]["ok"] = False
    mutations.append(altered)
    altered = json.loads(json.dumps(good))
    altered["cases"] = altered["cases"][:-1]
    mutations.append(altered)
    altered = json.loads(json.dumps(good))
    altered["cases"][0]["name"] = "invented"
    mutations.append(altered)
    rejections = 0
    for altered in mutations:
        try:
            verify_report(altered, "a" * 40, "1", "1", "Linux")
        except ValueError:
            rejections += 1
            continue
        except Exception:  # noqa: BLE001 - any refusal is a rejection
            rejections += 1
            continue
        raise AssertionError("a mutated report was accepted")
    require(rejections == len(mutations), "a mutation was not exercised")
    return rejections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    source = os.environ["GITHUB_SHA"]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "package": "EXReaderAccountProfiles 0.1.0",
        "fixed_start": "f43baf9182d75907c0cb5d6f77048f27bca8c950",
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "workflow": WORKFLOW,
        "accepted": False,
        "artifacts": [],
        "jobs": [],
        "problems": [],
        "platforms": [],
        "mutated_reports_rejected": 0,
        "host_ui_accepted": False,
        "product_integration_accepted": False,
    }
    try:
        run = fetch("actions/runs/%s" % run_id)
        require(run.get("head_sha") == source and str(run.get("run_attempt")) == attempt,
                "caller identity differs")
        require(str(run.get("path", "")).split("@")[0] == WORKFLOW, "wrong workflow")
        summary["mutated_reports_rejected"] = negative_controls()
        jobs = pages("actions/runs/%s/attempts/%s/jobs" % (run_id, attempt), "jobs")
        artifacts = pages("actions/runs/%s/artifacts" % run_id, "artifacts")
        suffix = "-%s-%s" % (run_id, attempt)
        outcomes = []
        for platform, runner in PLATFORMS:
            name = "reader-account-profiles-%s%s" % (platform, suffix)
            matches = [artifact for artifact in artifacts if artifact.get("name") == name]
            require(len(matches) == 1, "missing or duplicate artifact " + name)
            artifact = matches[0]
            job_name = "account profiles (%s)" % runner
            matches = [job for job in jobs if job.get("name") == job_name]
            require(len(matches) == 1, "missing or duplicate job " + job_name)
            job = matches[0]
            require(job.get("head_sha") == source and str(job.get("run_attempt")) == attempt,
                    "job identity differs for " + platform)
            require(job.get("conclusion") == "success", "job failed for " + platform)
            require(artifact.get("expired") is False, "artifact expired for " + platform)
            require(int(artifact.get("size_in_bytes", 0)) > 0, "empty artifact for " + platform)
            require(artifact["workflow_run"]["head_sha"] == source, "artifact source differs")
            data = download(artifact["id"])
            require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ for " + platform)
            require("sha256:" + hashlib.sha256(data).hexdigest() == artifact.get("digest"),
                    "ZIP digest differs for " + platform)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.namelist()
                reports = [entry for entry in entries
                           if entry.endswith("ap-evidence/result.json")]
                require(len(reports) == 1, "one result.json is required for " + platform)
                report = json.loads(archive.read(reports[0]).decode("utf-8"))
                verify_report(report, source, run_id, attempt, platform)
                logs = [entry for entry in entries if entry.endswith("ap-logs/check.log")]
                require(len(logs) == 1, "check log missing for " + platform)
                if platform == "Linux":
                    sanitizer = [entry for entry in entries
                                 if entry.endswith("ap-evidence/sanitizer.txt")]
                    require(len(sanitizer) == 1, "sanitizer record missing")
                    text = archive.read(sanitizer[0]).decode("utf-8")
                    require("failures=0" in text, "sanitizer reported a failure")
                    log = archive.read(logs[0]).decode("utf-8", "replace")
                    require("ERROR: AddressSanitizer" not in log, "sanitizer error in the log")
                    require("runtime error:" not in log, "undefined behaviour in the log")
                session = [case for case in report["cases"]
                           if case["name"] == "cross-account-real-session"]
                require(len(session) == 1 and session[0]["status"] == "pass",
                        "the real-session case is missing for " + platform)
                outcomes.append(sorted((case["name"], case["status"])
                                       for case in report["cases"]))
            summary["artifacts"].append({
                "platform": platform,
                "id": artifact["id"],
                "name": artifact["name"],
                "size_in_bytes": artifact["size_in_bytes"],
                "digest": artifact["digest"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "expires_at": artifact["expires_at"],
                "checks": len(REQUIRED_CASES),
            })
            summary["jobs"].append({"id": job["id"], "name": job["name"],
                                    "conclusion": job["conclusion"]})
            summary["platforms"].append(platform)
        require(len(outcomes) == 3 and outcomes[0] == outcomes[1] == outcomes[2],
                "platform case sets differ")
        summary["evidence_record"] = {
            "produced_by": "same-run artifact evidence job",
            "name": "reader-account-profiles-evidence%s" % suffix,
            "note": "uploaded after this record is written; the three upstream artifacts above are authenticated here",
        }
        summary["accepted"] = True
    except Exception as error:  # noqa: BLE001 - refusal is evidence
        summary["problems"].append(str(error))
    (output / "artifacts.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary["accepted"] else 1)


if __name__ == "__main__":
    main()