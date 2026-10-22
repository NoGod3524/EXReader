#!/usr/bin/env python3
"""Source-bound, synthetic PDF/CBZ measurements through an installed native SDK."""
# SPDX-License-Identifier: MIT
import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

from measure_reading_core import ROOT, git, sha256
from run_benchmarks import positive

CASES = {
    "pdf": {"path": "pdf-color/shading-axial.pdf", "bytes": 655, "pages": 1,
            "sha256": "e0b8b52aa4780a3edb036f88a26f5e84997b90ce97bfdcf741ccb8ba7d09a6ee"},
    "cbz": {"path": "comic.cbz", "bytes": 908, "pages": 4,
            "sha256": "08df7ceb8771ab82610651c2299072b8fc299d3f8fba3996ee6e12054ea6701f"}}
FONT_SHA256 = "ce360aed7a09322e2c815ed9c06ce9e3304cdfb886b19493e9e59216d622bfed"
METRICS = ("font_open_ms", "fixed_open_ms", "directory_ms", "first_visible_total_ms",
           "baseline_peak_rss_bytes", "peak_rss_bytes", "incremental_peak_rss_bytes",
           "directory_owned_bytes", "first_render_ms", "random_render_p50_ms", "random_render_p95_ms")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def validate(record, case):
    require(record["schema_version"] == 1 and record["success"] is True and
            record["status"] == 0 and record["error_stage"] == "complete", "Incomplete native run")
    require(isinstance(record["engine_version"], str) and record["engine_version"], "Missing engine version")
    require(record["clock"] == "monotonic" and record["disk_cache"] == "uncontrolled" and
            record["rss_metric"] == "process_high_water_mark", "Wrong measurement scope")
    require(record["scale"] == 1 and record["channels"] == 4 and record["background"] == "ffffffff" and
            record["pixel_hash_algorithm"] == "fnv1a64-active-rgba", "Wrong render parameters")
    require(record["seed"] == 20261022 and record["random_turns"] == 16 and
            record["page_count"] == case["pages"], "Wrong plan/page count")
    for field in METRICS[:8]:
        require(number(record[field]), f"Invalid metric: {field}")
    require(record["peak_rss_bytes"] > 0 and record["peak_rss_bytes"] >= record["baseline_peak_rss_bytes"] and
            record["incremental_peak_rss_bytes"] == record["peak_rss_bytes"] - record["baseline_peak_rss_bytes"],
            "Invalid RSS accounting")
    samples = record["samples"]
    require(record["sample_count"] == len(samples) == 1 + case["pages"] + 16, "Dropped sample")
    expected = [("first", 0)] + [("sequential", page) for page in range(case["pages"])]
    random = 20261022
    for _ in range(16):
        random = (random * 1664525 + 1013904223) & 0xffffffff
        expected.append(("random", random % case["pages"]))
    signatures = {}
    for item, (phase, page) in zip(samples, expected):
        require(item["phase"] == phase and type(item["page"]) is int and item["page"] == page and
                item["status"] == 0 and number(item["render_ms"]), "Invalid render sample/plan")
        require(type(item["width"]) is int and type(item["height"]) is int and
                0 < item["width"] <= 4096 and 0 < item["height"] <= 4096 and item["channels"] == 4 and
                item["pixel_bytes"] == item["width"] * item["height"] * 4, "Invalid bitmap")
        pixel_hash = item["pixel_hash"]
        require(isinstance(pixel_hash, str) and len(pixel_hash) == 16 and
                all(char in "0123456789abcdef" for char in pixel_hash), "Invalid pixel hash")
        signature = [item[key] for key in ("width", "height", "channels", "pixel_bytes", "pixel_hash")]
        require(page not in signatures or signatures[page] == signature, "Same-page redraw changed pixels")
        signatures[page] = signature
    require(record["first_visible_total_ms"] + .00001 >= sum(record[field] for field in
            ("font_open_ms", "fixed_open_ms", "directory_ms")) + samples[0]["render_ms"], "Invalid first-visible timing")
    ordered = sorted(item["render_ms"] for item in samples if item["phase"] == "random")
    metrics = {field: record[field] for field in METRICS[:8]}
    metrics.update(first_render_ms=samples[0]["render_ms"], random_render_p50_ms=ordered[7],
                   random_render_p95_ms=ordered[15], directory_owned_bytes=record["directory_owned_bytes"])
    require(number(metrics["directory_owned_bytes"]), "Invalid directory bytes")
    return metrics, signatures


def read_record(path):
    def reject(value):
        raise ValueError(f"Non-finite JSON: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def snapshot(binary, font, fixtures):
    return {"source_sha": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
            "source_clean": not git("status", "--porcelain", "--untracked-files=all"),
            "binary_sha256": sha256(binary), "binary_bytes": binary.stat().st_size,
            "font_sha256": sha256(font), "font_bytes": font.stat().st_size,
            "inputs": {name: {"sha256": sha256(fixtures / case["path"]),
                               "bytes": (fixtures / case["path"]).stat().st_size} for name, case in CASES.items()},
            "tools": {name: sha256(ROOT / name) for name in
                      ("tools/reading_pdf_benchmark.c", "tools/measure_reading_pdf.py", "tools/measure_reading_core.py",
                       "tools/run_benchmarks.py", "tests/reading_pdf/CMakeLists.txt")}}


def evaluate(summary, output):
    """Derive acceptance from retained raw runs, never from a claimed success flag."""
    before = summary["before"]
    require(before == summary["after"] and before["source_clean"] and
            before["source_sha"] == summary["expected_source_sha"], "Source/input identity changed")
    require(before["font_sha256"] == FONT_SHA256 and summary["compiler"]["exit_code"] == 0,
            "Wrong font/compiler identity")
    for name, case in CASES.items():
        require(before["inputs"][name] == {"sha256": case["sha256"], "bytes": case["bytes"]}, "Fixture drift")
    runs = summary["runs_requested"]
    require(type(runs) is int and 1 <= runs <= 10 and len(summary["attempts"]) == runs * len(CASES), "Missing run")
    metrics, signatures, versions = {name: [] for name in CASES}, {}, set()
    expected_order = [(name, run) for name in CASES for run in range(1, runs + 1)]
    for item, (name, run) in zip(summary["attempts"], expected_order):
        require(item["case"] == name and item["run"] == run and item["exit_code"] == 0 and not item.get("failure"),
                "Failed or misidentified attempt")
        for field in ("stdout", "stderr"):
            filename = item[field]
            require(Path(filename).name == filename and sha256(output / filename) == item[field + "_sha256"],
                    "Missing/changed process output")
        record = read_record(output / item["stdout"])
        values, pixels = validate(record, CASES[name])
        require(name not in signatures or signatures[name] == pixels, "Cross-process pixels changed")
        signatures[name] = pixels
        metrics[name].append(values)
        versions.add(record["engine_version"])
    require(len(versions) == 1, "Engine version mismatch")
    return {"engine_version": next(iter(versions)), "cases": {name: {
                "median": {field: statistics.median(values[field] for values in rows) for field in METRICS},
                "page_signatures": signatures[name]} for name, rows in metrics.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tests/fixtures")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--runs", type=positive, default=3)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--compiler", default="cc")
    args = parser.parse_args()
    if args.runs > 10 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("runs must be 1..10 and timeout positive/finite")
    if len(args.source_sha) != 40 or any(char not in "0123456789abcdef" for char in args.source_sha):
        parser.error("Use a full lowercase source SHA")
    binary, font, fixtures, output = [value.resolve() for value in (args.binary, args.font, args.fixtures, args.output)]
    if not binary.is_file() or not font.is_file():
        parser.error("binary/font must be files")
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": 1, "accepted": False, "expected_source_sha": args.source_sha,
               "scope": "synthetic_pdf_cbz_initial_native_measurement", "cases_frozen": CASES,
               "runs_requested": args.runs, "attempts": [], "results": None,
               "hard_budgets_established": False, "real_document_credit": 0,
               "disk_cache": "uncontrolled", "warmup_runs": 0,
               "render_scope": "exr_fixed_render only; excludes pixel hashing/free",
               "first_visible_scope": "font open through first render, hash and free; excludes process startup",
               "random_scope": "same open document after complete sequential sweep; warmed repeat plan",
               "environment": {"os": platform.platform(), "machine": platform.machine(),
                   "processor": platform.processor(), "logical_cpu_count": os.cpu_count(), "python": sys.version,
                   "build": {key: os.environ.get(key) for key in ("CC", "CXX", "CFLAGS", "CXXFLAGS",
                       "LDFLAGS", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_ARCH")}}}
    try:
        summary["before"] = snapshot(binary, font, fixtures)
        summary["compiler"] = {"command": [args.compiler, "--version"], "exit_code": None}
        try:
            result = subprocess.run(summary["compiler"]["command"], capture_output=True, timeout=20)
            summary["compiler"].update(exit_code=result.returncode,
                stdout=result.stdout.decode("utf-8", errors="replace"), stderr=result.stderr.decode("utf-8", errors="replace"))
        except (OSError, subprocess.TimeoutExpired) as error:
            summary["compiler"]["failure"] = type(error).__name__
        for name, case in CASES.items():
            for run in range(1, args.runs + 1):
                stdout, stderr = output / f"{name}-{run}.json", output / f"{name}-{run}.stderr.log"
                command = [str(binary), str(fixtures / case["path"]), str(font)]
                item = {"case": name, "run": run, "command": command, "exit_code": None,
                        "stdout": stdout.name, "stderr": stderr.name}
                summary["attempts"].append(item)
                try:
                    with stdout.open("wb") as out, stderr.open("wb") as err:
                        completed = subprocess.run(command, stdout=out, stderr=err, timeout=args.timeout)
                    item["exit_code"] = completed.returncode
                    if completed.returncode:
                        item["failure"] = "process_failure"
                except subprocess.TimeoutExpired:
                    item["failure"] = "timeout"
                except OSError as error:
                    item.update(failure="process_start_failure", detail=str(error))
                for field, path in (("stdout", stdout), ("stderr", stderr)):
                    item[field + "_sha256"] = sha256(path)
        summary["after"] = snapshot(binary, font, fixtures)
        summary["results"] = evaluate(summary, output)
        summary["accepted"] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary["failure"] = str(error)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"accepted": summary["accepted"], "results": summary["results"], "failure": summary.get("failure")}))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
