#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise complete-statement packaging and rollback using real catalog SQL."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from reader_catalog_assets import SCHEMA, build_asset
from check_reader_catalog_android import TESTS, inspect


def apply(db, statements):
    try:
        for statement in statements:
            db.execute(statement)
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise


def main():
    source = SCHEMA.read_bytes()
    asset = build_asset(source)
    assert "".join(asset["statements"]).encode("utf-8") == source
    assert asset["source_sha256"] == hashlib.sha256(source).hexdigest()
    roundtrip = json.loads(json.dumps(asset, ensure_ascii=False))
    assert roundtrip == asset
    db = sqlite3.connect(":memory:", isolation_level=None)
    apply(db, asset["statements"])
    assert db.execute("PRAGMA application_id").fetchone()[0] == 1163416144
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    triggers = db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
    assert triggers >= 10
    shelf = "1" * 32
    db.execute("INSERT INTO reader_shelves(shelf_id,name) VALUES(?,?)", (shelf, "Root"))
    try:
        db.execute("UPDATE reader_shelves SET parent_id=shelf_id WHERE shelf_id=?", (shelf,))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("complete trigger failed to refuse shelf cycle")
    db.close()

    db = sqlite3.connect(":memory:", isolation_level=None)
    damaged = list(asset["statements"])
    damaged.insert(len(damaged) // 2, "SELECT * FROM missing_migration_table;")
    try:
        apply(db, damaged)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("injected migration fault was accepted")
    assert not db.in_transaction
    assert db.execute("PRAGMA application_id").fetchone()[0] == 0
    assert not db.execute("SELECT name FROM sqlite_master").fetchall()
    apply(db, asset["statements"])
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()

    complex_sql = ("BEGIN;CREATE TABLE t(value TEXT);"
                   "CREATE TRIGGER t_guard BEFORE INSERT ON t BEGIN "
                   "SELECT CASE WHEN NEW.value='a;b' THEN RAISE(ABORT,'x;y') END; END;"
                   "COMMIT; -- retained tail\n")
    packaged = build_asset(complex_sql.encode())
    assert len(packaged["statements"]) == 4
    assert "".join(packaged["statements"]) == complex_sql
    db = sqlite3.connect(":memory:", isolation_level=None)
    apply(db, packaged["statements"])
    try:
        db.execute("INSERT INTO t VALUES('a;b')")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("semicolon in trigger literal was split")
    db.close()
    for invalid in (b"", b"SELECT 1", b"BEGIN;\n/* incomplete", b"SELECT '\x00';",
                    b"\xef\xbb\xbfSELECT 1;", b"\xff"):
        try:
            build_asset(invalid)
        except (ValueError, UnicodeDecodeError):
            pass
        else:
            raise AssertionError("invalid or incomplete migration accepted")

    with tempfile.TemporaryDirectory() as temporary:
        reports = Path(temporary)
        path = reports / "result.xml"
        suite = ET.Element("testsuite", tests=str(len(TESTS)), failures="0", errors="0", skipped="0")
        for name in sorted(TESTS):
            ET.SubElement(suite, "testcase", classname="org.exreader.host.CatalogStoreTest", name=name)
        path.write_bytes(ET.tostring(suite))
        assert len(inspect(reports)["tests"]) == len(TESTS)
        for change in ("missing", "duplicate", "skip", "failure", "suite_error", "wrong_class"):
            altered = ET.fromstring(ET.tostring(suite))
            case = altered.find("testcase")
            if change == "missing":
                altered.remove(case)
            elif change == "duplicate":
                altered.append(ET.fromstring(ET.tostring(case)))
            elif change in ("skip", "failure"):
                ET.SubElement(case, "skipped" if change == "skip" else "failure")
            elif change == "suite_error":
                altered.set("errors", "1")
            else:
                case.set("classname", "other.Test")
            path.write_bytes(ET.tostring(altered))
            try:
                inspect(reports)
            except ValueError:
                pass
            else:
                raise AssertionError("incomplete instrumentation report was accepted: " + change)
    print(json.dumps({"accepted": True, "source_sha256": asset["source_sha256"],
                      "statements": len(asset["statements"]), "triggers": triggers,
                      "checks": 6}))


if __name__ == "__main__":
    main()
