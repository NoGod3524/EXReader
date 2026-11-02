"""Synthetic handshake controls only; never substitute for native device evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import reader_android as reader


class OwnedStopHandshakeControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = {"source_sha": "a" * 40, "run_id": "synthetic-control", "attempt": "1"}
        self.stop = {"pid": 17, "window_id": 3}
        cases = [{"id": name, "status": "n/a" if name == "body_applicability" else "pass",
                  "finished_elapsed_ns": (i + 1) * 1_000_000_000} for i, name in enumerate(reader.CASES)]
        validation = {"identity": self.identity, "started_elapsed_ns": 0, "cases": cases}
        self.ready = {"schema": "reader-owned-stop-ready-v1", "nonce": "b" * 64,
                      "identity": self.identity, "helper_pid": 19, "product_pid": 17,
                      "ready_elapsed_ns": 9_000_000_000, "deadline_elapsed_ns": 180_000_000_000,
                      "validation": validation}
        self.ack = {"schema": "reader-owned-stop-ack-v1", "nonce": "b" * 64,
                    "identity": self.identity, "helper_pid": 19, "product_pid": 17,
                    "window_id": 3, "confirmed": True, "native_closed_elapsed_ns": 10_000_000_000}
        self.trace = {"nonce": "b" * 64, "instrumentation_thread_alive": False, "instrumentation_error": None}
        self.ui = {**copy.deepcopy(validation), "cleanup": {"started_elapsed_ns": 11_000_000_000},
                   "finished_elapsed_ns": 12_000_000_000}
        for folder, field in [("close-confirm/windows", "footer_elapsed_ns"),
                              ("close-confirm/windows/reader-draw", "elapsed_ns")]:
            p = self.root / folder / "window-17-3.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            rows = [{"kind": "start", "pid": 17, "window_id": 3},
                    {"kind": "stop", "stop_reason": "owned_reader_stop", field: 10_000_000_000}]
            p.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.write()

    def write(self):
        raw = (json.dumps(self.ready, sort_keys=True) + "\n").encode()
        (self.root / "actions-ready.json").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.ack["ready_sha256"] = self.trace["ready_sha256"] = digest
        self.ui["native_stop_handshake"] = copy.deepcopy(self.ack)
        for name, value in [("stop-ack.json", self.ack), ("reader-ui-lifecycle.json", self.trace)]:
            reader.save(self.root / name, value)

    def check(self):
        reader.validate_owned_stop_handshake(self.root, self.ui, self.identity, self.stop)

    def rejects(self):
        with self.assertRaises((ValueError, KeyError, TypeError, FileNotFoundError)):
            self.check()

    def test_complete_authenticated_order(self):
        self.check()

    def test_missing_required_nonce(self):
        del self.ready["nonce"]
        self.write()
        self.rejects()

    def test_old_ready_run_identity(self):
        self.ready["identity"] = {**self.identity, "run_id": "older-control"}
        self.write()
        self.rejects()

    def test_nonce_mismatch(self):
        self.ack["nonce"] = "c" * 64
        self.write()
        self.rejects()

    def test_wrong_product_pid(self):
        self.ack["product_pid"] = 18
        self.write()
        self.rejects()

    def test_wrong_window(self):
        self.ack["window_id"] = 4
        self.write()
        self.rejects()

    def test_ready_bytes_changed_after_ack(self):
        with (self.root / "actions-ready.json").open("ab") as f:
            f.write(b" ")
        self.rejects()

    def test_missing_ack(self):
        (self.root / "stop-ack.json").unlink()
        self.rejects()

    def test_instrumentation_still_running(self):
        self.trace["instrumentation_thread_alive"] = True
        self.write()
        self.rejects()

    def test_instrumentation_error_retained(self):
        self.trace["instrumentation_error"] = "retained original error"
        self.write()
        self.rejects()

    def test_cleanup_before_native_close(self):
        self.ui["cleanup"]["started_elapsed_ns"] = 9_500_000_000
        self.write()
        self.rejects()

    def test_cohort_deadline_not_extended(self):
        self.ready["deadline_elapsed_ns"] += 1
        self.write()
        self.rejects()

    def test_cleanup_reserve_not_consumed(self):
        self.ready["ready_elapsed_ns"] = 171_000_000_000
        self.write()
        self.rejects()

    def test_final_cleanup_within_original_cohort(self):
        self.ui["finished_elapsed_ns"] = 181_000_000_000
        self.write()
        self.rejects()

    def test_activity_destroy_is_not_explicit_stop(self):
        p = self.root / "close-confirm/windows/window-17-3.jsonl"
        p.write_text(p.read_text().replace("owned_reader_stop", "activity_destroy"), encoding="utf-8")
        self.rejects()

    def test_missing_native_close_stream(self):
        (self.root / "close-confirm/windows/reader-draw/window-17-3.jsonl").unlink()
        self.rejects()

    def test_ack_cannot_invent_native_close_time(self):
        self.ack["native_closed_elapsed_ns"] -= 1
        self.write()
        self.rejects()

    def test_changed_case_after_readiness(self):
        self.ui["cases"][0]["status"] = "fail"
        self.write()
        self.rejects()


if __name__ == "__main__":
    unittest.main()
