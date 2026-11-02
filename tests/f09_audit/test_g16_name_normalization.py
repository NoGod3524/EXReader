"""Eight additional synthetic controls; original twelve stay byte-identical."""
import copy
import json
import os
import unittest
from pathlib import Path
from g16_name_normalization import ax_name, candidate_name, name_equals
from g16_contract_v2_adapter import evaluate, digest
from test_g16_contract_v2 import fixture, RAW, CANDIDATE

class NameControls(unittest.TestCase):
    def check(self, fields, expected=True):
        data = fixture()
        item = data[0]["states"]["library.empty"][0]
        item.pop("name")
        item.update(fields)
        h = digest(data[0])
        data[1]["snapshot_sha256"] = h
        data[2]["synthetic-only"]["snapshot_sha256"] = h
        result = evaluate(RAW, CANDIDATE, *data)
        self.assertEqual(result["candidate_delta_passed"], expected, result)
        self.assertFalse(result["acceptance_eligible"])
        self.assertFalse(result["legacy_rules_evaluated"])

    def test_01_nonblank_label_priority(self):
        value = "  " + CANDIDATE["library_empty_name"] + "  "
        self.assertEqual(ax_name({"label": value, "value": "wrong"}), value)
        self.check({"label": value, "value": "wrong"})
    def test_02_empty_label_uses_value(self):
        self.check({"label": "", "value": CANDIDATE["library_empty_name"]})
    def test_03_whitespace_label_uses_value(self):
        self.check({"label": " \t\n", "value": CANDIDATE["library_empty_name"]})
    def test_04_nonstring_label_uses_string_value(self):
        self.check({"label": 12, "value": CANDIDATE["library_empty_name"]})
    def test_05_nonstring_or_missing_value_empty(self):
        for fields in ({"label": "", "value": 7}, {"label": None}, {"value": None}):
            self.assertEqual(ax_name(fields), "")
            self.check(fields, False)
    def test_06_compare_strips_both_sides(self):
        self.assertTrue(name_equals({"value": " \ttext\n"}, " text "))
        self.check({"value": " " + CANDIDATE["library_empty_name"] + "\n"})
    def test_07_raw_fields_cannot_be_overridden(self):
        self.check({"label": "wrong", "value": CANDIDATE["library_empty_name"],
                    "name": CANDIDATE["library_empty_name"]}, False)
        self.check({"label": "", "value": "", "name": CANDIDATE["library_empty_name"]}, False)
    def test_08_normalization_does_not_repair_identity(self):
        data = fixture()
        item = data[0]["states"]["library.empty"][0]
        item.pop("name")
        item["value"] = CANDIDATE["library_empty_name"]
        result = evaluate(RAW, CANDIDATE, *data)
        self.assertFalse(result["candidate_delta_passed"])
        self.assertFalse(result["acceptance_eligible"])
        self.assertIn("snapshot identity mismatch", result["failures"])

if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Actions only")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NameControls)
    assert suite.countTestCases() == 8
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"candidate_name_controls_validated": result.wasSuccessful(),
              "controls_expected": 8, "controls_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "synthetic_only": True, "acceptance_eligible": False,
              "real_ax_snapshots_retested": False, "source": os.environ.get("GITHUB_SHA")}
    output = Path("build/f09-g16-name-normalization")
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    raise SystemExit(0 if result.wasSuccessful() else 1)
