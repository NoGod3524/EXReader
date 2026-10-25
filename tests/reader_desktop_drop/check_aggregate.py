#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rejection regressions for the strict aggregator: every fixture below must be
refused, and a well-formed fixture must pass, so the aggregator cannot silently
accept a missing, expired, tampered or cross-source artifact."""
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone

import aggregate


def make_zip(report, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("evidence/report.json", json.dumps(report))
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def fixture(source_sha="a" * 40, run_id="12345", attempt="1", platform="windows", accepted=True):
    files = {"consumer/drop-probe.exe": b"probe-bytes", "logs/probe.log": b"{}\n"}
    report = {
        "schema": 1,
        "kind": "reader-desktop-drop-report",
        "platform": platform,
        "source_sha": source_sha,
        "run": {"id": run_id, "attempt": attempt, "job": "windows"},
        "cases": {"probe": [{"name": "attach_real_window", "status": "pass", "detail": ""}],
                  "portable": [{"name": "uri_file_existing", "status": "pass", "detail": ""}]},
        "bindings": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                     for name, data in files.items()],
        "accepted": accepted,
        "problems": [] if accepted else ["boom"],
    }
    return make_zip(report, files), report


def expect_reject(label, function, *arguments, **keywords):
    try:
        function(*arguments, **keywords)
    except aggregate.Reject:
        print(f"regression ok: {label} rejected")
        return True
    print(f"regression FAILED: {label} accepted", file=sys.stderr)
    return False


def main():
    failures = 0
    source = "b" * 40
    data, report = fixture(source_sha=source)
    meta = {"id": 7, "bytes": len(data), "expires_at": "2099-01-01T00:00:00Z", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}

    # positive control
    computed = aggregate.validate_download("reader-desktop-drop-windows", data, meta, meta["digest"])
    validated = aggregate.validate_report(report, source, "12345", "1", "windows")
    bound = aggregate.validate_bindings(report, data)
    if computed != hashlib.sha256(data).hexdigest() or validated["probe"] != 1 or bound != 2:
        print("regression FAILED: valid fixture rejected", file=sys.stderr)
        failures += 1
    else:
        print("regression ok: valid fixture accepted")

    # missing artifact
    if not expect_reject("missing artifact", aggregate.pick_artifact, [{"name": "other"}],
                         "reader-desktop-drop-windows-12345-1"):
        failures += 1
    # duplicate artifact
    if not expect_reject("duplicate artifact name", aggregate.pick_artifact,
                         [{"name": "x"}, {"name": "x"}], "x"):
        failures += 1
    # expired
    if not expect_reject("expired artifact", aggregate.validate_entry,
                         {"size_in_bytes": 10, "expires_at": "2000-01-01T00:00:00Z"}, "x"):
        failures += 1
    # zero bytes
    if not expect_reject("zero-byte artifact", aggregate.validate_entry,
                         {"size_in_bytes": 0, "expires_at": "2099-01-01T00:00:00Z"}, "x"):
        failures += 1
    # digest mismatch
    tampered = data[:-1] + b"X"
    if not expect_reject("tampered zip digest", aggregate.validate_download,
                         "reader-desktop-drop-windows", tampered, meta, meta["digest"]):
        failures += 1
    # size mismatch
    if not expect_reject("size mismatch", aggregate.validate_download,
                         "reader-desktop-drop-windows", data + b"extra", meta, meta["digest"]):
        failures += 1
    # cross-source report
    if not expect_reject("cross-source report", aggregate.validate_report,
                         report, "c" * 40, "12345", "1", "windows"):
        failures += 1
    # cross-attempt report
    if not expect_reject("cross-attempt report", aggregate.validate_report,
                         report, source, "12345", "2", "windows"):
        failures += 1
    # wrong platform
    if not expect_reject("wrong platform report", aggregate.validate_report,
                         report, source, "12345", "1", "linux"):
        failures += 1
    # binding hash tampered inside the zip
    broken = json.loads(json.dumps(report))
    broken["bindings"][0]["sha256"] = "0" * 64
    if not expect_reject("binding hash mismatch", aggregate.validate_bindings, broken, data):
        failures += 1
    # binding points at a missing member
    missing = json.loads(json.dumps(report))
    missing["bindings"].append({"path": "logs/absent.log", "sha256": "0" * 64, "bytes": 1})
    if not expect_reject("binding member missing", aggregate.validate_bindings, missing, data):
        failures += 1
    # report marked unaccepted
    rejected_report = dict(report)
    rejected_report["accepted"] = False
    rejected_report["problems"] = ["boom"]
    if not expect_reject("unaccepted report", aggregate.validate_report,
                         rejected_report, source, "12345", "1", "windows"):
        failures += 1
    # failed case inside the report
    failing = json.loads(json.dumps(report))
    failing["cases"]["probe"][0]["status"] = "fail"
    if not expect_reject("failed case in report", aggregate.validate_report,
                         failing, source, "12345", "1", "windows"):
        failures += 1

    now = datetime.now(timezone.utc)
    if aggregate.validate_entry({"size_in_bytes": 1, "expires_at": "2099-01-01T00:00:00Z"}, "x", now)["bytes"] != 1:
        print("regression FAILED: fresh artifact rejected", file=sys.stderr)
        failures += 1
    print(f"rejections: {13 - failures}/13")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
