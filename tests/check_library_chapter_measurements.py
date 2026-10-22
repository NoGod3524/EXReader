"""Exercise the new stored-EPUB rejection boundary; execute in CI only."""
# SPDX-License-Identifier: MIT
import copy
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("wp6_runner", Path(__file__).resolve().parents[1] / "tools/run_wp6_bounded_probe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

record = {"exit": 0, "report": {"status": 0, "sequential": {"page_hashes": [{"hash": "0123456789abcdef", "start": 0}]}, "library": {
    "imported": True, "progress_stored": True, "reopened": True, "resolved": True,
    "page_hash_equal": True, "tail_checked": True, "source_bytes": 123,
    "reference_page": 0, "tail_bytes_checked": 32, "reopened_source_bytes": 123,
    "reference_hash": "0123456789abcdef", "reopened_hash": "0123456789abcdef",
    "saved_chapter_offset": 0, "resolved_offset": 0, "resolved_state": 1, "progress_present": True}}}
assert module.library_record_ok(record, 123)
negative = 0
for key in record["report"]["library"]:
    bad = copy.deepcopy(record)
    del bad["report"]["library"][key]
    assert not module.library_record_ok(bad, 123), key
    negative += 1
for key in ("imported", "progress_stored", "reopened", "resolved", "page_hash_equal", "tail_checked"):
    bad = copy.deepcopy(record)
    bad["report"]["library"][key] = 1  # Numeric truthiness is not an executed-success claim.
    assert not module.library_record_ok(bad, 123), key
    negative += 1
for key, value in (("source_bytes", 124), ("reopened_source_bytes", 124), ("reference_page", 1),
                   ("resolved_state", 2), ("resolved_offset", 1), ("saved_chapter_offset", 1),
                   ("reopened_hash", "wrong"), ("reference_hash", "wrong"),
                   ("tail_bytes_checked", 0), ("tail_bytes_checked", 129)):
    bad = copy.deepcopy(record)
    bad["report"]["library"][key] = value
    assert not module.library_record_ok(bad, 123), key
    negative += 1
for key in ("exit", "status"):
    bad = copy.deepcopy(record)
    (bad if key == "exit" else bad["report"])[key] = 1
    assert not module.library_record_ok(bad, 123), key
    negative += 1
assert not module.library_record_ok({}, 123)
bad = copy.deepcopy(record)
bad["report"]["library"]["reference_hash"] = bad["report"]["library"]["reopened_hash"] = "stable but wrong"
assert not module.library_record_ok(bad, 123)
print(f"{negative + 2} library measurement rejection checks passed")
