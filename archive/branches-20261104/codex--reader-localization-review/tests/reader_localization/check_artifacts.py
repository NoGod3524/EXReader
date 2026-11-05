#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three localization jobs."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, pages, require
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_localization import REQUIRED_CASES


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    source = os.environ["GITHUB_SHA"]
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "accepted": False,
        "package": "EXReaderLocalization 0.1.0",
        "common_start": "f43baf9182d75907c0cb5d6f77048f27bca8c950",
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "artifacts": [],
        "jobs": [],
        "problems": [],
        "granted_platforms": [],
        "catalog_digests": {},
        "macos_accepted": False,
        "performance_claimed": False,
        "host_ui_accepted": False,
        "six_platform_accepted": False,
        "complete_product": False,
        "sdk_changed": False,
        "schema_changed": False,
        "host_strings_changed": False,
    }
    try:
        run = fetch("actions/runs/%d" % run_id)
        require(run["head_sha"] == source and run["run_attempt"] == attempt,
                "caller identity differs")
        require(run["path"] == ".github/workflows/reader-localization.yml", "wrong workflow")
        jobs = pages("actions/runs/%d/attempts/%d/jobs" % (run_id, attempt), "jobs")
        artifacts = pages("actions/runs/%d/artifacts" % run_id, "artifacts")
        outcomes = []
        digests = {}
        for platform, runner in (("Linux", "ubuntu-22.04"), ("Windows", "windows-2022"),
                                 ("macOS", "macos-14")):
            artifact_name = "reader-localization-%s-%d-%d" % (platform, run_id, attempt)
            job_name = "localization consumers (%s)" % runner
            matches = [a for a in artifacts if a["name"] == artifact_name]
            require(len(matches) == 1, "missing or duplicate artifact " + artifact_name)
            artifact = matches[0]
            matches = [j for j in jobs if j["name"] == job_name]
            require(len(matches) == 1, "missing or duplicate job " + job_name)
            job = matches[0]
            require(job["head_sha"] == source and job["run_attempt"] == attempt and
                    job["conclusion"] == "success", "upstream failed or different source")
            require(not artifact["expired"] and artifact["size_in_bytes"] > 0 and
                    artifact["workflow_run"]["head_sha"] == source, "artifact identity differs")
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact["id"], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ")
            require("sha256:" + hashlib.sha256(data).hexdigest() == artifact["digest"],
                    "ZIP digest differs")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                report = json.loads(archive.read("localization-evidence/result.json"))
            require(report.get("accepted") is True, "report refused")
            require(report.get("source_sha") == source and int(report.get("run_id", 0)) == run_id and
                    int(report.get("attempt", 0)) == attempt, "report identity differs")
            require(report.get("granted_platform") == platform.lower(), "platform grant differs")
            require(bool(report.get("macos_accepted")) == (platform == "macOS"),
                    "macOS grant differs")
            require(int(report.get("checks", 0)) == len(REQUIRED_CASES) and
                    len(report.get("cases", [])) == len(REQUIRED_CASES),
                    "required case count differs")
            cases = sorted((case["name"], bool(case["ok"])) for case in report["cases"])
            require({name for name, _ in cases} == set(REQUIRED_CASES),
                    "required case identity differs")
            require(all(ok for _, ok in cases), "a named case failed")
            digests[platform] = report.get("catalog_digest", "")
            require(len(digests[platform]) == 64, "catalog digest missing")
            bindings = report.get("bindings") or {}
            require({"header", "library", "c-consumer", "cpp-consumer", "worker"} <= set(bindings),
                    "consumer or install binding is missing")
            for name, entry in bindings.items():
                require(int(entry.get("bytes", 0)) > 0, "bound artifact %s is empty" % name)
                require(re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))) is not None,
                        "bound artifact %s has no digest" % name)
            require(bindings["c-consumer"]["sha256"] != bindings["worker"]["sha256"],
                    "the C consumer and the worker share a digest")
            summary.setdefault("bindings", {})[platform] = {
                name: bindings[name]["sha256"] for name in
                ("library", "c-consumer", "cpp-consumer", "worker")}
            outcomes.append(cases)
            summary["artifacts"].append({key: artifact[key] for key in
                                         ("id", "name", "size_in_bytes", "digest", "expires_at")})
            summary["jobs"].append({key: job[key] for key in ("id", "name", "conclusion")})
            summary["granted_platforms"].append(platform.lower())
        require(len(outcomes) == 3 and outcomes[0] == outcomes[1] == outcomes[2],
                "platform case sets differ")
        require(len(set(digests.values())) == 1, "catalog digests differ across platforms")
        summary["catalog_digests"] = digests
        summary["accepted"] = True
        summary["macos_accepted"] = True
    except Exception as error:  # noqa: BLE001 - refusal is evidence
        summary["problems"].append(str(error))
    (out / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary["accepted"] else 1)


if __name__ == "__main__":
    main()
