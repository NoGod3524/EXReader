#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Named WP12 legacy-migration scenarios. Runs the installed exreader-legacy-migrate binary against
packs built by legacy_data.py and writes one evidence JSON. Intended for the GitHub-hosted workflow."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legacy_data as L  # noqa: E402

CASES = []
PEAKS = []


def case(area):
    def wrap(fn):
        CASES.append((fn.__name__, area, fn))
        return fn
    return wrap


class Result:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err
        try:
            self.rep = json.loads(out) if out.strip() else None
        except ValueError:
            self.rep = None
        if self.rep and "memory" in self.rep:
            PEAKS.append(self.rep["memory"].get("peak_rss_bytes", 0))

    @property
    def result(self):
        return self.rep and self.rep.get("result")

    @property
    def codename(self):
        return self.rep and self.rep.get("code")

    def item(self, legacy):
        return next((i for i in self.rep["items"] if i["legacy_id"] == legacy), None)

    def note(self, legacy):
        return next((n for n in self.rep["notes"] if n["legacy_id"] == legacy), None)

    def entries(self, code, legacy=None):
        return [e for e in self.rep["entries"] if e["code"] == code and (legacy is None or e["legacy_id"] == legacy)]


class Ctx:
    def __init__(self, tool, root, name):
        self.tool, self.name = tool, name
        self.dir = os.path.join(root, name)
        os.makedirs(self.dir)
        self.checks = []
        self.runs = 0

    def check(self, condition, text):
        self.checks.append({"check": text, "ok": bool(condition)})
        return bool(condition)

    def path(self, name):
        return os.path.join(self.dir, name)

    def pack(self, books, notes, name="pack.exrpack", **kw):
        path = self.path(name)
        with open(path, "wb") as f:
            f.write(L.build_pack(books, notes, **kw))
        return path

    def raw_pack(self, data, name="pack.exrpack"):
        path = self.path(name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def tool_run(self, *args, inject=None, timeout=300):
        env = dict(os.environ)
        cmd = [self.tool] + list(args)
        if inject:
            env["EXR_MIGRATE_TEST_FAULTS"] = "1"
            cmd += ["--inject", inject]
        self.runs += 1
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
        return Result(p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"))

    def migrate(self, pack, target, *flags, inject=None):
        return self.tool_run("migrate", "--pack", pack, "--target", target, *flags, inject=inject)

    def dump(self, target):
        r = self.tool_run("dump", "--target", target)
        if r.code != 0 or r.rep is None:
            raise RuntimeError("dump failed: %s %s" % (r.out[:300], r.err[:300]))
        return r.rep

    def listing(self, ignore=()):
        return sorted(n for n in os.listdir(self.dir) if n not in ignore)

    def sha(self, path):
        if not os.path.exists(path):
            return None
        return hashlib.sha256(open(path, "rb").read()).hexdigest()

    def ledger(self, target):
        path = target + ".legacy-map.json"
        return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def by_title(d, title):
    return next(b for b in d["books"] if b["title"] == title)


def texts(book):
    return {n["text"]: n for n in book["notes"]}


def full(c, name="lib.sqlite", flags=("--allow-partial",)):
    books, notes = L.dataset()
    pack = c.pack(books, notes)
    target = c.path(name)
    r = c.migrate(pack, target, *flags)
    return pack, target, r


# ======================================================================== metadata and bytes
@case("metadata")
def metadata_roundtrip(c):
    pack, T, r = full(c)
    c.check(r.code == 0 and r.result == "success", "partial migration of the full dataset succeeds (exit 0)")
    d = c.dump(T)
    tale = by_title(d, "The Tale")
    c.check(tale["author"] == "A. Writer" and tale["tags"] == "fiction, local" and tale["favorite"] == 1 and tale["status"] == 1,
            "title/author/tags/favorite/status reach the library")
    c.check(tale["cover_bytes"] > 0, "data-URI cover decoded into the library cover column")
    c.check(len(d["books"]) == 4, "four storable books (audio original excluded) are in the library")


@case("metadata")
def status_favorite_mapping(c):
    books = []
    for i, status in enumerate(["unread", "reading", "finished"]):
        data = L.TXT.replace(b"Alpha", b"Bk%d" % i)
        books.append(L.entry(L.book_record("s%d" % i, "s%d.txt" % i, title="S%d" % i, status=status, favorite=bool(i % 2)), data))
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack(books, []), T)
    d = c.dump(T)
    got = {b["title"]: (b["status"], b["favorite"]) for b in d["books"]}
    c.check(r.code == 0 and got == {"S0": (0, 0), "S1": (1, 1), "S2": (2, 0)}, "unread/reading/finished -> 0/1/2 and favorite flags: %s" % got)


@case("originals")
def original_bytes_exact(c):
    pack, T, r = full(c)
    d = c.dump(T)
    want = {L.sha256(L.TXT), L.sha256(L.epub()), L.sha256(L.pdf()), L.sha256(L.cbz())}
    got = {b["source_sha256"] for b in d["books"]}
    c.check(got == want, "stored originals are byte-identical to the legacy files (sha256 set equal)")
    c.check(all(i["sha256"] for i in r.rep["items"] if i["status"] in ("created", "merged")), "report carries per-book digests")


@case("originals")
def sdk_rejects_garbage_original(c):
    rec = L.book_record("g1", "broken.epub", title="Broken")
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(rec, b"this is not a zip archive")], []), T)
    c.check(r.code == 2 and r.codename == "policy-strict" and r.entries("sdk-rejected-original", "g1"), "SDK-refused original is an item-level unsupported finding that rejects strictly")
    c.check(not os.path.exists(T), "nothing published")


@case("originals")
def dedup_is_content_not_name_or_size(c):
    assert len(L.TXT) == len(L.TXT_OTHER)
    a = L.book_record("d1", "dup.txt", title="Dup One", size=len(L.TXT), modified=5)
    b = L.book_record("d2", "dup.txt", title="Dup Two", size=len(L.TXT), modified=5)
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(a, L.TXT), L.entry(b, L.TXT_OTHER)], []), T)
    c.check(r.code == 0 and len(c.dump(T)["books"]) == 2 and r.rep["counts"]["books_created"] == 2, "same name+size+mtime with different bytes stays two books")


# ======================================================================== reflow progress and notes
@case("progress")
def reflow_progress_cfi_anchor(c):
    pack, T, r = full(c)
    d = c.dump(T)
    ep = by_title(d, "Lighthouse Chronicle")
    mark = texts(ep)["second chapter occurrence"]
    c.check(ep["progress_state"] == 1 and ep["progress_start"] == ep["position"] and ep["position"] > 0, "CFI progress stored as a FOUND point selector")
    c.check(ep["position"] == mark["start"], "CFI offset 24 equals the start of the second-chapter 'echo token'")


@case("progress")
def reflow_progress_percent_is_approximate(c):
    pack, T, r = full(c)
    tale = by_title(c.dump(T), "The Tale")
    c.check(tale["progress_state"] == 3 and 0 < tale["position"] < len(L.TXT), "fraction-only progress is stored as a LEGACY offset with no selector")
    c.check(any(e["legacy_id"] == "b-txt" for e in r.entries("approximate-progress")), "report flags the percentage estimate")


@case("annotations")
def note_unique_quote_located(c):
    pack, T, r = full(c)
    n = texts(by_title(c.dump(T), "The Tale"))["keep this"]
    c.check(n["exact"] == "unique sentence about silver tides" and n["located"], "unique quote becomes a selector-backed note")
    c.check(r.note("n-txt-unique")["method"] == "quote-unique", "method recorded")


@case("annotations")
def note_whitespace_equivalent_quote(c):
    pack, T, r = full(c)
    n = texts(by_title(c.dump(T), "The Tale"))["whitespace differs"]
    c.check(n["exact"] == "unique sentence about silver tides", "line breaks/runs of spaces in the legacy quote still locate the text")


@case("annotations")
def note_cjk_quote(c):
    pack, T, r = full(c)
    c.check(texts(by_title(c.dump(T), "The Tale"))["cjk"]["exact"] == "中文引用在此处出现一次", "CJK quote located on UTF-8 boundaries")


@case("annotations")
def note_ambiguous_quote_unlocated(c):
    pack, T, r = full(c)
    tale = by_title(c.dump(T), "The Tale")
    n = r.note("n-txt-ambiguous")
    c.check(n["status"] == "unlocated" and n["reason"] == "quote-ambiguous", "two occurrences -> unlocated, no guess")
    c.check("appears twice" not in texts(tale), "ambiguous note is not placed in the library")
    led = c.ledger(T)
    kept = next(x for x in led["notes"] if x["legacy_id"] == "n-txt-ambiguous")
    c.check(kept["located"] is False and kept["retained"]["note"] == "appears twice" and kept["retained"]["quote"] == "Repeat this phrase twice.", "content retained in the readable ledger")


@case("annotations")
def note_missing_quote_unlocated(c):
    pack, T, r = full(c)
    c.check(r.note("n-txt-missing")["reason"] == "quote-not-found", "edited-away quote is unlocated")
    c.check(r.rep["counts"]["notes_unlocated"] >= 5, "unlocated annotations are counted, not dropped")


@case("annotations")
def note_cfi_range_exact(c):
    pack, T, r = full(c)
    n = texts(by_title(c.dump(T), "Lighthouse Chronicle"))["exact range"]
    c.check(r.note("n-epub-range")["method"] == "cfi+quote" and n["exact"] == "cobalt lighthouse", "CFI range confirmed by quote")


@case("annotations")
def note_cfi_disambiguates_repeated_quote(c):
    pack, T, r = full(c)
    ep = by_title(c.dump(T), "Lighthouse Chronicle")
    n = texts(ep)["second chapter occurrence"]
    first = texts(ep)["exact range"]
    c.check(r.note("n-epub-disambiguate")["method"] == "quote-in-cfi-node" and n["start"] > first["start"], "CFI node picks the chapter-two occurrence")
    c.check(r.note("n-epub-ambiguous")["status"] == "unlocated", "same quote without a CFI stays unlocated")


@case("annotations")
def bookmark_with_cfi_is_a_point(c):
    pack, T, r = full(c)
    n = texts(by_title(c.dump(T), "Lighthouse Chronicle"))["point bookmark"]
    c.check(n["start"] == n["end"] and r.note("n-epub-bookmark")["method"] == "cfi-offset", "CFI bookmark becomes an empty-range point note")


@case("annotations")
def bookmark_without_cfi_unlocated(c):
    pack, T, r = full(c)
    c.check(r.note("n-txt-bookmark")["reason"] == "bookmark-without-cfi", "a bookmark without a CFI is never given a guessed place")


# ======================================================================== fixed pages and audio
@case("fixed")
def fixed_progress_is_one_based_to_zero_based(c):
    pack, T, r = full(c)
    c.check(by_title(c.dump(T), "Scan")["position"] == 1, "legacy page 2 (one-based) -> zero-based position 1")


@case("fixed")
def fixed_page_note_located(c):
    pack, T, r = full(c)
    n = texts(by_title(c.dump(T), "Scan"))["second page"]
    c.check(n["page"] == 1 and n["exact"] == "page two quote beta", "PDF quote located on its own page (zero-based page 1)")


@case("fixed")
def fixed_page_bookmark(c):
    pack, T, r = full(c)
    n = r.note("n-pdf-bookmark")
    c.check(n["status"] == "created" and n["method"] == "page-bookmark", "page bookmark stored as an empty page note")


@case("fixed")
def fixed_missing_quote_unlocated_and_rects_recorded(c):
    pack, T, r = full(c)
    c.check(r.note("n-pdf-missing")["reason"] == "quote-not-found", "quote absent from the page is unlocated")
    c.check(r.entries("rects-not-converted", "n-pdf-quote"), "legacy rectangles are reported as not converted")
    led = c.ledger(T)
    kept = next(x for x in led["notes"] if x["legacy_id"] == "n-pdf-quote")
    c.check(kept["retained"]["rects"][0]["w"] == 0.4, "rectangles retained verbatim in the ledger")


@case("fixed")
def cbz_percent_progress_is_page_estimate(c):
    pack, T, r = full(c)
    c.check(by_title(c.dump(T), "Comic")["position"] == 1 and r.entries("approximate-progress", "b-cbz"), "0.5 over 3 pages -> page index 1, flagged approximate")


@case("audio")
def audio_positions_and_bookmarks(c):
    pack, T, r = full(c)
    a = c.dump(T)["audio"]
    c.check(len(a) == 1 and a[0]["audio_id"] == "exreader-legacy:b-audio" and a[0]["resume_found"] and a[0]["resume_ms"] == 75500, "seconds -> millisecond resume point")
    c.check(sorted((m["offset_ms"], m["label"]) for m in a[0]["bookmarks"]) == [(30000, "chapter two"), (61250, "listen again")], "audio bookmarks use millisecond offsets and the best label")


@case("audio")
def audio_original_is_unsupported_so_strict_rejects(c):
    books, notes = L.dataset()
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack(books, notes), T)
    c.check(r.code == 2 and r.result == "rejected" and r.codename == "policy-strict" and r.entries("audio-original-not-storable", "b-audio"), "strict mode rejects because an audio original cannot be stored")
    c.check(not os.path.exists(T) and not os.path.exists(T + ".legacy-map.json") and c.listing(("pack.exrpack",)) == [], "no target, ledger or stray file after the rejection")


# ======================================================================== field handling
@case("fields")
def missing_fields_get_defaults(c):
    rec = {"id": "m1", "filename": "bare.txt"}
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(rec, L.TXT)], []), T)
    b = c.dump(T)["books"][0]
    c.check(r.code == 0 and b["title"] == "bare" and b["author"] == "" and b["tags"] == "" and b["status"] == 0 and b["favorite"] == 0, "absent fields get documented defaults")
    c.check(len(r.entries("missing-field", "m1")) >= 4, "each default is reported as info")


@case("fields")
def unknown_fields_reported_and_kept(c):
    rec = L.book_record("u1", "u.txt", title="U", highlightColor="red")
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(rec, L.TXT)], [L.note_record("un1", "u1", "unique sentence", "x", flair=3)]), T)
    c.check(r.code == 0 and r.entries("unknown-field", "u1") and r.entries("unknown-field", "un1"), "unknown book and note fields are reported")
    c.check(c.ledger(T)["books"][0]["retained"]["highlightColor"] == "red", "unknown field retained in the ledger")


@case("fields")
def wrong_type_record_is_item_rejection(c):
    bad = L.book_record("w1", "w.txt", title=123)
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(bad, L.TXT)], []), T)
    c.check(r.code == 2 and r.entries("invalid-book-record", "w1") and not os.path.exists(T), "wrong JSON type is rejected as an item and, strictly, as the run")


@case("fields")
def missing_original_distinguished(c):
    books, notes = L.dataset()
    books[0]["data"] = None
    T = c.path("lib.sqlite")
    strict = c.migrate(c.pack(books, notes), T)
    c.check(strict.code == 2 and strict.entries("missing-original", "b-txt"), "missing original bytes are their own finding")
    partial = c.migrate(c.pack(books, notes, name="p2.exrpack"), T, "--allow-partial")
    c.check(partial.code == 0 and partial.item("b-txt")["status"] == "skipped" and len(c.dump(T)["books"]) == 3, "--allow-partial publishes the rest and lists the skipped book")


@case("fields")
def unsupported_format_reported(c):
    rec = L.book_record("f1", "x.fbz", title="Zipped fb2")
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(rec, b"PK\x03\x04")], []), T)
    c.check(r.code == 2 and r.entries("unsupported-format", "f1"), "fb2.zip/fbz has no SDK format and is reported")


@case("fields")
def orphan_note_preserved(c):
    pack, T, r = full(c)
    n = r.note("n-orphan")
    kept = next(x for x in c.ledger(T)["notes"] if x["legacy_id"] == "n-orphan")
    c.check(n["status"] == "unlocated" and n["reason"] == "orphan-note" and kept["retained"]["note"] == "orphan", "note whose book is absent is kept in the ledger only")


@case("fields")
def memory_metering(c):
    big = (L.TXT * 40000)[:4 * 1024 * 1024]
    big = big[:big.rindex(bytes([10])) + 1]
    rec = L.book_record("big", "big.txt", title="Big")
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(rec, big)], []), T)
    m = r.rep["memory"]
    c.check(r.code == 0 and m["max_original_bytes"] == len(big) and m["peak_rss_bytes"] > 0, "peak RSS and largest original are reported: %s" % m)


# ======================================================================== idempotence, retry, conflicts
@case("idempotence")
def rerun_same_pack_is_stable(c):
    pack, T, r1 = full(c)
    d1, led1 = c.dump(T), open(T + ".legacy-map.json", "rb").read()
    r2 = c.migrate(pack, T, "--allow-partial")
    d2, led2 = c.dump(T), open(T + ".legacy-map.json", "rb").read()
    k = r2.rep["counts"]
    c.check(r2.code == 0 and k["books_created"] == 0 and k["notes_created"] == 0, "second run creates nothing: %s" % k)
    c.check(json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True), "library content identical after the second run (same IDs)")
    c.check(led1 == led2, "ledger byte-identical (stable ID mapping)")
    v = c.tool_run("verify", "--pack", pack, "--target", T)
    c.check(v.code == 0 and v.result == "success", "verify command agrees in a fresh process")


@case("idempotence")
def interrupted_run_then_retry_equals_clean_run(c):
    books, notes = L.dataset()
    pack = c.pack(books, notes)
    T, clean = c.path("retry.sqlite"), c.path("clean.sqlite")
    r1 = c.migrate(pack, T, "--allow-partial", inject="cancel@7")
    c.check(r1.code == 4 and r1.result == "cancelled" and not os.path.exists(T) and not os.path.exists(T + ".legacy-map.json"), "cancelled run publishes nothing")
    c.check(not [n for n in c.listing(("pack.exrpack",)) if n.startswith("retry.sqlite")], "stage, lock and temp files removed after cancellation")
    r2 = c.migrate(pack, T, "--allow-partial")
    r3 = c.migrate(pack, clean, "--allow-partial")
    c.check(r2.code == 0 and json.dumps(c.dump(T), sort_keys=True) == json.dumps(c.dump(clean), sort_keys=True), "retry result equals an uninterrupted run")


@case("idempotence")
def ledger_loss_does_not_duplicate(c):
    pack, T, r1 = full(c)
    d1 = c.dump(T)
    os.remove(T + ".legacy-map.json")
    r2 = c.migrate(pack, T, "--allow-partial")
    d2 = c.dump(T)
    c.check(r2.code == 0 and r2.rep["counts"]["books_created"] == 0 and r2.rep["counts"]["notes_created"] == 0, "content match adopts existing books/notes: %s" % r2.rep["counts"])
    c.check(json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True), "no duplicate books or annotations without the ledger")
    c.check(r2.entries("adopted-existing", "b-txt"), "adoption is reported")


@case("conflicts")
def same_original_different_legacy_id_merges(c):
    a = L.book_record("x1", "a.txt", title="First Copy", favorite=True)
    b = L.book_record("x2", "b.txt", title="Second Copy")
    notes = [L.note_record("xn1", "x1", "unique sentence about silver tides", "from first"), L.note_record("xn2", "x2", "lantern keeper", "from second")]
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack([L.entry(a, L.TXT), L.entry(b, L.TXT)], notes), T)
    d = c.dump(T)
    c.check(r.code == 0 and len(d["books"]) == 1 and d["books"][0]["title"] == "First Copy", "identical bytes with two legacy ids -> one book, first metadata kept")
    c.check(r.entries("same-original-different-id", "x2") and r.rep["counts"]["books_merged"] == 1, "merge rule reported")
    c.check(set(texts(d["books"][0])) == {"from first", "from second"}, "annotations of both legacy ids are merged")
    led = c.ledger(T)
    c.check(len({x["book_id"] for x in led["books"]}) == 1, "ledger maps both legacy ids to the same book")


@case("conflicts")
def same_id_changed_original_is_conflict(c):
    T = c.path("lib.sqlite")
    rec = L.book_record("c1", "c.txt", title="C")
    c.migrate(c.pack([L.entry(rec, L.TXT)], [], name="a.exrpack"), T)
    before, led = c.dump(T), c.sha(T + ".legacy-map.json")
    tsha = c.sha(T)
    strict = c.migrate(c.pack([L.entry(rec, L.TXT_OTHER)], [], name="b.exrpack"), T)
    c.check(strict.code == 2 and strict.entries("id-content-changed", "c1") and c.sha(T) == tsha and c.sha(T + ".legacy-map.json") == led, "strict: rejected, library and ledger untouched")
    part = c.migrate(c.pack([L.entry(rec, L.TXT_OTHER)], [], name="b.exrpack"), T, "--allow-partial")
    c.check(part.code == 0 and part.item("c1")["status"] == "skipped" and json.dumps(c.dump(T), sort_keys=True) == json.dumps(before, sort_keys=True), "--allow-partial keeps the earlier book and skips the changed one")


@case("conflicts")
def same_note_id_changed_content_is_conflict(c):
    T = c.path("lib.sqlite")
    rec = L.book_record("k1", "k.txt", title="K")
    c.migrate(c.pack([L.entry(rec, L.TXT)], [L.note_record("kn", "k1", "lantern keeper", "v1")], name="a.exrpack"), T)
    r = c.migrate(c.pack([L.entry(rec, L.TXT)], [L.note_record("kn", "k1", "lantern keeper", "v2")], name="b.exrpack"), T)
    c.check(r.code == 2 and r.entries("note-changed", "kn"), "same note id with different content is a conflict")
    c.check("v1" in texts(c.dump(T)["books"][0]) and "v2" not in texts(c.dump(T)["books"][0]), "earlier note kept")


@case("conflicts")
def existing_target_content_is_preserved(c):
    T = c.path("lib.sqlite")
    a = L.book_record("e1", "e1.txt", title="Existing")
    c.migrate(c.pack([L.entry(a, L.TXT)], [L.note_record("en", "e1", "lantern keeper", "mine")], name="a.exrpack"), T)
    before = c.dump(T)["books"][0]
    b = L.book_record("e2", "e2.txt", title="Newcomer")
    r = c.migrate(c.pack([L.entry(b, L.TXT_OTHER)], [], name="b.exrpack"), T)
    after = c.dump(T)
    c.check(r.code == 0 and len(after["books"]) == 2 and before in after["books"], "pre-existing book, notes and ids unchanged after a second migration into the same library")
    c.check(r.rep["target"]["existed"] and r.rep["atomicity"]["stage"] == "published", "stage was built from the existing library with the backup API and published")


# ======================================================================== corrupt and unsupported packs
def rejected(c, data, code, extra=""):
    path = c.raw_pack(data)
    T = c.path("lib.sqlite")
    r = c.migrate(path, T)
    c.check(r.code == 2 and r.result == "rejected" and r.codename == code, "%s -> rejected/%s (got %s/%s) %s" % (extra, code, r.result, r.codename, extra))
    c.check(not os.path.exists(T) and c.listing(("pack.exrpack",)) == [], "no target, ledger or stray file")


def good_pack():
    books, notes = L.dataset()
    return L.build_pack(books, notes)


@case("corrupt")
def corrupt_bad_magic(c):
    data = bytearray(good_pack()); data[0] ^= 0xFF
    rejected(c, bytes(data), "pack-bad-magic")


@case("corrupt")
def corrupt_unknown_container_version(c):
    data = bytearray(good_pack()); data[6] = ord("2")
    rejected(c, bytes(data), "pack-unknown-version")


@case("corrupt")
def corrupt_truncated(c):
    rejected(c, good_pack()[:-10], "pack-truncated")


@case("corrupt")
def corrupt_manifest_digest(c):
    payload, manifest, trailer = L.split(good_pack())
    bad = bytearray(manifest); bad[len(bad) // 2] ^= 0x01
    rejected(c, payload + bytes(bad) + trailer, "pack-manifest-hash")


@case("corrupt")
def corrupt_original_digest(c):
    data = bytearray(good_pack()); data[20] ^= 0x01  # inside the first original
    rejected(c, bytes(data), "pack-hash-mismatch")


@case("corrupt")
def corrupt_unknown_manifest_version(c):
    books, notes = L.dataset()
    rejected(c, L.build_pack(books, notes, version=2), "pack-unknown-version")


@case("corrupt")
def corrupt_unknown_manifest_format(c):
    books, notes = L.dataset()
    rejected(c, L.build_pack(books, notes, fmt="calibre-library"), "pack-unknown-format")


@case("corrupt")
def corrupt_duplicate_legacy_ids(c):
    books, notes = L.dataset()
    books.append(L.clone(books[0]))
    rejected(c, L.build_pack(books, notes), "pack-duplicate-id")


@case("corrupt")
def corrupt_manifest_is_not_json(c):
    payload, manifest, trailer = L.split(good_pack())
    junk = b'{"format": '
    rejected(c, L.finish(payload, junk), "pack-manifest-json")


@case("corrupt")
def corrupt_schema_missing_arrays(c):
    payload, manifest, trailer = L.split(good_pack())
    obj = json.loads(manifest); obj["books"] = {}
    rejected(c, L.finish(payload, json.dumps(obj).encode()), "pack-schema")


# ======================================================================== target state and atomicity
def seeded_target(c):
    books, notes = L.dataset()
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack(books[:3], [n for n in notes if n["bookId"] in ("b-txt", "b-epub", "b-pdf")], name="seed.exrpack"), T)
    assert r.code == 0, r.out
    rest = c.pack(books[2:4], [n for n in notes if n["bookId"] in ("b-pdf",)], name="second.exrpack")
    return T, rest


def unchanged(c, T, before, label):
    now = {"lib": c.sha(T), "ledger": c.sha(T + ".legacy-map.json")}
    c.check(now == before, "%s: library file and ledger bytes unchanged" % label)
    c.check(c.listing(("pack.exrpack", "seed.exrpack", "second.exrpack", "lib.sqlite", "lib.sqlite.legacy-map.json")) == [], "%s: no stage, lock, pre-image or temp file left (%s)" % (label, c.listing()))


def snapshot(c, T):
    return {"lib": c.sha(T), "ledger": c.sha(T + ".legacy-map.json")}


@case("target")
def target_not_a_library(c):
    T = c.path("lib.sqlite")
    open(T, "wb").write(b"definitely not sqlite" * 10)
    before = snapshot(c, T)
    r = c.migrate(c.pack(*L.dataset()), T, "--allow-partial")
    c.check(r.code == 2 and r.codename == "target-not-library", "non-SQLite target refused")
    unchanged(c, T, before, "garbage target")


@case("target")
def target_old_schema_not_upgraded(c):
    T, rest = seeded_target(c)
    data = bytearray(open(T, "rb").read()); data[60:64] = (5).to_bytes(4, "big")
    open(T, "wb").write(bytes(data))
    before = snapshot(c, T)
    r = c.migrate(rest, T)
    c.check(r.code == 2 and r.codename == "target-schema", "schema-5 target refused instead of upgraded in place")
    unchanged(c, T, before, "old schema")


@case("target")
def target_occupied_by_lock_file(c):
    T, rest = seeded_target(c)
    open(T + ".migrate-lock", "w").write("someone else\n")
    before = snapshot(c, T)
    r = c.migrate(rest, T)
    c.check(r.code == 5 and r.result == "busy" and r.codename == "target-busy", "existing lock -> busy (exit 5)")
    c.check(open(T + ".migrate-lock").read() == "someone else\n", "foreign lock file is not removed")
    r2 = c.migrate(rest, T, "--break-lock")
    c.check(r2.code == 0 and not os.path.exists(T + ".migrate-lock"), "--break-lock takes over and releases the lock")


@case("target")
def target_held_open_exclusively(c):
    T, rest = seeded_target(c)
    before = snapshot(c, T)
    con = sqlite3.connect(T, isolation_level=None, timeout=0)
    con.execute("BEGIN EXCLUSIVE")
    try:
        r = c.migrate(rest, T)
    finally:
        con.execute("ROLLBACK"); con.close()
    c.check(r.code in (3, 5) and r.result in ("busy", "failed"), "target locked by another connection -> busy/failed (got %s/%s)" % (r.result, r.codename))
    unchanged(c, T, before, "exclusively locked target")


@case("target")
def ledger_without_library_refused(c):
    T = c.path("lib.sqlite")
    open(T + ".legacy-map.json", "w").write("{}")
    r = c.migrate(c.pack(*L.dataset()), T, "--allow-partial")
    c.check(r.code == 2 and r.codename == "orphan-ledger" and not os.path.exists(T), "a ledger without its library is refused")


@case("target")
def ledger_with_unknown_version_refused(c):
    T, rest = seeded_target(c)
    led = json.load(open(T + ".legacy-map.json")); led["version"] = 2
    open(T + ".legacy-map.json", "w").write(json.dumps(led))
    before = snapshot(c, T)
    r = c.migrate(rest, T)
    c.check(r.code == 2 and r.codename == "ledger-unknown-version", "newer ledger version is never overwritten")
    unchanged(c, T, before, "unknown ledger version")


@case("atomicity")
def cancel_midway_keeps_target(c):
    T, rest = seeded_target(c)
    before, d = snapshot(c, T), json.dumps(c.dump(T), sort_keys=True)
    r = c.migrate(rest, T, inject="cancel@1")
    c.check(r.code == 4 and r.result == "cancelled", "cancelled (exit 4)")
    unchanged(c, T, before, "cancel")
    c.check(json.dumps(c.dump(T), sort_keys=True) == d, "logical library content identical")


@case("atomicity")
def read_failure_keeps_target(c):
    T, rest = seeded_target(c)
    before = snapshot(c, T)
    r = c.migrate(rest, T, inject="read-fail@1")
    c.check(r.code == 3 and r.codename == "pack-read-error", "source read failure -> failed")
    unchanged(c, T, before, "read failure")


@case("atomicity")
def write_failure_after_partial_writes_keeps_target(c):
    T, rest = seeded_target(c)
    before, d = snapshot(c, T), json.dumps(c.dump(T), sort_keys=True)
    r = c.migrate(rest, T, inject="write-fail@1")
    c.check(r.code == 3 and r.codename == "injected-write-fail" and r.rep["atomicity"]["stage"] in ("removed", "built-from-backup"), "library write failure after the first book was staged -> failed")
    unchanged(c, T, before, "write failure")
    c.check(json.dumps(c.dump(T), sort_keys=True) == d, "logical content identical")


@case("atomicity")
def verification_failure_keeps_target(c):
    T, rest = seeded_target(c)
    before = snapshot(c, T)
    r = c.migrate(rest, T, inject="verify-fail")
    c.check(r.code == 3 and r.codename == "verify-failed", "stage verification failure -> failed")
    unchanged(c, T, before, "verify failure")


@case("atomicity")
def publish_failure_keeps_target(c):
    T, rest = seeded_target(c)
    before = snapshot(c, T)
    r = c.migrate(rest, T, inject="publish-fail")
    c.check(r.code == 3 and r.codename == "injected-publish-fail", "publish failure before replacement -> failed")
    unchanged(c, T, before, "publish failure")


@case("atomicity")
def ledger_publish_failure_rolls_back_library(c):
    T, rest = seeded_target(c)
    before, d = snapshot(c, T), json.dumps(c.dump(T), sort_keys=True)
    r = c.migrate(rest, T, inject="sidecar-fail")
    c.check(r.code == 3 and r.codename == "ledger-publish-failed" and r.rep["atomicity"]["rolled_back"] is True, "ledger failure after replacement rolls the library back")
    unchanged(c, T, before, "ledger publish failure")
    c.check(json.dumps(c.dump(T), sort_keys=True) == d, "logical content identical after rollback")


@case("atomicity")
def failed_rollback_is_reported_and_pre_image_kept(c):
    T, rest = seeded_target(c)
    original = c.sha(T)
    r = c.migrate(rest, T, inject="rollback-fail")
    pre = [n for n in c.listing() if ".pre-" in n]
    c.check(r.code == 6 and r.result == "inconsistent", "rollback failure is its own outcome (exit 6)")
    c.check(len(pre) == 1 and c.sha(c.path(pre[0])) == original and r.rep["atomicity"]["pre_image"] == "retained", "pre-image with the original bytes is retained and reported")


@case("atomicity")
def dry_run_publishes_nothing(c):
    books, notes = L.dataset()
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack(books, notes), T, "--allow-partial", "--dry-run")
    c.check(r.code == 0 and r.result == "dry-run" and not os.path.exists(T) and c.listing(("pack.exrpack",)) == [], "dry run verifies the stage, leaves no file")


@case("atomicity")
def new_target_failure_leaves_nothing(c):
    books, notes = L.dataset()
    T = c.path("lib.sqlite")
    r = c.migrate(c.pack(books, notes), T, "--allow-partial", inject="publish-fail")
    c.check(r.code == 3 and not os.path.exists(T) and not os.path.exists(T + ".legacy-map.json") and c.listing(("pack.exrpack",)) == [], "failure with no pre-existing library creates no library, ledger or stage")


# ======================================================================== commands
@case("commands")
def legacy_backup_zip_converts_to_equivalent_pack(c):
    import zipfile
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "..", "..", "extras", "migration", "exporter", "backup_to_pack.py")
    books, notes = L.dataset()
    zpath = c.path("legacy-backup.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # the layout of the old app's createBackup()
        z.writestr("library.json", json.dumps({"version": 1, "books": [b["record"] for b in books], "notes": notes}))
        for b in books:
            z.writestr("files/" + b["record"]["id"], b["data"])
    conv = c.path("from-backup.exrpack")
    p = subprocess.run([sys.executable, script, zpath, conv], capture_output=True)
    c.check(p.returncode == 0, "backup_to_pack.py converts the legacy backup archive (exit %d)" % p.returncode)
    A, B = c.path("a.sqlite"), c.path("b.sqlite")
    ra = c.migrate(conv, A, "--allow-partial")
    rb = c.migrate(c.pack(books, notes, name="direct.exrpack"), B, "--allow-partial")
    c.check(ra.code == 0 and rb.code == 0 and json.dumps(c.dump(A), sort_keys=True) == json.dumps(c.dump(B), sort_keys=True), "backup-derived and directly built packs migrate to identical libraries")
    bad = c.path("bad.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("readme.txt", "not a backup")
    q = subprocess.run([sys.executable, script, bad, c.path("bad.exrpack")], capture_output=True)
    c.check(q.returncode == 2 and b"backup-not-exreader" in q.stderr, "an unrelated archive is refused with a named error")


@case("commands")
def inspect_command(c):
    books, notes = L.dataset()
    books.append(L.entry(L.book_record("z", "z.fbz"), b"PK"))
    r = c.tool_run("inspect", "--pack", c.pack(books, notes))
    states = {i["legacy_id"]: i["state"] for i in r.rep["items"]}
    c.check(r.code == 0 and states["b-epub"] == "convertible" and states["b-audio"] == "audio-positions-only" and states["z"] == "unsupported-format", "inspect classifies without touching any target: %s" % states)


@case("commands")
def verify_detects_a_pack_that_was_not_migrated(c):
    books, notes = L.dataset()
    T = c.path("lib.sqlite")
    c.migrate(c.pack(books[:2], [], name="a.exrpack"), T)
    ok = c.tool_run("verify", "--pack", c.path("a.exrpack"), "--target", T)
    other = c.tool_run("verify", "--pack", c.pack(books[:3], [], name="b.exrpack"), "--target", T)
    c.check(ok.code == 0 and other.code == 3 and other.entries("verify-unmapped-book"), "verify passes for the migrated pack and fails for one with an unmigrated book")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir")
    ap.add_argument("--only")
    ap.add_argument("--label", default=platform.system())
    a = ap.parse_args()
    root = a.workdir or tempfile.mkdtemp(prefix="wp12-")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    version = subprocess.run([a.tool, "--version"], capture_output=True, text=True).stdout.strip()
    results = []
    for name, area, fn in CASES:
        if a.only and a.only not in name:
            continue
        c = Ctx(a.tool, root, name)
        started = time.time()
        error = None
        try:
            fn(c)
        except Exception:  # noqa: BLE001 - evidence must record the failure
            error = traceback.format_exc()
            c.check(False, "case raised an exception")
        ok = error is None and all(x["ok"] for x in c.checks) and bool(c.checks)
        results.append({"name": name, "area": area, "passed": ok, "checks": c.checks, "tool_invocations": c.runs,
                        "duration_ms": round((time.time() - started) * 1000), "error": error})
        print("%s %-55s %d/%d checks" % ("PASS" if ok else "FAIL", name, sum(x["ok"] for x in c.checks), len(c.checks)), flush=True)
        for x in c.checks:
            if not x["ok"]:
                print("    failed:", x["check"], flush=True)
        if error:
            print(error, flush=True)
    summary = {"cases": len(results), "passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results),
               "checks": sum(len(r["checks"]) for r in results), "checks_passed": sum(x["ok"] for r in results for x in r["checks"]),
               "tool_invocations": sum(r["tool_invocations"] for r in results), "max_peak_rss_bytes": max(PEAKS or [0]), "areas": sorted({r["area"] for r in results})}
    tool_sha = hashlib.sha256(open(a.tool, "rb").read()).hexdigest()
    evidence = {"schema": 1, "kind": "wp12-legacy-migration-scenarios", "label": a.label, "platform": platform.platform(), "python": sys.version.split()[0],
                "tool": {"path": os.path.basename(a.tool), "sha256": tool_sha, "version": version},
                "summary": summary, "cases": results}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(evidence, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(summary), flush=True)
    return 0 if summary["failed"] == 0 and summary["cases"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
