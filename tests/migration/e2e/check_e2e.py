#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real-browser chain, step 2: feed the pack that the browser exporter produced to the installed
migration tool, reopen the library in new processes and compare with what the page created."""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import legacy_data as L  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools"))
from check_legacy_migration import E2E_CHECK_IDS

checks = []


def check(ok, text):
    checks.append({"id": E2E_CHECK_IDS[len(checks)], "check": text, "ok": bool(ok)})
    print(("ok   " if ok else "FAIL ") + text, flush=True)


def run(tool, *args):
    p = subprocess.run([tool, *args], capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    return p.returncode, (json.loads(out) if out.strip() else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True)
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--spec", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    pack = os.path.join(a.export_dir, "legacy.exrpack")
    export = json.load(open(os.path.join(a.export_dir, "e2e-export.json"), encoding="utf-8"))
    T = os.path.join(a.work, "e2e-library.sqlite")
    for suffix in ("", ".legacy-map.json"):
        if os.path.exists(T + suffix):
            os.remove(T + suffix)

    check(export["before"]["version"] == 1 and export["before"]["stores"] == ["books", "files", "notes"], "the page really created IndexedDB 'exreader' version 1 with books/files/notes")
    check(export["source_unchanged"], "source database snapshot identical before and after the export (read-only)")
    check(export["missing_database"].get("threw") and not export["missing_database"].get("exists"), "exporting a missing database fails without creating it")
    check(export["export_summary"]["books"] == 5 and export["export_summary"]["notes"] == 15, "exporter summary: 5 books, 15 notes: %s" % export["export_summary"])

    code, ins = run(a.tool, "inspect", "--pack", pack)
    states = {i["legacy_id"]: i["state"] for i in ins["items"]}
    check(code == 0 and states == {"b-txt": "convertible", "b-epub": "convertible", "b-pdf": "convertible", "b-cbz": "convertible", "b-audio": "audio-positions-only"}, "inspect classifies the exported originals: %s" % states)

    code, strict = run(a.tool, "migrate", "--pack", pack, "--target", T)
    check(code == 2 and strict["code"] == "policy-strict" and not os.path.exists(T), "strict migration is rejected because an audio original cannot be stored; nothing published")

    code, first = run(a.tool, "migrate", "--pack", pack, "--target", T, "--allow-partial")
    check(code == 0 and first["result"] == "success", "migration with --allow-partial succeeds: %s" % (first or {}).get("message"))
    code, d1 = run(a.tool, "dump", "--target", T)
    want_shas = {b["sha256"] for b in json.load(open(a.spec, encoding="utf-8"))["books"] if not b["record"].get("audio")}
    check(code == 0 and {b["source_sha256"] for b in d1["books"]} == want_shas, "reopened library holds byte-identical originals")
    titles = {b["title"]: b for b in d1["books"]}
    check(set(titles) == {"The Tale", "Lighthouse Chronicle", "Scan", "Comic"}, "titles survive: %s" % sorted(titles))
    check(titles["Scan"]["position"] == 1 and titles["Comic"]["position"] == 1, "fixed-page positions (page 2 -> index 1; 0.5 of 3 pages -> index 1)")
    ep_notes = {n["text"]: n for n in titles["Lighthouse Chronicle"]["notes"]}
    check(ep_notes["exact range"]["exact"] == "cobalt lighthouse" and titles["Lighthouse Chronicle"]["progress_state"] == 1, "CFI range note and CFI progress resolved through the exporter's data")
    check({"second page", ""} <= {n["text"] for n in titles["Scan"]["notes"]}, "PDF quote note and page bookmark present")
    check(d1["audio"][0]["resume_ms"] == 75500 and len(d1["audio"][0]["bookmarks"]) == 2, "audio resume and bookmarks")
    unloc = sorted(n["legacy_id"] for n in first["notes"] if n["status"] == "unlocated")
    check(unloc == ["n-epub-ambiguous", "n-pdf-missing", "n-txt-ambiguous", "n-txt-bookmark", "n-txt-missing"], "unlocated annotations: %s" % unloc)
    led = json.load(open(T + ".legacy-map.json", encoding="utf-8"))
    check(len(led["books"]) == 5 and len(led["notes"]) == 15, "ledger lists every exported book and annotation")

    code, second = run(a.tool, "migrate", "--pack", pack, "--target", T, "--allow-partial")
    code2, d2 = run(a.tool, "dump", "--target", T)
    k = second["counts"]
    check(code == 0 and k["books_created"] == 0 and k["notes_created"] == 0 and json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True), "second migration is a no-op (same library content and IDs): %s" % k)
    code, ver = run(a.tool, "verify", "--pack", pack, "--target", T)
    check(code == 0 and ver["result"] == "success", "verify in a new process agrees")

    evidence = {"schema": 1, "kind": "wp12-legacy-migration-e2e", "browser": export["browser"], "user_agent": export["user_agent"],
                "indexeddb": {"database": "exreader", "version": export["before"]["version"], "stores": export["before"]["stores"], "books": export["before"]["books"], "notes": export["before"]["notes"], "files": export["before"]["files"]},
                "exporter_sha256": export["exporter_sha256"], "legacy_sources": export["legacy_sources"], "pack": export["pack"],
                "tool_sha256": hashlib.sha256(open(a.tool, "rb").read()).hexdigest(), "sdk_version": first["sdk_version"],
                "first_run": {"counts": first["counts"], "memory": first["memory"]}, "second_run": {"counts": second["counts"], "memory": second["memory"]},
                "checks": checks, "passed": all(c["ok"] for c in checks)}
    json.dump(evidence, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("e2e", "PASSED" if evidence["passed"] else "FAILED", "%d/%d checks" % (sum(c["ok"] for c in checks), len(checks)))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
