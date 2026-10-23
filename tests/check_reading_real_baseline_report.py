#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic baseline provenance tests; no reading/performance credit."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import measure_reading_real as gate

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("Run report provenance tests in Actions")

identity = {"source_clean": True, "sdk_candidate": gate.SDK, "sdk_trees": {"src": "a" * 40},
            "font": {"sha256": "b" * 64}, "inputs": {"fixture": {"sha256": "c" * 64}}, "binary": {"bytes": 100}}
current = {"scope": "linux_representative_reading", "sdk_candidate": gate.SDK, "before": identity,
           "contract_sha256": "d" * 64, "corpus_manifest_sha256": "e" * 64,
           "contract": gate.read(gate.CONTRACT), "files": [{"id": "fixture"}],
           "environment": {"cpu_model": "synthetic", "compiler": "synthetic", "reference": "synthetic"}}
baseline = dict(copy.deepcopy(current), schema=1, source_sha=gate.SDK, run_id="123", run_attempt="1",
                measurement_valid=True, accepted=False, after=copy.deepcopy(identity),
                refusal_regression={"passed": True}, signature_refusal_regression={"passed": True},
                installed_sdk={"bytes": 1000}, results={"cases": {"fixture": {
                    "first_visible_ms": {"p95": 10}, "peak_rss_bytes": {"p95": 1048576},
                    "explicit_snapshot_bytes": {"p95": 0}, "oversize_fallbacks": {"p95": 1}}},
                    "page_signatures": {"fixture": {"0/0": {"pixel_hash": "abc"}}},
                    "pixel_comparisons": [{"case": "fixture", "page": 0, "normalized_mean_absolute_error": .05}]})
budget = {"baseline_source_sha": gate.SDK, "baseline_run_id": 123, "baseline_run_attempt": 1,
          "contract_sha256": "d" * 64, "corpus_manifest_sha256": "e" * 64,
          "cpu_model": "synthetic", "compiler": "synthetic", "consumer_bytes": 105, "installed_sdk_bytes": 1050,
          "cases": {"fixture": {"first_visible_ms": 12.5, "peak_rss_bytes": 2097152,
                                "explicit_snapshot_bytes": 0, "oversize_fallbacks": 1}},
          "page_signatures": baseline["results"]["page_signatures"], "pixel_tolerances": {"fixture/0": .05}}


def check_report(report, limits=None):
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder)
        (output / "baseline-summary.json").write_text(json.dumps(report), encoding="utf-8")
        digest = gate.sha256(output / "baseline-summary.json")
        candidate = copy.deepcopy(current)
        candidate["baseline_origin"] = {"run": {"head_sha": gate.SDK}, "summary_file": "baseline-summary.json", "summary_sha256": digest}
        frozen = copy.deepcopy(limits or budget)
        frozen["baseline_summary_sha256"] = digest
        return gate.verify_baseline_report(frozen, candidate, output)


check_report(baseline)
changes = {
    "incomplete_measurement": lambda r: r.update(measurement_valid=False),
    "wrong_source": lambda r: r.update(source_sha="0" * 40),
    "wrong_run": lambda r: r.update(run_id="124"),
    "wrong_attempt": lambda r: r.update(run_attempt="2"),
    "wrong_contract": lambda r: r.update(contract_sha256="0" * 64),
    "wrong_manifest": lambda r: r.update(corpus_manifest_sha256="0" * 64),
    "changed_sdk_trees": lambda r: r["before"]["sdk_trees"].update(src="0" * 40),
    "wrong_cpu": lambda r: r["environment"].update(cpu_model="other"),
    "wrong_compiler": lambda r: r["environment"].update(compiler="other"),
    "wrong_reference": lambda r: r["environment"].update(reference="other"),
    "missing_results": lambda r: r.pop("results"),
    "missing_signatures": lambda r: r["results"].update(page_signatures={}),
    "missing_refusals": lambda r: r["refusal_regression"].update(passed=False),
}
for name, change in changes.items():
    mutant = copy.deepcopy(baseline)
    change(mutant)
    try:
        check_report(mutant)
    except (ValueError, KeyError):
        continue
    raise AssertionError("Counterfeit baseline report accepted: " + name)
limits_changes = {
    "unbounded_latency": lambda b: b["cases"]["fixture"].update(first_visible_ms=999999),
    "unbounded_rss": lambda b: b["cases"]["fixture"].update(peak_rss_bytes=999999999),
    "new_snapshot": lambda b: b["cases"]["fixture"].update(explicit_snapshot_bytes=1),
    "more_fallbacks": lambda b: b["cases"]["fixture"].update(oversize_fallbacks=2),
    "invented_signatures": lambda b: b.update(page_signatures={}),
    "unbounded_size": lambda b: b.update(installed_sdk_bytes=999999),
    "unbounded_difference": lambda b: b.update(pixel_tolerances={"fixture/0": .9}),
}
for name, change in limits_changes.items():
    mutant = copy.deepcopy(budget)
    change(mutant)
    try:
        check_report(baseline, mutant)
    except ValueError:
        continue
    raise AssertionError("Unbounded baseline-derived budget accepted: " + name)

original_run = gate.subprocess.run
zip_checks = 0
try:
    for mode in ("valid", "wrong_digest", "missing_report"):
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            if mode != "missing_report":
                archive.writestr("reading-real/summary.json", json.dumps(baseline))
        data = zipped.getvalue()
        def fake_download(args, stdout, **kwargs):
            stdout.write(data)
            return subprocess.CompletedProcess(args, 0)
        gate.subprocess.run = fake_download
        origin = {"artifact": {"id": 456, "digest": "sha256:" + hashlib.sha256(data).hexdigest()}}
        if mode == "wrong_digest":
            origin["artifact"]["digest"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as folder:
            try:
                gate.retain_baseline_report(origin, Path(folder))
            except ValueError:
                if mode == "valid":
                    raise
                zip_checks += 1
            else:
                if mode != "valid":
                    raise AssertionError("Untrusted baseline archive accepted: " + mode)
                zip_checks += 1
finally:
    gate.subprocess.run = original_run
print({"scope": "synthetic_baseline_report_and_zip_only", "positive": 2,
       "refused": len(changes) + len(limits_changes) + zip_checks - 1, "passed": True,
       "performance_credit": 0, "real_document_credit": 0})
