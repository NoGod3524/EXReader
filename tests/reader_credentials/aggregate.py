#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source credential artifact collection."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from strict_contract import (EvidenceError, MAX_ZIP, MAX_EXPANDED, PLATFORMS, need, integer,
                             decode_json, unique, select, artifact_identity, verify)


def api(path):
    done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, timeout=120)
    need(done.returncode == 0, "github_api")
    return decode_json(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 21):
        body = api(path + f"?per_page=100&page={page}")
        need(integer(body.get("total_count")) and type(body.get(field)) is list and len(body[field]) <= 100, "api_pagination")
        result.extend(body[field])
        if len(result) >= body["total_count"]:
            need(len(result) == body["total_count"], "api_page_count");return result
        need(bool(body[field]), "api_incomplete_page")
    raise EvidenceError("api_page_limit")


def collect(repo, run_id, attempt, sha, folder, retrospective):
    prefix = f"/repos/{repo}/actions/runs/{run_id}"
    run = api(prefix + f"/attempts/{attempt}")
    jobs = pages(prefix + f"/attempts/{attempt}/jobs", "jobs")
    artifacts = pages(prefix + "/artifacts", "artifacts")
    unique(jobs, "job_duplicate");unique(artifacts, "artifact_duplicate")
    folder.mkdir(parents=True, exist_ok=True)
    archives, logs = {}, {}
    for key, (_, job_name, _, _) in PLATFORMS.items():
        artifact = select(artifacts, f"reader-credentials-{key}-{run_id}-{attempt}")
        artifact_identity(artifact, run, datetime.now(timezone.utc))
        path = folder / f"{artifact['id']}.zip"
        with path.open("wb") as target:
            done = subprocess.run(["gh", "api", f"/repos/{repo}/actions/artifacts/{artifact['id']}/zip"],
                                  stdout=target, stderr=subprocess.PIPE, timeout=180)
        need(done.returncode == 0 and path.stat().st_size <= MAX_ZIP, "archive_download")
        archives[artifact["id"]] = path.read_bytes()
        job = select(jobs, job_name)
        done = subprocess.run(["gh", "api", f"/repos/{repo}/actions/jobs/{job['id']}/logs"],
                              capture_output=True, timeout=180)
        need(done.returncode == 0 and len(done.stdout) <= MAX_EXPANDED, "job_log_download")
        logs[job["id"]] = done.stdout
        (folder / f"job-{job['id']}.log").write_bytes(done.stdout)
    return verify(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt, retrospective)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--source-sha")
    args = parser.parse_args()
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 2, "accepted": False, "complete_product": False}
    try:
        need(os.environ.get("GITHUB_ACTIONS") == "true", "cloud_required")
        retrospective = args.run_id is not None
        need(retrospective == (args.attempt is not None) == (args.source_sha is not None), "target_arguments")
        summary = collect(os.environ["GITHUB_REPOSITORY"], args.run_id or int(os.environ["GITHUB_RUN_ID"]),
                          args.attempt or int(os.environ["GITHUB_RUN_ATTEMPT"]), args.source_sha or os.environ["GITHUB_SHA"],
                          Path(args.downloads), retrospective)
        summary["verifier"] = {"source_sha": os.environ["GITHUB_SHA"], "run_id": int(os.environ["GITHUB_RUN_ID"]),
                               "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])}
    except Exception as error:
        summary["error"] = str(error) if isinstance(error, EvidenceError) else type(error).__name__
        if isinstance(error, EvidenceError):
            for name in ("platform", "phase"):
                if hasattr(error, name):
                    summary[name] = getattr(error, name)
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    (output / "aggregate.json").write_text(text, encoding="utf-8");print(text)
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
