"""Exactly twelve synthetic controls; Actions only; no app/device execution."""
import copy
import json
import os
from pathlib import Path
import unittest
from g16_contract_v2_adapter import evaluate, materialize, check_legacy, digest

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / "tests/reader_a11y_apple/a11y_contract.json").read_bytes()
CANDIDATE = json.loads(Path(__file__).with_name("g16_contract_v2.json").read_text())

def fixture(mode="production", present=False, name=None):
    settings = {"SWIFT_ACTIVE_COMPILATION_CONDITIONS":
                "DEBUG EXR_APPLE_HOST_REVIEW" if mode == "review" else "DEBUG",
                "OTHER_SWIFT_FLAGS": ""}
    identity = {"source_sha": "a"*40, "run_id": 1, "attempt": 1,
                "artifact_id": 2, "program_sha256": "b"*64}
    snapshot = {"complete": True, "identity": identity,
                "states": {"reader.epub": [],
                           "library.empty": [{"id": "library.empty", "role": "StaticText",
                            "name": CANDIDATE["library_empty_name"] if name is None else name}]}}
    if present:
        snapshot["states"]["reader.epub"].append(
            {"id": "reader.state", "role": "StaticText", "name": "Review state"})
    receipt = dict(identity, mode=mode, build_settings_sha256=digest(settings),
                   snapshot_sha256=digest(snapshot))
    evidence = dict(receipt, receipt_key="synthetic-only", build_settings=settings)
    return snapshot, evidence, {"synthetic-only": copy.deepcopy(receipt)}

class Controls(unittest.TestCase):
    def outcome(self, data, expected):
        result = evaluate(RAW, CANDIDATE, *data)
        self.assertEqual(result["candidate_delta_passed"], expected, result)
        self.assertFalse(result["acceptance_eligible"])
        self.assertFalse(result["legacy_rules_evaluated"])
        if not expected:
            self.assertTrue(result["failures"])

    def test_01_production_absent(self):
        self.outcome(fixture(), True)
    def test_02_production_present(self):
        self.outcome(fixture(present=True), False)
    def test_03_review_present(self):
        self.outcome(fixture(mode="review", present=True), True)
    def test_04_review_absent(self):
        self.outcome(fixture(mode="review"), False)
    def test_05_current_shelf_name(self):
        self.outcome(fixture(name="书架为空，打开文件即可导入。"), True)
    def test_06_old_shelf_name(self):
        self.outcome(fixture(name="书架为空，导入一本示例书开始。"), False)
    def test_07_empty_shelf_name(self):
        self.outcome(fixture(name=""), False)
    def test_08_unknown_mode(self):
        data = fixture()
        data[1]["mode"] = "unknown"
        self.outcome(data, False)
    def test_09_missing_build_evidence(self):
        data = fixture()
        self.outcome((data[0], None, data[2]), False)
    def test_10_mismatched_build_mode(self):
        data = fixture()
        data[1]["mode"] = "review"
        self.outcome(data, False)
        # Reject a self-consistent submitter rewrite against the independent pin.
        forged = fixture()
        forged[1]["build_settings"]["SWIFT_ACTIVE_COMPILATION_CONDITIONS"] = "DEBUG EXR_APPLE_HOST_REVIEW"
        forged[1]["build_settings_sha256"] = digest(forged[1]["build_settings"])
        self.outcome(forged, False)
    def test_11_missing_reader_snapshot(self):
        data = fixture()
        del data[0]["states"]["reader.epub"]
        # Independently model a genuinely collected incomplete tree, not only hash tampering.
        data[2]["synthetic-only"]["snapshot_sha256"] = digest(data[0])
        data[1]["snapshot_sha256"] = digest(data[0])
        self.outcome(data, False)
    def test_12_legacy_hash_and_other_rules_unchanged(self):
        old = check_legacy(RAW)
        for mode in ("production", "review"):
            adapted = materialize(RAW, CANDIDATE, mode)
            expected = copy.deepcopy(old)
            shelf = next(x for x in expected["states"]["library.empty"]["required"] if x["id"] == "library.empty")
            shelf["name_equals"] = CANDIDATE["library_empty_name"]
            if mode == "production":
                reader = expected["states"]["reader.epub"]
                reader["required"] = [x for x in reader["required"] if x["id"] != "reader.state"]
                reader["absent"] = ["reader.state"]
            self.assertEqual(adapted, expected)
        with self.assertRaises(ValueError):
            check_legacy(RAW + b" ")
        altered = copy.deepcopy(CANDIDATE)
        altered["legacy_sha256"] = "0"*64
        self.assertFalse(evaluate(RAW, altered, *fixture())["candidate_delta_passed"])
        for key, value in (("schema", 3), ("status", "accepted"),
                           ("source_base", "0"*40), ("reader_state_scope", "other"),
                           ("acceptance_eligible", True), ("library_empty_name", "wrong")):
            altered = copy.deepcopy(CANDIDATE)
            altered[key] = value
            self.assertFalse(evaluate(RAW, altered, *fixture())["candidate_delta_passed"])
        for key in ("states", "identity"):
            malformed = fixture()
            malformed[0][key] = None
            h = digest(malformed[0])
            malformed[1]["snapshot_sha256"] = h
            malformed[2]["synthetic-only"]["snapshot_sha256"] = h
            self.outcome(malformed, False)

if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Actions only")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    if suite.countTestCases() != 12:
        raise SystemExit("control budget must be exactly 12")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"candidate_contract_validated": result.wasSuccessful(),
              "acceptance_eligible": False, "synthetic_only": True,
              "real_ax_snapshots_retested": False, "controls_expected": 12,
              "controls_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "legacy_sha256": CANDIDATE["legacy_sha256"],
              "source": os.environ.get("GITHUB_SHA")}
    output = ROOT / "build/f09-g16-contract-v2"
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)
