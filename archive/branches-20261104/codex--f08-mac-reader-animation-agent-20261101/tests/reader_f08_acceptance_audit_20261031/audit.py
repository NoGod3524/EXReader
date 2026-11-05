"""Authenticate frozen F08 native audit receipts; report budgets and coverage without resampling."""
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "build/f08-acceptance-audit"
BASE = "632c7fb65a834f254021a0bcc83462a464ed694c"
REPO = "NoGod3524/EXReader"
OWNED = {"tests/reader_f08_acceptance_audit_20261031/audit.py",
         "tests/reader_f08_acceptance_audit_20261031/pins.json",
         ".github/workflows/dot-f08-acceptance-audit-20261031.yml"}
PRODUCTION = ["apps", "bindings", "cmake", "examples", "extras", "include",
              "src", "tools", "CMakeLists.txt", "CMakePresets.json"]

def need(ok, message):
    if not ok:
        raise ValueError(message)

def command(*args):
    return subprocess.check_output([str(x) for x in args], cwd=ROOT)

def api(path):
    return json.loads(command("gh", "api", "repos/" + REPO + "/" + path))

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(value, source):
    need(all(str(value[k]) == source[k] for k in ("source_sha", "run_id", "attempt")), "source/run/attempt")

def metadata(pin, source):
    meta = api("actions/artifacts/" + str(pin["id"]))
    run = meta["workflow_run"]
    need(meta["id"] == pin["id"] and meta["name"] == pin["name"] and not meta["expired"], "artifact identity")
    need(meta["size_in_bytes"] == pin["bytes"] and meta["digest"] == "sha256:" + pin["sha256"], "artifact bytes")
    need(str(run["id"]) == source["run_id"] and run["head_sha"] == source["source_sha"], "artifact producer")
    need(run["repository_id"] == run["head_repository_id"] == 1421442522, "artifact repository")
    save(OUT / "metadata" / (str(pin["id"]) + ".json"), meta)

def download(pin):
    data = command("gh", "api", "repos/" + REPO + "/actions/artifacts/" + str(pin["id"]) + "/zip")
    need(len(data) == pin["bytes"] and sha(data) == pin["sha256"], "download identity")
    return data

def archive(data, maximum):
    result = zipfile.ZipFile(io.BytesIO(data))
    entries = result.infolist()
    need(0 < len(entries) < 20000 and sum(x.file_size for x in entries) < maximum, "ZIP bounds")
    seen = set()
    for entry in entries:
        path = PurePosixPath(entry.filename)
        key = str(path).casefold()
        need(str(path) != "." and not path.is_absolute() and ".." not in path.parts and
             "\\" not in entry.filename and ":" not in entry.filename and key not in seen, "ZIP path")
        seen.add(key)
        need(not entry.flag_bits & 1 and stat.S_IFMT(entry.external_attr >> 16) in
             (0, stat.S_IFREG, stat.S_IFDIR), "ZIP kind")
    return result

def numeric(value):
    need(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid observation")
    return value

def checks(receipt, limits):
    values = receipt["checks"]
    need(len(values) == len(limits) and {v["metric"] for v in values} == set(limits), "metric inventory")
    result = {}
    for value in values:
        name = value["metric"]
        need(value["maximum"] == limits[name], "predeclared budget changed")
        passed = numeric(value["observed"]) <= limits[name]
        need(value["passed"] is passed, "budget verdict differs")
        result[name] = {**value, "status": "passed" if passed else "failed"}
    return result

def missing(reason):
    return {"status": "not_measured", "reason": reason}

def target(name, source, program, metrics, scope, device, full_workload):
    accepted = full_workload and all(v["status"] == "passed" for v in metrics.values())
    return {"target": name, "producer_run": source["run_id"], "source_sha": source["source_sha"],
            "program_sha256": program, "metrics": metrics, "measurement_scope": scope, "device_class": device,
            "full_product_workload_covered": full_workload, "accepted": accepted}

def apple_metric(entry, suffix, unit):
    found = [v for v in entry["performance_metrics"] if v["identifier"]["_value"].endswith(suffix)]
    if not found:
        return None
    need(len(found) == 1 and found[0]["unitOfMeasurement"]["_value"] == unit, "native metric unit")
    values = [numeric(float(v["_value"])) for v in found[0]["measurements"]["_values"]]
    need(len(values) == 5, "five native iterations")
    return values

def controls():
    valid = {"checks": [{"metric": "frame", "observed": 20, "maximum": 16.67, "passed": False}]}
    need(checks(valid, {"frame": 16.67})["frame"]["status"] == "failed", "failed sample retained")
    for bad in (
        {"checks": []},
        {"checks": [{"metric": "frame", "observed": 20, "maximum": 16.67, "passed": True}]},
        {"checks": [{"metric": "frame", "observed": 20, "maximum": 30, "passed": True}]},
        {"checks": [{"metric": "frame", "observed": float("nan"), "maximum": 16.67, "passed": False}]},
    ):
        try:
            checks(bad, {"frame": 16.67})
        except ValueError:
            pass
        else:
            raise ValueError("negative control accepted")
    source = {"run_id": "1", "source_sha": "test"}
    for metrics, complete in (({"frame": {"status": "passed"}}, False),
                              ({"frame": missing("missing")}, True), ({"frame": {"status": "failed"}}, True)):
        need(not target("control", source, None, metrics, "", "", complete)["accepted"], "false promotion")
    return {"checks": 8, "passed": True}

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "GitHub Actions only")
    need(set(command("git", "diff", "--name-only", BASE, "HEAD").decode().splitlines()) == OWNED, "test/CI-only scope")
    need(not command("git", "status", "--porcelain", "--untracked-files=no").strip(), "modified tracked files")
    OUT.mkdir(parents=True, exist_ok=False)
    save(OUT / "controls.json", controls())
    pins = json.loads((HERE / "pins.json").read_text())
    receipts, profiles, trees = {}, {}, {}
    for name, source in pins.items():
        command("git", "fetch", "--no-tags", "origin", source["source_sha"])
        trees[name] = command("git", "ls-tree", source["source_sha"], "--", *PRODUCTION).decode()
        run = api("actions/runs/" + source["run_id"])
        need(run["head_sha"] == source["source_sha"] and str(run["run_attempt"]) == source["attempt"] and
             run["status"] == "completed", "producer run/attempt")
        jobs = api("actions/runs/" + source["run_id"] + "/attempts/" + source["attempt"] + "/jobs?per_page=100")
        audit_jobs = [j for j in jobs["jobs"] if j["name"] == "audit"]
        need(len(audit_jobs) == 1 and audit_jobs[0]["conclusion"] == "success", "native receipt audit")
        metadata(source["receipt"], source)
        data = download(source["receipt"])
        (OUT / (name + "-receipt.zip")).write_bytes(data)
        with archive(data, 8 * 1024**2) as zipped:
            receipt = json.loads(zipped.read("audit.json"))
        identity(receipt, source)
        need(receipt["authenticated"] is True and receipt["f08_accepted"] is False, "receipt scope")
        entries = receipt["archives"] if name == "apple" else [receipt]
        need({e["artifact_id"] for e in entries} == {p["id"] for p in source["raw"]}, "raw artifact inventory")
        for pin in source["raw"]:
            metadata(pin, source)
            entry = next(e for e in entries if e["artifact_id"] == pin["id"])
            need(entry.get("bytes", entry.get("artifact_bytes")) == pin["bytes"] and
                 entry.get("sha256", entry.get("artifact_sha256")) == pin["sha256"], "raw receipt binding")
        profiles[name] = json.loads(command("git", "show", source["source_sha"] + ":" + source["profile"]))
        need(profiles[name]["sdk_version"] == "3.42.0" and
             profiles[name].get("library_books", profiles[name].get("real_sdk_sources")) == 2202, "SDK/library")
        save(OUT / "profiles" / (name + ".json"), profiles[name])
        receipts[name] = receipt
    need(len(set(trees.values())) == 1, "production source trees differ")
    save(OUT / "production-trees.json", trees)

    # The Android receipt omits the installed APK hash, so verify that payload separately.
    source = pins["android"]
    with archive(download(source["raw"][0]), 2 * 1024**3) as zipped:
        manifest = json.loads(zipped.read("manifest.json"))
        build = json.loads(zipped.read("build.json"))
        identity(manifest, source)
        identity(build, source)
        need(build["sdk_version"] == "3.42.0", "Android SDK")
        apk = zipped.read("packages/app-debug.apk")
        apk_hash = sha(apk)
        need(apk_hash == manifest["files"]["packages/app-debug.apk"]["sha256"] ==
             build["packages"]["app-debug.apk"]["sha256"] == sha(zipped.read("installed/app-debug.apk")), "installed APK")
        need(len(apk) == manifest["files"]["packages/app-debug.apk"]["bytes"], "APK bytes")
        need(json.loads(zipped.read("profile.json")) == profiles["android"], "Android profile")
        save(OUT / "android-build.json", build)
        save(OUT / "android-manifest.json", manifest)

    linux, windows, android, apple = (receipts[k] for k in ("linux", "windows", "android", "apple"))
    need(linux["collection_complete"] and windows["collection_complete"] and android["observation_complete"], "observations")
    need(linux["causal_launches"] == 6 and linux["causal_actions"] == 18 and linux["shelf_content_actions"] == 6 and
         linux["native_frame_incomplete"] == 0 and set(linux["replayed_verifiers"].values()) == {0}, "Linux causal verification")
    need(linux["frame_budget_measured"] is False and windows["frame_budget_measured"] is False, "frame scope")
    lc = checks(linux, {"peak_rss_bytes": 536870912, "cold_first_verified_selection_response_max_ms": 2000,
                       "warm_first_verified_selection_response_max_ms": 2000})
    wc = checks(windows, {"cold_shelf_first_interactive_max_ms": 2000, "warm_shelf_first_interactive_max_ms": 2000,
                         "peak_working_set_bytes": 536870912})
    ac = checks(android, {"ordinary_window_frame_p95_ms": 16.67, "ordinary_window_frame_p99_ms": 33.34,
                         "first_interactive_ms": 2000, "sampled_peak_pss_kib": 524288,
                         "forward_scroll_p95_ms": 16.67, "forward_scroll_p99_ms": 33.34,
                         "reverse_scroll_p95_ms": 16.67, "reverse_scroll_p99_ms": 33.34})
    matrix = [
        target("linux", pins["linux"], linux["program_sha256"],
               {**lc, "frame": missing("GDK phases/viewport composition do not measure application presentation")},
               "Full Release GTK host; 44 original launches plus six causal launches", "Ubuntu 22.04, Xvfb", False),
        target("windows", pins["windows"], windows["program_sha256"],
               {**wc, "frame": missing("Non-frame product sampler")},
               "Full Windows wave-3 host; 60 original launches plus ten interactions", "Hosted Windows 2022 desktop", False),
        target("android", pins["android"], apk_hash, ac,
               "Installed app-debug.apk; shelf Window callbacks and sampled PSS; reader-body/page/font/jump missing",
               "Pixel 6 API 34 x86_64 emulator, SwiftShader", False),
    ]
    for kind in ("macos", "iphone", "ipad"):
        entry = next(e for e in apple["archives"] if e["kind"] == kind)
        need(entry["configuration"] == "Release" and entry["collection_complete"] and entry["original_ui_accepted"] and
             len(entry["original_cases"]) == 7 and all(v["result"] == "Passed" for v in entry["original_cases"]), "Apple cases")
        rss = numeric(entry["native_measurements"]["process_peak_rss_bytes"])
        hitch = apple_metric(entry, ".animation.hitch.time.ratio", "ms per s")
        frames = apple_metric(entry, ".animation.frame.count", "frames")
        frame_result = missing("Native animation frame/hitch metrics absent")
        if hitch is not None and frames is not None and min(frames) > 0:
            frame_result = {"status": "passed" if max(hitch) <= 10 else "failed",
                            "observed": max(hitch), "maximum": 10, "unit": "ms per s",
                            "native_frames": sum(frames), "scope": "five measured shelf scrolls"}
        matrix.append(target(kind, pins["apple"], entry["program_sha256"],
                      {"shelf_animation_hitch": frame_result,
                       "process_peak_rss_bytes": {"status": "passed" if rss <= 536870912 else "failed",
                                                  "observed": rss, "maximum": 536870912},
                       "first_interactive": missing("Original Apple receipt has no first-interactive measurement")},
                      "Release native shelf host; reader-body/page/font/jump metrics missing",
                      "Hosted macOS 15" if kind == "macos" else kind + " simulator on macOS 15", False))
    for row in matrix:
        need(len(row["program_sha256"]) == 64 and all(c in "0123456789abcdef" for c in row["program_sha256"]), "program hash")
    report = {
        "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "receipt_audit_complete": True,
        "scope": "Frozen native audit receipts and producer metadata authenticated; budget verdicts recomputed. "
                 "Native samplers/verifiers are not rerun. Android installed APK additionally rehashed.",
        "common_production_source": True, "production_roots": PRODUCTION, "matrix": matrix,
        "f08_accepted": len(matrix) == 6 and all(row["accepted"] for row in matrix),
    }
    save(OUT / "audit.json", report)
    lines = ["# F08 evidence coverage", "", "F08 accepted: " + str(report["f08_accepted"]), "",
             "| Target | Failed metrics | Unmeasured metrics | Full workload |",
             "| --- | --- | --- | --- |"]
    for row in matrix:
        cells = [row["target"], ", ".join(k for k, v in row["metrics"].items() if v["status"] == "failed") or "none",
                 ", ".join(k for k, v in row["metrics"].items() if v["status"] == "not_measured") or "none",
                 str(row["full_product_workload_covered"])]
        lines.append("| " + " | ".join(cells) + " |")
    summary = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(summary, encoding="utf-8")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write(summary)
    print("F08_ACCEPTANCE_AUDIT", json.dumps(report), flush=True)

if __name__ == "__main__":
    main()
