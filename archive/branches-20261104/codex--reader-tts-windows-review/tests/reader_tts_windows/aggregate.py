#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source collection for the Windows TTS acceptance run.

Downloads the artifacts of the target run, recomputes every ZIP digest from the
downloaded bytes, binds the producer logs to the artifact id/size/digest and verifies
the uploaded report, the WAV containers, the installed tree and the consumer hashes.
Modes:
  in-run  (default)          the current run, producer artifact only
  strict  (--run-id ...)     a completed run, both artifacts, retrospective
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from strict_contract import (EvidenceError, MAX_EXPANDED, MAX_ZIP, PRODUCER_JOB, REPORT_JOB,
                             decode_json, integer, need, select, unique, artifact_identity,
                             verify, verify_in_run)


def api(path):
    done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, timeout=180)
    need(done.returncode == 0, "github_api")
    return decode_json(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 21):
        body = api(path + "?per_page=100&page=%d" % page)
        need(integer(body.get("total_count")) and type(body.get(field)) is list and len(body[field]) <= 100,
             "api_pagination")
        result.extend(body[field])
        if len(result) >= body["total_count"]:
            need(len(result) == body["total_count"], "api_page_count")
            return result
        need(bool(body[field]), "api_incomplete_page")
    raise EvidenceError("api_page_limit")


def download(repo, artifact, folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("%d.zip" % artifact["id"])
    with path.open("wb") as target:
        done = subprocess.run(["gh", "api", "/repos/%s/actions/artifacts/%d/zip" % (repo, artifact["id"])],
                              stdout=target, stderr=subprocess.PIPE, timeout=600)
    need(done.returncode == 0 and path.stat().st_size <= MAX_ZIP, "archive_download")
    return path.read_bytes()


def download_log(repo, job, folder):
    done = subprocess.run(["gh", "api", "--allow-escape-sequences",
                           "/repos/%s/actions/jobs/%d/logs" % (repo, job["id"])],
                          capture_output=True, timeout=300)
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace")
        for token in (os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_TOKEN")):
            if token:
                detail = detail.replace(token, "<redacted>")
        error = EvidenceError("job_log_download")
        error.diagnostic = re.sub(r"https?://\S+", "<url>", detail)[-300:]
        raise error
    need(len(done.stdout) <= MAX_EXPANDED, "job_log_size")
    (folder / ("job-%d.log" % job["id"])).write_bytes(done.stdout)
    return done.stdout


def collect(repo, run_id, attempt, sha, folder, strict_mode):
    prefix = "/repos/%s/actions/runs/%d" % (repo, run_id)
    run = api(prefix + "/attempts/%d" % attempt)
    jobs = pages(prefix + "/attempts/%d/jobs" % attempt, "jobs")
    artifacts = pages(prefix + "/artifacts", "artifacts")
    unique(jobs, "job_duplicate")
    unique(artifacts, "artifact_duplicate")
    folder.mkdir(parents=True, exist_ok=True)
    wanted = [PRODUCER_JOB] + ([REPORT_JOB] if strict_mode else [])
    logs = {}
    for job in jobs:
        if job.get("name") in wanted:
            logs[job["id"]] = download_log(repo, job, folder)
    names = ["reader-tts-windows-windows-%d-%d" % (run_id, attempt)]
    if strict_mode:
        names.append("reader-tts-windows-report-%d-%d" % (run_id, attempt))
    archives = {}
    for name in names:
        artifact = select(artifacts, name)
        archives[artifact["id"]] = download(repo, artifact, folder)
    if strict_mode:
        return verify(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt, True)
    return verify_in_run(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 2, "accepted": False, "complete_product": False}
    try:
        need(os.environ.get("GITHUB_ACTIONS") == "true", "cloud_required")
        retrospective = args.run_id is not None
        need(retrospective == (args.attempt is not None) == (args.source_sha is not None),
             "target_arguments")
        summary = collect(os.environ["GITHUB_REPOSITORY"], args.run_id or int(os.environ["GITHUB_RUN_ID"]),
                          args.attempt or int(os.environ["GITHUB_RUN_ATTEMPT"]),
                          args.source_sha or os.environ["GITHUB_SHA"], Path(args.downloads), retrospective)
        summary["verifier"] = {"source_sha": os.environ["GITHUB_SHA"],
                               "run_id": int(os.environ["GITHUB_RUN_ID"]),
                               "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                               "job": os.environ.get("GITHUB_JOB", "")}
        summary["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    except Exception as error:  # noqa: BLE001 - every failure must reach the report
        summary = {"schema": 2, "accepted": False, "complete_product": False}
        summary["error"] = str(error) if isinstance(error, EvidenceError) else type(error).__name__
        if isinstance(error, EvidenceError) and hasattr(error, "diagnostic"):
            summary["diagnostic"] = error.diagnostic
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    (output / "aggregate.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
