# SPDX-License-Identifier: MIT
"""Independent actual GTK host artifact semantics after API/ZIP provenance checks."""
import json
import sqlite3
from protocols import need, sha, json_value
from gtk_snapshots import audit_gtk_snapshots

def sqlite_books(raw):
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(raw)
        connection.execute("PRAGMA query_only=ON")
        return connection.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
    finally:
        connection.close()

def audit_gtk_host(files, spec, source, expected_cases):
    runtime = spec["runtime_prefix"]
    evidence = spec["evidence_prefix"]
    package = spec["package_prefix"]
    report = json_value(files[runtime + "report.json"])
    need(report["source"] == source and str(report["run"]) == str(spec["run"]) and
         str(report["attempt"]) == str(spec["attempt"]), "gtk-runtime-producer")
    need(report["actual_gtk"] is True and report["actual_sdk"] is True and
         report["actual_migration"] is False and report["full_c02_acceptance"] is False and
         report["passed"] is True and report["complete"] is True, "gtk-runtime-scope")
    rows = report["cases"]
    need(len(rows) == len(expected_cases) and len(rows) >= 13 and
         {row["name"] for row in rows} == expected_cases and
         all(row["passed"] is True for row in rows), "gtk-source-declared-original-cases")
    snapshots = audit_gtk_snapshots(files, runtime)
    original = files[runtime + "book.txt"]
    need(original and len(original.splitlines()) == 100, "gtk-original-source-fixture")
    for phase in ("clean", "borrowed", "released", "pending"):
        primary = sqlite_books(files[runtime + "snapshots/" + phase + "/library-0.sqlite"])
        secondary = sqlite_books(files[runtime + "snapshots/" + phase + "/library-1.sqlite"])
        need(not secondary, "gtk-second-library-independently-empty")
        if phase == "clean":
            need(not primary, "gtk-clean-library-independently-empty")
        else:
            need(len(primary) == 1 and type(primary[0][0]) is int and primary[0][0] > 0 and
                 bytes(primary[0][2]) == original, "gtk-actual-sqlite-retained-original")
    for name in ("unknown-host", "pending-actual-host", "replacement-identity", "copied-unregistered"):
        need(b"Library admission refused." in files[runtime + name + ".stderr"],
             "gtk-actual-before-sdk-refusal:" + name)
    for name in ("c02-gtk-host-check", "exreader-linux", "exreader-c02-admission"):
        need(files[evidence + name].startswith(b"\x7fELF"), "gtk-actual-native-binary:" + name)
    manifest = json_value(files[package + "build.json"])
    need(manifest["source_sha"] == source and manifest["sdk_version"] == "3.42.0" and
         manifest["c02_admission"] is True, "gtk-package-producer")
    for name in ("exreader-linux", "exreader-c02-admission"):
        need(files[package + "EXReader-Linux/bin/" + name] == files[evidence + name],
             "gtk-packaged-exact-qualified-binary")
    return dict(capabilities=["gtk-actual-before-sdk-admission", "gtk-last-search-page-custody",
                              "gtk-original-sqlite-content", "gtk-native-authority-byte-decoder",
                              "gtk-packaged-admission"],
                runtime_cases=len(rows), original_sha256=sha(original),
                native_snapshots=snapshots, actual_migration=False)
