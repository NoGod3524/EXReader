# SPDX-License-Identifier: MIT
"""Actions-only real-ZIP rejection regressions for credential evidence."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from unittest.mock import patch
import warnings
import zipfile
import aggregate
from strict_contract import (C, PLATFORMS, WINDOWS_DIAGNOSTICS, PENDING, SCENARIOS, EvidenceError,
                             digest, normal, plan_for, verify)

REPO, SOURCE, RUN, ATTEMPT = "fixture/repo", "a" * 40, 12345, 2
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def zipped(files, extra=()):
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for name, data in list(files.items()) + list(extra):
                target.writestr(name, data)
    return output.getvalue()


def phase(label, kind, ids, summaries, index, files, accepted=True):
    checks = [{"id": name, "result": "pass" if accepted else "fail", "detail": "status=0"} for name in ids]
    log = "%02d-%s" % (index, label)
    if not accepted:
        summaries = [{"phase": "unavailable", "passed": 0, "total": 5}]
    output = "\n".join("check %s %s %s" % (row["id"], row["result"], row["detail"]) for row in checks)
    output += "\n" + "\n".join("phase %s %d/%d" % (row["phase"], row["passed"], row["total"]) for row in summaries) + "\n"
    files["evidence/logs/" + log + ".stdout.log"] = output.encode()
    files["evidence/logs/" + log + ".stderr.log"] = b""
    return {"label": label, "phase": kind, "checks": checks, "expected": ids, "summaries": summaries,
            "exit": 0 if accepted else 1, "accepted": accepted, "log": log}


def fixture():
    run = {"id": RUN, "head_sha": SOURCE, "run_attempt": ATTEMPT, "path": ".github/workflows/reader-credentials.yml",
           "status": "completed", "conclusion": "success", "repository": {"id": 42, "full_name": REPO}, "head_repository": {"id": 42}}
    jobs, artifacts, archives, logs, files_by_key = [], [], {}, {}, {}
    for index, (key, (runner, job_name, producer, consumer)) in enumerate(PLATFORMS.items()):
        files = {"logs/build.log": b"native build completed\n", "stage/include/exr_credentials.h": b"public header\n",
                 "stage/lib/module.a": b"installed library\n", consumer: b"fixture consumer binary\n"}
        observations = {
            "windows": {"windows_unavailable_attempts": dict.fromkeys(WINDOWS_DIAGNOSTICS, False), "s4u_input_removed_by_consumer": True},
            "linux": {"linux_temporary_keyring_removed": True, "linux_collection_locked": "(<true>,)"},
            "macos": {"macos_keychain": {"search_list_only_test_keychain": True, "default_is_test_keychain": True}, "macos_user_keychains_restored": True},
            "ios": {"ios_boot": 0, "ios_install": 0, "ios_simulator": {"fresh_device": True},
                    **{"ios_" + name + "_input_removed_by_app": True for name in ("suite", "reopen", "cleanup")}},
            "android": {"android_device": {"api": "34", "abi": "x86_64", "fresh_install": True},
                        **{"android_" + name + "_input_removed_by_probe": True for name in ("uninitialized", "suite", "reopen", "cleanup")}},
        }[key]
        report = {"schema": 1, "module": "EXReaderCredentials", "module_version": "0.1.0", "platform": key,
                  "accepted": True, "source_sha": SOURCE, "run_id": str(RUN), "run_attempt": str(ATTEMPT),
                  "job": producer, "runner": {"os": runner}, "diagnostics": [], "observations": observations,
                  "not_exercised": [PENDING[key]] if key in PENDING else [],
                  "unavailable_scenarios": [] if key == "windows" else SCENARIOS[key]}
        if key == "windows":
            for n, label in enumerate(WINDOWS_DIAGNOSTICS):
                report["diagnostics"].append(phase(label, "unavailable", C["unavailable"], normal("unavailable")[3], n + 30, files, False))
            report["expected_phase_labels"] = ["suite", "reopen", "seed", "cleanup"]
        else:
            report["expected_phase_labels"] = {
                "linux": ["suite", "reopen", "cleanup", "seed", "unavailable-locked-collection", "unavailable-no-service"],
                "macos": ["suite", "reopen", "seed", "unavailable-locked-keychain", "cleanup"],
                "ios": ["suite", "reopen", "cleanup"], "android": ["uninitialized", "suite", "reopen", "cleanup"],
            }[key]
        plan = plan_for(key, report, files)
        report["phases"] = [phase(label, kind, ids, totals, n, files) for n, (label, kind, ids, totals) in enumerate(plan)]
        report["phase_labels"] = [row[0] for row in plan]
        report["checks"] = report["passed"] = report["expected_checks"] = sum(len(row[2]) for row in plan)
        report["secret_scan"] = {"files": len(files), "bytes": sum(map(len, files.values())), "secrets": 8, "hits": 0,
                                 "forms_per_secret": "raw, 32-byte window, hex, HEX, base64, base64url"}
        report["installed_files"] = [{"path": name[6:], "bytes": len(data), "sha256": digest(data)}
                                     for name, data in files.items() if name.startswith("stage/")]
        report["consumer"] = {"name": consumer.split("/")[-1], "bytes": len(files[consumer]), "sha256": digest(files[consumer])}
        files["evidence/report.json"] = encoded(report);files_by_key[key] = files
        job = {"id": 1000 + index, "name": job_name, "run_id": RUN, "run_attempt": ATTEMPT, "head_sha": SOURCE,
               "status": "completed", "conclusion": "success"};jobs.append(job)
        data = zipped(files)
        artifact = {"id": 2000 + index, "name": f"reader-credentials-{key}-{RUN}-{ATTEMPT}", "size_in_bytes": len(data),
                    "digest": "sha256:" + digest(data), "expired": False, "expires_at": "2099-01-01T00:00:00Z",
                    "workflow_run": {"id": RUN, "head_sha": SOURCE, "repository_id": 42, "head_repository_id": 42}}
        artifacts.append(artifact);archives[artifact["id"]] = data;logs[job["id"]] = upload_log(artifact)
    jobs.append({"id": 1005, "name": "same-source report", "run_id": RUN, "run_attempt": ATTEMPT, "head_sha": SOURCE,
                 "status": "completed", "conclusion": "success"})
    artifacts.append({"id": 2005, "name": f"reader-credentials-report-{RUN}-{ATTEMPT}", "size_in_bytes": 10,
                      "digest": "sha256:" + "b" * 64, "expired": False, "expires_at": "2099-01-01T00:00:00Z",
                      "workflow_run": {"id": RUN, "head_sha": SOURCE, "repository_id": 42, "head_repository_id": 42}})
    return {"run": run, "jobs": jobs, "artifacts": artifacts, "archives": archives, "logs": logs, "files": files_by_key}


def upload_log(artifact):
    return ("SHA256 digest of uploaded artifact zip is " + artifact["digest"][7:] + "\nArtifact " + artifact["name"]
            + " has been successfully uploaded! Final size is " + str(artifact["size_in_bytes"])
            + " bytes. Artifact ID is " + str(artifact["id"]) + "\n").encode()


def checked(state, completed=True):
    return verify(state["run"], state["jobs"], state["artifacts"], state["archives"], state["logs"],
                  REPO, SOURCE, RUN, ATTEMPT, completed, NOW)


def repack(state, key, edit, report_edit=False, recalc=False, extra=()):
    files = state["files"][key]
    if report_edit:
        report = json.loads(files["evidence/report.json"]);edit(report);files["evidence/report.json"] = encoded(report)
    else:
        edit(files)
    if recalc:
        report = json.loads(files["evidence/report.json"])
        scanned = [data for name, data in files.items() if name != "evidence/report.json"]
        report["secret_scan"]["files"] = len(scanned);report["secret_scan"]["bytes"] = sum(map(len, scanned))
        files["evidence/report.json"] = encoded(report)
    index = list(PLATFORMS).index(key);artifact = state["artifacts"][index];data = zipped(files, extra)
    artifact["size_in_bytes"] = len(data);artifact["digest"] = "sha256:" + digest(data)
    state["archives"][artifact["id"]] = data;state["logs"][state["jobs"][index]["id"]] = upload_log(artifact)


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--output", required=True);args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    original = fixture();accepted = checked(original)
    assert {key: row["checks"] for key, row in accepted["platforms"].items()} == dict(zip(PLATFORMS, (24, 34, 29, 23, 46)))
    checks = ["complete_real_zip_fixture_preserves_declared_platform_gaps"]
    def reject(name, mutate, expected=None):
        state = deepcopy(original);mutate(state)
        try:
            checked(state)
        except EvidenceError as error:
            if expected:
                assert str(error) == expected, (name, str(error), expected)
            checks.append(name);return
        raise AssertionError(name + " was accepted")
    for field, value in (("head_sha", "c" * 40), ("id", RUN + 1), ("run_attempt", ATTEMPT + 1),
                         ("path", ".github/workflows/other.yml"), ("status", "in_progress"), ("conclusion", "cancelled")):
        reject("run_" + field, lambda s, f=field, v=value: s["run"].__setitem__(f, v))
    reject("run_foreign_repository", lambda s: s["run"]["repository"].__setitem__("full_name", "other/repo"))
    reject("run_fork_repository", lambda s: s["run"]["head_repository"].__setitem__("id", 43))
    for field, value in (("head_sha", "c" * 40), ("run_id", RUN + 1), ("run_attempt", 1), ("status", "queued"), ("conclusion", "failure")):
        reject("job_" + field, lambda s, f=field, v=value: s["jobs"][0].__setitem__(f, v))
    reject("missing_platform_job", lambda s: s["jobs"].pop(0))
    reject("missing_report_job", lambda s: s["jobs"].pop())
    reject("failed_original_report_job", lambda s: s["jobs"][-1].__setitem__("conclusion", "failure"))
    reject("duplicate_job_record", lambda s: s["jobs"].append(deepcopy(s["jobs"][0])))
    reject("duplicate_job_id_different_name", lambda s: s["jobs"][1].__setitem__("id", s["jobs"][0]["id"]))
    reject("duplicate_job_name_different_id", lambda s: s["jobs"][1].__setitem__("name", s["jobs"][0]["name"]))
    reject("missing_artifact", lambda s: s["artifacts"].pop(0))
    reject("missing_original_report_artifact", lambda s: s["artifacts"].pop())
    reject("duplicate_artifact_id", lambda s: s["artifacts"][1].__setitem__("id", s["artifacts"][0]["id"]))
    reject("duplicate_artifact_name", lambda s: s["artifacts"][1].__setitem__("name", s["artifacts"][0]["name"]))
    for field, value in (("expired", True), ("expired", "false"), ("size_in_bytes", 0), ("size_in_bytes", True),
                         ("size_in_bytes", 33 * 1024 * 1024), ("expires_at", "2020-01-01T00:00:00Z"),
                         ("expires_at", "2099-01-01"), ("digest", ""), ("digest", "sha256:invalid")):
        reject("artifact_" + field + "_" + str(value), lambda s, f=field, v=value: s["artifacts"][0].__setitem__(f, v))
    for field, value in (("id", RUN + 1), ("head_sha", "c" * 40), ("repository_id", 43), ("head_repository_id", 43)):
        reject("artifact_origin_" + field, lambda s, f=field, v=value: s["artifacts"][0]["workflow_run"].__setitem__(f, v))
    reject("artifact_attempt_name", lambda s: s["artifacts"][0].__setitem__("name", f"reader-credentials-windows-{RUN}-1"))
    reject("missing_raw_zip", lambda s: s["archives"].pop(2000))
    reject("actual_zip_size_mismatch", lambda s: s["archives"].__setitem__(2000, s["archives"][2000] + b"x"), "zip_size")
    reject("actual_zip_digest_mismatch", lambda s: s["archives"].__setitem__(2000, bytes([s["archives"][2000][0] ^ 1]) + s["archives"][2000][1:]), "zip_digest")
    reject("producer_log_missing", lambda s: s["logs"].pop(1000))
    reject("producer_uploaded_other_id", lambda s: s["logs"].__setitem__(1000, s["logs"][1000].replace(b"ID is 2000", b"ID is 9999")), "producer_artifact_binding")
    reject("producer_upload_digest_mismatch", lambda s: s["logs"].__setitem__(1000, s["logs"][1000].replace(s["artifacts"][0]["digest"][7:].encode(), b"0" * 64)), "producer_digest_binding")
    reject("producer_duplicate_upload_claim", lambda s: s["logs"].__setitem__(1000, s["logs"][1000] + s["logs"][1000]), "producer_artifact_binding")
    for field, value in (("accepted", 1), ("schema", True), ("module", "other"), ("module_version", "0.2.0"),
                         ("platform", "linux"), ("source_sha", "c" * 40), ("run_id", str(RUN + 1)), ("run_attempt", "1"),
                         ("job", "android"), ("checks", 1), ("passed", True), ("expected_checks", 1)):
        reject("report_" + field, lambda s, f=field, v=value: repack(s, "windows", lambda r: r.__setitem__(f, v), True))
    reject("report_runner", lambda s: repack(s, "windows", lambda r: r["runner"].__setitem__("os", "Linux"), True))
    reject("report_missing_windows_gap", lambda s: repack(s, "windows", lambda r: r.__setitem__("not_exercised", []), True), "windows_missing_scope")
    reject("report_missing_ios_gap", lambda s: repack(s, "ios", lambda r: r.__setitem__("not_exercised", []), True), "platform_scope")
    reject("report_missing_android_gap", lambda s: repack(s, "android", lambda r: r.__setitem__("not_exercised", []), True), "platform_scope")
    reject("missing_windows_diagnostic", lambda s: repack(s, "windows", lambda r: r["diagnostics"].pop(), True), "windows_diagnostics")
    reject("phase_exit_boolean", lambda s: repack(s, "linux", lambda r: r["phases"][0].__setitem__("exit", False), True), "phase_exit")
    reject("phase_dropped_named_check", lambda s: repack(s, "linux", lambda r: r["phases"][0]["checks"].pop(), True), "phase_raw_mismatch")
    reject("phase_forged_expected_set", lambda s: repack(s, "linux", lambda r: r["phases"][0].__setitem__("expected", ["fabricated"]), True), "phase_expected_ids")
    reject("phase_summary_replaced", lambda s: repack(s, "android", lambda r: r["phases"][0].__setitem__("summaries", []), True), "phase_raw_mismatch")
    reject("phase_summary_boolean", lambda s: repack(s, "linux", lambda r: r["phases"][2]["summaries"][0].__setitem__("passed", True), True), "phase_summary_type")
    reject("windows_diagnostic_boolean_contract", lambda s: repack(s, "windows", lambda r: r["observations"]["windows_unavailable_attempts"].__setitem__(WINDOWS_DIAGNOSTICS[0], 0), True), "windows_observations")
    reject("phase_log_reference_missing", lambda s: repack(s, "linux", lambda r: r["phases"][0].__setitem__("log", "99-suite"), True), "phase_logs_missing")
    for field, value in (("hits", 1), ("hits", False), ("secrets", 7), ("forms_per_secret", "raw only"), ("files", 0), ("bytes", 0)):
        reject("secret_scan_" + field + "_" + str(value), lambda s, f=field, v=value: repack(s, "linux", lambda r: r["secret_scan"].__setitem__(f, v), True))
    reject("installed_duplicate_manifest_path", lambda s: repack(s, "linux", lambda r: r["installed_files"].append(deepcopy(r["installed_files"][0])), True), "installed_duplicate")
    reject("installed_path_traversal", lambda s: repack(s, "linux", lambda r: r["installed_files"][0].__setitem__("path", "../bad"), True), "archive_path")
    reject("installed_actual_bytes_mismatch", lambda s: repack(s, "linux", lambda f: f.__setitem__("stage/include/exr_credentials.h", b"changed"), recalc=True), "installed_hash")
    reject("installed_unreported_file", lambda s: repack(s, "linux", lambda f: f.__setitem__("stage/lib/extra.a", b"extra"), recalc=True), "installed_coverage")
    reject("consumer_actual_bytes_mismatch", lambda s: repack(s, "linux", lambda f: f.__setitem__(PLATFORMS["linux"][3], b"changed"), recalc=True), "consumer_hash")
    reject("linux_lock_not_proven", lambda s: repack(s, "linux", lambda r: r["observations"].__setitem__("linux_collection_locked", "(<false>,)"), True), "linux_isolation_lock_cleanup")
    reject("mac_keychain_not_restored", lambda s: repack(s, "macos", lambda r: r["observations"].__setitem__("macos_user_keychains_restored", False), True), "macos_isolation_cleanup")
    reject("ios_install_boolean", lambda s: repack(s, "ios", lambda r: r["observations"].__setitem__("ios_install", False), True), "ios_device")
    reject("android_input_retained", lambda s: repack(s, "android", lambda r: r["observations"].__setitem__("android_suite_input_removed_by_probe", False), True), "android_inputs")
    reject("zip_parent_path", lambda s: repack(s, "linux", lambda f: f.__setitem__("../outside", b"x")), "archive_path")
    reject("zip_absolute_path", lambda s: repack(s, "linux", lambda f: f.__setitem__("/outside", b"x")), "archive_path")
    reject("zip_backslash_path", lambda s: repack(s, "linux", lambda f: f.__setitem__("stage\\outside", b"x")), "archive_path")
    reject("zip_duplicate_entry", lambda s: repack(s, "linux", lambda f: None, extra=[("evidence/report.json", b"{}")]), "zip_duplicate_path")
    reject("zip_case_alias", lambda s: repack(s, "linux", lambda f: f.__setitem__("EVIDENCE/REPORT.JSON", b"{}")), "zip_duplicate_path")
    reject("json_duplicate_keys", lambda s: repack(s, "linux", lambda f: f.__setitem__("evidence/report.json", b'{"accepted":true,"accepted":true}')), "duplicate_json_key")
    reject("json_nonfinite", lambda s: repack(s, "linux", lambda f: f.__setitem__("evidence/report.json", b'{"value":NaN}')), "nonfinite_json")
    reject("json_malformed", lambda s: repack(s, "linux", lambda f: f.__setitem__("evidence/report.json", b"{")), "json_format")
    live = deepcopy(original);live["run"].update(status="in_progress", conclusion=None)
    live["jobs"][-1].update(status="in_progress", conclusion=None);live["artifacts"].pop()
    assert checked(live, False)["accepted"] is True;checks.append("live_aggregate_requires_completed_producers_but_current_report_in_progress")
    with patch.object(aggregate, "api", side_effect=[{"total_count": 123, "jobs": [{}] * 100}, {"total_count": 123, "jobs": [{}] * 23}]) as api:
        assert len(aggregate.pages("/fixture", "jobs")) == 123
        assert api.call_args_list[1].args[0].endswith("page=2")
    checks.append("all_api_pages_are_consumed")
    with patch.object(aggregate, "api", side_effect=[{"total_count": 101, "jobs": [{}] * 100}, {"total_count": 101, "jobs": []}]):
        try:
            aggregate.pages("/fixture", "jobs")
        except EvidenceError:
            checks.append("incomplete_api_pagination_rejected")
        else:
            raise AssertionError("missing API page accepted")
    assert len(checks) >= 80 and len(checks) == len(set(checks))
    result = {"accepted": True, "diagnostic_only": True, "source_sha": os.environ["GITHUB_SHA"],
              "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "checks": checks, "count": len(checks), "native_platform_credit": 0}
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    (output / "rejections.json").write_bytes(encoded(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
