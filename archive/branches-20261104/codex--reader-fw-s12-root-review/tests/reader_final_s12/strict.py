#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate the original S12 artifacts of one same-source run.

Reuses the existing repository GitHub helpers (tools/check_parallel_integration)
instead of a second API client. Every accepted byte here is the downloaded
artifact ZIP itself: its size, its digest, its expiry and its run identity, then
a re-hash of the members the platform reports claim to describe. No value is
taken from the working tree or from an earlier run.
"""
import datetime
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, require  # noqa: E402

PRODUCERS = ("source-preflight", "unicode-regression (windows-2022)", "unicode-regression (ubuntu-22.04)",
             "cross-platform byte equality")
STABILITY_PAIRS = (("main.after_seed", "main.after_reattach"), ("main.settled", "main.after_reopen"),
                   ("mirror.receive1", "mirror.receive2"), ("mirror.receive2", "mirror.after_reopen"),
                   ("sidecar.staged", "sidecar.reopened"))


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def member(archive, suffix):
    matches = [name for name in archive.namelist() if name == suffix or name.endswith("/" + suffix)]
    require(len(matches) == 1, "artifact member " + suffix + " is missing or duplicated")
    return matches[0]


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    source, run, attempt = (os.environ[key] for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    jobs = fetch("actions/runs/%s/attempts/%s/jobs?per_page=100" % (run, attempt))["jobs"]
    produced = [row for row in jobs if row["name"] in PRODUCERS]
    require({row["name"] for row in produced} == set(PRODUCERS), "a producer job is missing")
    for row in produced:
        require(row["status"] == "completed" and row["conclusion"] == "success", "producer " + row["name"] + " failed")
        require(row["head_sha"] == source and int(row["run_attempt"]) == int(attempt),
                "producer " + row["name"] + " belongs to another source or attempt")

    artifacts = fetch("actions/runs/%s/artifacts?per_page=100" % run)["artifacts"]
    expected = {"reader-final-s12-source-%s-%s" % (run, attempt)}
    expected |= {"reader-final-s12-%s-%s-%s" % (platform, run, attempt) for platform in ("Windows", "Linux")}
    expected.add("reader-final-s12-compare-%s-%s" % (run, attempt))
    selected = [row for row in artifacts if row["name"] in expected]
    require(len(selected) == len(expected) and {row["name"] for row in selected} == expected,
            "a required artifact is missing or duplicated")

    now = datetime.datetime.now(datetime.timezone.utc)
    retained = []
    platform_reports = {}
    compare_digests = None
    for item in sorted(selected, key=lambda row: row["name"]):
        require(not item["expired"], "artifact " + item["name"] + " expired")
        require(0 < item["size_in_bytes"] <= 512 * 1024 * 1024, "artifact " + item["name"] + " size is implausible")
        require(item["workflow_run"]["id"] == int(run) and item["workflow_run"]["head_sha"] == source,
                "artifact " + item["name"] + " belongs to another run or source")
        expires = datetime.datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        require(expires > now, "artifact " + item["name"] + " has expired")
        raw = download_artifact_zip(item["id"])
        require(len(raw) == item["size_in_bytes"], "downloaded size differs for " + item["name"])
        require("sha256:" + sha256(raw) == item["digest"], "downloaded digest differs for " + item["name"])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())), "duplicate member in " + item["name"])
            if item["name"].startswith("reader-final-s12-source-"):
                report = json.loads(archive.read(member(archive, "report.json")))
                require(report["source_preflight_passed"] is True and report["source"] == source,
                        "source preflight report differs")
                require(report["static_agreement"] is True, "static agreement did not pass")
                require(report["consumer_records"] > 0 and report["c_records"] > 0, "static counts are empty")
            elif item["name"].startswith("reader-final-s12-compare-"):
                compare_digests = json.loads(archive.read(member(archive, "compare.json")))
                require(compare_digests["accepted"] is True, "cross-platform comparison did not pass")
                require(compare_digests["source"] == source and str(compare_digests["run"]) == run
                        and str(compare_digests["attempt"]) == attempt, "comparison belongs to another run")
                require(all(value is True for value in compare_digests["byte_equality"].values()),
                        "cross-platform byte equality did not hold")
            else:
                platform = "Windows" if "-Windows-" in item["name"] else "Linux"
                report = json.loads(archive.read(member(archive, "evidence/report.json")))
                require(report["ok"] is True and report["problems"] == [], platform + " report is not ok")
                require(report["source"] == source and str(report["run"]) == run
                        and str(report["attempt"]) == attempt, platform + " report identity differs")
                observations = archive.read(member(archive, "evidence/observations.txt"))
                c_observations = archive.read(member(archive, "evidence/c-observations.txt"))
                require(report["observation_files"]["consumer"]["sha256"] == sha256(observations),
                        platform + " observations do not match their report")
                require(report["observation_files"]["c"]["sha256"] == sha256(c_observations),
                        platform + " C observations do not match their report")
                suffix = ".exe" if platform == "Windows" else ""
                for target in ("s12-consumer", "s12-c-consumer"):
                    payload = archive.read(member(archive, "consumer/" + target + suffix))
                    require(report["consumers"][target]["sha256"] == sha256(payload),
                            platform + " " + target + " hash differs from the report")
                digests = report["snapshots"]
                for left, right in STABILITY_PAIRS:
                    require(left in digests and right in digests, platform + " stability snapshot is missing")
                    require(digests[left]["sha256"] == digests[right]["sha256"],
                            platform + " bytes moved between " + left + " and " + right)
                require(digests["main.final"]["sha256"] == digests["main.settled"]["sha256"],
                        platform + " read-only reopen changed the product database")
                require(report["integrity"]["agreement_pairs"] == 9, platform + " ABI agreement is incomplete")
                platform_reports[platform] = {
                    "observations": report["observation_files"]["consumer"]["sha256"],
                    "c_observations": report["observation_files"]["c"]["sha256"],
                    "consumer": report["consumers"]["s12-consumer"]["sha256"],
                    "c_consumer": report["consumers"]["s12-c-consumer"]["sha256"],
                    "records": report["observation_files"]["consumer"]["records"],
                    "c_records": report["observation_files"]["c"]["records"],
                    "fixtures": report["fixtures"],
                }
        retained.append({key: item[key] for key in ("id", "name", "size_in_bytes", "digest", "expires_at")})

    require(len(platform_reports) == 2, "both platform reports are required")
    require(platform_reports["Windows"]["observations"] == platform_reports["Linux"]["observations"],
            "platform observations differ")
    require(platform_reports["Windows"]["c_observations"] == platform_reports["Linux"]["c_observations"],
            "platform C observations differ")
    require(platform_reports["Windows"]["fixtures"] == platform_reports["Linux"]["fixtures"],
            "platform fixture digests differ")
    require(compare_digests is not None, "comparison artifact is missing")
    for platform, report in platform_reports.items():
        require(compare_digests["digests"][platform]["observations"] == report["observations"],
                "comparison observations digest differs for " + platform)

    summary = {
        "accepted": True,
        "source": source, "run": run, "attempt": attempt,
        "jobs": {row["name"]: row["id"] for row in produced},
        "artifacts": retained,
        "platforms": sorted(platform_reports),
        "records": {platform: platform_reports[platform]["records"] for platform in platform_reports},
        "c_records": {platform: platform_reports[platform]["c_records"] for platform in platform_reports},
        "binaries": {platform: {"consumer": platform_reports[platform]["consumer"],
                               "c_consumer": platform_reports[platform]["c_consumer"]}
                     for platform in platform_reports},
        "scope": "installed module and path regression only; no host UI, SDK wiring, signing or release grant",
    }
    output = ROOT / "build" / "strict"
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
