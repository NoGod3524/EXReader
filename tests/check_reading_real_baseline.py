#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic metadata tests only; these grant no performance or document credit."""
import copy
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import measure_reading_real as gate

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("Run baseline gate tests in Actions")

source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
budget = {"baseline_run_id": 123, "baseline_source_sha": gate.SDK, "baseline_run_attempt": 1,
          "baseline_artifact_id": 456, "baseline_artifact_digest": "sha256:" + "a" * 64}
good = {
    "run": {"id": 123, "head_sha": gate.SDK, "run_attempt": 1, "status": "completed",
            "conclusion": "success", "path": ".github/workflows/reading-real.yml"},
    "jobs": [{"name": "reading-performance", "head_sha": gate.SDK, "status": "completed", "conclusion": "success"}],
    "artifacts": [{"id": 456, "name": "reading-real-123-1", "digest": budget["baseline_artifact_digest"],
                   "expired": False, "size_in_bytes": 100,
                   "workflow_run": {"id": 123, "head_sha": gate.SDK}}],
}


def evaluate(record, candidate=source):
    gate.fetch = lambda path: record["run"]
    gate.pages = lambda path, key: record[key]
    return gate.baseline_origin(budget, candidate)


evaluate(copy.deepcopy(good))
changes = {
    "failed_run": lambda r: r["run"].update(conclusion="failure"),
    "foreign_source": lambda r: r["run"].update(head_sha="0" * 40),
    "old_attempt": lambda r: r["run"].update(run_attempt=2),
    "wrong_workflow": lambda r: r["run"].update(path=".github/workflows/native.yml"),
    "missing_job": lambda r: r["jobs"].clear(),
    "skipped_job": lambda r: r["jobs"][0].update(conclusion="skipped"),
    "missing_artifact": lambda r: r["artifacts"].clear(),
    "expired_artifact": lambda r: r["artifacts"][0].update(expired=True),
    "empty_artifact": lambda r: r["artifacts"][0].update(size_in_bytes=0),
    "changed_digest": lambda r: r["artifacts"][0].update(digest="sha256:" + "b" * 64),
    "cross_source_artifact": lambda r: r["artifacts"][0]["workflow_run"].update(head_sha="0" * 40),
}
for name, change in changes.items():
    record = copy.deepcopy(good)
    change(record)
    try:
        evaluate(record)
    except ValueError:
        continue
    raise AssertionError("Metadata refusal accepted: " + name)
try:
    evaluate(copy.deepcopy(good), gate.SDK)
except ValueError:
    pass
else:
    raise AssertionError("Current source masqueraded as earlier baseline")
print({"scope": "synthetic_baseline_metadata_only", "positive": 1, "refused": len(changes) + 1,
       "accepted": True, "real_document_credit": 0, "performance_credit": 0})
