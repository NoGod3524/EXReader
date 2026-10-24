#!/usr/bin/env python3
"""Judge EXReaderLocalDownloads through the installed C probe (cloud only).

Every probe command is a fresh process, so each step reopens the SDK library and
the product catalog. Crash cases terminate the probe process from inside the
durable-stage hook (_exit), then reopen and recover in new processes.
The product database is read independently through Python's sqlite3 and the
SDK only through the probe's public-API commands.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

EXPECTED_CHECKS = [
    "cloud_only_noop", "remove_txt", "remove_epub", "remove_cbz",
    "repeat_request_idempotent", "reimport_same_identity", "reimport_wrong_file_rejected",
    "duplicate_sdk_ids_removed_exactly", "duplicate_with_legacy_rejected",
    "legacy_notes_rejected_then_backup", "legacy_progress_rejected",
    "busy_rejects_without_change", "held_source_readable_then_released",
    "kill_begun", "kill_prepared", "kill_unmapped", "kill_deleted", "kill_cleaned",
    "kill_unmapped_cbz", "kill_deleted_epub", "late_legacy_restores_mapping",
    "pending_blocks_other_removal", "pending_blocks_reimport",
    "disk_failure_leaves_book_readable", "mapping_failure_leaves_book_readable",
    "cancel_at_begun", "cancel_at_prepared", "corrupt_intent_refused",
    "identity_mismatch_refused", "missing_sdk_row_refused", "cpp_consumer",
    "reimport_path_swap_keeps_identity", "reimport_verifies_imported_row",
    "intent_trailing_bytes_refused", "intent_trailing_nul_refused",
    "intent_oversized_refused", "intent_truncated_refused",
    "intent_bad_number_refused", "intent_stage_suffix_refused",
    "intent_duplicate_field_refused", "intent_unknown_field_refused",
    "intent_empty_id_refused", "intent_nine_ids_refused",
    "state_dir_link_refused", "originals_link_refused", "intent_tmp_hardlink_kept",
    "reimport_publish_blocked", "reimport_over_ceiling", "reimport_longer_file",
    "reenter_remove_from_stage", "reenter_recover_from_busy", "reenter_pending_readonly",
    "pdf_private_original", "formats_all_remove_reimport",
]

FORMAT_FIXTURES = {
    "epub": "cover-import.epub", "cbz": "comic.cbz", "pdf": "pdf-public.pdf",
    "html": "sample.html", "fb2": "sample.fb2", "docx": "sample.docx",
    "rtf": "sample.rtf", "mobi": "sample.mobi",
}
ALL_FORMATS = ("txt", "html", "fb2", "epub", "docx", "rtf", "mobi", "pdf", "cbz")

PRODUCT_TABLES = ["reader_books", "reader_shelves", "reader_book_shelves", "reader_tags",
                  "reader_book_tags", "reader_series", "reader_book_series",
                  "reader_revisions", "reader_outbox"]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def same(actual, expected, message):
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r" % (message, expected, actual))


class Out:
    def __init__(self, completed):
        self.rc = completed.returncode
        self.stdout = completed.stdout.decode("utf-8", "replace")
        self.stderr = completed.stderr.decode("utf-8", "replace")
        self.lines = self.stdout.splitlines()

    def line(self, prefix):
        for text in self.lines:
            if text.startswith(prefix):
                return self.parse(text[len(prefix):])
        raise AssertionError("missing %r in output: %s %s" % (prefix, self.stdout, self.stderr))

    @staticmethod
    def parse(text):
        head, _, message = text.partition(" msg=")
        fields = {}
        for token in head.split():
            name, _, value = token.partition("=")
            fields[name] = value
        fields["msg"] = message
        return fields

    @property
    def result(self):
        return self.line("RESULT ")

    @property
    def after_release(self):
        return self.line("AFTER_RELEASE RESULT ")


class Book:
    def __init__(self, key, ids, path, sha, size, kind):
        self.key, self.ids, self.path, self.sha, self.size, self.kind = key, ids, path, sha, size, kind

    @property
    def mapped(self):
        return self.ids[0]


class Env:
    def __init__(self, ctx, name):
        self.ctx = ctx
        self.work = os.path.join(ctx.root, name).replace("\\", "/")
        for sub in ("", "state", "files", "remote"):
            os.makedirs(os.path.join(self.work, sub), exist_ok=True)
        self.counter = 0
        for index in range(3):
            path = os.path.join(self.work, "remote", "object%d.bin" % index)
            with open(path, "wb") as f:
                f.write(("remote object %d for %s\n" % (index, name)).encode() * 50)
        self.run("init")

    @property
    def catalog_path(self):
        return os.path.join(self.work, "catalog.db")

    @property
    def state(self):
        return os.path.join(self.work, "state")

    def run(self, command, *args, expect=0, timeout=240):
        argv = [self.ctx.probe, command, "--work", self.work] + [str(a) for a in args]
        completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=timeout, env=self.ctx.env)
        out = Out(completed)
        if expect is not None and out.rc != expect:
            raise AssertionError("%s exited %d, expected %s\n%s\n%s" % (
                command, out.rc, expect, out.stdout, out.stderr))
        return out

    def add(self, kind, title, copies=1, content=None, attach=True, fixture=None):
        self.counter += 1
        if kind == "txt":
            body = content if content is not None else (
                "Book %s serial %d. " % (title, self.counter) * 300 + "The end.\n").encode()
            path = os.path.join(self.work, "files", "book%d.txt" % self.counter)
            with open(path, "wb") as f:
                f.write(body)
        else:
            source = self.ctx.fixture(fixture or FORMAT_FIXTURES[kind])
            path = os.path.join(self.work, "files", "book%d.%s" % (self.counter, kind))
            shutil.copyfile(source, path)
        sha = sha256_file(path)
        size = os.path.getsize(path)
        args = ["--file", path, "--fmt", kind.upper(), "--title", title, "--sha", sha, "--copies", copies]
        if not attach:
            args.append("--no-attach")
        out = self.run("add", *args)
        fields = out.line("ADD ")
        ids = [int(v) for v in fields["ids"].split(",")]
        return Book("%s:%s" % (kind, sha), ids, path, sha, size, kind)

    def add_cloud(self, title):
        sha = sha256_bytes(title.encode())
        key = "epub:" + sha
        con = sqlite3.connect(self.catalog_path, timeout=30)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title)"
                        " VALUES(?,?,?,?,?,?,?)", (key, "epub", sha, 12345, title, "", title.lower()))
            con.commit()
        finally:
            con.close()
        return key

    def seed_product(self, books):
        """Revision history, an outbox and organization rows that must survive."""
        con = sqlite3.connect(self.catalog_path, timeout=30)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            shelf = hashlib.md5(self.work.encode()).hexdigest()
            con.execute("INSERT INTO reader_shelves(shelf_id,parent_id,name,ordinal) VALUES(?,NULL,?,1)", (shelf, "Shelf"))
            tag = hashlib.md5((self.work + "tag").encode()).hexdigest()
            con.execute("INSERT INTO reader_tags(tag_id,name) VALUES(?,?)", (tag, "Tag"))
            series = hashlib.md5((self.work + "series").encode()).hexdigest()
            con.execute("INSERT INTO reader_series(series_id,name) VALUES(?,?)", (series, "Series"))
            number = 0
            for book in books:
                con.execute("INSERT INTO reader_book_shelves(shelf_id,book_key,ordinal) VALUES(?,?,?)", (shelf, book.key, number))
                con.execute("INSERT INTO reader_book_tags(book_key,tag_id) VALUES(?,?)", (book.key, tag))
                con.execute("INSERT INTO reader_book_series(series_id,book_key,ordinal) VALUES(?,?,?)", (series, book.key, number))
                for kind in ("book", "progress", "annotation"):
                    number += 1
                    rid = hashlib.md5(("%s/%s/%d" % (self.work, book.key, number)).encode()).hexdigest()
                    body = json.dumps({"entity": book.key, "n": number, "kind": kind})
                    con.execute("INSERT INTO reader_revisions(revision_id,entity_kind,entity_key,operation,body_json,body_sha256)"
                                " VALUES(?,?,?,?,?,?)", (rid, kind, book.key, "put", body, sha256_bytes(body.encode())))
                    if kind != "book":
                        con.execute("INSERT INTO reader_outbox(revision_id,attempts,last_error) VALUES(?,?,?)", (rid, number, ""))
            rid = hashlib.md5((self.work + "tombstone").encode()).hexdigest()
            body = json.dumps({"deleted": True})
            con.execute("INSERT INTO reader_revisions(revision_id,entity_kind,entity_key,operation,body_json,body_sha256)"
                        " VALUES(?,?,?,?,?,?)", (rid, "shelf", "removed-shelf", "delete", body, sha256_bytes(body.encode())))
            con.commit()
        finally:
            con.close()

    def snap(self):
        uri = pathlib.Path(self.catalog_path).resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            tables = {}
            for table in PRODUCT_TABLES:
                tables[table] = [list(r) for r in con.execute("SELECT * FROM %s ORDER BY rowid" % table)]
            locals_ = dict((k, i) for k, i in con.execute("SELECT book_key,sdk_book_id FROM reader_local_books"))
            tombstones = con.execute("SELECT count(*) FROM reader_tombstones").fetchone()[0]
        finally:
            con.close()
        remote = []
        base = os.path.join(self.work, "remote")
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            remote.append([name, os.path.getsize(path), sha256_file(path), os.stat(path).st_mtime_ns])
        return {
            "product": sha256_bytes(json.dumps(tables, sort_keys=True).encode()),
            "revisions": len(tables["reader_revisions"]), "outbox": len(tables["reader_outbox"]),
            "tombstones": tombstones, "locals": locals_, "remote": remote,
        }

    def books(self):
        out = self.run("list")
        rows = {}
        for text in out.lines:
            if text.startswith("BOOK "):
                fields = Out.parse(text[5:])
                rows[int(fields["id"])] = fields
        return rows

    def dump_sha(self, book_id):
        path = os.path.join(self.work, "dump%d.bin" % book_id)
        out = self.run("dump", "--id", book_id, "--out", path)
        fields = out.line("DUMP ")
        if fields["status"] != "ok":
            return None
        return sha256_file(path)

    def catalog(self, key):
        fields = self.run("catalog", "--key", key).line("CATALOG ")
        return int(fields["found"]), int(fields["local"]), int(fields["mapped"]), int(fields["deleted"])

    def pending(self):
        return self.run("pending").line("PENDING ")

    def assert_state_clean(self):
        need(not os.path.exists(os.path.join(self.state, "intent.rdi")), "intent file remains")
        need(not os.path.exists(os.path.join(self.state, "intent.tmp")), "intent temp remains")
        originals = os.path.join(self.state, "originals")
        if os.path.isdir(originals):
            same(os.listdir(originals), [], "retained original exports")

    def assert_unchanged_but(self, before, removed_keys=()):
        after = self.snap()
        same(after["product"], before["product"], "product metadata/history/outbox/organization")
        same(after["revisions"], before["revisions"], "revision count")
        same(after["outbox"], before["outbox"], "outbox count")
        same(after["tombstones"], before["tombstones"], "tombstones (no deletion tombstone may appear)")
        same(after["remote"], before["remote"], "remote objects")
        expected = dict((k, v) for k, v in before["locals"].items() if k not in removed_keys)
        same(after["locals"], expected, "local mappings")
        return after


class Ctx:
    def __init__(self, probe, cpp, fixtures, root, extra_path):
        self.probe, self.cpp, self.fixtures, self.root = probe, cpp, fixtures, root
        self.env = dict(os.environ)
        if extra_path:
            self.env["PATH"] = os.pathsep.join(extra_path + [self.env.get("PATH", "")])

    def fixture(self, name):
        return os.path.join(self.fixtures, name)

    def new(self, name):
        return Env(self, name)


# ----------------------------------------------------------------- scenarios

def removed_ok(out, book, copies=1):
    r = out.result
    same(r["status"], "ok", "remove status: " + r["msg"])
    same(r["outcome"], "removed", "outcome")
    same(int(r["removed"]), copies, "removed rows")
    same(int(r["id"]), book.mapped, "mapped id")


def s_cloud_only(ctx):
    env = ctx.new("cloud_only")
    key = env.add_cloud("Cloud Only")
    neighbour = env.add("txt", "Local Neighbour")
    env.seed_product([neighbour])
    before = env.snap()
    r = env.run("remove", "--key", key).result
    same((r["status"], r["outcome"]), ("ok", "already_cloud"), "cloud-only remove")
    env.assert_unchanged_but(before)
    env.assert_state_clean()
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour original")


def remove_case(ctx, kind, name):
    env = ctx.new(name)
    book = env.add(kind, "Removable " + kind)
    neighbour = env.add("txt", "Neighbour " + kind)
    env.seed_product([book, neighbour])
    before = env.snap()
    sdk_before = env.books()
    need(book.mapped in sdk_before, "seed row missing")
    out = env.run("remove", "--key", book.key)
    removed_ok(out, book)
    after = env.assert_unchanged_but(before, {book.key})
    found, local, mapped, deleted = env.catalog(book.key)
    same((found, local, mapped, deleted), (1, 0, 0, 0), "global book kept, local mapping gone")
    sdk_after = env.books()
    need(book.mapped not in sdk_after, "SDK original still present")
    same(len(sdk_after), len(sdk_before) - 1, "SDK row count")
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour original")
    env.assert_state_clean()
    return env, book, after


def s_remove_txt(ctx):
    remove_case(ctx, "txt", "remove_txt")


def s_remove_epub(ctx):
    remove_case(ctx, "epub", "remove_epub")


def s_remove_cbz(ctx):
    remove_case(ctx, "cbz", "remove_cbz")


def s_repeat(ctx):
    env, book, after = remove_case(ctx, "txt", "repeat")
    r = env.run("remove", "--key", book.key).result
    same((r["status"], r["outcome"]), ("ok", "already_cloud"), "repeated remove")
    r = env.run("remove", "--key", book.key).result
    same((r["status"], r["outcome"]), ("ok", "already_cloud"), "third remove")
    again = env.snap()
    same(again["product"], after["product"], "product unchanged by repeats")
    same(again["locals"], after["locals"], "mappings unchanged by repeats")
    env.assert_state_clean()


def s_reimport(ctx):
    env, book, after = remove_case(ctx, "txt", "reimport")
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same((r["status"], r["outcome"]), ("ok", "attached"), "reimport: " + r["msg"])
    new_id = int(r["id"])
    found, local, mapped, deleted = env.catalog(book.key)
    same((found, local, mapped), (1, new_id, 1), "mapping restored for the same key")
    same(env.dump_sha(new_id), book.sha, "re-imported original bytes")
    re_snap = env.snap()
    same(re_snap["product"], after["product"], "product metadata unchanged by reimport")
    same(re_snap["remote"], after["remote"], "remote unchanged by reimport")
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same((r["status"], r["outcome"]), ("ok", "already_local"), "second reimport")
    # And it can be removed again with the very same identity.
    removed = env.run("remove", "--key", book.key).result
    same((removed["status"], removed["outcome"], removed["removed"]), ("ok", "removed", "1"), "second removal")
    env.assert_state_clean()


def s_reimport_wrong(ctx):
    env, book, after = remove_case(ctx, "txt", "reimport_wrong")
    wrong = os.path.join(env.work, "files", "wrong.txt")
    with open(book.path, "rb") as f:
        data = f.read()
    with open(wrong, "wb") as f:
        f.write(data[:-1] + b"X")  # same size, different SHA-256
    r = env.run("reimport", "--key", book.key, "--file", wrong).result
    same(r["status"], "identity", "same-size wrong file")
    shorter = os.path.join(env.work, "files", "shorter.txt")
    with open(shorter, "wb") as f:
        f.write(data[:-5])
    r = env.run("reimport", "--key", book.key, "--file", shorter).result
    same(r["status"], "identity", "different-size wrong file")
    other = "txt:" + "0" * 64
    r = env.run("reimport", "--key", other, "--file", book.path).result
    same(r["status"], "not_found", "unknown key")
    same(env.catalog(book.key), (1, 0, 0, 0), "still cloud-only")
    same(len(env.books()), 1, "no stray SDK row after refused reimports")
    same(env.snap()["product"], after["product"], "product unchanged")


def s_duplicates(ctx):
    env = ctx.new("duplicates")
    dup = env.add("txt", "Same Title", copies=3)
    same(len(dup.ids), 3, "three identical SDK ids")
    lookalike = env.add("txt", "Same Title")
    third = env.add("txt", "Unrelated")
    env.seed_product([dup, lookalike, third])
    before = env.snap()
    same(before["locals"][dup.key], dup.mapped, "lowest id is mapped")
    removed_ok(env.run("remove", "--key", dup.key), dup, copies=3)
    env.assert_unchanged_but(before, {dup.key})
    books = env.books()
    same(sorted(books), sorted(lookalike.ids + third.ids), "only the verified identical copies were removed")
    same(env.dump_sha(lookalike.mapped), lookalike.sha, "same-title other book")
    same(env.dump_sha(third.mapped), third.sha, "unrelated book")
    env.assert_state_clean()


def s_duplicate_legacy(ctx):
    env = ctx.new("duplicate_legacy")
    dup = env.add("txt", "Dup Legacy", copies=3)
    neighbour = env.add("txt", "Neighbour")
    env.seed_product([dup, neighbour])
    env.run("legacy", "--id", dup.ids[2], "--notes", 1)
    before = env.snap()
    r = env.run("remove", "--key", dup.key).result
    same(r["status"], "legacy_data", "older duplicate with SDK-only note")
    same(r["notes"], "1", "reported notes")
    env.assert_unchanged_but(before)
    books = env.books()
    for i in dup.ids:
        need(i in books, "duplicate %d was lost" % i)
        same(env.dump_sha(i), dup.sha, "duplicate %d readable" % i)
    same(books[dup.ids[2]]["notes"], "1", "note retained")
    same(env.catalog(dup.key)[1], dup.mapped, "mapping retained")
    env.assert_state_clean()
    out = env.run("remove", "--key", dup.key, "--policy", "backup")
    removed_ok(out, dup, copies=3)
    backup = out.result["backup"]
    need(backup and os.path.isfile(backup), "backup file missing")
    shown = env.run("backup-open", "--path", backup)
    notes = [Out.parse(t[7:]) for t in shown.lines if t.startswith("BACKUP ")]
    need(any(n["notes"] == "1" for n in notes), "backup does not retain the note")


def s_legacy_notes(ctx):
    env = ctx.new("legacy_notes")
    book = env.add("txt", "Annotated")
    neighbour = env.add("txt", "Neighbour")
    env.seed_product([book, neighbour])
    env.run("legacy", "--id", book.mapped, "--notes", 2)
    before = env.snap()
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "legacy_data", "SDK-only notes")
    same(r["notes"], "2", "reported notes")
    env.assert_unchanged_but(before)
    same(env.books()[book.mapped]["notes"], "2", "notes retained after refusal")
    same(env.dump_sha(book.mapped), book.sha, "original readable after refusal")
    env.assert_state_clean()
    out = env.run("remove", "--key", book.key, "--policy", "backup")
    removed_ok(out, book)
    backup = out.result["backup"]
    need(backup and os.path.isfile(backup), "backup file missing")
    rows = [Out.parse(t[7:]) for t in env.run("backup-open", "--path", backup).lines if t.startswith("BACKUP ")]
    need(any(r_["notes"] == "2" for r_ in rows), "backup lost the notes")
    need(book.mapped not in env.books(), "original not removed after backup")
    env.assert_unchanged_but(before, {book.key})
    env.assert_state_clean()


def s_legacy_progress(ctx):
    env = ctx.new("legacy_progress")
    book = env.add("txt", "Half Read")
    env.seed_product([book])
    env.run("legacy", "--id", book.mapped, "--position", 40)
    before = env.snap()
    r = env.run("remove", "--key", book.key).result
    same((r["status"], r["progress"]), ("legacy_data", "1"), "SDK-only progress")
    env.assert_unchanged_but(before)
    same(env.books()[book.mapped]["position"], "40", "progress retained")
    out = env.run("remove", "--key", book.key, "--policy", "backup")
    removed_ok(out, book)
    rows = [Out.parse(t[7:]) for t in env.run("backup-open", "--path", out.result["backup"]).lines if t.startswith("BACKUP ")]
    need(any(r_["position"] == "40" for r_ in rows), "backup lost the progress")


def s_busy(ctx):
    env = ctx.new("busy")
    book = env.add("txt", "In Use")
    neighbour = env.add("txt", "Neighbour")
    env.seed_product([book, neighbour])
    before = env.snap()
    r = env.run("remove", "--key", book.key, "--busy-all").result
    same(r["status"], "busy", "caller reports use")
    env.assert_unchanged_but(before)
    same(env.dump_sha(book.mapped), book.sha, "original readable after BUSY")
    env.assert_state_clean()
    removed_ok(env.run("remove", "--key", book.key), book)


def s_held(ctx):
    env = ctx.new("held")
    book = env.add("epub", "Held Open")
    env.seed_product([book])
    before = env.snap()
    out = env.run("remove", "--key", book.key, "--hold", book.mapped)
    same(out.result["status"], "busy", "open source blocks removal")
    held = out.line("HELD ")
    same(held["readable"], "1", "source opened before the refused call stays readable")
    after = out.after_release
    same((after["status"], after["outcome"]), ("ok", "removed"), "removal after releasing the source")
    env.assert_unchanged_but(before, {book.key})
    need(book.mapped not in env.books(), "original not removed")
    env.assert_state_clean()


EXPECT_PENDING = {"begun": "begun", "prepared": "prepared", "unmapped": "unmapped",
                  "deleted": "deleted", "cleaned": "deleted"}


def kill_case(ctx, stage, kind, name):
    env = ctx.new(name)
    book = env.add(kind, "Crash " + stage)
    neighbour = env.add("txt", "Neighbour")
    env.seed_product([book, neighbour])
    before = env.snap()
    out = env.run("remove", "--key", book.key, "--kill-at", stage, expect=43)
    need(("KILL " + stage) in out.lines, "probe did not reach stage " + stage)
    need(not any(t.startswith("RESULT") for t in out.lines), "process continued past the kill point")
    # Reopen: nothing has been closed or cleaned up by the killed process.
    p = env.pending()
    same((p["status"], p["pending"], p["stage"]), ("ok", "1", EXPECT_PENDING[stage]), "durable intent stage")
    same(p["key"], book.key, "intent key")
    after_unmap = stage in ("unmapped", "deleted", "cleaned")
    after_delete = stage in ("deleted", "cleaned")
    found, local, mapped, deleted = env.catalog(book.key)
    same(mapped, 0 if after_unmap else 1, "mapping state after kill")
    books = env.books()
    same(book.mapped in books, not after_delete, "SDK row state after kill")
    if not after_delete:
        same(env.dump_sha(book.mapped), book.sha, "original readable after kill")
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour readable after kill")
    blocked = env.run("remove", "--key", book.key).result
    same(blocked["status"], "pending", "a new request must not run beside an unfinished intent")
    rec = env.run("recover").result
    same(rec["status"], "ok", "recover: " + rec["msg"])
    if stage in ("begun", "prepared"):
        same(rec["outcome"], "rolled_back", "pre-mapping stages roll back")
    else:
        same(rec["outcome"], "removed", "post-mapping stages roll forward")
    again = env.run("recover").result
    same(again["outcome"], "nothing_pending", "recovery is idempotent")
    env.assert_state_clean()
    if stage in ("begun", "prepared"):
        env.assert_unchanged_but(before)
        same(env.dump_sha(book.mapped), book.sha, "original intact after rollback")
        removed_ok(env.run("remove", "--key", book.key), book)
        env.assert_unchanged_but(before, {book.key})
    else:
        env.assert_unchanged_but(before, {book.key})
        need(book.mapped not in env.books(), "original not removed by recovery")
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour intact")
    same(env.catalog(book.key)[:2], (1, 0), "global book kept without local copy")
    return env, book


def make_kill(stage, kind="txt"):
    def run(ctx):
        kill_case(ctx, stage, kind, "kill_%s_%s" % (stage, kind))
    return run


def s_late_legacy(ctx):
    env = ctx.new("late_legacy")
    book = env.add("txt", "Late Notes")
    env.seed_product([book])
    before = env.snap()
    env.run("remove", "--key", book.key, "--kill-at", "unmapped", expect=43)
    env.run("legacy", "--id", book.mapped, "--notes", 1)  # the user writes between crash and recovery
    r = env.run("recover").result
    same(r["status"], "legacy_data", "late legacy data is not deleted")
    same(r["outcome"], "restored", "mapping restored")
    env.assert_unchanged_but(before)
    same(env.books()[book.mapped]["notes"], "1", "note retained")
    same(env.dump_sha(book.mapped), book.sha, "original retained")
    env.assert_state_clean()
    removed_ok(env.run("remove", "--key", book.key, "--policy", "backup"), book)


def s_pending_other(ctx):
    env = ctx.new("pending_other")
    a = env.add("txt", "Book A")
    b = env.add("txt", "Book B")
    env.seed_product([a, b])
    before = env.snap()
    env.run("remove", "--key", a.key, "--kill-at", "prepared", expect=43)
    r = env.run("remove", "--key", b.key).result
    same(r["status"], "pending", "other book while an intent exists")
    env.assert_unchanged_but(before)
    same(env.dump_sha(b.mapped), b.sha, "other book untouched")
    same(env.run("recover").result["outcome"], "rolled_back", "recover")
    removed_ok(env.run("remove", "--key", b.key), b)
    same(env.catalog(a.key)[2], 1, "book A remains mapped")


def s_pending_reimport(ctx):
    env = ctx.new("pending_reimport")
    a = env.add("txt", "Book A")
    b = env.add("txt", "Book B")
    env.seed_product([a, b])
    removed_ok(env.run("remove", "--key", b.key), b)
    env.run("remove", "--key", a.key, "--kill-at", "unmapped", expect=43)
    rows = len(env.books())
    r = env.run("reimport", "--key", b.key, "--file", b.path).result
    same(r["status"], "pending", "reimport beside an unfinished intent")
    same(env.catalog(b.key)[1], 0, "nothing attached")
    same(len(env.books()), rows, "no stray SDK import")
    same(env.run("recover").result["outcome"], "removed", "recover")
    r = env.run("reimport", "--key", b.key, "--file", b.path).result
    same(r["outcome"], "attached", "reimport after recovery")


def s_disk_failure(ctx):
    env = ctx.new("disk_failure")
    book = env.add("txt", "Disk Full")
    env.seed_product([book])
    before = env.snap()
    blocker = os.path.join(env.state, "originals")
    with open(blocker, "wb") as f:
        f.write(b"not a directory")
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "io", "private export directory unavailable")
    env.assert_unchanged_but(before)
    same(env.dump_sha(book.mapped), book.sha, "original readable after disk failure")
    need(not os.path.exists(os.path.join(env.state, "intent.rdi")), "intent left behind")
    os.remove(blocker)
    removed_ok(env.run("remove", "--key", book.key), book)


def s_mapping_failure(ctx):
    env = ctx.new("mapping_failure")
    book = env.add("txt", "Mapping Locked")
    env.seed_product([book])
    before = env.snap()
    con = sqlite3.connect(env.catalog_path, timeout=0, isolation_level=None)
    try:
        con.execute("BEGIN IMMEDIATE")  # readers pass, the mapping write cannot
        r = env.run("remove", "--key", book.key).result
    finally:
        con.execute("ROLLBACK")
        con.close()
    same(r["status"], "catalog", "mapping removal failed: " + r["msg"])
    env.assert_unchanged_but(before)
    same(env.dump_sha(book.mapped), book.sha, "original readable after mapping failure")
    env.assert_state_clean()
    removed_ok(env.run("remove", "--key", book.key), book)


def make_cancel(stage):
    def run(ctx):
        env = ctx.new("cancel_" + stage)
        book = env.add("txt", "Cancel " + stage)
        env.seed_product([book])
        before = env.snap()
        r = env.run("remove", "--key", book.key, "--cancel-at", stage).result
        same(r["status"], "cancelled", "cancellation at " + stage)
        env.assert_unchanged_but(before)
        same(env.dump_sha(book.mapped), book.sha, "original readable after cancellation")
        env.assert_state_clean()
        removed_ok(env.run("remove", "--key", book.key), book)
    return run


def s_corrupt(ctx):
    env = ctx.new("corrupt")
    book = env.add("txt", "Corrupt Intent")
    env.seed_product([book])
    before = env.snap()
    intent = os.path.join(env.state, "intent.rdi")
    with open(intent, "wb") as f:
        f.write(b"garbage\n")
    for command in (("remove", "--key", book.key), ("recover",)):
        same(env.run(*command).result["status"], "corrupt_intent", "garbage intent for " + command[0])
    same(env.pending()["status"], "corrupt_intent", "pending inspection")
    os.remove(intent)
    env.run("remove", "--key", book.key, "--kill-at", "prepared", expect=43)
    with open(intent, "rb") as f:
        good = f.read()
    for broken in (good[:-1], good.replace(b"stage=2", b"stage=3"), good.replace(b"mapped=", b"mapped=9")):
        with open(intent, "wb") as f:
            f.write(broken)
        same(env.run("recover").result["status"], "corrupt_intent", "damaged intent")
        need(book.mapped in env.books(), "damaged intent caused a deletion")
    with open(intent, "wb") as f:
        f.write(good)
    same(env.run("recover").result["outcome"], "rolled_back", "undamaged intent")
    env.assert_unchanged_but(before)
    same(env.dump_sha(book.mapped), book.sha, "original readable")


def s_identity(ctx):
    env = ctx.new("identity")
    book = env.add("txt", "Mapped Wrongly")
    other = env.add("txt", "Different Book", attach=False)
    env.seed_product([book])
    con = sqlite3.connect(env.catalog_path, timeout=30)
    con.execute("UPDATE reader_local_books SET sdk_book_id=? WHERE book_key=?", (other.mapped, book.key))
    con.commit()
    con.close()
    before = env.snap()
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "identity", "mapping points at another book")
    after = env.assert_unchanged_but(before)
    same(after["locals"][book.key], other.mapped, "mapping kept")
    books = env.books()
    for i in book.ids + other.ids:
        need(i in books, "row %d deleted" % i)
    same(env.dump_sha(other.mapped), other.sha, "other book intact")
    env.assert_state_clean()


def s_missing_row(ctx):
    env = ctx.new("missing_row")
    book = env.add("txt", "Dangling")
    env.seed_product([book])
    con = sqlite3.connect(env.catalog_path, timeout=30)
    con.execute("UPDATE reader_local_books SET sdk_book_id=99 WHERE book_key=?", (book.key,))
    con.commit()
    con.close()
    before = env.snap()
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "identity", "dangling mapping")
    env.assert_unchanged_but(before)
    need(book.mapped in env.books(), "unrelated row deleted")
    env.assert_state_clean()


def s_cpp(ctx):
    completed = subprocess.run([ctx.cpp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ctx.env, timeout=60)
    same(completed.returncode, 0, "C++ consumer: " + completed.stdout.decode() + completed.stderr.decode())
    need(b"CPP ok version=0.1.0" in completed.stdout, "C++ consumer output")


# ------------------------------------------------- root review regressions

class SkipCheck(Exception):
    """A named, visible skip; never a silent pass."""


def make_dir_link(target, link):
    """Directory link (symlink, or a Windows junction) or None with a reason."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return None
    except (OSError, AttributeError, NotImplementedError) as exc:
        reason = str(exc)
    if os.name == "nt":
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            return None
        reason += " / junction: " + completed.stderr.decode("utf-8", "replace").strip()
    return reason


def intent_record(book, lines=None, extra=b"", checksum=True, stage=1):
    if lines is None:
        lines = [b"stage=%d" % stage, b"key=" + book.key.encode("ascii"),
                 b"bytes=%d" % book.size, b"mapped=%d" % book.mapped,
                 b"ids=%d" % book.mapped]
    body = b"EXRLD1\n" + b"".join(line + b"\n" for line in lines)
    tail = b"check=" + hashlib.sha256(body).hexdigest().encode("ascii") + b"\n" if checksum else b""
    return body + tail + extra


def damaged_intent(ctx, name, build):
    """A damaged record is refused and neither database nor the file changes."""
    env = ctx.new(name)
    book = env.add("txt", "Damaged " + name)
    neighbour = env.add("txt", "Damaged neighbour")
    env.seed_product([book, neighbour])
    intent_path = os.path.join(env.state, "intent.rdi")
    damaged = build(book)
    with open(intent_path, "wb") as f:
        f.write(damaged)
    before = env.snap()
    sdk_before = sha256_file(os.path.join(env.work, "sdk.db"))
    catalog_before = sha256_file(env.catalog_path)
    r = env.run("recover").result
    same(r["status"], "corrupt_intent", "damaged intent refused: " + r["msg"])
    same(sha256_file(intent_path), sha256_bytes(damaged), "damaged intent left verbatim")
    same(sha256_file(os.path.join(env.work, "sdk.db")), sdk_before, "SDK database unchanged")
    same(sha256_file(env.catalog_path), catalog_before, "catalog database unchanged")
    env.assert_unchanged_but(before)
    same(env.pending()["status"], "corrupt_intent", "pending refuses the damaged record too")
    with open(intent_path, "wb") as f:
        f.write(intent_record(book))
    rec = env.run("recover").result
    same(rec["status"], "ok", "restored record recovers: " + rec["msg"])
    same(rec["outcome"], "rolled_back", "a begun record rolls back")
    env.assert_state_clean()
    env.assert_unchanged_but(before)
    same(env.dump_sha(book.mapped), book.sha, "original intact after the restored rollback")


def s_intent_trailing_bytes(ctx):
    damaged_intent(ctx, "intent_trailing", lambda b: intent_record(b, extra=b"x"))


def s_intent_trailing_nul(ctx):
    damaged_intent(ctx, "intent_trailing_nul", lambda b: intent_record(b, extra=b"\x00"))


def oversized_record(book):
    """A record whose first 2048 bytes are complete, followed by more bytes:
    the previous reader stopped at 2048 and never looked at the end."""
    lines = [b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
             b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped]
    body = b"EXRLD1\n" + b"".join(line + b"\n" for line in lines)
    pad = 2048 - (len(body) + 5 + 71)
    need(pad > 0, "record is already past the bound")
    body += b"pad=" + b"A" * pad + b"\n"
    record = body + b"check=" + hashlib.sha256(body).hexdigest().encode("ascii") + b"\n"
    need(len(record) == 2048, "padded record must reach the bound exactly")
    return record + b"TRAILING"


def s_intent_oversized(ctx):
    damaged_intent(ctx, "intent_oversized", oversized_record)


def s_intent_truncated(ctx):
    damaged_intent(ctx, "intent_truncated", lambda b: intent_record(b)[:-1])


def s_intent_bad_number(ctx):
    def build(book):
        return intent_record(book, lines=[
            b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%dabc" % book.size,
            b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped])
    damaged_intent(ctx, "intent_bad_number", build)


def s_intent_stage_suffix(ctx):
    def build(book):
        return intent_record(book, lines=[
            b"stage=2junk", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped])
    damaged_intent(ctx, "intent_stage_suffix", build)


def s_intent_duplicate_field(ctx):
    def build(book):
        return intent_record(book, lines=[
            b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"bytes=%d" % book.size, b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped])
    damaged_intent(ctx, "intent_duplicate_field", build)


def s_intent_unknown_field(ctx):
    def build(book):
        return intent_record(book, lines=[
            b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped, b"extra=1"])
    damaged_intent(ctx, "intent_unknown_field", build)


def s_intent_empty_id(ctx):
    def build(book):
        return intent_record(book, lines=[
            b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"mapped=%d" % book.mapped, b"ids=%d,,%d" % (book.mapped, book.mapped)])
    damaged_intent(ctx, "intent_empty_id", build)


def s_intent_nine_ids(ctx):
    def build(book):
        ids = b",".join(b"%d" % (book.mapped + i) for i in range(9))
        return intent_record(book, lines=[
            b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"mapped=%d" % book.mapped, b"ids=" + ids])
    damaged_intent(ctx, "intent_nine_ids", build)


def s_state_dir_link_refused(ctx):
    env = ctx.new("state_link")
    book = env.add("txt", "State Link")
    env.seed_product([book])
    sentinel_dir = os.path.join(env.work, "sentinel")
    os.makedirs(sentinel_dir, exist_ok=True)
    sentinel = os.path.join(sentinel_dir, "keep.bin")
    with open(sentinel, "wb") as f:
        f.write(b"sentinel outside the cache\n" * 4)
    digest = sha256_file(sentinel)
    shutil.rmtree(env.state)
    reason = make_dir_link(sentinel_dir, env.state)
    if reason is not None:
        raise SkipCheck("directory link unavailable: " + reason)
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "io", "a linked state directory is refused: " + r["msg"])
    same(sha256_file(sentinel), digest, "sentinel untouched")
    same(sorted(os.listdir(sentinel_dir)), ["keep.bin"], "no intent written through the link")
    need(book.mapped in env.books(), "SDK row kept")


def s_originals_link_refused(ctx):
    env = ctx.new("originals_link")
    book = env.add("txt", "Originals Link")
    neighbour = env.add("txt", "Originals neighbour")
    env.seed_product([book, neighbour])
    sentinel_dir = os.path.join(env.work, "sentinel")
    os.makedirs(sentinel_dir, exist_ok=True)
    sentinel = os.path.join(sentinel_dir, "keep.bin")
    with open(sentinel, "wb") as f:
        f.write(b"sentinel outside the cache\n" * 8)
    digest = sha256_file(sentinel)
    reason = make_dir_link(sentinel_dir, os.path.join(env.state, "originals"))
    if reason is not None:
        raise SkipCheck("directory link unavailable: " + reason)
    before = env.snap()
    r = env.run("remove", "--key", book.key).result
    same(r["status"], "io", "a linked originals directory is refused: " + r["msg"])
    same(sha256_file(sentinel), digest, "sentinel untouched")
    same(sorted(os.listdir(sentinel_dir)), ["keep.bin"], "no file cleared through the link")
    env.assert_unchanged_but(before)
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour readable")


def s_intent_tmp_hardlink_kept(ctx):
    env = ctx.new("tmp_hardlink")
    book = env.add("txt", "Hard Link")
    neighbour = env.add("txt", "Hard Link neighbour")
    env.seed_product([book, neighbour])
    sentinel = os.path.join(env.work, "sentinel.bin")
    with open(sentinel, "wb") as f:
        f.write(b"victim outside the cache\n" * 8)
    digest = sha256_file(sentinel)
    tmp = os.path.join(env.state, "intent.tmp")
    try:
        os.link(sentinel, tmp)
    except OSError as exc:
        raise SkipCheck("hard link unavailable: %s" % exc)
    before = env.snap()
    removed_ok(env.run("remove", "--key", book.key), book)
    env.assert_unchanged_but(before, {book.key})
    same(sha256_file(sentinel), digest, "a pre-placed hard link is never truncated")
    env.assert_state_clean()
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour readable")


def s_reimport_path_swap(ctx):
    """The pathname is replaced after the hash read: the stored bytes must still
    be the bytes that were verified."""
    env = ctx.new("swap_reimport")
    book = env.add("txt", "Swap Target", content=b"A" * 4096)
    other = env.add("txt", "Swap Source", content=b"B" * 4096)
    env.seed_product([book, other])
    removed_ok(env.run("remove", "--key", book.key), book)
    substitute = os.path.join(env.work, "files", "substitute.txt")
    with open(substitute, "wb") as f:
        f.write(b"B" * 4096)  # same size, different bytes
    out = env.run("reimport", "--key", book.key, "--file", book.path,
                  "--swap-at", "1", "--swap-from", substitute)
    if not any(t.startswith("SWAP ok") for t in out.lines):
        detail = next((t for t in out.lines if t.startswith("SWAP ")), "no SWAP line")
        raise SkipCheck("the host refused to replace the open file: " + detail)
    r = out.result
    same((r["status"], r["outcome"]), ("ok", "attached"), "reimport after swap: " + r["msg"])
    new_id = int(r["id"])
    same(env.dump_sha(new_id), book.sha, "imported bytes are the verified bytes")
    found, local, mapped, deleted = env.catalog(book.key)
    same((found, local, mapped), (1, new_id, 1), "mapping points at the verified row")
    same(env.dump_sha(other.mapped), other.sha, "unrelated row unchanged")
    env.assert_state_clean()


def s_reimport_import_verified(ctx):
    env = ctx.new("import_verified")
    book = env.add("epub", "Verified Import")
    env.seed_product([book])
    removed_ok(env.run("remove", "--key", book.key), book)
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same((r["status"], r["outcome"]), ("ok", "attached"), "reimport: " + r["msg"])
    same(env.dump_sha(int(r["id"])), book.sha, "stored bytes match the identity")
    same(env.catalog(book.key)[:3], (1, int(r["id"]), 1), "mapping written after verification")
    env.assert_state_clean()


def s_reimport_publish_blocked(ctx):
    """A blocked retained-original publish must leave no SDK row and no mapping,
    and the same call must succeed after the obstruction is removed."""
    env = ctx.new("publish_blocked")
    book = env.add("pdf", "Publish Blocked")
    neighbour = env.add("txt", "Publish neighbour")
    env.seed_product([book, neighbour])
    removed_ok(env.run("remove", "--key", book.key), book)
    originals = os.path.join(env.state, "originals")
    os.makedirs(originals, exist_ok=True)
    blocked = os.path.join(originals, book.sha + ".orig")
    os.makedirs(blocked)  # a directory where the retained file has to go
    keep = os.path.join(blocked, "keep.bin")
    with open(keep, "wb") as f:
        f.write(b"blocked target\n")
    before = env.snap()
    sdk_before = sha256_file(os.path.join(env.work, "sdk.db"))
    catalog_before = sha256_file(env.catalog_path)
    rows_before = sorted(env.books())
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same(r["status"], "io", "a blocked publish is refused: " + r["msg"])
    same(sha256_file(os.path.join(env.work, "sdk.db")), sdk_before, "no SDK row was created")
    same(sha256_file(env.catalog_path), catalog_before, "the catalog was not touched")
    same(sorted(env.books()), rows_before, "SDK rows unchanged")
    same(env.catalog(book.key)[:3], (1, 0, 0), "no mapping was written")
    need(not os.path.exists(os.path.join(originals, book.sha + ".open")), "staging left behind")
    need(os.path.isfile(keep), "the blocking target was modified")
    env.assert_unchanged_but(before)
    shutil.rmtree(blocked)
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same((r["status"], r["outcome"]), ("ok", "attached"), "retry after clearing the block")
    same(env.dump_sha(int(r["id"])), book.sha, "the retry stored the verified bytes")
    same(env.catalog(book.key)[:3], (1, int(r["id"]), 1), "mapping restored on the retry")
    book.ids[0] = int(r["id"])
    removed_ok(env.run("remove", "--key", book.key), book)
    env.assert_state_clean()


def s_reimport_over_ceiling(ctx):
    """A ceiling below the book refuses before copying anything."""
    env = ctx.new("reimport_ceiling")
    book = env.add("txt", "Ceiling", content=b"C" * 4096)
    env.seed_product([book])
    removed_ok(env.run("remove", "--key", book.key), book)
    before = env.snap()
    sdk_before = sha256_file(os.path.join(env.work, "sdk.db"))
    catalog_before = sha256_file(env.catalog_path)
    r = env.run("reimport", "--key", book.key, "--file", book.path, "--max-input", "1024").result
    same(r["status"], "argument", "a ceiling below the book is refused: " + r["msg"])
    same(sha256_file(os.path.join(env.work, "sdk.db")), sdk_before, "no SDK row was created")
    same(sha256_file(env.catalog_path), catalog_before, "the catalog was not touched")
    originals = os.path.join(env.state, "originals")
    same(os.listdir(originals) if os.path.isdir(originals) else [], [], "nothing was staged")
    env.assert_unchanged_but(before)
    r = env.run("reimport", "--key", book.key, "--file", book.path, "--max-input", "8192").result
    same((r["status"], r["outcome"]), ("ok", "attached"), "a sufficient ceiling succeeds")
    same(env.dump_sha(int(r["id"])), book.sha, "verified bytes stored")
    env.assert_state_clean()


def s_reimport_longer_file(ctx):
    """An input far past the identity length is refused and the private copy
    never exceeds that length."""
    env = ctx.new("reimport_longer")
    book = env.add("txt", "Longer", content=b"D" * 4096)
    env.seed_product([book])
    removed_ok(env.run("remove", "--key", book.key), book)
    longer = os.path.join(env.work, "files", "longer.txt")
    with open(longer, "wb") as f:
        f.write(b"D" * 4096)
        f.write(b"E" * (192 * 1024))
    before = env.snap()
    sdk_before = sha256_file(os.path.join(env.work, "sdk.db"))
    r = env.run("reimport", "--key", book.key, "--file", longer).result
    same(r["status"], "identity", "a longer file is refused: " + r["msg"])
    same(sha256_file(os.path.join(env.work, "sdk.db")), sdk_before, "no SDK row was created")
    originals = os.path.join(env.state, "originals")
    staged = os.listdir(originals) if os.path.isdir(originals) else []
    same(staged, [], "no staging file is left")
    biggest = 0
    for name in staged:
        biggest = max(biggest, os.path.getsize(os.path.join(originals, name)))
    need(biggest <= book.size, "a private copy exceeded the identity length")
    env.assert_unchanged_but(before)
    env.assert_state_clean()


def s_reenter_remove_from_stage(ctx):
    env = ctx.new("reenter_remove")
    book = env.add("txt", "Reenter Remove")
    neighbour = env.add("txt", "Reenter neighbour")
    env.seed_product([book, neighbour])
    before = env.snap()
    out = env.run("remove", "--key", book.key, "--reenter", "remove")
    same(out.line("REENTER ")["status"], "busy", "reentrant remove refused")
    removed_ok(out, book)
    env.assert_state_clean()
    env.assert_unchanged_but(before, {book.key})


def s_reenter_recover_from_busy(ctx):
    """is_busy is consulted before any destructive step; a callback that calls
    recover from there must be refused without disturbing the outer call."""
    env = ctx.new("reenter_busy")
    book = env.add("txt", "Reenter Busy")
    neighbour = env.add("txt", "Reenter Busy neighbour")
    env.seed_product([book, neighbour])
    before = env.snap()
    out = env.run("remove", "--key", book.key, "--reenter", "recover", "--reenter-in-busy")
    same(out.line("REENTER ")["status"], "busy", "reentrant recover refused from is_busy")
    removed_ok(out, book)
    env.assert_state_clean()
    env.assert_unchanged_but(before, {book.key})
    same(env.dump_sha(neighbour.mapped), neighbour.sha, "neighbour readable")


def s_reenter_pending_readonly(ctx):
    env = ctx.new("reenter_pending")
    book = env.add("txt", "Reenter Pending")
    env.seed_product([book])
    out = env.run("remove", "--key", book.key, "--reenter", "pending")
    fields = out.line("REENTER ")
    same(fields["status"], "ok", "pending is read-only and allowed")
    same(fields["pending"], "1", "pending reports the live record")
    same(fields["stage"], "begun", "pending reports the committed stage")
    removed_ok(out, book)
    env.assert_state_clean()


def s_pdf_private_original(ctx):
    env = ctx.new("pdf_private")
    book = env.add("pdf", "Private PDF")
    other = env.add("pdf", "Private PDF Other", fixture="pdf-graphics.pdf")
    env.seed_product([book, other])
    removed_ok(env.run("remove", "--key", book.key), book)
    r = env.run("reimport", "--key", book.key, "--file", book.path).result
    same((r["status"], r["outcome"]), ("ok", "attached"), "PDF reimport: " + r["msg"])
    book.ids[0] = int(r["id"])  # the reimport created a new SDK row
    stable = os.path.join(env.state, "originals", book.sha + ".orig")
    need(os.path.isfile(stable), "the PDF private original is retained")
    same(sha256_file(stable), book.sha, "retained PDF bytes")
    removed_ok(env.run("remove", "--key", other.key), other)
    r = env.run("reimport", "--key", other.key, "--file", other.path).result
    same((r["status"], r["outcome"]), ("ok", "attached"), "second PDF reimport")
    other.ids[0] = int(r["id"])
    other_stable = os.path.join(env.state, "originals", other.sha + ".orig")
    need(os.path.isfile(other_stable), "the second PDF private original is retained")
    other_digest = sha256_file(other_stable)
    removed_ok(env.run("remove", "--key", book.key), book)
    need(not os.path.exists(stable), "the removed book's private original is gone")
    need(os.path.isfile(other_stable), "another book's private original is untouched")
    same(sha256_file(other_stable), other_digest, "other private bytes unchanged")
    same(env.catalog(book.key)[:2], (1, 0), "global book kept without a local copy")
    need(not os.path.exists(os.path.join(env.state, "intent.rdi")), "intent left behind")
    need(not os.path.exists(os.path.join(env.state, "intent.tmp")), "intent temp left behind")
    same(sorted(os.listdir(os.path.join(env.state, "originals"))), [other.sha + ".orig"],
         "only the live book's private original remains")
    removed_ok(env.run("remove", "--key", other.key), other)
    env.assert_state_clean()
    same(env.catalog(other.key)[:2], (1, 0), "second book kept without a local copy")


def s_formats_all(ctx):
    """Every supported format: remove, exact reimport, remove again."""
    for kind in ALL_FORMATS:
        env = ctx.new("format_" + kind)
        book = env.add(kind, "Format " + kind)
        neighbour = env.add("txt", "Format neighbour " + kind)
        env.seed_product([book, neighbour])
        before = env.snap()
        removed_ok(env.run("remove", "--key", book.key), book)
        env.assert_unchanged_but(before, {book.key})
        found, local, mapped, deleted = env.catalog(book.key)
        same((found, local, mapped), (1, 0, 0), kind + ": global kept, local gone")
        need(book.mapped not in env.books(), kind + ": SDK row removed")
        need(not os.path.exists(os.path.join(env.state, "originals", book.sha + ".orig")),
             kind + ": no retained export after removal")
        r = env.run("reimport", "--key", book.key, "--file", book.path).result
        same((r["status"], r["outcome"]), ("ok", "attached"), kind + " reimport: " + r["msg"])
        new_id = int(r["id"])
        same(env.dump_sha(new_id), book.sha, kind + ": reimported bytes match the identity")
        same(env.catalog(book.key)[:3], (1, new_id, 1), kind + ": mapping back")
        book.ids[0] = new_id  # the reimport created a new SDK row
        removed_ok(env.run("remove", "--key", book.key), book)
        same(env.dump_sha(neighbour.mapped), neighbour.sha, kind + ": neighbour readable")
        env.assert_state_clean()


SCENARIOS = [
    ("cloud_only_noop", s_cloud_only), ("remove_txt", s_remove_txt), ("remove_epub", s_remove_epub),
    ("remove_cbz", s_remove_cbz), ("repeat_request_idempotent", s_repeat),
    ("reimport_same_identity", s_reimport), ("reimport_wrong_file_rejected", s_reimport_wrong),
    ("duplicate_sdk_ids_removed_exactly", s_duplicates), ("duplicate_with_legacy_rejected", s_duplicate_legacy),
    ("legacy_notes_rejected_then_backup", s_legacy_notes), ("legacy_progress_rejected", s_legacy_progress),
    ("busy_rejects_without_change", s_busy), ("held_source_readable_then_released", s_held),
    ("kill_begun", make_kill("begun")), ("kill_prepared", make_kill("prepared")),
    ("kill_unmapped", make_kill("unmapped")), ("kill_deleted", make_kill("deleted")),
    ("kill_cleaned", make_kill("cleaned")), ("kill_unmapped_cbz", make_kill("unmapped", "cbz")),
    ("kill_deleted_epub", make_kill("deleted", "epub")), ("late_legacy_restores_mapping", s_late_legacy),
    ("pending_blocks_other_removal", s_pending_other), ("pending_blocks_reimport", s_pending_reimport),
    ("disk_failure_leaves_book_readable", s_disk_failure),
    ("mapping_failure_leaves_book_readable", s_mapping_failure),
    ("cancel_at_begun", make_cancel("begun")), ("cancel_at_prepared", make_cancel("prepared")),
    ("corrupt_intent_refused", s_corrupt), ("identity_mismatch_refused", s_identity),
    ("missing_sdk_row_refused", s_missing_row), ("cpp_consumer", s_cpp),
    # root review round: identity TOCTOU, strict intent, cache boundary,
    # reentrancy and the full nine-format matrix
    ("reimport_path_swap_keeps_identity", s_reimport_path_swap),
    ("reimport_verifies_imported_row", s_reimport_import_verified),
    ("intent_trailing_bytes_refused", s_intent_trailing_bytes),
    ("intent_trailing_nul_refused", s_intent_trailing_nul),
    ("intent_oversized_refused", s_intent_oversized),
    ("intent_truncated_refused", s_intent_truncated),
    ("intent_bad_number_refused", s_intent_bad_number),
    ("intent_stage_suffix_refused", s_intent_stage_suffix),
    ("intent_duplicate_field_refused", s_intent_duplicate_field),
    ("intent_unknown_field_refused", s_intent_unknown_field),
    ("intent_empty_id_refused", s_intent_empty_id),
    ("intent_nine_ids_refused", s_intent_nine_ids),
    ("state_dir_link_refused", s_state_dir_link_refused),
    ("originals_link_refused", s_originals_link_refused),
    ("intent_tmp_hardlink_kept", s_intent_tmp_hardlink_kept),
    ("reimport_publish_blocked", s_reimport_publish_blocked),
    ("reimport_over_ceiling", s_reimport_over_ceiling),
    ("reimport_longer_file", s_reimport_longer_file),
    ("reenter_remove_from_stage", s_reenter_remove_from_stage),
    ("reenter_recover_from_busy", s_reenter_recover_from_busy),
    ("reenter_pending_readonly", s_reenter_pending_readonly),
    ("pdf_private_original", s_pdf_private_original),
    ("formats_all_remove_reimport", s_formats_all),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True)
    parser.add_argument("--cpp", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--library", action="append", default=[])
    parser.add_argument("--path-extra", action="append", default=[])
    args = parser.parse_args()
    names = [n for n, _ in SCENARIOS]
    if names != EXPECTED_CHECKS:
        print("scenario list differs from the declared check list")
        return 2
    shutil.rmtree(args.work, ignore_errors=True)
    os.makedirs(args.work)
    os.makedirs(args.output, exist_ok=True)
    ctx = Ctx(os.path.abspath(args.probe), os.path.abspath(args.cpp), os.path.abspath(args.fixtures),
              os.path.abspath(args.work), args.path_extra)
    checks = []
    skipped = []
    for name, fn in SCENARIOS:
        started = time.time()
        try:
            fn(ctx)
            checks.append({"name": name, "ok": True, "seconds": round(time.time() - started, 2)})
            print("PASS", name)
        except SkipCheck as exc:
            skipped.append({"name": name, "reason": str(exc)[:300]})
            checks.append({"name": name, "ok": True, "skipped": str(exc)[:300],
                           "seconds": round(time.time() - started, 2)})
            print("SKIP", name, str(exc))
        except Exception as exc:  # report every failure, never stop early
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            checks.append({"name": name, "ok": False, "detail": detail[:2000],
                           "seconds": round(time.time() - started, 2)})
            print("FAIL", name, detail)
            traceback.print_exc()
    report = {
        "ok": all(c["ok"] for c in checks) and len(checks) == len(EXPECTED_CHECKS),
        "source": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "os": os.environ.get("RUNNER_OS", sys.platform),
        "consumer_sha256": {
            "probe": sha256_file(args.probe), "cpp": sha256_file(args.cpp),
            "libraries": dict((os.path.basename(p), sha256_file(p)) for p in args.library if os.path.isfile(p)),
        },
        "real_process_kill_stages": ["begun", "prepared", "unmapped", "deleted", "cleaned"],
        "skipped": skipped,
        "checks": checks,
    }
    with open(os.path.join(args.output, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print("report ok=%s checks=%d skipped=%d" % (report["ok"], len(checks), len(skipped)))
    print("consumer probe=%s" % report["consumer_sha256"]["probe"])
    print("consumer cpp=%s" % report["consumer_sha256"]["cpp"])
    for name in sorted(report["consumer_sha256"].get("libraries", {})):
        print("library %s %s" % (name, report["consumer_sha256"]["libraries"][name]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
