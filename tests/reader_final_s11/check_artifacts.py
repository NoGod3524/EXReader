#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-run evidence job for S11.

It reads this run attempt's job conclusions and artifact metadata from the
GitHub API and records, for every job and artifact of this attempt: id, name,
conclusion, bytes, SHA-256 digest and expiry. Nothing is downloaded; the
artifact bytes stay in the cloud and are identified by their published digest.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

API = "https://api.github.com"


def get(path):
    request = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "exreader-s11-evidence",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    source_sha = os.environ.get("GITHUB_SHA", "")
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)

    jobs = get("/repos/" + repository + "/actions/runs/" + run_id + "/attempts/" +
               attempt + "/jobs?per_page=100")
    records = []
    for job in jobs.get("jobs", []):
        records.append({
            "id": job["id"],
            "name": job["name"],
            "status": job["status"],
            "conclusion": job["conclusion"],
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "html_url": job.get("html_url"),
        })
    matrix = [r for r in records if r["name"].startswith("S11 import faults (")]
    matrix.sort(key=lambda r: r["name"])
    assert len(matrix) == 3, "expected three matrix jobs: " + json.dumps(records, indent=2)
    for row in matrix:
        assert row["status"] == "completed", row
        assert row["conclusion"] == "success", row
    runners = sorted(row["name"].split("(")[-1].rstrip(")") for row in matrix)

    artifacts = get("/repos/" + repository + "/actions/runs/" + run_id +
                    "/artifacts?per_page=100")
    selected = []
    for artifact in artifacts.get("artifacts", []):
        run = artifact.get("workflow_run") or {}
        if str(run.get("id")) != str(run_id):
            continue
        if not artifact["name"].startswith("reader-final-s11-"):
            continue
        selected.append({
            "id": artifact["id"],
            "name": artifact["name"],
            "bytes": artifact["size_in_bytes"],
            "digest": artifact.get("digest"),
            "expires_at": artifact.get("expires_at"),
            "created_at": artifact.get("created_at"),
        })
    selected.sort(key=lambda row: row["name"])
    matrix_artifacts = [a for a in selected if "-evidence-" not in a["name"]]
    assert len(matrix_artifacts) == 3, (
        "expected three matrix artifacts: " + json.dumps(selected, indent=2))
    for artifact in matrix_artifacts:
        assert artifact["bytes"] > 0, artifact
        assert artifact["digest"] and artifact["digest"].startswith("sha256:"), artifact
        assert artifact["expires_at"], artifact
        assert artifact["name"].endswith(run_id + "-" + attempt), artifact

    record = {
        "repository": repository,
        "run_id": run_id,
        "attempt": attempt,
        "source_sha": source_sha,
        "runners": runners,
        "jobs": records,
        "artifacts": selected,
        "matrix_artifacts": matrix_artifacts,
    }
    (folder / "artifact-evidence.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print("S11_EVIDENCE_SUMMARY " + json.dumps(record, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
