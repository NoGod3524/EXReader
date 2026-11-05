#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute the production catalog migration and its storage contract in CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def reject(db, sql, values=()):
    try:
        db.execute(sql, values)
    except sqlite3.IntegrityError:
        return
    raise AssertionError("invalid write was accepted: " + sql)


def connect(schema):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema)
    require(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys off")
    return db


def ident(number):
    return f"{number:032x}"


def book(db, number=1, fmt="epub", **changes):
    digest = hashlib.sha256(f"original {number}".encode()).hexdigest()
    values = dict(book_key=fmt + ":" + digest, format=fmt, source_sha256=digest,
                  source_bytes=number + 100, title=f"Book {number}", author="",
                  sort_title=f"title-{number // 5:05d}", deleted=0)
    values.update(changes)
    db.execute("INSERT INTO reader_books(" + ",".join(values) + ") VALUES(" +
               ",".join("?" for _ in values) + ")", tuple(values.values()))
    return values["book_key"]


def shelf(db, number, parent=None):
    key = ident(number)
    db.execute("INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES(?,?,?)",
               (key, parent, f"Shelf {number}"))
    return key


def revision(db, number, key, operation="put", parents=()):
    rid = ident(number)
    body = json.dumps(dict(version=1, revision_id=rid, entity_kind="book",
                           entity_key=key, operation=operation, parents=list(parents),
                           payload={} if operation == "delete" else {"title": "Book"}),
                      sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode()).hexdigest()
    db.execute("INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)",
               (rid, "book", key, operation, body, digest))
    return rid


def migration_identity(schema):
    db = connect(schema)
    require(db.execute("PRAGMA application_id").fetchone()[0] == 1163416144, "wrong app ID")
    require(db.execute("PRAGMA user_version").fetchone()[0] == 1, "wrong schema version")
    expected = {"reader_books", "reader_local_books", "reader_shelves", "reader_book_shelves",
                "reader_tags", "reader_book_tags", "reader_series", "reader_book_series",
                "reader_revisions", "reader_outbox"}
    actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    require(actual == expected, "unexpected tables or SDK schema mixed into product catalog")
    try:
        db.executescript(schema)
    except sqlite3.IntegrityError:
        db.rollback()
    else:
        raise AssertionError("migration rerun accepted")
    require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "rerun damaged catalog")
    db.close()
    for setup in ("CREATE TABLE unrelated(value TEXT);INSERT INTO unrelated VALUES('keep');",
                  "CREATE TABLE sqliteXbooks(value TEXT);INSERT INTO sqliteXbooks VALUES('keep prefix-lookalike');",
                  "PRAGMA application_id=1163416131;PRAGMA user_version=7;"
                  "CREATE TABLE books(id INTEGER PRIMARY KEY,source BLOB);INSERT INTO books VALUES(1,x'1234');",
                  "PRAGMA user_version=2;"):
        other = sqlite3.connect(":memory:", isolation_level=None)
        other.executescript(setup)
        before = list(other.iterdump())
        identity = (other.execute("PRAGMA application_id").fetchone(), other.execute("PRAGMA user_version").fetchone())
        try:
            other.executescript(schema)
        except sqlite3.IntegrityError:
            other.rollback()
        else:
            raise AssertionError("migration accepted a nonempty/foreign/versioned database")
        require(list(other.iterdump()) == before, "rejected migration changed existing database")
        require((other.execute("PRAGMA application_id").fetchone(), other.execute("PRAGMA user_version").fetchone()) == identity,
                "rejected migration changed existing application identity/version")
        other.close()


def source_and_local_mapping(schema):
    db = connect(schema)
    epub = book(db)
    pdf = book(db, 2, "pdf")
    db.execute("INSERT INTO reader_local_books VALUES(?,?,?)", (epub, 10, "epub_chapter"))
    reject(db, "INSERT INTO reader_local_books VALUES(?,?,?)", (pdf, 10, "fixed_page"))
    reject(db, "INSERT INTO reader_local_books VALUES(?,?,?)", (pdf, 11, "epub_chapter"))
    db.execute("INSERT INTO reader_local_books VALUES(?,?,?)", (pdf, 11, "fixed_page"))
    reject(db, "UPDATE reader_local_books SET location_kind='reflow_global' WHERE book_key=?", (pdf,))
    reject(db, "UPDATE reader_books SET book_key='epub:other' WHERE book_key=?", (epub,))
    reject(db, "UPDATE reader_books SET source_bytes=200 WHERE book_key=?", (epub,))
    reject(db, "UPDATE reader_books SET source_sha256=upper(source_sha256) WHERE book_key=?", (epub,))
    reject(db, "UPDATE reader_books SET source_bytes=1.5 WHERE book_key=?", (epub,))
    reject(db, "UPDATE reader_books SET favorite=2 WHERE book_key=?", (epub,))
    reject(db, "UPDATE reader_books SET title=? WHERE book_key=?", ("bad\0title", epub))
    reject(db, "INSERT OR REPLACE INTO reader_books SELECT * FROM reader_books WHERE book_key=?", (epub,))
    reject(db, "DELETE FROM reader_books WHERE book_key=?", (epub,))
    digest = hashlib.sha256(b"new original").hexdigest()
    insert = "INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,sort_title) VALUES(?,?,?,?,?,?)"
    for bad in (("zip:" + digest, "zip", digest, 100, "Book", "book"),
                ("epub:" + digest.upper(), "epub", digest.upper(), 100, "Book", "book"),
                ("epub:" + "g" * 64, "epub", "g" * 64, 100, "Book", "book"),
                ("epub:wrong", "epub", digest, 100, "Book", "book"),
                ("epub:" + digest, "epub", digest.encode(), 100, "Book", "book"),
                ("epub:" + digest, "epub", digest, 1.5, "Book", "book")):
        reject(db, insert, bad)
    require(db.execute("SELECT sdk_book_id FROM reader_local_books WHERE book_key=?", (epub,)).fetchone() == (10,),
            "failed mapping writes changed an existing book")
    db.close()


def shelf_tree(schema):
    db = connect(schema)
    chain = []
    for number in range(1, 9):
        chain.append(shelf(db, number, chain[-1] if chain else None))
    reject(db, "INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES(?,?,?)",
           (ident(9), chain[-1], "Too deep"))
    reject(db, "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", (chain[-1], chain[0]))
    reject(db, "UPDATE reader_shelves SET parent_id=shelf_id WHERE shelf_id=?", (chain[0],))
    branch = shelf(db, 20)
    child = shelf(db, 21, branch)
    reject(db, "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", (chain[6], branch))
    reject(db, "UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", (ident(999), child))
    db.execute("UPDATE reader_shelves SET parent_id=? WHERE shelf_id=?", (chain[5], branch))
    require(db.execute("SELECT parent_id FROM reader_shelves WHERE shelf_id=?", (branch,)).fetchone() == (chain[5],),
            "legal subtree move failed")
    reject(db, "UPDATE reader_shelves SET shelf_id=? WHERE shelf_id=?", (ident(22), branch))
    reject(db, "INSERT OR REPLACE INTO reader_shelves SELECT * FROM reader_shelves WHERE shelf_id=?", (branch,))
    require(db.execute("PRAGMA foreign_key_check").fetchall() == [], "tree has broken references")
    db.close()


def organization(schema):
    db = connect(schema)
    key = book(db)
    sid = shelf(db, 1)
    db.execute("INSERT INTO reader_tags(tag_id,name) VALUES(?,?)", (ident(2), "分类"))
    db.execute("INSERT INTO reader_series(series_id,name) VALUES(?,?)", (ident(3), "Series"))
    db.execute("INSERT INTO reader_book_shelves VALUES(?,?,?)", (sid, key, 1))
    db.execute("INSERT INTO reader_book_tags VALUES(?,?)", (key, ident(2)))
    db.execute("INSERT INTO reader_book_series VALUES(?,?,?)", (ident(3), key, 10))
    reject(db, "INSERT INTO reader_book_tags VALUES(?,?)", (key, ident(2)))
    reject(db, "INSERT INTO reader_book_tags VALUES(?,?)", (key, ident(99)))
    reject(db, "UPDATE reader_book_series SET ordinal=-1")
    reject(db, "UPDATE reader_book_series SET ordinal=1.5")
    reject(db, "DELETE FROM reader_tags WHERE tag_id=?", (ident(2),))
    reject(db, "DELETE FROM reader_series WHERE series_id=?", (ident(3),))
    require(db.execute("SELECT ordinal FROM reader_book_series").fetchone() == (10,), "series order changed")
    db.close()


def atomic_failure(schema):
    db = connect(schema)
    db.execute("BEGIN IMMEDIATE")
    key = book(db)
    rid = revision(db, 1, key)
    db.execute("INSERT INTO reader_outbox(revision_id) VALUES(?)", (rid,))
    reject(db, "INSERT INTO reader_local_books VALUES(?,?,?)", (key, -1, "epub_chapter"))
    db.rollback()
    for name in ("reader_books", "reader_local_books", "reader_revisions", "reader_outbox"):
        require(db.execute("SELECT count(*) FROM " + name).fetchone() == (0,), "failed transaction leaked " + name)
    db.close()


def immutable_revisions_and_queue(schema):
    db = connect(schema)
    key = book(db)
    rid = revision(db, 1, key)
    original = db.execute("SELECT * FROM reader_revisions WHERE revision_id=?", (rid,)).fetchone()
    reject(db, "INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)", original)
    changed = list(original)
    changed[4] = "{}"
    changed[5] = hashlib.sha256(b"{}").hexdigest()
    reject(db, "INSERT INTO reader_revisions VALUES(?,?,?,?,?,?)", changed)
    reject(db, "INSERT OR REPLACE INTO reader_revisions VALUES(?,?,?,?,?,?)", changed)
    reject(db, "UPDATE reader_revisions SET body_json='{}' WHERE revision_id=?", (rid,))
    reject(db, "DELETE FROM reader_revisions WHERE revision_id=?", (rid,))
    db.execute("INSERT INTO reader_outbox(revision_id) VALUES(?)", (rid,))
    reject(db, "INSERT INTO reader_outbox(revision_id) VALUES(?)", (rid,))
    reject(db, "INSERT INTO reader_outbox(revision_id) VALUES(?)", (ident(999),))
    reject(db, "UPDATE reader_outbox SET attempts=-1")
    db.execute("UPDATE reader_outbox SET attempts=attempts+1,last_error='retryable transport failure'")
    db.execute("DELETE FROM reader_outbox WHERE revision_id=?", (rid,))
    require(db.execute("SELECT * FROM reader_revisions WHERE revision_id=?", (rid,)).fetchone() == original,
            "acknowledgement or replay changed immutable revision")
    db.close()


def retained_delete_and_conflict(schema):
    db = connect(schema)
    key = book(db)
    initial = revision(db, 1, key)
    deleted = revision(db, 2, key, "delete", (initial,))
    db.execute("UPDATE reader_books SET deleted=1 WHERE book_key=?", (key,))
    delayed = revision(db, 3, key, "put", (initial,))
    rows = [json.loads(row[0]) for row in db.execute("SELECT body_json FROM reader_revisions")]
    parent_ids = {parent for row in rows for parent in row["parents"]}
    heads = {row["revision_id"] for row in rows} - parent_ids
    require(heads == {deleted, delayed}, "concurrent delete/edit history was collapsed")
    require(db.execute("SELECT revision_id FROM reader_tombstones").fetchall() == [(deleted,)], "tombstone lost")
    require(db.execute("SELECT deleted FROM reader_books WHERE book_key=?", (key,)).fetchone() == (1,),
            "recording an old remote edit resurrected the local projection")
    revision(db, 4, key, "restore", sorted(heads))
    require(db.execute("SELECT count(*) FROM reader_tombstones").fetchone() == (1,), "restore erased delete history")
    require(db.execute("SELECT count(*) FROM reader_revisions").fetchone() == (4,), "conflict versions not retained")
    db.close()


def persistent_outbox(schema):
    with tempfile.TemporaryDirectory(prefix="reader-catalog-") as folder:
        path = Path(folder) / "catalog.sqlite"
        db = sqlite3.connect(path, isolation_level=None)
        db.executescript(schema)
        db.execute("BEGIN IMMEDIATE")
        key = book(db)
        rid = revision(db, 1, key, "delete")
        db.execute("INSERT INTO reader_outbox(revision_id) VALUES(?)", (rid,))
        db.commit()
        db.close()
        reopened = sqlite3.connect(path, isolation_level=None)
        reopened.execute("PRAGMA foreign_keys=ON")
        require(reopened.execute("PRAGMA application_id").fetchone() == (1163416144,), "catalog identity not persisted")
        require(reopened.execute("PRAGMA user_version").fetchone() == (1,), "catalog version not persisted")
        require(reopened.execute("SELECT revision_id FROM reader_outbox").fetchall() == [(rid,)], "offline outbox lost on reopen")
        require(reopened.execute("SELECT revision_id FROM reader_tombstones").fetchall() == [(rid,)], "delete record lost on reopen")
        reject(reopened, "INSERT INTO reader_outbox(revision_id) VALUES(?)", (ident(999),))
        reopened.close()


def indexed_pages(schema):
    db = connect(schema)
    sid = shelf(db, 1)
    series = ident(2)
    db.execute("INSERT INTO reader_series(series_id,name) VALUES(?,?)", (series, "Long series"))
    db.execute("BEGIN IMMEDIATE")
    for number in range(3500):
        key = book(db, number, deleted=int(number % 101 == 0))
        db.execute("INSERT INTO reader_book_shelves VALUES(?,?,?)", (sid, key, number // 7))
        db.execute("INSERT INTO reader_book_series VALUES(?,?,?)", (series, key, number // 7))
    db.commit()
    sql = ("SELECT sort_title,book_key FROM reader_books WHERE deleted=0 AND "
           "(sort_title,book_key)>(?,?) ORDER BY sort_title,book_key LIMIT ?")
    plan = " ".join(str(row[-1]) for row in db.execute("EXPLAIN QUERY PLAN " + sql, ("", "", 73)))
    require("reader_books_title" in plan and "TEMP B-TREE" not in plan, "catalog page lacks ordered index: " + plan)
    expected = db.execute("SELECT sort_title,book_key FROM reader_books WHERE deleted=0 ORDER BY sort_title,book_key").fetchall()
    seen, cursor = [], ("", "")
    while True:
        page = db.execute(sql, (*cursor, 73)).fetchall()
        if not page:
            break
        require(len(page) <= 73 and page[0] > cursor, "invalid catalog page boundary")
        seen.extend(page)
        cursor = page[-1]
    require(seen == expected and len(seen) > 3000, "catalog keyset skipped or duplicated books")
    for table, owner, index in (("reader_book_shelves", "shelf_id", "reader_book_shelves_page"),
                                ("reader_book_series", "series_id", "reader_book_series_page")):
        owner_id = sid if owner == "shelf_id" else series
        member_sql = (f"SELECT m.ordinal,m.book_key FROM {table} m JOIN reader_books b ON b.book_key=m.book_key "
                      f"WHERE m.{owner}=? AND b.deleted=0 AND (m.ordinal,m.book_key)>(?,?) "
                      "ORDER BY m.ordinal,m.book_key LIMIT ?")
        plan = " ".join(str(row[-1]) for row in db.execute("EXPLAIN QUERY PLAN " + member_sql, (owner_id, -1, "", 73)))
        require(index in plan and "TEMP B-TREE" not in plan, "membership page lacks ordered index: " + plan)
        expected = db.execute(f"SELECT m.ordinal,m.book_key FROM {table} m JOIN reader_books b ON b.book_key=m.book_key "
                              f"WHERE m.{owner}=? AND b.deleted=0 ORDER BY m.ordinal,m.book_key", (owner_id,)).fetchall()
        seen, cursor = [], (-1, "")
        while True:
            page = db.execute(member_sql, (owner_id, *cursor, 73)).fetchall()
            if not page:
                break
            require(len(page) <= 73 and page[0] > cursor, "invalid membership page boundary")
            seen.extend(page)
            cursor = page[-1]
        require(seen == expected, "membership keyset skipped or duplicated books")
    require(db.execute("PRAGMA foreign_key_check").fetchall() == [], "broken catalog references")
    require(db.execute("PRAGMA integrity_check").fetchone() == ("ok",), "catalog integrity failed")
    metrics = dict(metadata_rows=db.execute("SELECT count(*) FROM reader_books").fetchone()[0],
                   visible_rows=len(seen), page_limit=73, ordered_page_queries=3)
    db.close()
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[2] / "apps/reader/store/001_catalog.sql")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.schema.read_bytes()
    schema = raw.decode("utf-8")
    result = dict(accepted=False, schema_version=1, schema_sha256=hashlib.sha256(raw).hexdigest(),
                  source_sha=os.environ.get("GITHUB_SHA"), run_id=os.environ.get("GITHUB_RUN_ID"),
                  run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"), product_complete=False,
                  sqlite_version=sqlite3.sqlite_version, planned_metadata_rows=3500, expected_cases=9,
                  cases=[], problems=[])
    for check in (migration_identity, source_and_local_mapping, shelf_tree, organization,
                  atomic_failure, immutable_revisions_and_queue, retained_delete_and_conflict,
                  persistent_outbox, indexed_pages):
        try:
            metrics = check(schema)
            result["cases"].append(dict(name=check.__name__, passed=True, metrics=metrics))
        except Exception as error:
            result["cases"].append(dict(name=check.__name__, passed=False))
            result["problems"].append(f"{check.__name__}: {type(error).__name__}: {error}")
    result["passed_cases"] = sum(case["passed"] for case in result["cases"])
    result["failed_cases"] = len(result["cases"]) - result["passed_cases"]
    result["accepted"] = not result["problems"] and len(result["cases"]) == result["expected_cases"]
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
