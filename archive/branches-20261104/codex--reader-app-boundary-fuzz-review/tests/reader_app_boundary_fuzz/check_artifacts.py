#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-source evidence for the single Linux boundary-fuzz job.

The exact ZIP is downloaded again through the Actions API, its byte length and
sha256 are recomputed, and its contents are bound to the report: named cases,
fuzz journals, consumer binaries and the installed headers must all agree.
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
from boundary_cases import REPLAY_CASES, REQUIRED_CASES  # noqa: E402

WORKFLOW = ".github/workflows/reader-app-boundary-fuzz.yml"
JOB = "app boundary fuzz (ubuntu-22.04)"
TARGETS = ("preferences", "wire-validate", "wire-decode", "wire-receive", "wire-local")
INSTALLED = (
    ("include/reader_preferences.h", "reader_preferences.h"),
    ("include/reader_revisions.h", "reader_revisions.h"),
    ("include/reader_reading_state.h", "reader_reading_state.h"),
    ("lib/libreader_preferences.a", "libreader_preferences.a"),
    ("lib/libreader_revisions.a", "libreader_revisions.a"),
    ("lib/libreader_reading_state.a", "libreader_reading_state.a"),
)


def member(archive, suffix):
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    require(len(matches) == 1, "missing or duplicate artifact member " + suffix)
    return matches[0]


def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "cloud only")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    source = os.environ["GITHUB_SHA"]
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "accepted": False,
        "package": "J23 reader application boundary fuzz",
        "workflow": WORKFLOW,
        "source_sha": source,
        "run_id": run_id,
        "attempt": attempt,
        "platform": "linux",
        "artifacts": [],
        "jobs": [],
        "cases": [],
        "fuzz": [],
        "replay": [],
        "problems": [],
        "granted_platforms": [],
        "windows_accepted": False,
        "macos_accepted": False,
        "android_accepted": False,
        "apple_accepted": False,
        "host_ui_accepted": False,
        "sync_accepted": False,
        "complete_product": False,
    }
    try:
        run = fetch("actions/runs/%d" % run_id)
        require(run["head_sha"] == source and run["run_attempt"] == attempt, "caller identity differs")
        require(run["path"].split("@")[0] == WORKFLOW, "wrong workflow")
        # The evidence job runs before the run itself settles; the upstream job's
        # own conclusion is the authoritative gate here.
        require(run["status"] in ("in_progress", "completed"), "the run has no usable state")

        jobs = pages("actions/runs/%d/attempts/%d/jobs" % (run_id, attempt), "jobs")
        matches = [job for job in jobs if job["name"] == JOB]
        require(len(matches) == 1, "missing or duplicate job " + JOB)
        job = matches[0]
        require(job["head_sha"] == source and job["run_attempt"] == attempt and job["conclusion"] == "success",
                "the fuzz job failed or belongs to another source")

        artifacts = pages("actions/runs/%d/artifacts" % run_id, "artifacts")
        name = "reader-app-boundary-fuzz-linux-%d-%d" % (run_id, attempt)
        matches = [artifact for artifact in artifacts if artifact["name"] == name]
        require(len(matches) == 1, "missing or duplicate artifact " + name)
        artifact = matches[0]
        require(not artifact["expired"] and artifact["size_in_bytes"] > 0 and
                artifact["workflow_run"]["head_sha"] == source and
                artifact["workflow_run"]["id"] == run_id, "artifact identity differs")

        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(artifact["id"], stream)
            stream.seek(0)
            data = stream.read()
        require(len(data) == artifact["size_in_bytes"], "ZIP bytes differ from the API")
        require("sha256:" + hashlib.sha256(data).hexdigest() == artifact["digest"], "ZIP digest differs")

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            report = json.loads(archive.read(member(archive, "evidence/result.json")))
            manifest = json.loads(archive.read(member(archive, "seeds/manifest.json")))

            require(report.get("accepted") is True, "the report refused the run")
            require(report.get("source_sha") == source, "report source differs")
            require(int(report.get("run_id", 0)) == run_id and int(report.get("attempt", 0)) == attempt,
                    "report run identity differs")
            require(report.get("workflow") == WORKFLOW, "report workflow differs")
            require(report.get("platform") == "linux", "report platform differs")
            require(report.get("sdk_sha") == "9854061be331fe603a1822d9b2b36ee357154927", "report SDK differs")
            require(report.get("start_sha") == "f43baf9182d75907c0cb5d6f77048f27bca8c950", "report start differs")
            require(report.get("sdk_changed") is False and report.get("schema_changed") is False,
                    "report claims a protected change")
            require("detect_leaks=1" in report["environment"]["asan_options"], "LeakSanitizer is not recorded")
            require("halt_on_error=1" in report["environment"]["ubsan_options"], "UBSan is not recorded")

            cases = report.get("cases", [])
            by_name = {case["name"]: case for case in cases}
            require(len(by_name) == len(cases), "duplicate named case")
            require(report.get("checks") == len(cases), "the check count differs from the case list")
            require(set(REQUIRED_CASES) <= set(by_name), "a required named case is missing")
            unexpected = [name for name in by_name if name not in REQUIRED_CASES and name not in REPLAY_CASES]
            require(not unexpected, "unexpected named case " + ", ".join(sorted(unexpected)))
            require(all(case["ok"] for case in cases), "a named case failed")
            summary["cases"] = [{"name": case["name"], "ok": case["ok"]} for case in cases]

            fuzz = {entry["target"]: entry for entry in report.get("fuzz", [])}
            require(set(fuzz) == set(TARGETS), "the fuzz target set differs")
            for target in TARGETS:
                entry = fuzz[target]
                require(entry["iterations"] >= 1, "fuzz target %s ran no case" % target)
                require(entry["stop"] in ("iterations", "budget"), "fuzz target %s did not stop cleanly" % target)
                journal = archive.read(member(archive, "work/fuzz/%s/journal.log" % target))
                require(hashlib.sha256(journal).hexdigest() == entry["journal_sha256"],
                        "the %s journal digest differs" % target)
                require(len(journal.splitlines()) == entry["iterations"],
                        "the %s journal lost iterations" % target)
                require(len(entry["current_sha256"]) == 64, "fuzz target %s has no case hash" % target)
                summary["fuzz"].append({key: entry[key] for key in
                                        ("target", "iterations", "stop", "journal_sha256", "current_sha256")})

            replays = report.get("replay", [])
            require(len(replays) == len(TARGETS), "the replay set differs")
            require({entry["target"] for entry in replays} == set(TARGETS), "a replay target is missing")
            require(all(entry["matched"] for entry in replays), "a replay was not deterministic")
            summary["replay"] = [{"target": entry["target"], "case_sha256": entry["case_sha256"],
                                  "matched": entry["matched"]} for entry in replays]

            consumers = report.get("manifest", {}).get("consumers", [])
            require(len(consumers) == 2, "the consumer manifest differs")
            for entry in consumers:
                payload = archive.read(member(archive, "consumer/" + entry["name"]))
                require(len(payload) == entry["bytes"], "consumer bytes differ for " + entry["name"])
                require(hashlib.sha256(payload).hexdigest() == entry["sha256"],
                        "consumer digest differs for " + entry["name"])

            installed = {item["path"]: item for item in report.get("manifest", {}).get("installed", [])}
            for suffix, relative in INSTALLED:
                payload = archive.read(member(archive, "stage/" + suffix))
                entry = installed.get(relative)
                require(entry is not None, "the report omits " + relative)
                require(len(payload) == entry["bytes"], "installed bytes differ for " + relative)
                require(hashlib.sha256(payload).hexdigest() == entry["sha256"],
                        "installed digest differs for " + relative)

            require(manifest.get("generated_by", "").endswith("make_boundary_seeds.py"),
                    "the seed manifest identity differs")
            require(len(manifest.get("seeds", [])) == 25, "the seed count differs")
            for item in manifest["seeds"]:
                payload = archive.read(member(archive, "seeds/" + item["file"]))
                require(len(payload) == item["bytes"], "seed bytes differ from the manifest: " + item["file"])
            fuzz_seeds = [item for item in manifest["seeds"] if item["fuzz"]]
            require(fuzz_seeds and all(item["bytes"] > 0 and item["status"] == "OK" for item in fuzz_seeds),
                    "a fuzz seed is empty or not legal")
            limits = report.get("limits", {})
            require(limits.get("iterations") == 2500 and limits.get("time_budget_ms") == 90000,
                    "the fixed iteration/time budget was changed")
            for target in TARGETS:
                entry = fuzz[target]
                require(entry.get("exit") == 0, "fuzz target %s exited abnormally" % target)
                require(entry["stop"] == "iterations" or entry["iterations"] > 50,
                        "fuzz target %s stopped almost immediately" % target)
            cache = archive.read(member(archive, "logs/consumer-CMakeCache.txt")).decode("utf-8", "replace")
            require("fsanitize=address,undefined" in cache, "the consumers were not built with the sanitizers")
            negative = by_name["harness.crash_and_exit_negative_controls"]["detail"]
            require(negative.get("leak") in (23, -6) and negative.get("hang") == "timeout" and
                    negative.get("abort") == -6 and negative.get("exit-code") == 7,
                    "the negative controls did not observe the real failures")

        summary["accepted"] = True
        summary["granted_platforms"] = ["linux"]
        summary["artifacts"].append({key: artifact[key] for key in
                                     ("id", "name", "size_in_bytes", "digest", "expires_at")})
        summary["jobs"].append({key: job[key] for key in ("id", "name", "conclusion")})
    except Exception as error:  # noqa: BLE001 - refusal is evidence
        summary["problems"].append(str(error))
    (out / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("accepted", "source_sha", "run_id", "attempt", "problems")}), flush=True)
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
