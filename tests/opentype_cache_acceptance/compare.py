#!/usr/bin/env python3
"""Actions-only fixture execution against two independently installed public SDKs."""
import argparse
import hashlib
import json
import math
import os
import pathlib
import subprocess
import time

P = argparse.ArgumentParser()
P.add_argument("--baseline", required=True)
P.add_argument("--candidate", required=True)
P.add_argument("--fixtures", type=pathlib.Path, required=True)
P.add_argument("--output", type=pathlib.Path, required=True)
A = P.parse_args()
if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("Fixture execution and result parsing are restricted to GitHub Actions")
A.output.mkdir(parents=True, exist_ok=True)
manifest = json.loads((A.fixtures / "manifest.json").read_text())
cases = {c["id"]: c for c in manifest["cases"]}
failures, observations, operations = [], [], []
all_records = []


def fail(where, message):
    failures.append({"where": where, "message": message})


def request(c, rid, **overrides):
    x = dict(c)
    x.update(overrides)
    return {
        "id": rid, "case": c["id"], "text_hex": x["text_hex"],
        "repeat": x.get("repeat", 1), "feature": x.get("feature", "c001"),
        "cancel_calls": x.get("cancel_calls", 0),
        "cancel_progress": x.get("cancel_progress", -1),
        "feature_count": x.get("feature_count", 0),
        "expected": x.get("expected_status", -1),
        "check_expected": not overrides,
    }


def run(label, exe, name, font, rows):
    stem = A.output / (name + "." + label)
    tsv = stem.with_suffix(stem.suffix + ".requests.tsv")
    tsv.write_text("".join("\t".join(str(r[k]) for k in
        ["id", "text_hex", "repeat", "feature", "cancel_calls", "cancel_progress", "feature_count"]) + "\n"
        for r in rows), encoding="ascii")
    start = time.monotonic()
    try:
        proc = subprocess.run([str(pathlib.Path(exe).resolve()), str((A.fixtures / font).resolve()), str(tsv.resolve())],
                              capture_output=True, text=True, timeout=180)
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        stderr, rc = "Dedicated acceptance consumer timeout: 180 seconds; existing regression timeouts remain unchanged", -999
    elapsed = time.monotonic() - start
    stem.with_suffix(stem.suffix + ".jsonl").write_text(stdout)
    stem.with_suffix(stem.suffix + ".stderr.txt").write_text(stderr)
    records = []
    for line in stdout.splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            fail(name + "." + label, "Invalid JSONL: " + line[:200])
    operations.append({"name": name, "sdk": label, "returncode": rc, "seconds": elapsed,
                       "rows": len(records), "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest()})
    if rc != 0 or len(records) != len(rows):
        fail(name + "." + label, f"Consumer exit {rc}; got {len(records)} / {len(rows)} records")
    for r, got in zip(rows, records):
        where = name + "." + label + "." + r["id"]
        all_records.append({"operation": name, "sdk": label, **got})
        if got["id"] != r["id"]:
            fail(where, "Record identity mismatch")
        if not got["cleared"] or not got["finite"]:
            fail(where, "Invalid failure output clearing or non-finite positions")
        if got["status"] != 0 and got["error_code"] != got["status"]:
            fail(where, "Status/error code mismatch")
        if got["cancel_true"] and got["status"] != 9:
            fail(where, "Cancellation callback returned true but SDK did not return EXR_CANCELLED")
        if r["cancel_calls"] and got["create_status"] == 0:
            if got["cancel_calls"] >= r["cancel_calls"] and got["status"] != 9:
                fail(where, "Reached cancellation call threshold without EXR_CANCELLED")
        if r["cancel_progress"] >= 0 and got["create_status"] == 0:
            if got["progress_completed"] >= r["cancel_progress"] and got["status"] != 9:
                fail(where, "Reached progress cancellation threshold without EXR_CANCELLED")
        if r["check_expected"]:
            check_expected(where, cases[r["case"]], got)
    return records


def close(a, b):
    return math.isclose(float(a), float(b), abs_tol=1e-5, rel_tol=1e-6)


def check_expected(where, c, got):
    expected = c.get("expected_status", -1)
    if expected >= 0 and got["status"] != expected:
        fail(where, f"Handwritten status {expected}, observed {got['status']}")
    if got["status"] != 0:
        return
    glyphs = got["glyphs"]
    if "expected_glyphs" in c and c["expected_glyphs"] is not None:
        if [g[0] for g in glyphs] != c["expected_glyphs"]:
            fail(where, "Handwritten glyph IDs differ")
    if "expected_ranges" in c and c["expected_ranges"] is not None:
        if [g[1:3] for g in glyphs] != c["expected_ranges"]:
            fail(where, "Handwritten UTF-8 source ranges differ")
    if "expected_flags" in c and c["expected_flags"] is not None:
        expected_flags = c["expected_flags"]
        if isinstance(expected_flags, int):
            expected_flags = [expected_flags] * len(glyphs)
        if [g[7] for g in glyphs] != expected_flags:
            fail(where, "Handwritten flags differ")
    for key, columns in [("expected_advances", (3, 4)), ("expected_offsets", (5, 6))]:
        if key not in c or c[key] is None:
            continue
        expected_values = c[key]
        if len(expected_values) != len(glyphs):
            fail(where, key + " count differs")
            continue
        for g, values in zip(glyphs, expected_values):
            if isinstance(values, (int, float)):
                values = [values, 0]
            if not all(close(g[col], v) for col, v in zip(columns, values)):
                fail(where, key + " differs")
                break


semantic = ["create_status", "status", "error_code", "count", "cleared", "finite", "hashes", "glyphs"]


def pair(name, font, rows, cancellation=False):
    old = run("baseline", A.baseline, name, font, rows)
    new = run("candidate", A.candidate, name, font, rows)
    for r, b, c in zip(rows, old, new):
        differences = {k: {"baseline": b[k], "candidate": c[k]} for k in semantic if b[k] != c[k]}
        callback_diff = {k: [b[k], c[k]] for k in ["cancel_calls", "progress_calls", "progress_hash"]
                         if b[k] != c[k]}
        if differences:
            fail(name + "." + r["id"], "Baseline/candidate semantic difference: " + json.dumps(differences))
        if callback_diff:
            observations.append({"case": name + "." + r["id"], "kind": "callback_work_difference",
                                 "differences": callback_diff})
            fail(name + "." + r["id"], "Candidate promises unchanged work charges and cancellation polls: " + json.dumps(callback_diff))
    return old, new


# Every simple fixture gets both a fresh call and a warm call on the same face.
for cid, case in cases.items():
    old, new = pair("case-" + cid, case["font"], [request(case, cid + "-cold"), request(case, cid + "-warm")])
    for label, records in [("baseline", old), ("candidate", new)]:
        if len(records) == 2:
            for key in semantic + ["cancel_calls", "progress_calls", "progress_hash"]:
                if records[0][key] != records[1][key]:
                    fail("case-" + cid + "." + label, "Cold/warm mismatch in " + key)

# Alternating texts/features on one face are essential: contextual mismatch must
# never be cached as a first-glyph miss, and collisions must retain full keys.
for scenario in manifest.get("scenarios", []):
    steps = scenario["steps"]
    if not steps:
        fail(scenario["id"], "Empty scenario")
        continue
    rows = []
    for round_index in range(3):
        for index, cid in enumerate(steps):
            rows.append(request(cases[cid], f"r{round_index}-s{index}-{cid}"))
    fonts = {cases[cid]["font"] for cid in steps}
    if len(fonts) != 1:
        fail(scenario["id"], "Scenario must use one font instance")
        continue
    old, new = pair("scenario-" + scenario["id"], next(iter(fonts)), rows)
    for label, records in [("baseline", old), ("candidate", new)]:
        for index in range(len(steps)):
            first = records[index] if len(records) > index else None
            for round_index in (1, 2):
                at = round_index * len(steps) + index
                if first and len(records) > at:
                    if any(first[k] != records[at][k] for k in semantic):
                        fail(scenario["id"] + "." + label, "Cold/warm alternating results changed")

# Cancellation is exercised at immediate callbacks, shaping work callbacks, and
# source-progress checkpoints. Raw callback histories remain visible.
normal = next((c for c in cases.values() if c.get("category") == "cancel_source"), None)
if normal is None:
    normal = next((c for c in cases.values() if c.get("expected_status", 0) == 0), None)
if normal:
    longcase = dict(normal)
    longcase["repeat"] = max(4096, normal.get("repeat", 1))
    # Repetition expectations are differential rather than the short handwritten array.
    longcase["expected_status"] = 0
    for k in ["expected_glyphs", "expected_ranges", "expected_flags", "expected_advances", "expected_offsets"]:
        longcase.pop(k, None)
    rows = [request(longcase, "long-observe", repeat=longcase["repeat"])]
    observed_old, observed_new = pair("cancel-observe", longcase["font"], rows)
    thresholds = {1, 2, 3, 4, 8, 16, 32}
    for record in observed_old + observed_new:
        thresholds.update([max(1, record["cancel_calls"] // 2), record["cancel_calls"],
                           record["cancel_calls"] + 1])
    rows = [request(longcase, "call-" + str(n), repeat=longcase["repeat"], cancel_calls=n)
            for n in sorted(thresholds)]
    pair("cancel-callbacks", longcase["font"], rows, cancellation=True)
    size = len(bytes.fromhex(longcase["text_hex"])) * longcase["repeat"]
    rows = [request(longcase, "progress-" + str(n), repeat=longcase["repeat"], cancel_progress=n)
            for n in sorted({0, 1, size // 2, size})]
    pair("cancel-progress", longcase["font"], rows, cancellation=True)
    # Public limits are never changed to make the optimization pass.
    rows = [request(normal, "feature-count-257", feature_count=257),
            request(normal, "text-limit-64m-plus", text_hex="61", repeat=64 * 1024 * 1024 + 1)]
    b, c = pair("public-limits", normal["font"], rows)
    for label, records in [("baseline", b), ("candidate", c)]:
        for r in records:
            if r["status"] != 6:
                fail("public-limits." + label + "." + r["id"], "Expected EXR_LIMIT (6)")

status_counts = {}
for record in all_records:
    key = record["sdk"] + ":" + str(record["status"])
    status_counts[key] = status_counts.get(key, 0) + 1
summary = {
    "record_count": len(all_records), "total_sdk_operations": len(operations),
    "status_counts": status_counts,
    "cancelled_records": sum(r["status"] == 9 for r in all_records),
    "cancel_callbacks": sum(r["cancel_calls"] for r in all_records),
    "cancel_true_callbacks": sum(r["cancel_true"] for r in all_records),
    "progress_callbacks": sum(r["progress_calls"] for r in all_records),
    "work_limit_results": [{k: r[k] for k in ["sdk", "id", "status", "error_code", "count", "cleared", "cancel_calls", "progress_calls"]}
                           for r in all_records if r["operation"] == "case-work_limit"],
    "cancellation_results": [{k: r[k] for k in ["operation", "sdk", "id", "status", "cancel_calls", "cancel_true", "progress_calls", "progress_completed"]}
                             for r in all_records if r["operation"].startswith("cancel-")],
}
report = {"accepted": not failures, "failures": failures, "observations": observations,
          "summary": summary,
          "operations": operations, "case_count": len(cases),
          "scenario_count": len(manifest.get("scenarios", [])),
          "method": "Public installed SDK; one face per scenario; exact field hashes within each platform; no private cache instrumentation",
          "limits": {"consumer_seconds": 180, "product_work_limit_unchanged": 64000000},
          "callback_policy": "Exact return status, callback count and progress trace equivalence; candidate replays original work charges and cancellation polls"}
(A.output / "report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["accepted"] else 1)
