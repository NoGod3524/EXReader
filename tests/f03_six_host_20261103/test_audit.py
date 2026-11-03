"""Verifier unit checks only. These fixtures never grant native-host acceptance."""
import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from audit import golden
from run import ROOT, setup


class EvidenceChecks(unittest.TestCase):
    def fixture(self):
        book = "txt:" + "f" * 64
        return book, {
            "reader_shelves": [
                {"shelf_id": "a" * 32, "parent_id": None, "name": "F03 Root", "ordinal": 1, "deleted": 0},
                {"shelf_id": "b" * 32, "parent_id": "a" * 32, "name": "F03 Child", "ordinal": 2, "deleted": 0}],
            "reader_tags": [{"tag_id": "c" * 32, "name": "F03 Tag", "deleted": 0}],
            "reader_series": [{"series_id": "d" * 32, "name": "F03 Series", "deleted": 0}],
            "reader_book_shelves": [{"shelf_id": "b" * 32, "book_key": book, "ordinal": 3}],
            "reader_book_tags": [{"tag_id": "c" * 32, "book_key": book}],
            "reader_book_series": [{"series_id": "d" * 32, "book_key": book, "ordinal": 7}],
        }

    def test_converged_hosts_still_must_match_fixed_expectations(self):
        book, original = self.fixture()
        golden(original, "create", book)
        mutations = [
            ("missing or extra organization", lambda s: s["reader_tags"].clear()),
            ("nested shelf order differs", lambda s: s["reader_shelves"][1].update(parent_id=None)),
            ("membership order differs", lambda s: s["reader_book_series"][0].update(ordinal=8)),
            ("group tombstone differs", lambda s: s["reader_tags"][0].update(deleted=1)),
        ]
        for reason, change in mutations:
            with self.subTest(reason=reason):
                changed = copy.deepcopy(original)
                change(changed)
                with self.assertRaisesRegex(AssertionError, reason):
                    golden(changed, "create", book)
        with self.assertRaisesRegex(AssertionError, "membership count differs"):
            golden(original, "member-remove", book)

    def test_retained_database_includes_uncheckpointed_wal(self):
        identity = setup()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "product.sqlite"
            with closing(sqlite3.connect(database)) as source:
                source.execute("PRAGMA journal_mode=WAL")
                source.execute("PRAGMA wal_autocheckpoint=0")
                source.executescript((ROOT / "apps/reader/store/001_catalog.sql").read_text())
                source.execute("INSERT INTO reader_shelves(shelf_id,parent_id,name,ordinal,deleted) VALUES(?,NULL,?,1,0)",
                               ("a" * 32, "uncheckpointed shelf"))
                source.commit()
                self.assertGreater(Path(str(database) + "-wal").stat().st_size, 32)
                expected = identity.read_snapshot(database)
                retained = identity.retain_database(database, root / "retained", expected)
                self.assertEqual(identity.read_snapshot(retained), expected)
                self.assertEqual(expected["reader_shelves"][0]["name"], "uncheckpointed shelf")
                with self.assertRaises(FileExistsError):
                    identity.retain_database(database, root / "retained", expected)


if __name__ == "__main__":
    unittest.main()
