#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run artifact evidence for the book-information package.

Every platform ZIP is listed through the GitHub API, downloaded in the cloud,
re-hashed, re-sized and unzipped; its report must carry the same source, run,
attempt and platform, the exact named case set and no failure. Nothing is taken
on trust from an upload log.
"""
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
from check_book_information import REQUIRED_CASES  # noqa: E402

PLATFORMS = (("Windows", "windows-2022"), ("Linux", "ubuntu-22.04"), ("macOS", "macos-15"))


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    source = os.environ["GITHUB_SHA"]
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "accepted": False,
        "package": "EXReaderBookInformation 0.1.0",
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "platforms": [],
        "artifacts": [],
        "jobs": [],
        "problems": [],
        "complete_product": False,
    }
    required = set(REQUIRED_CASES)
    try:
        run = fetch("actions/runs/%d" % run_id)
        require(run["head_sha"] == source and run["run_attempt"] == attempt, "caller identity differs")
        require(run["path"].split("@")[0] == ".github/workflows/reader-book-information.yml", "wrong workflow")
        jobs = pages("actions/runs/%d/attempts/%d/jobs" % (run_id, attempt), "jobs")
        artifacts = pages("actions/runs/%d/artifacts" % run_id, "artifacts")
        require(len({row["id"] for row in jobs}) == len(jobs), "duplicate jobs")
        require(len({row["id"] for row in artifacts}) == len(artifacts), "duplicate artifacts")
        per_platform_cases = {}
        for platform, runner in PLATFORMS:
            name = "reader-book-information-%s-%d-%d" % (platform, run_id, attempt)
            job_name = "book information (%s)" % runner
            matches = [row for row in artifacts if row["name"] == name]
            require(len(matches) == 1, "missing or duplicate artifact " + name)
            artifact = matches[0]
            matches = [row for row in jobs if row["name"] == job_name]
            require(len(matches) == 1, "missing or duplicate job " + job_name)
            job = matches[0]
            require(job["head_sha"] == source and job["run_attempt"] == attempt and job["conclusion"] == "success",
                    "upstream job failed or is a different source: " + job_name)
            require(artifact["expired"] is False and artifact["size_in_bytes"] > 0 and
                    artifact["workflow_run"]["head_sha"] == source and artifact["workflow_run"]["id"] == run_id,
                    "artifact identity differs: " + name)
            require(isinstance(artifact.get("digest"), str) and artifact["digest"].startswith("sha256:"),
                    "artifact digest missing: " + name)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact["id"], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ: " + name)
            digest = hashlib.sha256(data).hexdigest()
            require(artifact["digest"] == "sha256:" + digest, "ZIP digest differs: " + name)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [entry for entry in archive.namelist() if entry.endswith("book-info-evidence/report.json")]
                require(len(entries) == 1, "one report required: " + name)
                report = json.loads(archive.read(entries[0]).decode("utf-8"))
            require(report.get("ok") is True, "refused report: " + name)
            require(report.get("source") == source and int(report.get("run_id", 0)) == run_id and
                    int(report.get("attempt", 0)) == attempt, "report identity differs: " + name)
            require(report.get("platform") == platform, "report platform differs: " + name)
            checks = report.get("checks")
            require(isinstance(checks, list) and len(checks) == len(required), "named case count differs: " + name)
            names = [row.get("name") for row in checks]
            require(sorted(names) == sorted(required), "named case set differs: " + name)
            require(all(row.get("ok") is True and isinstance(row.get("assertions"), int) and
                        row["assertions"] > 0 and not row.get("problems") for row in checks),
                    "a named case failed: " + name)
            require(report.get("complete_product") is False and report.get("host_ui_accepted") is False,
                    "scope claims differ: " + name)
            # The named verdicts must be identical on every platform; the number of
            # assertions inside a case may legitimately track a platform-specific
            # poll budget, so it is reported but not compared.
            per_platform_cases[platform] = {row["name"]: bool(row["ok"]) for row in checks}
            summary["artifacts"].append({key: artifact[key] for key in
                                         ("id", "name", "size_in_bytes", "digest", "expires_at")})
            summary["jobs"].append({key: job[key] for key in ("id", "name", "conclusion")})
            summary["platforms"].append({"name": platform, "assertions": report.get("assertions"),
                                         "cases": len(checks), "sha256": digest})
        require(len(per_platform_cases) == 3 and
                per_platform_cases["Windows"] == per_platform_cases["Linux"] == per_platform_cases["macOS"],
                "platform case sets differ")
        summary["accepted"] = True
    except Exception as error:  # noqa: BLE001 - a refusal is the evidence
        summary["problems"].append(str(error))
    (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    raise SystemExit(0 if summary["accepted"] else 1)


if __name__ == "__main__":
    main()
