#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Named positive and negative regressions of the evidence verifier (pure Python)."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

from evidence import EvidenceError, artifact_name, expected_checks, verify_archive, verify_artifact, verify_report, verify_jobs, verify_download

SHA, RUN, ATTEMPT = "a" * 40, 4242, 2
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def good_report(platform):
    expected = expected_checks(platform)
    reports = {}
    for name in ("probe", "consumer"):
        checks = [{"id": i, "result": "pass", "detail": "ok"} for i in expected[name]]
        reports[name] = {"exit": 0, "checks": checks, "expected": expected[name], "passed": len(checks), "failed": 0}
    total = sum(len(v["checks"]) for v in reports.values())
    digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
    return {"schema": 1, "platform": platform, "accepted": True, "problems": [], "source_sha": SHA,
            "run_id": str(RUN), "run_attempt": str(ATTEMPT), "job": "native", "reports": reports,
            "total_checks": total, "passed_checks": total, "not_exercised": ["real iCloud"],
            "binaries": {"probe": digest("probe"), "consumer": digest("consumer")},
            "installed_module_sha256": digest("library"),
            "simulator": None if platform == "macos" else {"fresh_device": True, "boot": 0}}


def archive(report, mutate=None, skip=()):
    files = {"out/report.json": json.dumps(report).encode(), "out/probe": b"probe", "out/consumer": b"consumer",
             "prefix/lib/libEXRFileEntry.a": b"library"}
    for name in ("probe", "consumer"):
        lines = ["check %s pass ok" % c["id"] for c in report["reports"][name]["checks"]]
        files["out/evidence/%s/result.txt" % name] = ("\n".join(lines) + "\n").encode()
    if mutate:
        mutate(files)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as target:
        for name, data in files.items():
            if name not in skip:
                target.writestr(name, data)
    return stream.getvalue()


def meta(**override):
    value = {"name": artifact_name("macos", RUN, ATTEMPT), "id": 7, "expired": False, "size_in_bytes": 1000,
             "expires_at": (NOW + timedelta(days=30)).isoformat(), "workflow_run": {"id": RUN, "head_sha": SHA},
             "digest": "sha256:" + "d" * 64}
    value.update(override)
    return value


def good_jobs(**override):
    names = ["scope and negative regressions", "SDK macos", "SDK iphonesimulator", "native macos", "native iphone", "native ipad"]
    jobs = [dict(id=index + 1, name=name, status="completed", conclusion="success", head_sha=SHA, run_id=RUN, run_attempt=ATTEMPT)
            for index, name in enumerate(names)]
    jobs[0].update(override)
    return jobs


def duplicate_zip():
    data = io.BytesIO(archive(good_report("macos")))
    with zipfile.ZipFile(data, "a") as target:
        target.writestr("out/report.json", b"{}")
    return data.getvalue()


def rejects(label, code, action):
    try:
        action()
    except EvidenceError as error:
        if code is not None and str(error) != code:
            raise SystemExit(f"{label}: rejected as {error}, expected {code}")
        return {"id": label, "result": "pass", "rejected_as": str(error)}
    raise SystemExit(f"{label}: invalid evidence was accepted")


def mutated(platform, change):
    report = good_report(platform)
    change(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = []
    # Positive: every platform's well-formed evidence is accepted.
    for platform in ("macos", "iphone", "ipad"):
        report = good_report(platform)
        verify_report(report, platform, SHA, RUN, ATTEMPT)
        verify_archive(archive(report), platform, SHA, RUN, ATTEMPT)
        results.append({"id": f"accepts-complete-{platform}-evidence", "result": "pass"})
    verify_artifact(meta(), "macos", SHA, RUN, ATTEMPT, NOW)
    results.append({"id": "accepts-matching-artifact-metadata", "result": "pass"})
    verify_jobs(good_jobs(), SHA, RUN, ATTEMPT)
    results.append({"id": "accepts-authenticated-upstream-jobs", "result": "pass"})
    data = archive(good_report("macos"))
    download_meta = meta(size_in_bytes=len(data), digest="sha256:" + hashlib.sha256(data).hexdigest())
    verify_download(data, download_meta)
    results.append({"id": "accepts-api-bound-zip-bytes", "result": "pass"})

    def check(report):
        verify_report(report, "macos", SHA, RUN, ATTEMPT)

    negatives = [
        ("rejects-other-source-sha", "report_source", lambda: check(mutated("macos", lambda r: r.update(source_sha="b" * 40)))),
        ("rejects-other-run-id", "report_run", lambda: check(mutated("macos", lambda r: r.update(run_id="1")))),
        ("rejects-other-attempt", "report_run", lambda: check(mutated("macos", lambda r: r.update(run_attempt="1")))),
        ("rejects-wrong-platform-label", "report_platform", lambda: check(mutated("iphone", lambda r: None))),
        ("rejects-accepted-false", "report_not_accepted", lambda: check(mutated("macos", lambda r: r.update(accepted=False)))),
        ("rejects-recorded-problem", "report_not_accepted", lambda: check(mutated("macos", lambda r: r.update(problems=["x"])))),
        ("rejects-missing-check", "check_ids_probe", lambda: check(mutated("macos", lambda r: r["reports"]["probe"]["checks"].pop()))),
        ("rejects-extra-check", "check_ids_consumer", lambda: check(mutated("macos", lambda r: r["reports"]["consumer"]["checks"].append({"id": "extra", "result": "pass", "detail": ""})))),
        ("rejects-duplicate-check-id", "check_ids_probe", lambda: check(mutated("macos", lambda r: r["reports"]["probe"]["checks"].__setitem__(1, deepcopy(r["reports"]["probe"]["checks"][0]))))),
        ("rejects-reordered-checks", "check_ids_probe", lambda: check(mutated("macos", lambda r: r["reports"]["probe"]["checks"].reverse()))),
        ("rejects-failed-check", "check_failed_probe", lambda: check(mutated("macos", lambda r: r["reports"]["probe"]["checks"][3].update(result="fail")))),
        ("rejects-skipped-check", "check_failed_consumer", lambda: check(mutated("macos", lambda r: r["reports"]["consumer"]["checks"][0].update(result="skip")))),
        ("rejects-nonzero-exit", "section_counts_probe", lambda: check(mutated("macos", lambda r: r["reports"]["probe"].update(exit=1)))),
        ("rejects-inflated-counts", "total_counts", lambda: check(mutated("macos", lambda r: r.update(passed_checks=999)))),
        ("rejects-empty-pending-list", "pending_not_listed", lambda: check(mutated("macos", lambda r: r.update(not_exercised=[])))),
        ("rejects-simulator-not-fresh", "simulator_not_fresh", lambda: verify_report(mutated("ipad", lambda r: r["simulator"].update(fresh_device=False)), "ipad", SHA, RUN, ATTEMPT)),
        ("rejects-missing-simulator-on-ios", "simulator_not_fresh", lambda: verify_report(mutated("iphone", lambda r: r.update(simulator=None)), "iphone", SHA, RUN, ATTEMPT)),
        ("rejects-expired-artifact", "artifact_expired", lambda: verify_artifact(meta(expired=True), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-lapsed-expiry", "artifact_expiry", lambda: verify_artifact(meta(expires_at=(NOW - timedelta(days=1)).isoformat()), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-other-head-sha-artifact", "artifact_run", lambda: verify_artifact(meta(workflow_run={"id": RUN, "head_sha": "c" * 40}), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-other-run-artifact", "artifact_run", lambda: verify_artifact(meta(workflow_run={"id": 1, "head_sha": SHA}), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-misnamed-artifact", "artifact_name", lambda: verify_artifact(meta(name="reader-apple-file-entry-macos-1-1"), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-empty-artifact", "artifact_size", lambda: verify_artifact(meta(size_in_bytes=0), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-binary-swapped-in-zip", "binary_digest_mismatch", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"out/probe": b"other"})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-zip-without-report", "zip_report_missing", lambda: verify_archive(archive(good_report("macos"), skip=("out/report.json",)), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-zip-without-installed-module", "installed_module_missing", lambda: verify_archive(archive(good_report("macos"), skip=("prefix/lib/libEXRFileEntry.a",)), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-result-file-mismatch", "result_file_mismatch", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"out/evidence/probe/result.txt": b"check x pass ok\n"})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-path-traversal-member", "zip_path", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"../escape": b"x"})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-corrupt-zip", "zip_invalid", lambda: verify_archive(b"not a zip", "macos", SHA, RUN, ATTEMPT)),
        ("rejects-duplicate-json-key", "json_duplicate_key", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"out/report.json": b'{"schema":1,"schema":1}'})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-missing-api-digest", "artifact_digest", lambda: verify_artifact(meta(digest=None), "macos", SHA, RUN, ATTEMPT, NOW)),
        ("rejects-api-size-mismatch", "download_size", lambda: verify_download(data + b"x", download_meta)),
        ("rejects-api-digest-mismatch", "download_digest", lambda: verify_download(data[:-1] + bytes([data[-1] ^ 1]), download_meta)),
        ("rejects-duplicate-zip-member", "zip_member", lambda: verify_archive(duplicate_zip(), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-second-report", "zip_report_duplicate", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"other/report.json": b"{}"})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-installed-module-swapped", "installed_module_digest_mismatch", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"prefix/lib/libEXRFileEntry.a": b"other"})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-result-text-failure-with-same-count", "result_file_mismatch", lambda: verify_archive(archive(good_report("macos"), lambda f: f.update({"out/evidence/probe/result.txt": f["out/evidence/probe/result.txt"].replace(b" pass ", b" fail ", 1)})), "macos", SHA, RUN, ATTEMPT)),
        ("rejects-wrong-job-label", "report_job", lambda: check(mutated("macos", lambda r: r.update(job="sdk")))),
        ("rejects-missing-upstream-job", "job_unique", lambda: verify_jobs(good_jobs()[1:], SHA, RUN, ATTEMPT)),
        ("rejects-duplicate-upstream-job", "job_unique", lambda: verify_jobs(good_jobs() + [good_jobs()[0]], SHA, RUN, ATTEMPT)),
        ("rejects-running-upstream-job", "job_success", lambda: verify_jobs(good_jobs(status="in_progress"), SHA, RUN, ATTEMPT)),
        ("rejects-failed-upstream-job", "job_success", lambda: verify_jobs(good_jobs(conclusion="failure"), SHA, RUN, ATTEMPT)),
        ("rejects-wrong-source-job", "job_identity", lambda: verify_jobs(good_jobs(head_sha="b" * 40), SHA, RUN, ATTEMPT)),
        ("rejects-wrong-run-job", "job_identity", lambda: verify_jobs(good_jobs(run_id=1), SHA, RUN, ATTEMPT)),
        ("rejects-wrong-attempt-job", "job_identity", lambda: verify_jobs(good_jobs(run_attempt=1), SHA, RUN, ATTEMPT)),
    ]
    for label, code, action in negatives:
        results.append(rejects(label, code, action))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "aggregate-regressions.json").write_text(json.dumps({"schema": 1, "passed": len(results), "results": results}, indent=2) + "\n")
    print(f"{len(results)} evidence regressions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
