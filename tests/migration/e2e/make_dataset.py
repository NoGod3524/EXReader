#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Writes the legacy dataset (originals + records) that the browser driver loads into IndexedDB."""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import legacy_data as L  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
books, notes = L.dataset()
spec = {"books": [], "notes": [n for n in notes if n["bookId"] != "b-gone"]}  # the old app deletes notes together with their book
for b in books:
    spec["books"].append({"record": dict(b["record"]), "file_b64": base64.b64encode(b["data"]).decode(), "sha256": L.sha256(b["data"])})
json.dump(spec, open(os.path.join(out, "spec.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", len(spec["books"]), "books and", len(spec["notes"]), "notes")
