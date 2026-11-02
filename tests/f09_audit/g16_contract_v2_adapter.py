"""Candidate-only G16 delta evaluator. No legacy gate or device execution."""
import copy
import hashlib
import json
import re

LEGACY_SHA256 = "0d330a6841831494a15fafbf1f318d8441cffd9bee0a068fca9b10b3105ed2f1"
IDENTITY = ("source_sha", "run_id", "attempt", "artifact_id", "program_sha256",
            "build_settings_sha256", "snapshot_sha256")

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()

def check_legacy(raw):
    if hashlib.sha256(raw).hexdigest() != LEGACY_SHA256:
        raise ValueError("legacy contract bytes changed")
    return json.loads(raw)

def materialize(raw, candidate, mode):
    """Return a separate proposed contract; never write the legacy file."""
    legacy = check_legacy(raw)
    expected = {
        "schema": 2, "status": "candidate-only",
        "source_base": "190c52edccba76ea4054af2cbc3399f916a2269c",
        "reader_state_scope": "reader.epub", "acceptance_eligible": False,
        "legacy_path": "tests/reader_a11y_apple/a11y_contract.json",
        "library_empty_name": "书架为空，打开文件即可导入。",
    }
    if not isinstance(candidate, dict):
        raise ValueError("malformed candidate")
    for key, value in expected.items():
        if candidate.get(key) != value or type(candidate.get(key)) is not type(value):
            raise ValueError("candidate policy mismatch: " + key)
    if mode not in ("production", "review"):
        raise ValueError("unknown mode")
    if candidate["legacy_sha256"] != LEGACY_SHA256:
        raise ValueError("candidate legacy pin mismatch")
    if candidate["modes"] != {"production": "absent", "review": "required"}:
        raise ValueError("unsupported mode policy")
    contract = copy.deepcopy(legacy)
    matches = [x for x in contract["states"]["library.empty"]["required"]
               if x["id"] == "library.empty"]
    if len(matches) != 1:
        raise ValueError("ambiguous library rule")
    matches[0]["name_equals"] = candidate["library_empty_name"]
    reader = contract["states"]["reader.epub"]
    states = [x for x in reader["required"] if x["id"] == "reader.state"]
    if len(states) != 1:
        raise ValueError("ambiguous reader state rule")
    if mode == "production":
        reader["required"] = [x for x in reader["required"] if x["id"] != "reader.state"]
        reader["absent"] = ["reader.state"]
    return contract

def evaluate(raw, candidate, snapshot, evidence, trusted_receipts):
    """trusted_receipts must be independently pinned by the caller, not supplied
    by the evidence submitter. This module does not establish provenance.
    Every result is candidate-only, never formal G16/F09 acceptance.
    """
    result = {"acceptance_eligible": False, "candidate_delta_passed": False,
              "legacy_rules_evaluated": False, "failures": []}
    try:
        check_legacy(raw)
        if not isinstance(evidence, dict):
            raise ValueError("missing build-mode evidence")
        mode = evidence.get("mode")
        if mode not in ("production", "review"):
            raise ValueError("unknown mode")
        receipt = trusted_receipts.get(evidence.get("receipt_key"))
        if not isinstance(receipt, dict):
            raise ValueError("missing independently pinned receipt")
        for key in IDENTITY:
            if not evidence.get(key) or evidence[key] != receipt.get(key):
                raise ValueError("identity mismatch: " + key)
        if evidence.get("mode") != receipt.get("mode"):
            raise ValueError("receipt mode mismatch")
        settings = evidence.get("build_settings")
        if not isinstance(settings, dict) or digest(settings) != receipt["build_settings_sha256"]:
            raise ValueError("missing or mismatched build settings")
        conditions = settings.get("SWIFT_ACTIVE_COMPILATION_CONDITIONS")
        flags = settings.get("OTHER_SWIFT_FLAGS")
        if not isinstance(conditions, str) or not isinstance(flags, str):
            raise ValueError("incomplete build-mode settings")
        tokens = set(re.findall(r"EXR_APPLE_[A-Z0-9_]+", conditions + " " + flags))
        review = {x for x in tokens if x.endswith("_REVIEW")}
        if mode == "production" and review:
            raise ValueError("production has review compile flags")
        if mode == "review" and "EXR_APPLE_HOST_REVIEW" not in review:
            raise ValueError("review missing HOST_REVIEW compile flag")
        if not isinstance(snapshot, dict) or digest(snapshot) != receipt["snapshot_sha256"]:
            raise ValueError("snapshot identity mismatch")
        if snapshot.get("complete") is not True:
            raise ValueError("snapshot incomplete")
        if not isinstance(snapshot.get("identity"), dict) or not isinstance(snapshot.get("states"), dict):
            raise ValueError("malformed snapshot identity or states")
        for key in ("source_sha", "run_id", "attempt", "artifact_id", "program_sha256"):
            if snapshot.get("identity", {}).get(key) != receipt[key]:
                raise ValueError("snapshot program identity mismatch")
        states = snapshot.get("states", {})
        if "reader.epub" not in states or "library.empty" not in states:
            raise ValueError("missing required snapshot")
        for name in ("reader.epub", "library.empty"):
            rows = states[name]
            if not isinstance(rows, list) or any(not isinstance(x, dict) or
                not isinstance(x.get("id"), str) for x in rows):
                raise ValueError("malformed snapshot elements")
            ids = [x["id"] for x in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate element identifiers")
        materialize(raw, candidate, mode)
        reader = {x["id"]: x for x in states["reader.epub"]}
        shelf = {x["id"]: x for x in states["library.empty"]}
        if mode == "production" and "reader.state" in reader:
            raise ValueError("production reader.state must be absent")
        if mode == "review":
            item = reader.get("reader.state")
            if not item or item.get("role") != "StaticText" or not item.get("name"):
                raise ValueError("review reader.state must be present and named")
        item = shelf.get("library.empty")
        if not item or item.get("role") != "StaticText" or item.get("name") != candidate["library_empty_name"]:
            raise ValueError("library.empty name mismatch")
        result["candidate_delta_passed"] = True
    except (ValueError, KeyError, TypeError) as error:
        result["failures"].append(str(error))
    return result
