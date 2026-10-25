#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Red-action regression for the S08 aggregator itself.

Every case builds a synthetic artifact or report in memory, plants one specific
defect, and requires the aggregator's pure checks to refuse it. A clean control
must still be accepted, so the gate cannot pass by rejecting everything.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate import EvidenceError, check_artifact, check_job, check_zip  # noqa: E402

SOURCE = "a" * 40
PLATFORMS = {"windows": "platform (windows-2022)", "linux": "platform (ubuntu-22.04)"}


def good_report(platform: str = "windows", **overrides) -> tuple[dict, dict]:
    files = {"logs/01-opds.stdout.log": b"phase opds 34/34\n",
             "logs/02-credentials.stderr.log": b"",
             "transcript.log": b"[s08] verdict accepted=True\n"}
    manifest = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in sorted(files.items())]
    report = {"schema": 1, "package": "S08", "accepted": True, "platform": platform,
              "job": PLATFORMS[platform], "source_sha": SOURCE, "run_id": 7, "run_attempt": 2,
              "checks": 34, "expected_checks": 34, "passed": 34, "judge_problems": [],
              "detector": {"passed": True},
              "scans": {"final": {"files": 4, "bytes": 120, "hits": 0}},
              "manifest": manifest, "consumer": {"sha256": "b" * 64},
              "phase_labels": ["opds"], "diagnostics": {"opds": {"http": 1}},
              "not_exercised": []}
    report.update(overrides)
    return report, files


def make_zip(report: dict, files: dict, extra: dict | None = None,
             duplicate: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        if duplicate:
            archive.writestr("logs/01-opds.stdout.log", b"phase opds 34/34\n")
        archive.writestr("report.json", json.dumps(report).encode("utf-8"))
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def artifact(**overrides) -> dict:
    item = {"id": 42, "name": "reader-final-s08-windows-7-2", "expired": False,
            "size_in_bytes": 512, "expires_at":
            (datetime.now(timezone.utc) + timedelta(days=60)).isoformat().replace("+00:00", "Z"),
            "workflow_run": {"id": 7},
            "digest": "sha256:" + "c" * 64, "created_at":
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    item.update(overrides)
    return item


def expect_error(label: str, function, fragment: str) -> dict:
    try:
        function()
    except EvidenceError as error:
        return {"case": label, "passed": fragment in str(error), "error": str(error)}
    return {"case": label, "passed": False, "error": "no error"}


def main() -> int:
    results = []
    now = datetime.now(timezone.utc)
    report, files = good_report()
    archive = make_zip(report, files)
    digest = hashlib.sha256(archive).hexdigest()
    expected = {"source_sha": SOURCE, "run_id": 7, "attempt": 2, "platform": "windows",
                "job": PLATFORMS["windows"]}
    try:
        detail = check_zip(archive, digest=digest, expected=expected)
        results.append({"case": "clean-control", "passed": detail["checks"] == 34,
                        "error": ""})
    except EvidenceError as error:
        results.append({"case": "clean-control", "passed": False, "error": str(error)})

    results.append(expect_error(
        "zip-digest", lambda: check_zip(archive, digest="d" * 64, expected=expected),
        "zip_digest_mismatch"))

    slip = make_zip(report, files, extra={"../escape.txt": b"x"})
    results.append(expect_error(
        "zip-slip", lambda: check_zip(slip, digest=hashlib.sha256(slip).hexdigest(),
                                      expected=expected), "zip_entry_unsafe"))

    extra = make_zip(report, files, extra={"unlisted.log": b"x"})
    results.append(expect_error(
        "zip-extra-member", lambda: check_zip(extra, digest=hashlib.sha256(extra).hexdigest(),
                                              expected=expected), "manifest_members"))

    duplicated = make_zip(report, files, duplicate=True)
    results.append(expect_error(
        "zip-duplicate", lambda: check_zip(duplicated,
                                           digest=hashlib.sha256(duplicated).hexdigest(),
                                           expected=expected), "zip_duplicate"))

    broken = dict(report)
    broken["manifest"] = [dict(item) for item in report["manifest"]]
    broken["manifest"][0]["sha256"] = "e" * 64
    broken_zip = make_zip(broken, files)
    results.append(expect_error(
        "manifest-digest", lambda: check_zip(broken_zip,
                                             digest=hashlib.sha256(broken_zip).hexdigest(),
                                             expected=expected), "manifest_digest"))

    wrong_source, files2 = good_report(source_sha="f" * 40)
    wrong_zip = make_zip(wrong_source, files2)
    results.append(expect_error(
        "report-source", lambda: check_zip(wrong_zip,
                                           digest=hashlib.sha256(wrong_zip).hexdigest(),
                                           expected=expected), "report_source"))

    rejected, files3 = good_report(accepted=False)
    rejected_zip = make_zip(rejected, files3)
    results.append(expect_error(
        "report-accepted-false", lambda: check_zip(rejected_zip,
                                                   digest=hashlib.sha256(rejected_zip).hexdigest(),
                                                   expected=expected), "report_rejected"))

    leaking, files4 = good_report()
    leaking["scans"]["final"]["hits"] = 1
    leaking_zip = make_zip(leaking, files4)
    results.append(expect_error(
        "report-scan-hit", lambda: check_zip(leaking_zip,
                                             digest=hashlib.sha256(leaking_zip).hexdigest(),
                                             expected=expected), "report_scan_hits"))

    judged, files5 = good_report(judge_problems=["profiles coverage missing IO"])
    judged_zip = make_zip(judged, files5)
    results.append(expect_error(
        "report-judge", lambda: check_zip(judged_zip,
                                          digest=hashlib.sha256(judged_zip).hexdigest(),
                                          expected=expected), "report_judge"))

    wrong_platform, files6 = good_report(platform="linux")
    wrong_platform_zip = make_zip(wrong_platform, files6)
    results.append(expect_error(
        "report-platform", lambda: check_zip(wrong_platform_zip,
                                             digest=hashlib.sha256(wrong_platform_zip).hexdigest(),
                                             expected=expected), "report_platform"))

    short, files7 = good_report(checks=40)
    short_zip = make_zip(short, files7)
    results.append(expect_error(
        "report-check-count", lambda: check_zip(short_zip,
                                                digest=hashlib.sha256(short_zip).hexdigest(),
                                                expected=expected), "report_check_count"))

    try:
        check_artifact(artifact(), run_id=7, attempt=2, name="reader-final-s08-windows-7-2",
                       now=now)
        results.append({"case": "artifact-clean", "passed": True, "error": ""})
    except EvidenceError as error:
        results.append({"case": "artifact-clean", "passed": False, "error": str(error)})
    results.append(expect_error(
        "artifact-expired",
        lambda: check_artifact(artifact(expired=True), run_id=7, attempt=2,
                               name="reader-final-s08-windows-7-2", now=now),
        "artifact_expired"))
    results.append(expect_error(
        "artifact-expiry-date",
        lambda: check_artifact(artifact(expires_at="2020-01-01T00:00:00Z"), run_id=7, attempt=2,
                               name="reader-final-s08-windows-7-2", now=now),
        "artifact_expiry"))
    results.append(expect_error(
        "artifact-run",
        lambda: check_artifact(artifact(workflow_run={"id": 8}), run_id=7, attempt=2,
                               name="reader-final-s08-windows-7-2", now=now),
        "artifact_run"))
    results.append(expect_error(
        "artifact-name",
        lambda: check_artifact(artifact(), run_id=7, attempt=2, name="other", now=now),
        "artifact_name"))
    results.append(expect_error(
        "artifact-digest",
        lambda: check_artifact(artifact(digest="sha256:short"), run_id=7, attempt=2,
                               name="reader-final-s08-windows-7-2", now=now),
        "artifact_digest"))

    job = {"id": 3, "name": "guard", "conclusion": "success", "head_sha": SOURCE, "run_id": 7,
           "run_attempt": 2}
    try:
        check_job(job, name="guard", source_sha=SOURCE, run_id=7)
        results.append({"case": "job-clean", "passed": True, "error": ""})
    except EvidenceError as error:
        results.append({"case": "job-clean", "passed": False, "error": str(error)})
    results.append(expect_error(
        "job-conclusion",
        lambda: check_job(dict(job, conclusion="failure"), name="guard", source_sha=SOURCE,
                          run_id=7), "job_conclusion"))
    results.append(expect_error(
        "job-source",
        lambda: check_job(dict(job, head_sha="0" * 40), name="guard", source_sha=SOURCE,
                          run_id=7), "job_source"))

    failed = [item for item in results if not item["passed"]]
    for item in results:
        print("%s %s %s" % ("PASS" if item["passed"] else "FAIL", item["case"], item["error"]))
    print("aggregate red actions: %d/%d passed" % (len(results) - len(failed), len(results)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
