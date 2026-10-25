#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only same-source aggregation of the three native platform artifacts."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from evidence import EvidenceError, PLATFORMS, artifact_name, need, verify_archive, verify_artifact, verify_download, verify_jobs


def api(path):
    done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True, timeout=120)
    need(done.returncode == 0, "github_api")
    return json.loads(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 11):
        body = api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
        result.extend(body[field])
        if len(result) >= body["total_count"]:
            need(len(result) == body["total_count"], "api_count")
            return result
    raise EvidenceError("api_pages")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--downloads", required=True)
    args = parser.parse_args()
    out, downloads = Path(args.output), Path(args.downloads)
    out.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 1, "accepted": False}
    try:
        need(os.environ.get("GITHUB_ACTIONS") == "true", "cloud_required")
        repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
        run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
        prefix = f"/repos/{repo}/actions/runs/{run_id}"
        run = api(prefix + f"/attempts/{attempt}")
        need(run.get("head_sha") == sha and run.get("id") == int(run_id)
             and run.get("run_attempt") == int(attempt)
             and run.get("path") == ".github/workflows/reader-apple-file-entry.yml", "run_identity")
        jobs = pages(prefix + f"/attempts/{attempt}/jobs", "jobs")
        artifacts = pages(prefix + "/artifacts", "artifacts")
        names = [a["name"] for a in artifacts]
        need(len(names) == len(set(names)), "artifact_duplicate")
        job_rows = verify_jobs(jobs, sha, run_id, attempt)
        platforms = {}
        for platform in PLATFORMS:
            meta = [a for a in artifacts if a["name"] == artifact_name(platform, run_id, attempt)]
            need(len(meta) == 1, "artifact_missing_" + platform)
            verify_artifact(meta[0], platform, sha, run_id, attempt)
            path = downloads / f"{meta[0]['id']}.zip"
            with path.open("wb") as target:
                done = subprocess.run(["gh", "api", f"/repos/{repo}/actions/artifacts/{meta[0]['id']}/zip"],
                                      stdout=target, stderr=subprocess.PIPE, timeout=300)
            need(done.returncode == 0, "artifact_download")
            data = path.read_bytes()
            verify_download(data, meta[0])
            report, total = verify_archive(data, platform, sha, run_id, attempt)
            platforms[platform] = {
                "artifact_id": meta[0]["id"], "artifact_name": meta[0]["name"], "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "expires_at": meta[0]["expires_at"],
                "api_digest": meta[0]["digest"], "checks": total, "job": job_rows[f"native {platform}"],
                "binaries": report["binaries"], "installed_module_sha256": report["installed_module_sha256"],
                "not_exercised": report["not_exercised"],
                "xcode": report.get("xcode"), "simulator": report.get("simulator"),
            }
        summary = {"schema": 1, "accepted": True, "source_sha": sha, "run_id": int(run_id), "attempt": int(attempt),
                   "jobs": job_rows, "platforms": platforms}
    except EvidenceError as error:
        summary["error"] = str(error)
    except Exception as error:  # report, never treat as success
        summary["error"] = type(error).__name__
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    (out / "aggregate.json").write_text(text, encoding="utf-8")
    print(text)
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
