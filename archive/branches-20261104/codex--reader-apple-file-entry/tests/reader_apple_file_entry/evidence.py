# SPDX-License-Identifier: MIT
"""Pure verification of Apple file-entry evidence (no network, no GitHub access)."""
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLATFORMS = ("macos", "iphone", "ipad")
MAX_ZIP = 64 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(Exception):
    pass


def need(condition, code):
    if not condition:
        raise EvidenceError(code)


def no_duplicates(pairs):
    keys = [key for key, _ in pairs]
    need(len(keys) == len(set(keys)), "json_duplicate_key")
    return dict(pairs)


def decode(data):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, ValueError):
        raise EvidenceError("json_decode")


def expected_checks():
    return decode((HERE / "expected_checks.json").read_bytes())


def artifact_name(platform, run_id, attempt):
    return f"reader-apple-file-entry-{platform}-{run_id}-{attempt}"


def verify_artifact(meta, platform, sha, run_id, attempt, now=None):
    """GitHub artifact metadata: right name, same head commit, unexpired, non-empty."""
    now = now or datetime.now(timezone.utc)
    need(meta.get("name") == artifact_name(platform, run_id, attempt), "artifact_name")
    need(type(meta.get("id")) is int and not meta.get("expired"), "artifact_expired")
    need(type(meta.get("size_in_bytes")) is int and 0 < meta["size_in_bytes"] <= MAX_ZIP, "artifact_size")
    run = meta.get("workflow_run") or {}
    need(run.get("id") == int(run_id) and run.get("head_sha") == sha, "artifact_run")
    expires = datetime.fromisoformat(meta["expires_at"].replace("Z", "+00:00"))
    need(expires > now, "artifact_expiry")


def read_zip(data):
    """Returns {member: bytes}; refuses unsafe names, duplicates and oversized members."""
    need(len(data) <= MAX_ZIP, "zip_size")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise EvidenceError("zip_invalid")
    members = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename
        need(not name.startswith("/") and ".." not in Path(name).parts, "zip_path")
        need(name not in members and info.file_size <= MAX_MEMBER, "zip_member")
        members[name] = archive.read(info)
    return members


def verify_report(report, platform, sha, run_id, attempt):
    need(type(report) is dict and report.get("schema") == 1, "report_schema")
    need(SHA.match(sha or "") is not None and report.get("source_sha") == sha, "report_source")
    need(str(report.get("run_id")) == str(run_id) and str(report.get("run_attempt")) == str(attempt), "report_run")
    need(report.get("platform") == platform, "report_platform")
    need(report.get("accepted") is True and report.get("problems") == [], "report_not_accepted")
    expected = expected_checks()
    need(set(report.get("reports", {})) == {"probe", "consumer"}, "report_sections")
    total = 0
    for name in ("probe", "consumer"):
        section = report["reports"][name]
        checks = section.get("checks")
        need(type(checks) is list and [c.get("id") for c in checks] == expected[name], "check_ids_" + name)
        for check in checks:
            need(check.get("result") == "pass" and type(check.get("detail")) is str, "check_failed_" + name)
        need(section.get("exit") == 0 and section.get("passed") == len(checks) and section.get("failed") == 0, "section_counts_" + name)
        total += len(checks)
    need(report.get("total_checks") == total == report.get("passed_checks"), "total_counts")
    pending = report.get("not_exercised")
    need(type(pending) is list and pending and all(type(item) is str and item for item in pending), "pending_not_listed")
    binaries = report.get("binaries")
    need(type(binaries) is dict and all(re.fullmatch(r"[0-9a-f]{64}", str(binaries.get(n, ""))) for n in ("probe", "consumer")), "binary_digests")
    if platform != "macos":
        simulator = report.get("simulator") or {}
        need(simulator.get("fresh_device") is True and simulator.get("boot") == 0, "simulator_not_fresh")
    else:
        need(report.get("simulator") is None, "macos_simulator")
    return total


def verify_archive(data, platform, sha, run_id, attempt):
    """Zip bytes -> verified report; binaries inside the zip must match the report."""
    members = read_zip(data)
    need("out/report.json" in members, "zip_report_missing")
    report = decode(members["out/report.json"])
    total = verify_report(report, platform, sha, run_id, attempt)
    for name in ("probe", "consumer"):
        need(name_in(members, "out/" + name), "zip_binary_missing")
        need(hashlib.sha256(members["out/" + name]).hexdigest() == report["binaries"][name], "binary_digest_mismatch")
    for name in ("probe", "consumer"):
        need(("out/evidence/%s/result.txt" % name) in members, "zip_result_missing")
        lines = [l for l in members["out/evidence/%s/result.txt" % name].decode("utf-8").splitlines() if l.startswith("check ")]
        need(len(lines) == len(report["reports"][name]["checks"]), "result_file_mismatch")
    need("prefix/lib/libEXRFileEntry.a" in members, "installed_module_missing")
    return report, total


def name_in(members, name):
    return name in members and len(members[name]) > 0
