#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S08 same-source aggregator.

Runs in Actions only. It binds this run/attempt, its jobs, the three artifacts
and their ZIP bytes to the tested source, recomputes every digest, and refuses
stale sources, wrong attempts, expired or unsafe archives, rewritten reports and
non-zero secret-scan counts.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MAX_ZIP = 512 * 1024 * 1024
PLATFORMS = {"windows": "platform (windows-2022)", "linux": "platform (ubuntu-22.04)"}


class EvidenceError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.diagnostic = ""


def need(condition, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_artifact(artifact: dict, *, run_id: int, attempt: int, name: str,
                   now: datetime) -> str:
    """Returns the declared sha256 (hex) of the artifact ZIP."""
    need(isinstance(artifact.get("id"), int), "artifact_id")
    need(artifact.get("name") == name, "artifact_name")
    need(artifact.get("expired") is False, "artifact_expired")
    expires = parse_time(artifact.get("expires_at"))
    need(expires is not None and expires > now, "artifact_expiry")
    need(isinstance(artifact.get("size_in_bytes"), int) and artifact["size_in_bytes"] > 0,
         "artifact_bytes")
    run = artifact.get("workflow_run") or {}
    need(run.get("id") == run_id, "artifact_run")
    digest = artifact.get("digest") or ""
    need(re.match(r"^sha256:[0-9a-f]{64}$", digest) is not None, "artifact_digest")
    return digest.split(":", 1)[1]


def check_zip(zip_bytes: bytes, *, digest: str, expected: dict) -> dict:
    """Verifies the archive bytes, member safety and the embedded report."""
    need(len(zip_bytes) > 0 and len(zip_bytes) <= MAX_ZIP, "zip_size")
    need(hashlib.sha256(zip_bytes).hexdigest() == digest, "zip_digest_mismatch")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        need(len(names) == len(set(names)), "zip_duplicate")
        for name in names:
            need(name and not name.startswith("/") and "\\" not in name and
                 ".." not in name.split("/"), "zip_entry_unsafe")
        members = {name: archive.read(name) for name in names}
    need("report.json" in members, "zip_report_missing")
    report = json.loads(members["report.json"].decode("utf-8"))
    need(report.get("schema") == 1 and report.get("package") == "S08", "report_schema")
    need(report.get("source_sha") == expected["source_sha"], "report_source")
    need(str(report.get("run_id")) == str(expected["run_id"]), "report_run")
    need(str(report.get("run_attempt")) == str(expected["attempt"]), "report_attempt")
    need(report.get("platform") == expected["platform"], "report_platform")
    need(report.get("job") == expected["job"], "report_job")
    need(report.get("accepted") is True, "report_rejected")
    need(report.get("judge_problems") == [], "report_judge")
    need((report.get("detector") or {}).get("passed") is True, "report_detector")
    need(report.get("checks") == report.get("expected_checks"), "report_check_count")
    need(report.get("passed") == report.get("checks"), "report_checks")
    scans = report.get("scans")
    need(isinstance(scans, dict) and scans, "report_scans")
    for stage, scan in scans.items():
        need(isinstance(scan, dict) and scan.get("hits") == 0, "report_scan_hits")
    manifest = report.get("manifest")
    need(isinstance(manifest, list) and manifest, "report_manifest")
    paths = [entry.get("path") for entry in manifest]
    need(len(paths) == len(set(paths)), "manifest_duplicate")
    need(set(members) - {"report.json"} == set(paths), "manifest_members")
    for entry in manifest:
        data = members[entry["path"]]
        need(len(data) == entry.get("bytes"), "manifest_bytes")
        need(hashlib.sha256(data).hexdigest() == entry.get("sha256"), "manifest_digest")
    need(isinstance(report.get("consumer"), dict) and report["consumer"].get("sha256"),
         "report_consumer")
    return {"platform": report["platform"], "job": report["job"],
            "checks": report["checks"], "expected_checks": report["expected_checks"],
            "phases": report.get("phase_labels"), "scan": scans.get("final"),
            "diagnostics": report.get("diagnostics"), "not_exercised":
            report.get("not_exercised", [])}


def check_job(job: dict, *, name: str, source_sha: str, run_id: int) -> dict:
    need(job.get("name") == name, "job_name")
    need(job.get("conclusion") == "success", "job_conclusion")
    need(job.get("head_sha") == source_sha, "job_source")
    need(job.get("run_id") == run_id, "job_run")
    need(isinstance(job.get("id"), int), "job_id")
    return {"name": name, "id": job["id"], "conclusion": job["conclusion"],
            "head_sha": job["head_sha"], "attempt": job.get("run_attempt")}


def api(path: str) -> dict:
    done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, timeout=180)
    need(done.returncode == 0, "github_api")
    return json.loads(done.stdout.decode("utf-8"))


def pages(path: str, field: str) -> list:
    result = []
    for page in range(1, 21):
        body = api(path + "?per_page=100&page=%d" % page)
        need(isinstance(body.get(field), list) and body[field], "api_page")
        result.extend(body[field])
        if len(result) >= body.get("total_count", 0):
            return result
    raise EvidenceError("api_page_limit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--downloads", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    downloads = Path(args.downloads)
    downloads.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 1, "package": "S08", "role": "aggregate", "accepted": False,
               "complete_product": False}
    try:
        need(os.environ.get("GITHUB_ACTIONS") == "true", "cloud_required")
        repo = os.environ["GITHUB_REPOSITORY"]
        source = os.environ["GITHUB_SHA"]
        run_id = int(os.environ["GITHUB_RUN_ID"])
        attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
        run = api("/repos/%s/actions/runs/%d/attempts/%d" % (repo, run_id, attempt))
        need(run.get("id") == run_id and run.get("run_attempt") == attempt, "run_identity")
        need(run.get("head_sha") == source, "run_source")
        jobs = pages("/repos/%s/actions/runs/%d/attempts/%d/jobs" % (repo, run_id, attempt),
                     "jobs")
        artifacts = pages("/repos/%s/actions/runs/%d/artifacts" % (repo, run_id), "artifacts")
        now = datetime.now(timezone.utc)

        def pick(job_name: str) -> dict:
            matches = [item for item in jobs if item.get("name") == job_name]
            need(len(matches) == 1, "job_missing_or_duplicate:" + job_name)
            return matches[0]

        verified_jobs = [check_job(pick("guard"), name="guard", source_sha=source,
                                   run_id=run_id)]
        for key, job_name in PLATFORMS.items():
            verified_jobs.append(check_job(pick(job_name), name=job_name, source_sha=source,
                                           run_id=run_id))
        verified = []
        for key in ("guard", "windows", "linux"):
            name = "reader-final-s08-%s-%d-%d" % (key, run_id, attempt)
            matches = [item for item in artifacts if item.get("name") == name]
            need(len(matches) == 1, "artifact_missing_or_duplicate:" + key)
            artifact = matches[0]
            digest = check_artifact(artifact, run_id=run_id, attempt=attempt, name=name, now=now)
            target = downloads / ("%d.zip" % artifact["id"])
            with target.open("wb") as handle:
                done = subprocess.run(
                    ["gh", "api", "/repos/%s/actions/artifacts/%d/zip" % (repo, artifact["id"])],
                    stdout=handle, stderr=subprocess.PIPE, timeout=300)
            need(done.returncode == 0, "artifact_download")
            zip_bytes = target.read_bytes()
            need(len(zip_bytes) == artifact["size_in_bytes"], "artifact_bytes_mismatch")
            if key == "guard":
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                    need("guard.json" in archive.namelist(), "guard_report_missing")
                    guard = json.loads(archive.read("guard.json").decode("utf-8"))
                need(guard.get("accepted") is True, "guard_rejected")
                need(guard.get("source_sha") == source, "guard_source")
                need((guard.get("detector") or {}).get("passed") is True, "guard_detector")
                verified.append({"key": key, "name": name, "id": artifact["id"],
                                 "bytes": artifact["size_in_bytes"],
                                 "api_sha256": digest,
                                 "zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
                                 "created_at": artifact.get("created_at"),
                                 "expires_at": artifact.get("expires_at"),
                                 "guard_checks": len(guard.get("checks", []))})
            else:
                # GITHUB_JOB is the workflow job id, not the matrix display name.
                detail = check_zip(zip_bytes, digest=digest, expected={
                    "source_sha": source, "run_id": run_id, "attempt": attempt,
                    "platform": key, "job": "platform"})
                verified.append({"key": key, "name": name, "id": artifact["id"],
                                 "bytes": artifact["size_in_bytes"], "api_sha256": digest,
                                 "zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
                                 "created_at": artifact.get("created_at"),
                                 "expires_at": artifact.get("expires_at"),
                                 "detail": detail})
        summary.update({"accepted": True, "source_sha": source, "run_id": run_id,
                        "attempt": attempt, "workflow": run.get("name") or "",
                        "jobs": verified_jobs, "artifacts": verified,
                        "verifier": {"source_sha": source, "run_id": run_id,
                                     "attempt": attempt,
                                     "job": os.environ.get("GITHUB_JOB", "")}})
    except EvidenceError as error:
        summary["error"] = str(error)
        summary["diagnostic"] = error.diagnostic
    except Exception as error:  # keep an inspectable failure without secrets
        summary["error"] = type(error).__name__
        summary["diagnostic"] = str(error)[:200]
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    (output / "aggregate.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if summary.get("accepted") else 1


if __name__ == "__main__":
    sys.exit(main())
