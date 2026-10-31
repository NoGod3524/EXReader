#!/usr/bin/env python3
"""Cloud self-check for fail-closed reading measurement evidence."""
# SPDX-License-Identifier: MIT
import copy
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from measure_reading_core import accepted, sha256, validate_sample
import measure_reading_core as runner


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sample = {"schema_version": 2, "engine_version": "self-check-only",
              "clock": "monotonic", "disk_cache": "uncontrolled",
              "rss_metric": "process_high_water_mark", "mode": "generated_txt",
              "layout_mode": "paged", "total_pages_known": False,
              "font_open_ms": 1, "publication_open_ms": 1, "first_layout_ms": 1,
              "first_paint_ms": 1, "first_visible_total_ms": 4,
              "input_bytes": 1048576, "text_bytes": 1048576, "part_count": 1,
              "part_index": 0, "page_count": 33, "glyph_count": 100,
              "sample_count": 32, "baseline_peak_rss_bytes": 100,
              "peak_rss_bytes": 200, "incremental_peak_rss_bytes": 100,
              "sample_first_page": 1, "single_page_repaint": False}
    for metric, value in (("turn_layout", 1), ("turn_render", 1), ("turn_total", 2)):
        sample[metric + "_ms_samples"] = [value] * 32
        sample[metric + "_p50_ms"] = sample[metric + "_p95_ms"] = value
    validate_sample(sample)
    rejected = 0
    for field, value in (("first_layout_ms", -1), ("peak_rss_bytes", float("nan")),
                         ("sample_count", 31), ("mode", "indexed_epub"),
                         ("layout_mode", "eager"), ("input_bytes", 42),
                         ("turn_total_p95_ms", 999), ("turn_render_ms_samples", [1]),
                         ("first_visible_total_ms", 0)):
        invalid = dict(sample, **{field: value})
        try:
            validate_sample(invalid)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError(f"Invalid sample accepted: {field}")
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        raw, log = output / "run-1.json", output / "run-1.stderr.log"
        raw.write_text(json.dumps(sample), encoding="utf-8")
        log.write_text("", encoding="utf-8")
        identity = {"source_sha": "a" * 40, "source_clean": True}
        summary = {"before": identity, "after": dict(identity), "expected_source_sha": "a" * 40,
                   "compiler": {"exit_code": 0}, "runs_requested": 1,
                   "attempts": [{"exit_code": 0, "stdout": raw.name, "stderr": log.name,
                                 "stdout_sha256": sha256(raw), "stderr_sha256": sha256(log)}]}
        require(accepted(summary, output), "Valid raw sample rejected")
        invalid_summaries = []
        for change in ({"runs_requested": 2}, {"attempts": []},
                       {"compiler": {"exit_code": 1}}, {"expected_source_sha": "b" * 40},
                       {"after": dict(identity, source_sha="b" * 40)},
                       {"before": dict(identity, source_clean=False)}):
            invalid_summaries.append(dict(summary, **change))
        for change in ({"exit_code": 1}, {"failure": "timeout"}, {"failure": "invalid_report"},
                       {"stdout": "../run-1.json"}, {"stdout_sha256": "0" * 64}):
            invalid = copy.deepcopy(summary)
            invalid["attempts"][0].update(change)
            invalid["accepted"] = True  # A forged success flag has no authority.
            invalid_summaries.append(invalid)
        for invalid in invalid_summaries:
            require(not accepted(invalid, output), "Invalid summary accepted")
            rejected += 1
        raw.write_text("{}", encoding="utf-8")
        require(not accepted(summary, output), "Modified raw report accepted")
        summary["attempts"][0]["stdout_sha256"] = sha256(raw)
        require(not accepted(summary, output), "Rehashed invalid raw report accepted")
        raw.unlink()
        require(not accepted(summary, output), "Missing raw report accepted")
        rejected += 3
        binary, font = output / "binary", output / "font"
        binary.write_bytes(b"fake")
        font.write_bytes(b"fake")
        real_run = subprocess.run
        compiler_command = ["self-check-compiler", "--version"]
        benchmark_command = [str(binary), "--text-bytes", "1048576", str(font),
                             "--paging", "--max-pages", "32"]
        for outcome in ("failure", "timeout", "invalid", "success"):
            destination = output / outcome
            def fake_run(command, **kwargs):
                if command == compiler_command:
                    return subprocess.CompletedProcess(command, 0, b"self-check compiler", b"")
                if command != benchmark_command:
                    return real_run(command, **kwargs)
                kwargs["stdout"].write(json.dumps(sample if outcome != "invalid" else {}).encode())
                kwargs["stderr"].write(b"retained self-check diagnostic")
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired(command, 1)
                return subprocess.CompletedProcess(command, 1 if outcome == "failure" else 0)
            argv = ["measure_reading_core.py", str(binary), str(font), str(destination),
                    "--runs", "2", "--source-sha", "a" * 40, "--compiler", "self-check-compiler"]
            with patch.object(sys, "argv", argv), patch.object(runner, "identity", return_value=identity), \
                    patch.object(runner.subprocess, "run", side_effect=fake_run), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = runner.main()
                saved = json.loads((destination / "summary.json").read_text())
                require((code == 0) == (outcome == "success"), "Wrong process result")
                require(saved["accepted"] == (outcome == "success"), "Wrong retained acceptance")
                require(len(saved["attempts"]) == 2, "Dropped failed attempt")
                require((saved["median"] is not None) == (outcome == "success"), "Misleading median")
                require(all((destination / item["stderr"]).read_bytes() for item in saved["attempts"]),
                        "Lost stderr")
                try:
                    runner.main()
                except FileExistsError:
                    pass
                else:
                    raise RuntimeError("Existing output directory overwritten")
            rejected += outcome != "success"
    print(json.dumps({"self_check_passed": True, "negative_cases": rejected,
                      "measurement_accepted": False, "scope": "validator_self_check_only"}))


if __name__ == "__main__":
    main()
