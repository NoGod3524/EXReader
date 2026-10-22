#!/usr/bin/env python3
"""Cloud-only checks for PDF/CBZ measurement evidence rejection."""
# SPDX-License-Identifier: MIT
import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from measure_reading_pdf import CASES, FONT_SHA256, ROOT, evaluate, require, sha256, validate


def sample(case):
    record = {"schema_version": 1, "engine_version": "self-check-only", "success": True,
              "status": 0, "error_stage": "complete", "clock": "monotonic", "disk_cache": "uncontrolled",
              "rss_metric": "process_high_water_mark", "scale": 1, "channels": 4, "background": "ffffffff",
              "pixel_hash_algorithm": "fnv1a64-active-rgba", "seed": 20261022, "random_turns": 16,
              "page_count": case["pages"], "sample_count": 1 + case["pages"] + 16, "directory_owned_bytes": 100,
              "font_open_ms": 1, "fixed_open_ms": 1, "directory_ms": 1, "first_visible_total_ms": 4,
              "baseline_peak_rss_bytes": 100, "peak_rss_bytes": 200, "incremental_peak_rss_bytes": 100,
              "samples": []}
    plan = [("first", 0)] + [("sequential", page) for page in range(case["pages"])]
    random = 20261022
    for _ in range(16):
        random = (random * 1664525 + 1013904223) & 0xffffffff
        plan.append(("random", random % case["pages"]))
    for phase, page in plan:
        record["samples"].append({"phase": phase, "page": page, "status": 0, "render_ms": 1,
                                  "width": 2, "height": 2, "channels": 4, "pixel_bytes": 16,
                                  "pixel_hash": f"{page + 1:016x}"})
    return record


def rejected(function, *args):
    try:
        function(*args)
    except (ValueError, KeyError, TypeError, OSError):
        return
    raise RuntimeError("Invalid measurement evidence accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/reading-pdf-selfcheck")
    args = parser.parse_args()
    checks = 0
    for case in CASES.values():
        valid = sample(case)
        validate(valid, case)
        for field, value in (("success", False), ("status", 1), ("page_count", 99),
                             ("random_turns", 15), ("scale", 2), ("font_open_ms", -1),
                             ("fixed_open_ms", float("nan")), ("peak_rss_bytes", 0),
                             ("sample_count", 1), ("first_visible_total_ms", 0)):
            rejected(validate, dict(valid, **{field: value}), case)
            checks += 1
        for field, value in (("render_ms", float("inf")), ("status", 1), ("page", 999),
                             ("pixel_hash", "x" * 16), ("pixel_bytes", 0), ("width", 8192)):
            invalid = copy.deepcopy(valid)
            invalid["samples"][-1][field] = value
            rejected(validate, invalid, case)
            checks += 1
        invalid = copy.deepcopy(valid)
        invalid["samples"][1]["pixel_hash"] = "0" * 16
        rejected(validate, invalid, case)
        checks += 1
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        identity = {"source_sha": "a" * 40, "source_clean": True, "font_sha256": FONT_SHA256,
                    "inputs": {name: {"bytes": case["bytes"], "sha256": case["sha256"]}
                               for name, case in CASES.items()}}
        summary = {"before": identity, "after": copy.deepcopy(identity), "expected_source_sha": "a" * 40,
                   "compiler": {"exit_code": 0}, "runs_requested": 1, "attempts": []}
        for name, case in CASES.items():
            raw, log = output / f"{name}.json", output / f"{name}.stderr.log"
            raw.write_text(json.dumps(sample(case)), encoding="utf-8")
            log.write_text("", encoding="utf-8")
            summary["attempts"].append({"case": name, "run": 1, "exit_code": 0,
                "stdout": raw.name, "stderr": log.name, "stdout_sha256": sha256(raw), "stderr_sha256": sha256(log)})
        evaluate(summary, output)
        changes = [{"runs_requested": 2}, {"attempts": []}, {"compiler": {"exit_code": 1}},
                   {"expected_source_sha": "b" * 40}, {"after": dict(identity, font_sha256="0" * 64)}]
        for change in changes:
            rejected(evaluate, dict(summary, **change), output)
            checks += 1
        for change in ({"exit_code": 1}, {"failure": "timeout"}, {"stdout_sha256": "0" * 64},
                       {"stdout": "../pdf.json"}, {"case": "unknown"}):
            invalid = copy.deepcopy(summary)
            invalid["accepted"] = True
            invalid["attempts"][0].update(change)
            rejected(evaluate, invalid, output)
            checks += 1
        raw = output / summary["attempts"][0]["stdout"]
        raw.write_text("{}", encoding="utf-8")
        rejected(evaluate, summary, output)
        summary["attempts"][0]["stdout_sha256"] = sha256(raw)
        rejected(evaluate, summary, output)
        raw.unlink()
        rejected(evaluate, summary, output)
        checks += 3
    if args.binary:
        args.output.mkdir(parents=True, exist_ok=False)
        raw, log = args.output / "native-failure.json", args.output / "native-failure.stderr.log"
        with raw.open("wb") as out, log.open("wb") as err:
            result = subprocess.run([str(args.binary.resolve()), str(ROOT / "tests/fixtures/pdf-bad-header.pdf"),
                                     str(ROOT / "tests/fixtures/fonts/primary.ttf")], stdout=out, stderr=err, timeout=30)
        require(result.returncode != 0, "Native malformed input was accepted")
        report = json.loads(raw.read_text())
        require(report["success"] is False and report["status"] != 0, "Native failure report claims success")
        rejected(validate, report, CASES["pdf"])
        checks += 1
    print(json.dumps({"self_check_passed": True, "negative_cases": checks,
                      "measurement_accepted": False, "scope": "evidence_rejection_self_check_only"}))


if __name__ == "__main__":
    main()
