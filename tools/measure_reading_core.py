#!/usr/bin/env python3
"""Initial synthetic reading measurements; no performance budget is asserted."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

from run_benchmarks import positive, validate

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("font_open_ms", "publication_open_ms", "first_layout_ms", "first_paint_ms",
           "first_visible_total_ms", "turn_layout_p50_ms", "turn_layout_p95_ms",
           "turn_render_p50_ms", "turn_render_p95_ms", "turn_total_p50_ms",
           "turn_total_p95_ms", "baseline_peak_rss_bytes", "peak_rss_bytes",
           "incremental_peak_rss_bytes")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def identity(binary, font):
    return {"source_sha": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
            "source_clean": not git("status", "--porcelain", "--untracked-files=all"),
            "binary_sha256": sha256(binary), "binary_bytes": binary.stat().st_size,
            "font_sha256": sha256(font), "font_bytes": font.stat().st_size,
            "runner_sha256": sha256(__file__),
            "validator_sha256": sha256(ROOT / "tools/run_benchmarks.py"),
            "benchmark_source_sha256": sha256(ROOT / "tools/benchmark.c")}


def validate_sample(record):
    # The shared validator uses assertions; refuse optimized Python, which removes them.
    if sys.flags.optimize:
        raise ValueError("Run without Python -O/PYTHONOPTIMIZE")
    try:
        validate(record)
        if (record["schema_version"] != 2 or record["mode"] != "generated_txt" or
                record["layout_mode"] != "paged" or record["input_bytes"] != 1048576 or
                record["part_count"] != 1 or record["part_index"] != 0 or
                record["sample_count"] != 32 or record["page_count"] != 33 or
                record["total_pages_known"] is not False or record["glyph_count"] <= 0):
            raise ValueError("Sample does not match the fixed 1 MiB / 32-turn workload")
    except (AssertionError, KeyError, TypeError, OverflowError) as error:
        raise ValueError(f"Invalid benchmark sample: {error}") from error


def read_sample(path):
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON constant: {value}")
    record = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    validate_sample(record)
    return record


def accepted(summary, output):
    """Re-read retained raw samples: passed flags alone cannot grant acceptance."""
    try:
        if (summary["before"] != summary["after"] or not summary["before"]["source_clean"] or
                summary["before"]["source_sha"] != summary["expected_source_sha"] or
                summary["compiler"]["exit_code"] != 0 or summary.get("identity_failure") or
                len(summary["attempts"]) != summary["runs_requested"] or
                summary["runs_requested"] < 1):
            return False
        versions = set()
        for attempt in summary["attempts"]:
            if attempt.get("failure") or attempt.get("exit_code") != 0:
                return False
            for field in ("stdout", "stderr"):
                name = attempt[field]
                if Path(name).name != name or sha256(output / name) != attempt[field + "_sha256"]:
                    return False
            record = read_sample(output / attempt["stdout"])
            versions.add(record["engine_version"])
        return len(versions) == 1
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runs", type=positive, default=3)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--source-sha", required=True, help="Expected full checked-out commit SHA")
    parser.add_argument("--compiler", default=os.environ.get("CC", "cc"),
                        help="Actual compiler executable; queried with --version")
    args = parser.parse_args()
    if len(args.source_sha) != 40 or any(char not in "0123456789abcdef" for char in args.source_sha):
        parser.error("--source-sha must be a full lowercase commit SHA")
    if sys.flags.optimize:
        parser.error("Run without Python -O/PYTHONOPTIMIZE")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    binary, font, output = args.binary.resolve(), args.font.resolve(), args.output.resolve()
    if not binary.is_file() or not font.is_file():
        parser.error("binary and font must be existing files")
    # exist_ok=False also rejects an existing empty directory and symlinks.
    output.mkdir(parents=True, exist_ok=False)
    summary = {"schema_version": 1, "scope": "synthetic_reflow_initial_measurement",
               "expected_source_sha": args.source_sha, "runs_requested": args.runs,
               "accepted": False, "attempts": [], "median": None,
               "binary": str(binary), "font": str(font),
               "disk_cache": "uncontrolled", "process_policy": "fresh process for every run",
               "warmup_runs": 0, "pdf_baseline_complete": False,
               "random_access_baseline_complete": False, "hard_budgets_established": False,
               "rss_scope": "process high-water mark; includes font and generated input",
               "percentile_method": "nearest rank within each process; median across processes",
               "environment": {"os": platform.platform(), "machine": platform.machine(),
                   "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
                   "python": sys.version, "build_environment": {key: os.environ.get(key) for key in
                       ("CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS", "CMAKE_BUILD_TYPE",
                        "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_OS", "RUNNER_ARCH")}}}
    if hasattr(os, "sched_getaffinity"):
        summary["environment"]["available_cpu_count"] = len(os.sched_getaffinity(0))
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        summary["environment"]["cpu_model"] = next((line.split(":", 1)[1].strip()
            for line in cpuinfo.read_text().splitlines() if line.startswith("model name")), None)
    try:
        summary["before"] = identity(binary, font)
        compiler = {"command": [args.compiler, "--version"], "exit_code": None}
        summary["compiler"] = compiler
        try:
            completed = subprocess.run(compiler["command"], capture_output=True, timeout=20)
            compiler.update(exit_code=completed.returncode,
                            stdout=completed.stdout.decode("utf-8", errors="replace"),
                            stderr=completed.stderr.decode("utf-8", errors="replace"))
        except (OSError, subprocess.TimeoutExpired) as error:
            compiler["failure"] = type(error).__name__
        records = []
        for number in range(1, args.runs + 1):
            stdout, stderr = output / f"run-{number}.json", output / f"run-{number}.stderr.log"
            command = [str(binary), "--text-bytes", "1048576", str(font), "--paging", "--max-pages", "32"]
            attempt = {"command": command, "stdout": stdout.name, "stderr": stderr.name,
                       "exit_code": None}
            summary["attempts"].append(attempt)
            try:
                with stdout.open("wb") as out, stderr.open("wb") as err:
                    result = subprocess.run(command, stdout=out, stderr=err, timeout=args.timeout)
                attempt["exit_code"] = result.returncode
                if result.returncode:
                    attempt["failure"] = "process_failure"
                else:
                    try:
                        records.append(read_sample(stdout))
                    except (ValueError, KeyError, TypeError) as error:
                        attempt.update(failure="invalid_report", detail=str(error))
            except subprocess.TimeoutExpired:
                attempt["failure"] = "timeout"
            except OSError as error:
                attempt.update(failure="process_start_failure", detail=str(error))
            for name, path in (("stdout", stdout), ("stderr", stderr)):
                attempt[name + "_sha256"] = sha256(path)
        summary["after"] = identity(binary, font)
        summary["accepted"] = accepted(summary, output)
        if summary["accepted"]:
            summary["engine_version"] = records[0]["engine_version"]
            summary["median"] = {metric: statistics.median(record[metric] for record in records)
                                 for metric in METRICS}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        summary["identity_failure"] = str(error)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                   allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": summary["accepted"], "summary": str(output / "summary.json")}))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
