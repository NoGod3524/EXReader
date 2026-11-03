"""Actions-only counterexamples for case alignment and clipboard cleanup."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from case_alignment import CASES, align_cases
from fixture import write_role_receipt
import native_runtime
from driver import deletion_detail_contract, native_cleanup_contract
from retained_diagnostics import targeted_return


class RecoveryChecks(unittest.TestCase):
    def test_import_return_targets_original_window_and_preserves_errors(self):
        alive=Mock(returncode=0,stdout='456\n')
        gone=Mock(returncode=1,stdout='')
        reply={'window':'123','pid':456,'focus':'123','sent':True,'mechanism':'XTest-server-grab'}
        send,record=Mock(return_value=json.dumps(reply)),Mock()
        self.assertEqual(targeted_return('123',456,1,send,Mock(return_value=alive),record),'')
        self.assertEqual(send.call_args.args[-2:],('123','456'))
        self.assertTrue(send.call_args.args[1].endswith('x11_return.py'))
        send.reset_mock()
        targeted_return('123',456,2,send,Mock(return_value=gone),record)
        send.assert_not_called()
        with self.assertRaises(RuntimeError):targeted_return('123',456,1,send,Mock(return_value=gone),record)
        with self.assertRaises(AssertionError):targeted_return('123',999,1,send,Mock(return_value=alive),record)
        failure=subprocess.CalledProcessError(1,['xdotool','key'])
        send.side_effect=failure
        with self.assertRaises(subprocess.CalledProcessError):
            targeted_return('123',456,2,send,Mock(return_value=alive),record)
        send.side_effect=None;send.return_value=json.dumps(dict(reply,focus='999',sent=False))
        targeted_return('123',456,2,send,Mock(return_value=alive),record)
        self.assertTrue(record.call_args.kwargs['ignored_after_close'])
        with self.assertRaises(RuntimeError):targeted_return('123',456,1,send,Mock(return_value=alive),record)
        send.return_value=json.dumps(dict(reply,pid=999))
        with self.assertRaises(AssertionError):targeted_return('123',456,2,send,Mock(return_value=alive),record)

    def test_full_run_cleanup_records_and_deadline(self):
        rows=[{"action":"native-close-"+str(i),"seconds":.1} for i in range(4)]
        self.assertEqual(native_cleanup_contract(rows),rows)
        variants=[rows[:3], [], rows+[copy.deepcopy(rows[-1])],
                  rows[:2]+[dict(rows[2],seconds=20.01)]+rows[3:],
                  rows[:2]+[dict(rows[2],seconds=True)]+rows[3:]]
        for damaged in variants:
            with self.assertRaises(AssertionError):native_cleanup_contract(damaged)

    def test_native_deletion_detail_counterexamples(self):
        case={"entity_key":"tag-control", "retained_heads":["put-head","delete-head"],
              "deletion_conflict_ui_detail":True,"deletion_details":{}}
        for peer in ("first","second"):
            case['deletion_details'][peer]={"screenshot":"delete-detail-"+peer+".png", "state":{
                "visible":"1","editor":"1","editor_accept":"0","selected_id":"tag-control","kind":"1",
                "editor_conflict_heads":"put-head,delete-head",
                "editor_notice":"Version 1: Edit retained\\nVersion 2: Deletion requested"}}
        deletion_detail_contract(case)
        changes=[lambda c:c['deletion_details'].pop('second'),
                 lambda c:c['deletion_details']['first']['state'].update(editor_accept='1'),
                 lambda c:c['deletion_details']['first']['state'].update(editor='0'),
                 lambda c:c['deletion_details']['first']['state'].update(selected_id='other-tag'),
                 lambda c:c['deletion_details']['first']['state'].update(editor_conflict_heads='put-head'),
                 lambda c:c['deletion_details']['first']['state'].update(editor_notice='Versions differ'),
                 lambda c:c['deletion_details']['first'].update(screenshot='unrelated.png')]
        for change in changes:
            damaged=copy.deepcopy(case);change(damaged)
            with self.assertRaises(AssertionError):deletion_detail_contract(damaged)

    def reports(self, count=2):
        coverage = [{"name":row[0], "outcome":"passed"} for row in CASES[:count]]
        normalized = [{"id":row[0], "outcome":"passed", "source_evidence":["coverage.json"]}
                      for row in CASES[:count]]
        claims = {row[1]:[{"case_id":row[0], "role":row[2]}] for row in CASES[:count]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/"coverage.json").write_text(json.dumps(coverage))
            program = path/"test-program"
            program.write_bytes(b"comparator-control-only")
            write_role_receipt(path, "linux", program, {}, normalized, claims, ["coverage.json"])
            receipt = json.loads((path/"receipt.json").read_text())
        return coverage, receipt

    def test_actual_writer_not_run_and_reordered_cases(self):
        coverage, receipt = self.reports()
        rows = align_cases(coverage[::-1], receipt["cases"][::-1], receipt["claims"])
        self.assertEqual([r["executed"] for r in rows], [True, True, False, False, False, False])
        self.assertEqual([r["outcome"] for r in rows][2:], ["not-run"]*4)

    def test_full_execution(self):
        coverage, receipt = self.reports(6)
        self.assertTrue(all(r["executed"] for r in align_cases(coverage, receipt["cases"], receipt["claims"])))

    def test_negative_cases(self):
        coverage, receipt = self.reports()
        variants = []
        def variant(change):
            c, r = copy.deepcopy(coverage), copy.deepcopy(receipt)
            change(c, r)
            variants.append((c, r))
        variant(lambda c,r: c.clear())
        variant(lambda c,r: c.append(copy.deepcopy(c[0])))
        variant(lambda c,r: c.append({"name":"extra", "outcome":"passed"}))
        variant(lambda c,r: c.pop())
        variant(lambda c,r: r["cases"].pop())
        variant(lambda c,r: r["cases"].__setitem__(1, copy.deepcopy(r["cases"][0])))
        variant(lambda c,r: r["cases"][0].update(outcome="failed"))
        variant(lambda c,r: r["cases"][2].update(outcome="passed"))
        variant(lambda c,r: r["cases"][2].update(reason="arbitrary placeholder"))
        variant(lambda c,r: r["cases"][2].update(id="not-run-extra"))
        variant(lambda c,r: r["cases"][2].update(actual_host_actions=True))
        variant(lambda c,r: r["claims"].pop("offline_read"))
        variant(lambda c,r: r["claims"]["offline_read"][0].update(case_id="cancel_sync_retry"))
        for index, (c, r) in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                align_cases(c, r["cases"], r["claims"])

    def test_cleanup_checks_group_after_leader_exited(self):
        process = Mock(pid=123)
        with patch.object(native_runtime.os, "killpg", side_effect=[None, None, ProcessLookupError]), \
             patch.object(native_runtime.time, "sleep"):
            native_runtime.reap_group(process)
        process.wait.assert_called_once()

    def test_remaining_group_is_failure(self):
        with patch.object(native_runtime.os, "killpg"), \
             patch.object(native_runtime.time, "monotonic", side_effect=[0, 0, 6]), \
             self.assertRaises(TimeoutError):
            native_runtime.reap_group(Mock(pid=123))

    def test_clipboard_preserves_first_exception(self):
        first = ValueError("first clipboard failure")
        process = Mock()
        process.stdin.write.side_effect = first
        with patch.object(native_runtime.subprocess, "Popen", return_value=process), \
             patch.object(native_runtime, "reap_group", side_effect=RuntimeError("cleanup failure")):
            with self.assertRaises(ValueError) as caught:
                native_runtime.paste(Mock(), "fixture")
        self.assertIs(caught.exception, first)
        self.assertIn("cleanup failure", caught.exception.f05_cleanup_errors[0])

    def test_real_clipboard_owner_reaped(self):
        class Host:
            def key(self, key):
                self.value = subprocess.check_output(["xclip", "-o", "-selection", "clipboard"], timeout=5)
        host = Host()
        native_runtime.paste(host, "F05 clipboard control")
        self.assertEqual(host.value, b"F05 clipboard control")


if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    unittest.main(verbosity=2)
