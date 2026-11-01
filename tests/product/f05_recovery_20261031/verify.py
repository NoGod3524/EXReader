# SPDX-License-Identifier: MIT
"""Actions-only role-aware F05 receipt gate and original-artifact authentication.
No result from this module is full F05 acceptance. Producer runtime adapters,
complete native coverage and independent review remain separately required.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

HOSTS = {"windows", "linux", "android", "macos", "iphone", "ipad"}
SDK = "8357eafa28423a7ab93ba08b823af80f01ad1505"

class Rejected(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)

def require(condition, code, detail):
    if not condition:
        raise Rejected(code, detail)

def unique(values, code, detail):
    require(isinstance(values, list) and all(isinstance(v, str) for v in values),
            code, detail + ": string list required")
    require(len(values) == len(set(values)), code, detail + ": duplicates")

def exact(values, expected, code, detail):
    unique(values, code, detail)
    require(set(values) == set(expected), code, detail + ": missing or extra")

def digest_file(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()

def api(endpoint):
    # gh uses the runner's normal authenticated Actions route; no credential
    # files are opened, exported or placed in command arguments/evidence.
    command = ["gh", "api", "--method", "GET", endpoint]
    value = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    require(value.returncode == 0, "api_failed", endpoint)
    return json.loads(value.stdout)

def paged(endpoint, key):
    rows = []
    for page in range(1, 101):
        separator = "&" if "?" in endpoint else "?"
        result = api(endpoint + separator + "per_page=100&page=" + str(page))
        batch = result[key]
        require(isinstance(batch, list), "api_shape", endpoint)
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise Rejected("api_page_limit", endpoint)

def stamp(value):
    require(isinstance(value, str), "invalid_time", "timestamp absent")
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))

def member_index(archive, policy):
    entries = archive.infolist()
    require(len(entries) <= policy["max_members"], "zip_limit", "member count")
    result, total = {}, 0
    for entry in entries:
        name = entry.filename
        path = PurePosixPath(name)
        require(name and not name.startswith("/") and "\\" not in name and ":" not in name
                and ".." not in path.parts and "." not in path.parts,
                "unsafe_member", name)
        require(name not in result, "duplicate_member", name)
        require(not stat.S_ISLNK(entry.external_attr >> 16), "unsafe_member", name + ": symlink")
        require(not entry.flag_bits & 1, "unsafe_member", name + ": encrypted")
        total += entry.file_size
        require(total <= policy["max_uncompressed_bytes"], "zip_limit", "expanded bytes")
        result[name] = entry
    return result

def zip_hash(archive, entry):
    result, size = hashlib.sha256(), 0
    with archive.open(entry) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            require(size <= entry.file_size, "zip_size", entry.filename)
            result.update(block)
    require(size == entry.file_size, "zip_size", entry.filename)
    return result.hexdigest()

def read_json_member(archive, members, name, policy):
    require(name in members and not members[name].is_dir(), "missing_member", name)
    require(members[name].file_size <= policy["max_receipt_bytes"], "zip_limit", name)
    return json.loads(archive.read(members[name]))

def authenticate(manifest, output, identity):
    policy = manifest["artifact_policy"]
    require(policy["repository"] == "NoGod3524/EXReader", "wrong_repository", "fixed repository required")
    roles = manifest["artifact_roles"]
    require(roles, "unwired_artifact_roles", "review actual producer names, jobs and member paths first")
    repo = policy["repository"]
    run, attempt, source = identity["run"], identity["attempt"], identity["source"]
    current = api("repos/" + repo + "/actions/runs/" + run + "/attempts/" + attempt)
    require(str(current["id"]) == run and str(current["run_attempt"]) == attempt,
            "wrong_run", "attempt API identity")
    require(current["head_sha"] == source, "wrong_source", "run head SHA")
    jobs = paged("repos/" + repo + "/actions/runs/" + run + "/attempts/" + attempt + "/jobs", "jobs")
    artifacts = paged("repos/" + repo + "/actions/runs/" + run + "/artifacts", "artifacts")
    output.mkdir(parents=True, exist_ok=False)
    (output / "attempt.json").write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    (output / "jobs.json").write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")
    authenticated = {"identity": identity, "roles": {}, "F05_accepted": False}
    for role, spec in roles.items():
        require(re.fullmatch(r"[a-z0-9_-]+", role) is not None, "invalid_role", role)
        expected_name = spec["artifact_name"].format(run=run, attempt=attempt)
        matches = [a for a in artifacts if a["name"] == expected_name]
        require(len(matches) == 1, "ambiguous_artifact", expected_name)
        artifact = matches[0]
        require(artifact["expired"] is False, "expired_artifact", expected_name)
        require(str(artifact["workflow_run"]["id"]) == run
                and artifact["workflow_run"]["head_sha"] == source,
                "wrong_run", "artifact run/source binding")
        candidates = [j for j in jobs if j["name"] == spec["job_name"]]
        require(len(candidates) == 1, "ambiguous_job", spec["job_name"])
        job = candidates[0]
        require(str(job["run_id"]) == run and str(job["run_attempt"]) == attempt
                and job["head_sha"] == source, "wrong_run", "attempt job binding")
        require(job["status"] == "completed" and job["conclusion"] == "success",
                "producer_not_passed", spec["job_name"])
        created = stamp(artifact["created_at"])
        require(stamp(job["started_at"]) <= created <= stamp(job["completed_at"]),
                "wrong_attempt_time", "artifact not uploaded during the exact successful producer job")
        claimed = artifact.get("digest", "")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", claimed) is not None,
                "missing_digest", expected_name)
        require(0 < artifact["size_in_bytes"] <= policy["max_archive_bytes"],
                "zip_limit", expected_name)
        folder = output / role
        folder.mkdir()
        raw = folder / "original.zip"
        with raw.open("wb") as stream:
            download = subprocess.run(["gh", "api", "--method", "GET",
                "repos/" + repo + "/actions/artifacts/" + str(artifact["id"]) + "/zip"],
                stdout=stream, stderr=subprocess.PIPE, timeout=300)
        require(download.returncode == 0, "download_failed", expected_name)
        require(raw.stat().st_size == artifact["size_in_bytes"], "wrong_zip_size", expected_name)
        actual = digest_file(raw)
        require("sha256:" + actual == claimed, "wrong_digest", expected_name)
        (folder / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        (folder / "producer-job.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(raw) as archive:
            members = member_index(archive, policy)
            receipt = read_json_member(archive, members, spec["receipt_member"], policy)
            require(receipt["identity"] == identity, "wrong_source", role + ": receipt identity")
            program = spec["program_member"]
            require(program in members and not members[program].is_dir(), "missing_member", program)
            program_hash = zip_hash(archive, members[program])
            require(receipt["program_sha256"] == program_hash, "wrong_program", role)
            referenced = receipt["evidence_members"]
            unique(referenced, "duplicate_evidence", role)
            evidence = {}
            for name in referenced:
                require(name in members and not members[name].is_dir(), "missing_member", name)
                evidence[name] = {"bytes": members[name].file_size,
                                  "sha256": zip_hash(archive, members[name])}
            retained = {}
            for suite_id, member in spec["retained_members"].items():
                require(suite_id in manifest["retained_suites"], "unknown_suite", suite_id)
                retained[suite_id] = read_json_member(archive, members, member, policy)
        authenticated["roles"][role] = {
            "artifact_id": artifact["id"], "artifact_name": artifact["name"],
            "job_id": job["id"], "original_zip_sha256": actual,
            "original_zip_bytes": raw.stat().st_size, "program_sha256": program_hash,
            "receipt": receipt, "evidence": evidence, "retained": retained}
    return authenticated

def retained_check(spec, report, identity, suite_id):
    require(report.get("accepted", report.get("passed")) is True,
            "retained_failed", suite_id)
    require(str(report["source_sha"]) == identity["source"]
            and str(report["run_id"]) == identity["run"]
            and str(report["attempt"]) == identity["attempt"], "wrong_source", suite_id)
    kind = spec["report_kind"]
    if kind == "ordered-checks":
        require(report["checks"] == spec["ordered_assertions"] and report["count"] == spec["count"],
                "wrong_suite_names", suite_id)
    elif kind == "phase-ordered-checks":
        phases = report["phases"]
        require([p["phase"] for p in phases] == list(spec["phases"]),
                "wrong_suite_names", suite_id + ": phases")
        for phase in phases:
            require([c["name"] for c in phase["checks"]] == spec["phases"][phase["phase"]]
                    and all(c["pass"] is True for c in phase["checks"])
                    and phase["count"] == len(spec["phases"][phase["phase"]]),
                    "wrong_suite_names", suite_id + ":" + phase["phase"])
        require(len({p["pid"] for p in phases}) == spec["distinct_pids"]
                and len(report["boundaries"]) == spec["real_blocked_boundaries"]
                and report["checks"] == spec["count"], "retained_boundary", suite_id)
    elif kind == "apple-account":
        require(report["cases"] == spec["count"] and report["named_steps"] == spec["named_steps"]
                and report["attachments"] == spec["attachments"]
                and report["https"]["actual_shards"] == spec["actual_shards"]
                and report["https"]["minimum_completed_sweeps"] >= spec["minimum_completed_sweeps"],
                "retained_boundary", suite_id)
    elif kind == "apple-failure":
        require(report["failure_requests"] > 0 and all(report[key] == spec[key]
                for key in ("failed_state_pending_revisions", "recovery_shards", "outbox_after_retry")),
                "retained_boundary", suite_id)
    elif kind == "command-exit":
        require(report["exit_code"] == 0 and report["authenticated_requests"] > 0
                and report["unauthenticated_requests"] > 0, "retained_boundary", suite_id)
    else:
        raise Rejected("unknown_suite_kind", suite_id)

def check(manifest, bundle, identity):
    require(manifest["state"] == "ready-for-client-validation",
            "not_ready", "runtime roles, retained suites and native capabilities remain unresolved")
    require(manifest["schema"] == 2 and manifest["requirement"] == "F05",
            "wrong_manifest", "F05 role schema required")
    require(manifest["sdk_freeze"] == SDK, "wrong_sdk", "frozen SDK differs")
    require(bundle["identity"] == identity, "wrong_source", "authenticated aggregate identity")
    roles = bundle["roles"]
    require(set(roles) == set(manifest["artifact_roles"]), "missing_role", "producer roles differ")
    host_rows = {}
    for role, authenticated in roles.items():
        row = authenticated["receipt"]
        host = row["host"]
        require(host in HOSTS and host not in host_rows, "duplicate_host", host)
        host_rows[host] = row
        require(row["identity"] == identity and row["sdk_freeze"] == SDK,
                "wrong_source", host)
        require(row["program_sha256"] == authenticated["program_sha256"],
                "wrong_program", host)
        suites = {name for name, spec in manifest["retained_suites"].items() if host in spec["hosts"]}
        require(set(authenticated["retained"]) == suites, "missing_suite", host)
        for suite_id in suites:
            retained_check(manifest["retained_suites"][suite_id], authenticated["retained"][suite_id],
                           identity, suite_id)
        cases = row["cases"]
        unique([case["id"] for case in cases], "duplicate_case", host)
        indexed = {case["id"]: case for case in cases}
        require(set(row["claims"]) == set(manifest["host_claims"][host]),
                "missing_claim", host)
        for claim, references in row["claims"].items():
            require(isinstance(references, list) and references, "missing_claim", host + ":" + claim)
            contract = manifest["claims"][claim]
            for reference in references:
                require(reference["role"] in contract["roles"], "wrong_claim_role", host + ":" + claim)
                require(reference["case_id"] in indexed, "missing_case", host + ":" + claim)
                case = indexed[reference["case_id"]]
                label = host + ":" + case["id"]
                require(case["outcome"] == "passed", "partial_case", label)
                require(case["actual_host_actions"] is True and case["receiver_database_injection"] is False,
                        "not_native", label)
                require(case["source_evidence"] and all(p in authenticated["evidence"]
                        for p in case["source_evidence"]), "missing_evidence", label)
                require(case["original_identity_preserved"] is True
                        and case["revision_bytes_preserved"] is True, "identity_changed", label)
                if contract["wire_required"]:
                    require(case["peer_wire_observed"] is True, "missing_wire", label)
                if claim == "concurrent_heads_preserved":
                    heads = case["competing_heads"]
                    unique(heads, "invalid_heads", label)
                    require(len(heads) >= 2 and case["conflict_displayed"] is True,
                            "silent_conflict", label)
                    if case.get("explicit_user_resolution", False):
                        exact(case["resolution_parents"], heads, "wrong_resolution_parents", label)
                        exact(case["final_heads"], [case["resolution_revision"]], "wrong_final_heads", label)
                    else:
                        exact(case["final_heads"], heads, "wrong_final_heads", label)
                elif claim == "delete_put_tombstone_preserved":
                    require(case["stale_peer_did_not_resurrect"] is True and case["tombstone_preserved"] is True,
                            "tombstone_lost", label)
                    require(case["delete_conflict_displayed"] is True, "silent_delete_conflict", label)
                    if case.get("explicit_user_restore", False):
                        exact(case["restore_parents"], case["competing_heads"], "wrong_restore_parents", label)
                elif claim == "cancel_retry":
                    require(case["cancel_layer"] in {"transport", "receive", "import"}
                            and case["native_cancel_observed"] is True and case["explicit_retry_passed"] is True,
                            "cancel_recovery_missing", label)
                elif claim == "process_recovery":
                    require(case["terminated_pid"] != case["reopened_pid"]
                            and case["actual_process_termination"] is True
                            and case["recovery_boundary"] and case["durable_recovery_passed"] is True,
                            "process_recovery_missing", label)
                elif claim == "offline_read":
                    require(case["reopened_host_readable"] is True and case["network_requests"] == 0,
                            "offline_read_missing", label)
    exact(list(host_rows), HOSTS, "missing_host", "six native receivers")
    return {"receipt_contract_passed": True, "F05_accepted": False,
            "reason": "Authenticated receipts and contract checks are not full independent product acceptance"}

def main():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "not_actions", "Actions execution only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original-artifacts", type=Path, required=True)
    args = parser.parse_args()
    identity = {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                "attempt": os.environ["GITHUB_RUN_ATTEMPT"]}
    result = {"identity": identity, "receipt_contract_passed": False, "F05_accepted": False, "errors": []}
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        require(subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == identity["source"],
                "wrong_source", "audit checkout")
        # Avoid consuming ZIP resources for the intentionally unfinished matrix.
        require(manifest["state"] == "ready-for-client-validation", "not_ready", "F05 preparation only")
        authenticated = authenticate(manifest, args.original_artifacts, identity)
        (args.original_artifacts / "authenticated.json").write_text(
            json.dumps(authenticated, indent=2) + "\n", encoding="utf-8")
        result.update(check(manifest, authenticated, identity))
    except (Rejected, KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile,
            subprocess.SubprocessError) as error:
        result["errors"].append({"code": getattr(error, "code", "malformed_evidence"), "detail": str(error)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    require(result["receipt_contract_passed"], "receipt_rejected", "see exact error keys")

if __name__ == "__main__":
    main()
