#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-source aggregate of one workflow run, executed in Actions.

Reads every platform report downloaded from this run, binds it to the run's
jobs and artifacts through the GitHub API (id, bytes, SHA-256 digest), and
grants a platform only for an accepted report of this exact source and run.
Platforms without such evidence stay pending; nothing is borrowed across
platforms or runs.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PLATFORMS = {
    "windows": ("Windows", "credentials (windows-2022)"),
    "linux": ("Linux", "credentials (ubuntu-22.04)"),
    "macos": ("macOS", "credentials (macos-15)"),
    "ios": ("iOS simulator", "credentials (ios-simulator)"),
    "android": ("Android emulator", "credentials (android-emulator)"),
}


def api(path: str) -> dict:
    done = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", required=True, help="directory holding downloaded artifacts")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    repo, run_id = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    attempt, sha = os.environ["GITHUB_RUN_ATTEMPT"], os.environ["GITHUB_SHA"]
    jobs = api(f"/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")["jobs"]
    artifacts = api(f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    summary = {"schema": 1, "module": "EXReaderCredentials", "module_version": "0.1.0", "source_sha": sha,
               "run_id": int(run_id), "attempt": int(attempt), "platforms": {}, "granted": [], "pending": []}
    for key, (label, job_name) in PLATFORMS.items():
        job = next((j for j in jobs if j["name"] == job_name), None)
        name = f"reader-credentials-{key}-{run_id}-{attempt}"
        artifact = next((a for a in artifacts if a["name"] == name), None)
        report_path = Path(args.reports) / name / "evidence" / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        entry = {
            "label": label,
            "job_id": job and job["id"],
            "job_conclusion": job and job["conclusion"],
            "artifact": artifact and {"id": artifact["id"], "name": name, "bytes": artifact["size_in_bytes"],
                                      "digest": artifact.get("digest"), "expires_at": artifact["expires_at"]},
        }
        if report:
            entry.update({k: report.get(k) for k in ("accepted", "checks", "passed", "expected_checks",
                                                     "phase_labels", "unavailable_scenarios", "not_exercised")})
            entry["secret_hits"] = report.get("secret_scan", {}).get("hits")
            entry["same_source"] = report.get("source_sha") == sha and report.get("run_id") == run_id \
                and report.get("run_attempt") == attempt
        granted = bool(report and report.get("accepted") and entry.get("same_source") and job
                       and job["conclusion"] == "success" and artifact and artifact.get("digest"))
        entry["granted"] = granted
        summary["platforms"][key] = entry
        (summary["granted"] if granted else summary["pending"]).append(key)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    (out / "aggregate.json").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
