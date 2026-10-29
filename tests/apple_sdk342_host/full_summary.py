#!/usr/bin/env python3
"""Authenticate all original same-run supplemental receipts; no final-product grant."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_parallel_integration import fetch, download_artifact_zip

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    source, run, attempt = (os.environ[k] for k in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    output = ROOT / "build/apple-sdk342-full-summary.json"
    result = {"source_sha": source, "run_id": run, "attempt": attempt, "accepted": False,
              "complete_product_accepted": False, "physical_device": False, "artifacts": [], "failures": []}
    try:
        platforms = ("macos", "iphone", "ipad")
        suites = ("font", "original", "organization", "sync")
        expected = {"Team24 Apple installed " + t for t in ("macos", "iphonesimulator")}
        expected |= {"Team24 Apple native " + p for p in platforms}
        expected |= {"Apple 3.42 " + s + " " + p for p in platforms for s in suites}
        expected.add("Team24 Apple original ZIP authentication")
        jobs = fetch("actions/runs/%s/attempts/%s/jobs?per_page=100" % (run, attempt))["jobs"]
        producers = [j for j in jobs if j["name"] in expected]
        assert len(producers) == len(expected) and {j["name"] for j in producers} == expected
        result["jobs"] = [{k: j[k] for k in ("id", "name", "head_sha", "status", "conclusion")} for j in producers]
        assert all(j["head_sha"] == source and j["status"] == "completed" and j["conclusion"] == "success" for j in producers)
        artifacts = fetch("actions/runs/%s/artifacts?per_page=100" % run)["artifacts"]
        for platform in platforms:
            for suite in suites:
                name = "apple-sdk342-supplemental-%s-%s-%s-%s" % (suite, platform, run, attempt)
                matches = [a for a in artifacts if a["name"] == name]
                assert len(matches) == 1
                a = matches[0]
                assert not a["expired"] and a["workflow_run"]["head_sha"] == source
                raw = download_artifact_zip(a["id"])
                assert len(raw) == a["size_in_bytes"] and "sha256:" + hashlib.sha256(raw).hexdigest() == a["digest"]
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    names = z.namelist()
                    assert len(names) == len(set(names))
                    assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and "\\" not in n for n in names)
                    receipts = [n for n in names if n.endswith("sdk342-supplemental.json")]
                    assert len(receipts) == 1
                    receipt = json.loads(z.read(receipts[0]))
                    assert (receipt["source_sha"], str(receipt["run_id"]), str(receipt["attempt"]), receipt["platform"], receipt["suite"]) == (source, run, attempt, platform, suite)
                    assert receipt["accepted"] is True and receipt["sdk_version"] == "3.42.0" and receipt["physical_device"] is False
                    base = receipts[0][:-len("sdk342-supplemental.json")]
                    for path, item in receipt["files"].items():
                        data = z.read(base + path)
                        assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
                    expected_programs = {"sync", "failure"} if suite == "sync" else {suite}
                    assert set(receipt["programs"]) == expected_programs
                    for role, program in receipt["programs"].items():
                        assert program["bundle_source_sha"] == source and program["sdk_version"] == "3.42.0"
                        with zipfile.ZipFile(io.BytesIO(z.read(base + role + "-app.zip"))) as app:
                            info_path = "EXReaderHost.app/" + ("Contents/Info.plist" if platform == "macos" else "Info.plist")
                            binary_path = "EXReaderHost.app/" + ("Contents/MacOS/EXReaderHost" if platform == "macos" else "EXReaderHost")
                            info = plistlib.loads(app.read(info_path))
                            assert info["EXRSourceSHA"] == source and info["EXRSDKVersion"] == "3.42.0"
                            assert hashlib.sha256(app.read(binary_path)).hexdigest() == program["sha256"]
                    result["artifacts"].append({"id": a["id"], "name": name, "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(), "programs": receipt["programs"]})
        result["accepted"] = len(result["artifacts"]) == 12
    except BaseException as error:
        result["failures"].append(repr(error))
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    assert result["accepted"], "retain exact same-run host gate failure"

if __name__ == "__main__":
    main()
