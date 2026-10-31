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
        item = manifest["retained"][host]
        report = read(file_record(root, item))
        same_identity(report, stamp)
        require(report.get("accepted") is True and report.get("failed", 0) == 0 and
                report.get("skipped", 0) == 0 and not report.get("problems", []),
                "retained host failure: " + host)
        require(report.get("sdk_version") == SCOPE["sdk_version"], "retained SDK missing")
        require(report.get("program_sha256") == manifest["programs"][host], "retained binary mismatch")
    rounds = manifest["rounds"]
    require(rounds and all(r["author"] in SCOPE["hosts"] for r in rounds), "invalid author rounds")
    require(len({r["author"] for r in rounds}) >= 2, "at least two actual device authors required")
    previous_wire = {}
    for round_number, round_record in enumerate(rounds):
        author = round_record["author"]
        require(round_record["operations"] == SCOPE["operations"], "lifecycle incomplete")
        wire = read(file_record(root, round_record["wire"]))
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
        require(set(operation_evidence) == set(SCOPE["operations"]), "UI operations unproven")
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
            require(requests and all(r.get("authenticated") is True for r in requests),
                    "network authenticity absent")
            method = "PUT" if host == author else "GET"
            require(any(r.get("method") == method and "/revisions/" in r.get("path", "")
                        for r in requests), "required native revision transport absent")
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
