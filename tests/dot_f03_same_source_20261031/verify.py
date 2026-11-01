"""Fail-closed F03 convergence audit; preparatory/local evidence can never award F03."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from identity import SCOPE, TABLES, canonical, digest, identity, require, same_identity, write_json

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
def file_record(root, item):
    path = (root / item["path"]).resolve(strict=True)
    require(path.is_relative_to(root.resolve()), "evidence path escape")
    require(path.stat().st_size == item["bytes"] and digest(path) == item["sha256"],
            "evidence bytes differ: " + item["path"])
    return path
def projection(value, selected):
    result = {}
    for table, columns in TABLES.items():
        rows = value[table]
        require(all(set(row) == set(columns) for row in rows), "wrong projection columns")
        ids = selected[table]
        key = columns[0]
        result[table] = sorted([row for row in rows if row[key] in ids],
                               key=lambda row: canonical(row))
    return result

def retained_binding(root, manifest, host, stamp):
    """Keep original schema; bind its real bytes to successful same-run producer evidence."""
    report = read(file_record(root, manifest["retained"][host]))
    same_identity(report, stamp)
    require(report.get("accepted") is True and report.get("failed", 0) == 0 and
            report.get("skipped", 0) == 0 and not report.get("problems", []),
            "retained host failure: " + host)
    binding = manifest["producer_evidence"][host]
    job = read(file_record(root, binding["job_metadata"]))
    require(str(job.get("run_id")) == stamp["run_id"] and
            str(job.get("run_attempt")) == stamp["attempt"] and
            job.get("head_sha") == stamp["source_sha"] and
            job.get("status") == "completed" and job.get("conclusion") == "success",
            "producer job not successful at this source/run/attempt: " + host)
    artifact = read(file_record(root, binding["artifact_metadata"]))
    origin = artifact.get("workflow_run", {})
    require(str(origin.get("id")) == stamp["run_id"] and
            origin.get("head_sha") == stamp["source_sha"] and not artifact.get("expired"),
            "artifact provenance differs: " + host)
    archive = file_record(root, binding["archive"])
    require(archive.stat().st_size == artifact.get("size_in_bytes") and
            artifact.get("digest") == "sha256:" + digest(archive),
            "original artifact bytes differ: " + host)
    build = read(file_record(root, binding["build"]))
    same_identity(build, stamp)
    require(build.get("operation_completed") is True and
            build.get("sdk_source") == SCOPE["sdk_source"] and
            build.get("sdk_version") == SCOPE["sdk_version"],
            "SDK build provenance incomplete: " + host)
    program = file_record(root, binding["program"])
    require(digest(program) == manifest["programs"][host], "actual program bytes differ: " + host)
    fields = {"windows": "consumer_sha256", "gtk": "program_sha256",
              "macos": "executable_sha256", "iphone": "executable_sha256",
              "ipad": "executable_sha256"}
    if host == "android":
        driver = read(file_record(root, binding["installed_apk_receipt"]))
        same_identity(driver, stamp)
        require(driver.get("mode") == "retained" and driver.get("native_lifecycle_passed") is True and
                driver.get("apk_sha256", {}).get("host_apk") == digest(program),
                "actual retained installed APK differs")
        # The original checker validates its native/UI/XML/recovery cases and all-exits.
        require(report.get("native_checks") == 8 and report.get("real_ui_checks") == 8 and
                report.get("real_process_retry_checks") == 1 and
                report.get("original_owner_checks") == 17 and
                report.get("original_typed_kill_checks") == 2 and
                report.get("original_functional_checks") == 112 and
                report.get("original_gate_checks") == 87 and
                report.get("original_owner_altered_evidence_checks") == 19,
                "original Android all-exits coverage incomplete")
    else:
        require(report.get(fields[host]) == digest(program), "retained native executable differs: " + host)
    # Archive member identity must be established by the Actions extraction admission,
    # not by adding nonexistent fields to the preserved original report.
    members = read(file_record(root, binding["archive_members"]))
    same_identity(members, stamp)
    require(members.get("archive_sha256") == digest(archive) and
            members.get("artifact_id") == artifact.get("id") and
            members.get("producer_job_id") == job.get("id"),
            "artifact member admission provenance differs")
    for role, record in (("retained-report", manifest["retained"][host]),
                         ("build-identity", binding["build"]), ("program", binding["program"])):
        archive_member = record.get("archive_member")
        require(isinstance(archive_member, str) and archive_member and
                not archive_member.startswith("/") and "\\" not in archive_member and
                ":" not in archive_member and ".." not in archive_member.split("/"), "artifact member path invalid")
        matches = [m for m in members.get("members", []) if m.get("path") == archive_member]
        require(len(matches) == 1 and matches[0].get("role") == role and
                matches[0].get("sha256") == record["sha256"] and
                matches[0].get("bytes") == record["bytes"], "original artifact member missing/wrong role")

def audit(root, manifest, stamp):
    same_identity(manifest, stamp)
    require(manifest.get("sdk_version") == SCOPE["sdk_version"], "SDK version differs")
    require(manifest.get("producer_kind") == "actual-native-hosts", "not actual host producer")
    require(manifest.get("hosts") == SCOPE["hosts"], "missing or reordered host set")
    require(manifest.get("same_source") is True, "not one source")
    require(manifest.get("synthesized_revisions") is False, "synthetic revisions refused")
    require(manifest.get("retained_suites_complete") is True, "original suites not complete")
    # Historical red runs remain evidence; they do not fulfill current mandatory retained suites.
    for host in SCOPE["hosts"]:
        retained_binding(root, manifest, host, stamp)
    rounds = manifest["rounds"]
    require(rounds and all(r["author"] in SCOPE["hosts"] for r in rounds), "invalid author rounds")
    covered_operations = set()
    previous_wire = {}
    previous_wire_digest = None
    for round_number, round_record in enumerate(rounds):
        author = round_record["author"]
        operations = round_record["operations"]
        require(operations and set(operations).issubset(SCOPE["operations"]), "unknown lifecycle operation")
        covered_operations.update(operations)
        wire_path = file_record(root, round_record["wire"])
        wire = read(wire_path)
        restart_only = set(operations) == {"restart"}
        if restart_only:
            require(previous_wire_digest is not None and
                    round_record.get("previous_wire_sha256") == previous_wire_digest,
                    "restart lacks preceding authentic author wire")
        same_identity(wire, stamp)
        bodies = {}
        for key, record in wire["entries"].items():
            body = base64.b64decode(record["body"], validate=True)
            require(hashlib.sha256(body).hexdigest() == record["sha256"], "wire digest mismatch")
            bodies[key] = body
        require(all(bodies.get(k) == v for k, v in previous_wire.items()),
                "immutable wire history overwritten")
        previous_wire = bodies
        receipts = round_record["receipts"]
        require(set(receipts) == set(SCOPE["hosts"]), "six receivers required in each round")
        expected_projection = None
        required_revisions = set(round_record["revision_ids"])
        require(required_revisions, "no actual lifecycle revisions")
        wire_revisions = {}
        for key, body in bodies.items():
            if "/revisions/" not in key:
                continue
            value = json.loads(body)
            if isinstance(value, dict) and value.get("id") in required_revisions:
                require(value["id"] not in wire_revisions, "duplicate revision identity")
                wire_revisions[value["id"]] = value
        require(set(wire_revisions) == required_revisions, "missing authored wire revisions")
        operation_evidence = round_record["operation_evidence"]
        require(set(operation_evidence) == set(operations), "UI operations unproven")
        for operation, item in operation_evidence.items():
            raw = file_record(root, item)
            event = read(raw)
            same_identity(event, stamp)
            require(event.get("host") == author and event.get("operation") == operation and
                    event.get("passed") is True and event.get("native_ui") is True,
                    "missing native operation witness")
            require(event.get("program_sha256") == manifest["programs"][author], "wrong author program")
            require(set(event.get("revision_ids", [])).issubset(required_revisions),
                    "operation revision not on authentic wire")
            original = event.get("original_assertion_files", [])
            require(original, "native original assertion evidence missing")
            for original_file in original:
                file_record(root, original_file)
            # A new screenshot filename/role is NOT an original acceptance requirement.
            # Native original logs/results can evidence the operation without a new PNG.
        for host, record in receipts.items():
            receipt = read(file_record(root, record))
            same_identity(receipt, stamp)
            require(receipt.get("host") == host and receipt.get("sdk_version") == SCOPE["sdk_version"],
                    "receiver identity differs")
            require(receipt.get("program_sha256") == manifest["programs"][host], "receiver program differs")
            if not restart_only:
                require(receipt.get("native_sync_completed") is True, "receiver bypassed native sync")
            require(receipt.get("restart_verified") is True, "receiver persistence unverified")
            snapshot = receipt["snapshot"]
            require(hashlib.sha256(canonical(snapshot)).hexdigest() == receipt["snapshot_sha256"],
                    "snapshot digest mismatch")
            local = {r["id"]: r["body"] for r in snapshot["revisions"]}
            require(all(local.get(rid) == body for rid, body in wire_revisions.items()),
                    "receiver lacks exact wire revision bodies")
            actual = projection(snapshot, round_record["selected"])
            if expected_projection is None:
                expected_projection = actual
            require(actual == expected_projection, "cross-host organization diverges")
            requests = read(file_record(root, receipt["requests"]))
            require(isinstance(requests, list) and (restart_only or requests) and
                    all(r.get("authenticated") is True for r in requests),
                    "network authenticity absent")
            if not restart_only:
                method = "PUT" if host == author else "GET"
                require(any(r.get("method") == method and "/revisions/" in r.get("path", "")
                            for r in requests), "required native revision transport absent")
        previous_wire_digest = digest(wire_path)
    require(covered_operations == set(SCOPE["operations"]), "lifecycle coverage incomplete")
    require(SCOPE["complete"] is True and SCOPE["ci_authorized"] is True,
            "preparation_only: final acceptance disabled by current authorization")
    return {**stamp, "accepted": True, "preparation_only": False,
            "requirement": "F03", "sdk_version": SCOPE["sdk_version"],
            "hosts": SCOPE["hosts"], "author_rounds": len(rounds),
            "scope": "same-source six-host organization lifecycle consistency",
            "physical_device_accepted": False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    stamp = identity()
    result = {**stamp, "accepted": False, "preparation_only": not SCOPE["complete"], "requirement": "F03", "problems": []}
    try:
        result = audit(a.manifest.parent, read(a.manifest), stamp)
    except Exception as error:
        result["problems"].append(type(error).__name__ + ": " + str(error))
        write_json(a.output, result)
        raise
    write_json(a.output, result)
if __name__ == "__main__":
    main()
