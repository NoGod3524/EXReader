# SPDX-License-Identifier: MIT
"""Pure identity/archive/report checks, exercised by Actions rejection fixtures."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile
import zlib
from check_credentials import PHASE_CHECKS as C, ANDROID_JAVA_CHECKS as JAVA, CHECK_LINE, PHASE_LINE, DETAIL

PLATFORMS = {
    "windows": ("Windows", "credentials (windows-2022)", "desktop", "consumer/credentials-consumer.exe"),
    "linux": ("Linux", "credentials (ubuntu-22.04)", "desktop", "consumer/credentials-consumer"),
    "macos": ("macOS", "credentials (macos-15)", "desktop", "consumer/credentials-consumer"),
    "ios": ("macOS", "credentials (ios-simulator)", "ios", "consumer/CredentialsProbe.app/CredentialsProbe"),
    "android": ("Linux", "credentials (android-emulator)", "android", "consumer/probe-debug.apk"),
}
WINDOWS_DIAGNOSTICS = ["unavailable-low-integrity", "unavailable-vault-service-stopped", "unavailable-s4u-task"]
WINDOWS_SCENARIOS = ["low-integrity process (file mandatory label Low)", "Credential Manager service (VaultSvc) stopped", "S4U scheduled task"]
PENDING = {
    "windows": "Windows UNAVAILABLE: Credential Manager stayed available to a low-integrity process, with VaultSvc stopped and in an S4U task (all recorded as diagnostics)",
    "ios": "iOS locked keychain: the simulator has no passcode lock to engage",
    "android": "Android Keystore service failure: not inducible on the emulator",
}
SCENARIOS = {
    "linux": ["default Secret Service collection locked", "no Secret Service / session bus reachable"],
    "macos": ["test keychain locked, no user interaction allowed"],
    "ios": [], "android": ["C ABI used before binding to the Keystore-backed Java store"],
}
MAX_ZIP, MAX_EXPANDED, MAX_FILES = 32 * 1024 * 1024, 64 * 1024 * 1024, 512


class EvidenceError(Exception):
    pass


def need(value, code):
    if not value:
        raise EvidenceError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "duplicate_json_key");result[key] = value
        return result
    def constant(_):
        raise EvidenceError("nonfinite_json")
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        need(type(value) is dict, "json_root");return value
    except (ValueError, UnicodeError):
        raise EvidenceError("json_format") from None


def safe_path(name):
    need(type(name) is str and name and "\\" not in name and "\0" not in name and ":" not in name, "archive_path")
    path = PurePosixPath(name)
    need(not path.is_absolute() and ".." not in path.parts and str(path) == name and name != ".", "archive_path")
    return name


def select(rows, name):
    matches = [row for row in rows if row.get("name") == name]
    need(len(matches) == 1, "named_evidence_missing_or_duplicate");return matches[0]


def unique(rows, code):
    need(type(rows) is list, code);ids, names = set(), set()
    for row in rows:
        need(type(row) is dict and integer(row.get("id"), 1) and type(row.get("name")) is str, code)
        need(row["id"] not in ids and row["name"] not in names, code);ids.add(row["id"]);names.add(row["name"])


def artifact_identity(artifact, run, now):
    need(artifact.get("expired") is False and integer(artifact.get("size_in_bytes"), 1)
         and artifact["size_in_bytes"] <= MAX_ZIP, "artifact_expired_or_empty")
    try:
        expires = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        need(expires.tzinfo is not None and expires > now, "artifact_expired_time")
    except (ValueError, TypeError, AttributeError, KeyError):
        raise EvidenceError("artifact_expiry") from None
    need(type(artifact.get("digest")) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", artifact["digest"]), "artifact_digest")
    origin = artifact.get("workflow_run", {})
    need(origin.get("id") == run["id"] and origin.get("head_sha") == run["head_sha"]
         and origin.get("repository_id") == run["repository"]["id"]
         and origin.get("head_repository_id") == run["head_repository"]["id"], "artifact_origin")


def archive_files(data, artifact):
    need(type(data) is bytes and len(data) == artifact["size_in_bytes"] and len(data) <= MAX_ZIP, "zip_size")
    need("sha256:" + digest(data) == artifact["digest"], "zip_digest")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist();need(0 < len(infos) <= MAX_FILES, "zip_file_limit")
            names, files, total = set(), {}, 0
            for info in infos:
                name = safe_path(info.filename.rstrip("/") if info.is_dir() else info.filename)
                need(name.casefold() not in names, "zip_duplicate_path");names.add(name.casefold())
                need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR)
                     and not info.flag_bits & 1, "zip_special_or_encrypted")
                if info.is_dir():
                    continue
                total += info.file_size
                need(total <= MAX_EXPANDED and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "zip_expanded_or_compression")
                files[name] = archive.read(info)
            return files
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, zlib.error):
        raise EvidenceError("zip_format") from None


def upload_binding(log, artifact):
    need(type(log) is bytes and 0 < len(log) <= MAX_EXPANDED, "producer_log")
    text = log.decode("utf-8", "replace")
    matches = list(re.finditer(r"Artifact " + re.escape(artifact["name"])
        + r" has been successfully uploaded! Final size is (\d+) bytes\. Artifact ID is (\d+)", text))
    need(len(matches) == 1 and int(matches[0][1]) == artifact["size_in_bytes"]
         and int(matches[0][2]) == artifact["id"], "producer_artifact_binding")
    hashes = re.findall(r"SHA256 digest of uploaded artifact zip is ([a-f0-9]{64})", text[:matches[0].start()])
    need(hashes and "sha256:" + hashes[-1] == artifact["digest"], "producer_digest_binding")
    return digest(log)


def normal(label, phase=None):
    phase = phase or label
    return label, phase, C[phase], [{"phase": phase, "passed": len(C[phase]), "total": len(C[phase])}]


def raw_phase(entry, files, expected, summaries, diagnostic=False):
    need(type(entry) is dict and entry.get("expected") == expected, "phase_expected_ids")
    name = entry.get("log")
    need(type(name) is str and re.fullmatch(r"\d{2}-[a-z0-9-]+", name)
         and name.endswith("-" + entry["label"]), "phase_log_name")
    out, err = "evidence/logs/" + name + ".stdout.log", "evidence/logs/" + name + ".stderr.log"
    need(out in files and err in files, "phase_logs_missing")
    checks, observed = [], []
    for line in files[out].decode("utf-8", "strict").splitlines():
        check = CHECK_LINE.fullmatch(line.strip())
        if check:
            need(DETAIL.fullmatch(check[3]) is not None, "phase_detail")
            checks.append({"id": check[1], "result": check[2], "detail": check[3]})
        phase = PHASE_LINE.fullmatch(line.strip())
        if phase:
            observed.append({"phase": phase[1], "passed": int(phase[2]), "total": int(phase[3])})
    reported = entry.get("summaries")
    need(type(reported) is list and all(type(row) is dict and type(row.get("passed")) is int
         and type(row.get("total")) is int for row in reported), "phase_summary_type")
    need(entry.get("checks") == checks and reported == observed, "phase_raw_mismatch")
    ids = [row["id"] for row in checks];need(len(ids) == len(set(ids)), "phase_duplicate_check")
    code = entry.get("exit");need(code is None or integer(code), "phase_exit")
    complete = ids == expected and all(row["result"] == "pass" for row in checks) and type(code) is int and code == 0 and observed == summaries
    need(entry.get("accepted") is complete and (diagnostic or complete), "phase_incomplete")
    return complete


def plan_for(key, report, files):
    diagnostics = report.get("diagnostics");need(type(diagnostics) is list, "diagnostics_type")
    if key == "windows":
        need([row.get("label") for row in diagnostics] == WINDOWS_DIAGNOSTICS, "windows_diagnostics")
        states = []
        for row in diagnostics:
            need(row.get("phase") == "unavailable", "windows_diagnostic_phase")
            states.append(raw_phase(row, files, C["unavailable"], normal("unavailable")[3], True))
        obs = report.get("observations", {})
        attempts = obs.get("windows_unavailable_attempts")
        need(type(attempts) is dict and all(type(value) is bool for value in attempts.values())
             and attempts == dict(zip(WINDOWS_DIAGNOSTICS, states))
             and obs.get("s4u_input_removed_by_consumer") is True, "windows_observations")
        plan = [normal("suite"), normal("reopen"), normal("seed")]
        if any(states):
            index = states.index(True);plan.append(normal(WINDOWS_DIAGNOSTICS[index], "unavailable"))
            need(report.get("not_exercised") == [] and report.get("unavailable_scenarios") == [WINDOWS_SCENARIOS[index]], "windows_scope")
            labels = ["suite", "reopen", "seed", "unavailable-*", "cleanup"]
        else:
            need(report.get("not_exercised") == [PENDING[key]] and report.get("unavailable_scenarios") == [], "windows_missing_scope")
            labels = ["suite", "reopen", "seed", "cleanup"]
        plan.append(normal("cleanup"))
    else:
        need(diagnostics == [], "unexpected_diagnostics")
        need(report.get("not_exercised") == ([PENDING[key]] if key in PENDING else [])
             and report.get("unavailable_scenarios") == SCENARIOS[key], "platform_scope")
        if key == "linux":
            plan = [normal("suite"), normal("reopen"), normal("cleanup"), normal("seed"),
                    normal("unavailable-locked-collection", "unavailable"), normal("unavailable-no-service", "unavailable")]
        elif key == "macos":
            plan = [normal("suite"), normal("reopen"), normal("seed"), normal("unavailable-locked-keychain", "unavailable"), normal("cleanup")]
        elif key == "ios":
            plan = [normal("suite"), normal("reopen"), normal("cleanup")]
        else:
            bind = ["jni-bind-keystore-store"]
            def totals(*rows):
                return [{"phase": name, "passed": count, "total": count} for name, count in rows]
            plan = [
                ("uninitialized", "uninitialized", C["unavailable"] + JAVA["uninitialized"], totals(("unavailable", 5), ("java-uninitialized", 1))),
                ("suite", "suite", bind + C["suite"] + JAVA["suite"], totals(("suite", 20), ("java-suite", 11))),
                ("reopen", "reopen", JAVA["reopen"] + bind + C["reopen"], totals(("java-reopen", 2), ("reopen", 2))),
                ("cleanup", "cleanup", bind + C["cleanup"] + JAVA["cleanup"], totals(("cleanup", 1), ("java-cleanup", 1))),
            ]
        labels = [row[0] for row in plan]
    need(report.get("expected_phase_labels") == labels, "expected_phase_labels")
    return plan


def observations(key, report):
    obs = report.get("observations");need(type(obs) is dict, "observations_type")
    if key == "linux":
        need(obs.get("linux_temporary_keyring_removed") is True and type(obs.get("linux_collection_locked")) is str
             and re.fullmatch(r"\(\s*<true>\s*,?\s*\)\s*", obs["linux_collection_locked"]), "linux_isolation_lock_cleanup")
    elif key == "macos":
        item = obs.get("macos_keychain", {})
        need(item.get("search_list_only_test_keychain") is True and item.get("default_is_test_keychain") is True
             and obs.get("macos_user_keychains_restored") is True, "macos_isolation_cleanup")
    elif key == "ios":
        need(type(obs.get("ios_boot")) is int and obs["ios_boot"] == 0 and type(obs.get("ios_install")) is int
             and obs["ios_install"] == 0 and obs.get("ios_simulator", {}).get("fresh_device") is True, "ios_device")
        need(all(obs.get("ios_" + phase + "_input_removed_by_app") is True for phase in ("suite", "reopen", "cleanup")), "ios_inputs")
    elif key == "android":
        item = obs.get("android_device", {})
        need(item.get("api") == "34" and item.get("abi") == "x86_64" and item.get("fresh_install") is True, "android_device")
        need(all(obs.get("android_" + phase + "_input_removed_by_probe") is True for phase in ("uninitialized", "suite", "reopen", "cleanup")), "android_inputs")


def verify_report(key, files, run):
    need("evidence/report.json" in files and len(files["evidence/report.json"]) <= 2 * 1024 * 1024, "report_missing_or_large")
    report = decode_json(files["evidence/report.json"]);os_name, _, producer, consumer = PLATFORMS[key]
    need(type(report.get("schema")) is int and report["schema"] == 1 and report.get("module") == "EXReaderCredentials"
         and report.get("module_version") == "0.1.0" and report.get("platform") == key and report.get("accepted") is True, "report_contract")
    need(report.get("source_sha") == run["head_sha"] and report.get("run_id") == str(run["id"])
         and report.get("run_attempt") == str(run["run_attempt"]) and report.get("job") == producer, "report_origin")
    need(report.get("runner", {}).get("os") == os_name, "report_runner")
    plan = plan_for(key, report, files);phases = report.get("phases")
    need(type(phases) is list and len(phases) == len(plan) and report.get("phase_labels") == [row[0] for row in plan], "phase_labels")
    for entry, (label, phase, ids, totals) in zip(phases, plan):
        need(entry.get("label") == label and entry.get("phase") == phase, "phase_contract")
        try:
            raw_phase(entry, files, ids, totals)
        except EvidenceError as error:
            error.phase = label
            raise
    logs = [row["log"] for row in phases + report["diagnostics"]];need(len(logs) == len(set(logs)), "phase_log_duplicate")
    count = sum(len(row[2]) for row in plan)
    need(all(type(report.get(name)) is int and report[name] == count for name in ("checks", "passed", "expected_checks")), "report_counts")
    scan = report.get("secret_scan", {})
    need(type(scan.get("hits")) is int and scan["hits"] == 0 and type(scan.get("secrets")) is int and scan["secrets"] == 8
         and scan.get("forms_per_secret") == "raw, 32-byte window, hex, HEX, base64, base64url", "secret_scan")
    scanned = {name: value for name, value in files.items() if name != "evidence/report.json"}
    need(all(name.startswith(("evidence/", "logs/", "stage/", "consumer/")) for name in scanned), "unscanned_path")
    need(type(scan.get("files")) is int and scan["files"] == len(scanned) and scan["files"] > 0
         and type(scan.get("bytes")) is int and scan["bytes"] == sum(map(len, scanned.values())) and scan["bytes"] > 0, "scan_coverage")
    manifest = report.get("installed_files");need(type(manifest) is list and 0 < len(manifest) <= MAX_FILES, "installed_manifest")
    stage = set()
    for row in manifest:
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"}, "installed_record")
        name = "stage/" + safe_path(row["path"]);need(name not in stage, "installed_duplicate");stage.add(name)
        need(name in files and integer(row["bytes"], 1) and row["bytes"] == len(files[name])
             and row["sha256"] == digest(files[name]), "installed_hash")
    need(stage == {name for name in files if name.startswith("stage/")} and "stage/include/exr_credentials.h" in stage, "installed_coverage")
    binary = report.get("consumer", {})
    need(binary.get("name") == PurePosixPath(consumer).name and consumer in files and integer(binary.get("bytes"), 1)
         and binary["bytes"] == len(files[consumer]) and binary.get("sha256") == digest(files[consumer]), "consumer_hash")
    observations(key, report)
    return {"checks": count, "passed": count, "phase_labels": report["phase_labels"], "secret_hits": 0,
            "not_exercised": report["not_exercised"], "unavailable_scenarios": report["unavailable_scenarios"],
            "report_sha256": digest(files["evidence/report.json"]), "installed_files": manifest, "consumer": binary}


def verify_checked(run, jobs, artifacts, archives, logs, repo, sha, run_id, attempt, completed=True, now=None):
    now = now or datetime.now(timezone.utc)
    need(integer(run_id, 1) and integer(attempt, 1) and type(sha) is str and re.fullmatch(r"[a-f0-9]{40}", sha), "target_identity")
    need(type(run.get("id")) is int and type(run.get("run_attempt")) is int
         and run.get("id") == run_id and run.get("head_sha") == sha and run.get("run_attempt") == attempt
         and run.get("path") == ".github/workflows/reader-credentials.yml", "run_identity")
    need(run.get("repository", {}).get("full_name") == repo and integer(run["repository"].get("id"), 1)
         and run.get("head_repository", {}).get("id") == run["repository"]["id"], "run_repository")
    need((run.get("status") == "completed" and run.get("conclusion") == "success") if completed else
         run.get("status") == "in_progress" and run.get("conclusion") is None, "run_conclusion")
    unique(jobs, "job_duplicate");unique(artifacts, "artifact_duplicate")
    need({row["name"] for row in jobs} == {row[1] for row in PLATFORMS.values()} | {"same-source report"}, "job_set")
    for job in jobs:
        need(type(job.get("run_id")) is int and type(job.get("run_attempt")) is int
             and job.get("run_id") == run_id and job.get("run_attempt") == attempt and job.get("head_sha") == sha, "job_origin")
        need(job.get("status") == "completed" and job.get("conclusion") == "success" if completed or job["name"] != "same-source report"
             else job.get("status") == "in_progress" and job.get("conclusion") is None, "job_conclusion")
    expected = {f"reader-credentials-{key}-{run_id}-{attempt}" for key in PLATFORMS}
    if completed:
        expected.add(f"reader-credentials-report-{run_id}-{attempt}")
    relevant = [row for row in artifacts if row["name"].endswith(f"-{run_id}-{attempt}")]
    need({row["name"] for row in relevant} == expected, "artifact_set")
    for artifact in relevant:
        artifact_identity(artifact, run, now)
    result = {"schema": 2, "module": "EXReaderCredentials", "module_version": "0.1.0", "accepted": False,
              "source_sha": sha, "run_id": run_id, "attempt": attempt, "verified_at": now.isoformat(),
              "complete_product": False, "physical_device_execution": False,
              "scope": "original declared credential scopes; unavailable gaps retained",
              "platforms": {}, "granted": [], "pending": []}
    for key, (_, job_name, _, _) in PLATFORMS.items():
        job = select(jobs, job_name);artifact = select(artifacts, f"reader-credentials-{key}-{run_id}-{attempt}")
        need(artifact["id"] in archives and job["id"] in logs, "archive_or_log_missing")
        try:
            log_hash = upload_binding(logs[job["id"]], artifact);files = archive_files(archives[artifact["id"]], artifact)
            item = verify_report(key, files, run)
        except EvidenceError as error:
            error.platform = key
            raise
        item.update(job_id=job["id"], job_attempt=job["run_attempt"], job_source_sha=job["head_sha"],
                    producer_log_sha256=log_hash, granted=True,
                    artifact={field: artifact[field] for field in ("id", "name", "size_in_bytes", "digest", "expired", "expires_at")})
        result["platforms"][key] = item;result["granted"].append(key)
    result["zip_digests_recomputed"] = len(PLATFORMS);result["accepted"] = True
    return result


def verify(*args, **kwargs):
    try:
        return verify_checked(*args, **kwargs)
    except (KeyError, AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        raise EvidenceError("malformed_evidence") from None
