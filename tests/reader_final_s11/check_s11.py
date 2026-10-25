#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S11 persistence-failure regression for the four public import surfaces.

What is exercised, through installed packages only:

  * EXReaderSideload        exr_sideload_import_file
  * EXReaderBatchImport     reader_batch_import (with the enumerator)
  * EXReaderCloudImport     reader_cloud_download + reader_cloud_import
  * EXReaderLocalDownloads  reader_ld_remove / reader_ld_reimport / reader_ld_pending

Every row injects a real operating-system fault (read-only directory, bounded
tmpfs, changed or deleted original, cancellation through the published control
callback) and then asserts the shared private-staging and commit-boundary
contract: the exact status name, the committed/created receipt, the stored
original bytes, the untouched input file, the empty staging directory and the
absence of undeclared files or directories after a fresh-process reopen.

Nothing is simulated: a row that the platform cannot inject is recorded as
pending with the exact reason, and every assertion failure aborts the run after
writing the failing record.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reader_reviewed_composition"))
sys.path.insert(0, str(HERE))
from webdav_fixture import WebDAVFixture  # noqa: E402  (existing TLS fixture, read only)
import faultdir  # noqa: E402

MIB = 1024 * 1024
EXR_STATUS = {
    0: "OK", 1: "ARGUMENT", 2: "MEMORY", 3: "IO", 4: "ENCODING", 5: "FORMAT",
    6: "LIMIT", 7: "DATABASE", 8: "FONT", 9: "CANCELLED", 10: "PASSWORD",
    11: "UNSUPPORTED",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class Checks:
    """Named records; the first violated assertion aborts the run."""

    def __init__(self):
        self.rows = []
        self.pending = []

    def check(self, name, condition, detail=None):
        row = {"id": name, "pass": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        self.rows.append(row)
        if not condition:
            raise AssertionError(name + ": " + json.dumps(detail, default=str)[:1200])
        return row

    def equal(self, name, actual, expected):
        return self.check(name, actual == expected, {"actual": actual, "expected": expected})

    def member(self, name, actual, allowed):
        return self.check(name, actual in allowed,
                          {"actual": actual, "allowed": sorted(allowed)})

    def skip(self, name, reason):
        self.pending.append({"id": name, "reason": reason})
        return True

    def count(self):
        return len(self.rows)

    def passed(self):
        return len(self.rows)


class Probe:
    """One short-lived process per command; stdout JSON is the only channel."""

    def __init__(self, executable, logs, checks):
        self.executable = Path(executable)
        self.logs = Path(logs)
        self.checks = checks
        self.invocations = 0

    def run(self, tag, spec, allow_failure=False):
        self.invocations += 1
        path = self.logs / (tag + ".spec")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for key in sorted(spec):
                handle.write(str(key) + "=" + str(spec[key]) + "\n")
        try:
            result = subprocess.run([str(self.executable), str(path)],
                                    capture_output=True, text=True, errors="replace")
        finally:
            path.unlink()
        (self.logs / (tag + ".log")).write_text(
            "tag=" + tag + "\nexit=" + str(result.returncode) + "\nstdout:\n" +
            result.stdout + "\nstderr:\n" + result.stderr, encoding="utf-8")
        objects = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{") or not line.endswith("}"):
                continue
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if result.returncode != 0 and not allow_failure:
            raise AssertionError("probe " + tag + " exit " + str(result.returncode) +
                                 ": " + result.stderr.strip()[:600])
        if not objects:
            raise AssertionError("probe " + tag + " printed no JSON object: " +
                                 result.stderr.strip()[:600])
        return objects[-1]


def readback(probe, checks, library, folder, tag):
    folder.mkdir(parents=True, exist_ok=True)
    value = probe.run("readback-" + tag, {"cmd": "readback", "library": str(library),
                                         "out": str(folder)})
    checks.equal("readback." + tag + ".ok", value.get("ok"), 1)
    books = []
    for entry in value.get("books", []):
        dump = folder / entry["dump"]
        books.append({
            "id": entry["id"],
            "format": entry["format"],
            "bytes": entry["bytes"],
            "read_ok": entry["read_ok"],
            "title": entry["title"],
            "sha256": sha256_file(dump) if dump.is_file() else None,
        })
    checks.equal("readback." + tag + ".count", len(books), value.get("count"))
    for book in books:
        checks.equal("readback." + tag + ".read_ok." + str(book["id"]), book["read_ok"], 1)
    return value.get("count", 0), books


def inventory(root, allowed):
    """Entries under root that the row never declared."""
    root = Path(root)
    seen = set()
    for path in root.rglob("*"):
        seen.add(path.relative_to(root).as_posix())
    strays = sorted(name for name in seen if name not in allowed)
    return strays, sorted(seen)


def row_clean(checks, name, root, allowed):
    """No undeclared entry, and no stale SQLite journal, after a clean close."""
    strays, seen = inventory(root, set(allowed))
    journals = [s for s in strays if s.endswith(("-journal", "-wal", "-shm"))]
    strays = [s for s in strays if s not in journals]
    checks.check(name + ".stray", not strays, {"stray": strays, "seen": seen})
    checks.check(name + ".journal", not journals, {"journal": journals})


def empty_dir(checks, name, path):
    entries = sorted(p.name for p in Path(path).iterdir())
    checks.equal(name, entries, [])


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def fault_supported(checks, name, fault):
    """True when the platform really provided the fault; otherwise pending."""
    if fault["supported"]:
        checks.check(name + ".fault", True, fault["detail"])
        return True
    checks.skip(name, fault["detail"])
    return False


def batch_rows(ctx):
    probe, checks, fx, work, out = ctx["probe"], ctx["checks"], ctx["fixtures"], ctx["work"], ctx["output"]
    small = fx["text/small.txt"]
    large = fx["text/large.txt"]
    epub = fx["epub/sample.epub"]
    changed = fx["epub/changed.epub"]
    broken = fx["epub/broken.epub"]

    # B1: the private staging directory does not exist.
    row = work / "batch-missing"
    row.mkdir(parents=True)
    library = row / "lib.sqlite"
    value = probe.run("b1-missing", {
        "cmd": "batch", "library": str(library), "staging": str(row / "absent"),
        "count": 2, "item0": small["path"] + "|TXT|", "item1": epub["path"] + "|EPUB|"})
    checks.equal("batch.missing.status", value["status_name"], "IO")
    checks.equal("batch.missing.results", value["count"], 0)
    checks.equal("batch.missing.commits", value["commits"], 0)
    checks.check("batch.missing.not_created", not (row / "absent").exists(), str(row / "absent"))
    count, _ = readback(probe, checks, library, out / "readback" / "b1", "b1")
    checks.equal("batch.missing.books", count, 0)
    row_clean(checks, "batch.missing", row, {"lib.sqlite"})

    # B2: the staging path is a regular file.
    row = work / "batch-notdir"
    row.mkdir(parents=True)
    library = row / "lib.sqlite"
    (row / "staging-file").write_bytes(b"not a directory")
    value = probe.run("b2-notdir", {
        "cmd": "batch", "library": str(library), "staging": str(row / "staging-file"),
        "count": 1, "item0": small["path"] + "|TXT|"})
    checks.equal("batch.notdir.status", value["status_name"], "ARGUMENT")
    checks.equal("batch.notdir.results", value["count"], 0)
    count, _ = readback(probe, checks, library, out / "readback" / "b2", "b2")
    checks.equal("batch.notdir.books", count, 0)
    row_clean(checks, "batch.notdir", row, {"lib.sqlite", "staging-file"})

    # B3: an existing but read-only staging directory (real permission fault).
    row = work / "batch-readonly"
    row.mkdir(parents=True)
    library, staging = row / "lib.sqlite", row / "staging"
    staging.mkdir()
    fault = faultdir.make_readonly(staging)
    if fault_supported(checks, "batch.readonly", fault):
        value = probe.run("b3-readonly", {
            "cmd": "batch", "library": str(library), "staging": str(staging),
            "count": 2, "item0": small["path"] + "|TXT|", "item1": epub["path"] + "|EPUB|"})
        checks.equal("batch.readonly.status", value["status_name"], "OK")
        checks.equal("batch.readonly.results", value["count"], 2)
        for item in value["items"]:
            checks.equal("batch.readonly.item%d.status" % item["index"],
                         item["status"], "FAILED")
            checks.equal("batch.readonly.item%d.committed" % item["index"],
                         item["committed"], 0)
            checks.equal("batch.readonly.item%d.created" % item["index"], item["created"], 0)
            checks.equal("batch.readonly.item%d.code" % item["index"],
                         EXR_STATUS.get(item["sdk_code"]), "IO")
        empty_dir(checks, "batch.readonly.staging_empty", staging)
        count, _ = readback(probe, checks, library, out / "readback" / "b3", "b3")
        checks.equal("batch.readonly.books", count, 0)
        restored = faultdir.restore_writable(staging, fault)
        checks.check("batch.readonly.restored", restored["restored"], restored["detail"])
        row_clean(checks, "batch.readonly", row, {"lib.sqlite", "staging"})

    # B4: a genuinely bounded volume (256 KiB tmpfs) refuses the staging copy.
    row = work / "batch-nospace"
    row.mkdir(parents=True)
    library = row / "lib.sqlite"
    volume = row / "small-volume"
    fault = faultdir.mount_tmpfs(volume, 256)
    if fault_supported(checks, "batch.nospace", fault):
        try:
            value = probe.run("b4-nospace", {
                "cmd": "batch", "library": str(library), "staging": str(volume),
                "count": 1, "item0": large["path"] + "|TXT|"})
            checks.equal("batch.nospace.status", value["status_name"], "OK")
            checks.equal("batch.nospace.results", value["count"], 1)
            item = value["items"][0]
            checks.equal("batch.nospace.item.status", item["status"], "FAILED")
            checks.equal("batch.nospace.item.committed", item["committed"], 0)
            checks.equal("batch.nospace.item.code", EXR_STATUS.get(item["sdk_code"]), "IO")
            empty_dir(checks, "batch.nospace.staging_empty", volume)
            count, _ = readback(probe, checks, library, out / "readback" / "b4", "b4")
            checks.equal("batch.nospace.books", count, 0)
        finally:
            faultdir.unmount_tmpfs(volume)
        checks.equal("batch.nospace.input_sha", sha256_file(large["path"]), large["sha256"])

    # B5: the same original imports exactly once after the staging fault clears.
    row = work / "batch-retry"
    row.mkdir(parents=True)
    library, staging = row / "lib.sqlite", row / "staging"
    staging.mkdir()
    value = probe.run("b5-retry", {
        "cmd": "batch", "library": str(library), "staging": str(staging),
        "count": 1, "item0": large["path"] + "|TXT|"})
    checks.equal("batch.retry.status", value["status_name"], "OK")
    item = value["items"][0]
    checks.equal("batch.retry.item.status", item["status"], "IMPORTED")
    checks.equal("batch.retry.item.committed", item["committed"], 1)
    checks.equal("batch.retry.item.created", item["created"], 1)
    checks.check("batch.retry.item.id", item["book_id"] > 0, item["book_id"])
    empty_dir(checks, "batch.retry.staging_empty", staging)
    count, books = readback(probe, checks, library, out / "readback" / "b5", "b5")
    checks.equal("batch.retry.books", count, 1)
    checks.equal("batch.retry.sha", books[0]["sha256"], large["sha256"])
    checks.equal("batch.retry.bytes", books[0]["bytes"], large["bytes"])
    row_clean(checks, "batch.retry", row, {"lib.sqlite", "staging"})

    # B6: the original changes after enumeration; the staged copy decides.
    row = work / "batch-changed"
    source = row / "src"
    source.mkdir(parents=True)
    (source / "a.txt").write_bytes(Path(small["path"]).read_bytes())
    shutil.copyfile(epub["path"], source / "b.epub")
    scan = probe.run("b6-scan", {"cmd": "scan", "root": str(source), "recursive": 0,
                                 "batch": 8})
    checks.equal("batch.changed.scan.complete", scan["complete"], 1)
    checks.equal("batch.changed.scan.total", scan["total"], 2)
    hint = {c["relative"]: c for c in scan["candidates"]}
    checks.equal("batch.changed.scan.hint", hint["b.epub"]["size_hint"], epub["bytes"])
    shutil.copyfile(changed["path"], source / "b.epub")
    changed_sha = sha256_file(source / "b.epub")
    checks.check("batch.changed.replaced", changed_sha != epub["sha256"], changed_sha)
    library, staging = row / "lib.sqlite", row / "staging"
    staging.mkdir()
    value = probe.run("b6-import", {
        "cmd": "batch", "library": str(library), "staging": str(staging), "count": 2,
        "item0": hint["a.txt"]["path"] + "|TXT|", "item1": hint["b.epub"]["path"] + "|EPUB|"})
    checks.equal("batch.changed.status", value["status_name"], "OK")
    checks.equal("batch.changed.committed",
                 [i["committed"] for i in value["items"]], [1, 1])
    checks.equal("batch.changed.created", [i["created"] for i in value["items"]], [1, 1])
    empty_dir(checks, "batch.changed.staging_empty", staging)
    count, books = readback(probe, checks, library, out / "readback" / "b6", "b6")
    checks.equal("batch.changed.books", count, 2)
    checks.equal("batch.changed.stored_shas", sorted(b["sha256"] for b in books),
                 sorted([small["sha256"], changed_sha]))
    checks.check("batch.changed.hint_not_trusted",
                 epub["bytes"] not in [b["bytes"] for b in books],
                 {"hint": epub["bytes"], "stored": [b["bytes"] for b in books]})
    checks.equal("batch.changed.source_untouched", sha256_file(source / "b.epub"), changed_sha)
    row_clean(checks, "batch.changed", row, {"lib.sqlite", "staging", "src", "src/a.txt",
                                             "src/b.epub"})

    # B7: corrupt and oversized originals keep their state; the valid row commits.
    row = work / "batch-rejects"
    row.mkdir(parents=True)
    library, staging = row / "lib.sqlite", row / "staging"
    staging.mkdir()
    before = {name: sha256_file(fx[name]["path"]) for name in
              ("text/small.txt", "epub/broken.epub", "text/large.txt")}
    value = probe.run("b7-rejects", {
        "cmd": "batch", "library": str(library), "staging": str(staging), "count": 3,
        "max_input": ctx["oversize_limit"],
        "item0": small["path"] + "|TXT|", "item1": broken["path"] + "|EPUB|",
        "item2": large["path"] + "|TXT|"})
    checks.equal("batch.rejects.status", value["status_name"], "OK")
    items = {item["index"]: item for item in value["items"]}
    checks.equal("batch.rejects.valid.status", items[0]["status"], "IMPORTED")
    checks.equal("batch.rejects.valid.committed", items[0]["committed"], 1)
    checks.equal("batch.rejects.valid.created", items[0]["created"], 1)
    checks.equal("batch.rejects.corrupt.status", items[1]["status"], "FAILED")
    checks.equal("batch.rejects.corrupt.committed", items[1]["committed"], 0)
    checks.equal("batch.rejects.corrupt.code", EXR_STATUS.get(items[1]["sdk_code"]),
                 "FORMAT")
    checks.equal("batch.rejects.oversize.status", items[2]["status"], "FAILED")
    checks.equal("batch.rejects.oversize.committed", items[2]["committed"], 0)
    checks.equal("batch.rejects.oversize.code", EXR_STATUS.get(items[2]["sdk_code"]),
                 "LIMIT")
    after = {name: sha256_file(fx[name]["path"]) for name in before}
    checks.equal("batch.rejects.inputs_unchanged", after, before)
    empty_dir(checks, "batch.rejects.staging_empty", staging)
    count, books = readback(probe, checks, library, out / "readback" / "b7", "b7")
    checks.equal("batch.rejects.books", count, 1)
    checks.equal("batch.rejects.sha", books[0]["sha256"], small["sha256"])
    row_clean(checks, "batch.rejects", row, {"lib.sqlite", "staging"})

    # B8: interruption keeps the committed item and stops only the later ones.
    row = work / "batch-cancel"
    source = row / "src"
    source.mkdir(parents=True)
    (source / "a.txt").write_bytes(Path(small["path"]).read_bytes())
    write_text(source / "b.txt", "s11 cancel row second original\n")
    write_text(source / "c.txt", "s11 cancel row third original\n")
    library, staging = row / "lib.sqlite", row / "staging"
    staging.mkdir()
    items = {name: str(source / name) + "|TXT|" for name in ("a.txt", "b.txt", "c.txt")}
    value = probe.run("b8-cancel", {
        "cmd": "batch", "library": str(library), "staging": str(staging), "count": 3,
        "cancel_after_commits": 1, **{"item" + str(i): items[name]
                                      for i, name in enumerate(("a.txt", "b.txt", "c.txt"))}})
    checks.equal("batch.cancel.status", value["status_name"], "CANCELLED")
    checks.equal("batch.cancel.items",
                 [i["status"] for i in value["items"]],
                 ["IMPORTED", "CANCELLED", "CANCELLED"])
    checks.equal("batch.cancel.committed",
                 [i["committed"] for i in value["items"]], [1, 0, 0])
    empty_dir(checks, "batch.cancel.staging_empty", staging)
    count, books = readback(probe, checks, library, out / "readback" / "b8", "b8")
    checks.equal("batch.cancel.books", count, 1)
    checks.equal("batch.cancel.sha", books[0]["sha256"], small["sha256"])
    value = probe.run("b8-retry", {
        "cmd": "batch", "library": str(library), "staging": str(staging), "count": 2,
        "item0": items["b.txt"], "item1": items["c.txt"]})
    checks.equal("batch.cancel.retry.status", value["status_name"], "OK")
    checks.equal("batch.cancel.retry.committed",
                 [i["committed"] for i in value["items"]], [1, 1])
    count, books = readback(probe, checks, library, out / "readback" / "b8-retry", "b8r")
    checks.equal("batch.cancel.retry.books", count, 3)
    checks.equal("batch.cancel.committed_not_revoked", small["sha256"] in
                 [b["sha256"] for b in books])
    row_clean(checks, "batch.cancel", row,
              {"lib.sqlite", "staging", "src", "src/a.txt", "src/b.txt", "src/c.txt"})


def cloud_rows(ctx):
    probe, checks, fx, work, out = ctx["probe"], ctx["checks"], ctx["fixtures"], ctx["work"], ctx["output"]
    url, auth = ctx["url"], ctx["auth"]
    epub = fx["epub/sample.epub"]
    large = fx["text/large.txt"]

    def spec(row, resource, name, fmt, expected, **extra):
        value = {"cmd": "cloud", "root": url, "auth": auth, "resource": resource,
                 "name": name, "format": fmt, "staging": str(row / "staging"),
                 "expected": expected, "library": str(row / "lib.sqlite"),
                 "title": "S11 cloud"}
        value.update(extra)
        return value

    # C1: one published staging file, one commit, exact stored bytes.
    row = work / "cloud-ok"
    row.mkdir(parents=True)
    (row / "staging").mkdir()
    value = probe.run("c1-ok", spec(row, "books/book.epub", "book.epub", "EPUB", epub["bytes"]))
    checks.equal("cloud.ok.create", value["create"], 0)
    checks.equal("cloud.ok.download", value["download"], "ok")
    checks.equal("cloud.ok.staged", value["staged"], 1)
    checks.equal("cloud.ok.staged_sha", value["staged_sha"], epub["sha256"])
    checks.equal("cloud.ok.staged_bytes", value["staged_bytes"], epub["bytes"])
    checks.equal("cloud.ok.import", value["import"], "ok")
    checks.equal("cloud.ok.committed", value["committed"], 1)
    checks.equal("cloud.ok.created", value["created"], 1)
    checks.check("cloud.ok.book_id", value["book_id"] > 0, value["book_id"])
    checks.equal("cloud.ok.staging_removed", value["staging_removed"], 1)
    checks.equal("cloud.ok.consumed", value["consumed"], 1)
    checks.equal("cloud.ok.file_after", value["file_after"], 0)
    empty_dir(checks, "cloud.ok.staging_empty", row / "staging")
    count, books = readback(probe, checks, row / "lib.sqlite", out / "readback" / "c1", "c1")
    checks.equal("cloud.ok.books", count, 1)
    checks.equal("cloud.ok.sha", books[0]["sha256"], epub["sha256"])
    checks.equal("cloud.ok.bytes", books[0]["bytes"], epub["bytes"])
    row_clean(checks, "cloud.ok", row, {"lib.sqlite", "staging"})

    # C2: the private staging directory does not exist.
    row = work / "cloud-missing"
    row.mkdir(parents=True)
    value = probe.run("c2-missing", spec(row, "books/book.epub", "book.epub", "EPUB",
                                         epub["bytes"]))
    checks.equal("cloud.missing.download", value["download"], "io")
    checks.equal("cloud.missing.staged", value["staged"], 0)
    checks.check("cloud.missing.no_import", "import" not in value, value)
    checks.check("cloud.missing.not_created", not (row / "staging").exists(),
                 str(row / "staging"))
    count, _ = readback(probe, checks, row / "lib.sqlite", out / "readback" / "c2", "c2")
    checks.equal("cloud.missing.books", count, 0)
    row_clean(checks, "cloud.missing", row, {"lib.sqlite"})

    # C3: a read-only staging directory.
    row = work / "cloud-readonly"
    row.mkdir(parents=True)
    (row / "staging").mkdir()
    fault = faultdir.make_readonly(row / "staging")
    if fault_supported(checks, "cloud.readonly", fault):
        value = probe.run("c3-readonly", spec(row, "books/book.epub", "book.epub",
                                              "EPUB", epub["bytes"]))
        checks.equal("cloud.readonly.download", value["download"], "io")
        checks.equal("cloud.readonly.staged", value["staged"], 0)
        empty_dir(checks, "cloud.readonly.staging_empty", row / "staging")
        count, _ = readback(probe, checks, row / "lib.sqlite", out / "readback" / "c3", "c3")
        checks.equal("cloud.readonly.books", count, 0)
        restored = faultdir.restore_writable(row / "staging", fault)
        checks.check("cloud.readonly.restored", restored["restored"], restored["detail"])
        row_clean(checks, "cloud.readonly", row, {"lib.sqlite", "staging"})

    # C4: a bounded volume ends the download without a published file.
    row = work / "cloud-nospace"
    row.mkdir(parents=True)
    volume = row / "small-volume"
    fault = faultdir.mount_tmpfs(volume, 256)
    if fault_supported(checks, "cloud.nospace", fault):
        try:
            value = probe.run("c4-nospace", spec(row, "books/large.txt", "large.txt",
                                                 "TXT", large["bytes"]))
            checks.equal("cloud.nospace.download", value["download"], "io")
            checks.equal("cloud.nospace.staged", value["staged"], 0)
            empty_dir(checks, "cloud.nospace.staging_empty", volume)
            count, _ = readback(probe, checks, row / "lib.sqlite",
                                out / "readback" / "c4", "c4")
            checks.equal("cloud.nospace.books", count, 0)
        finally:
            faultdir.unmount_tmpfs(volume)
        checks.equal("cloud.nospace.input_sha", sha256_file(large["path"]), large["sha256"])

    # C5/C6: the staged bytes change between the two phases.
    for tag, tamper in (("c5-flip", "flip"), ("c6-truncate", "truncate")):
        row = work / ("cloud-" + tamper)
        row.mkdir(parents=True)
        (row / "staging").mkdir()
        value = probe.run(tag, spec(row, "books/book.epub", "book.epub", "EPUB",
                                    epub["bytes"], tamper=tamper))
        checks.equal("cloud." + tamper + ".download", value["download"], "ok")
        checks.equal("cloud." + tamper + ".tamper_ok", value["tamper_ok"], 1)
        checks.equal("cloud." + tamper + ".import", value["import"], "corrupt")
        checks.equal("cloud." + tamper + ".committed", value["committed"], 0)
        checks.equal("cloud." + tamper + ".created", value["created"], 0)
        checks.equal("cloud." + tamper + ".staging_removed", value["staging_removed"], 1)
        checks.equal("cloud." + tamper + ".consumed", value["consumed"], 1)
        checks.equal("cloud." + tamper + ".file_after", value["file_after"], 0)
        empty_dir(checks, "cloud." + tamper + ".staging_empty", row / "staging")
        count, _ = readback(probe, checks, row / "lib.sqlite",
                            out / "readback" / tamper, tamper)
        checks.equal("cloud." + tamper + ".books", count, 0)
        row_clean(checks, "cloud." + tamper, row, {"lib.sqlite", "staging"})

    # C7: cancellation during the transfer leaves no staging file.
    row = work / "cloud-cancel-net"
    row.mkdir(parents=True)
    (row / "staging").mkdir()
    value = probe.run("c7-cancel", spec(row, "books/large.txt", "large.txt", "TXT",
                                       large["bytes"], cancel_net=2))
    checks.equal("cloud.cancel.download", value["download"], "cancelled")
    checks.equal("cloud.cancel.staged", value["staged"], 0)
    empty_dir(checks, "cloud.cancel.staging_empty", row / "staging")
    count, _ = readback(probe, checks, row / "lib.sqlite", out / "readback" / "c7", "c7")
    checks.equal("cloud.cancel.books", count, 0)
    row_clean(checks, "cloud.cancel", row, {"lib.sqlite", "staging"})

    # C8: cancellation before the SDK commit removes the staging file only.
    row = work / "cloud-cancel-import"
    row.mkdir(parents=True)
    (row / "staging").mkdir()
    value = probe.run("c8-cancel-import", spec(row, "books/book.epub", "book.epub",
                                               "EPUB", epub["bytes"],
                                               cancel_import_poll=1))
    checks.equal("cloud.cancel_import.download", value["download"], "ok")
    checks.equal("cloud.cancel_import.import", value["import"], "cancelled")
    checks.equal("cloud.cancel_import.committed", value["committed"], 0)
    checks.equal("cloud.cancel_import.staging_removed", value["staging_removed"], 1)
    checks.equal("cloud.cancel_import.consumed", value["consumed"], 1)
    checks.equal("cloud.cancel_import.file_after", value["file_after"], 0)
    empty_dir(checks, "cloud.cancel_import.staging_empty", row / "staging")
    count, _ = readback(probe, checks, row / "lib.sqlite", out / "readback" / "c8", "c8")
    checks.equal("cloud.cancel_import.books", count, 0)
    row_clean(checks, "cloud.cancel_import", row, {"lib.sqlite", "staging"})


def sideload_rows(ctx):
    probe, checks, fx, work, out = ctx["probe"], ctx["checks"], ctx["fixtures"], ctx["work"], ctx["output"]
    small, large = fx["text/small.txt"], fx["text/large.txt"]
    epub, pdf = fx["epub/sample.epub"], fx["pdf/public-text.pdf"]

    # S1: the baseline commit.
    row = work / "sideload-ok"
    row.mkdir(parents=True)
    value = probe.run("s1-ok", {"cmd": "import", "library": str(row / "lib.sqlite"),
                               "file": epub["path"], "format": "EPUB",
                               "title": "S11 sideload"})
    checks.equal("sideload.ok.status", value["status_name"], "OK")
    checks.equal("sideload.ok.created", value["created"], 1)
    checks.check("sideload.ok.book_id", value["book_id"] > 0, value["book_id"])
    count, books = readback(probe, checks, row / "lib.sqlite", out / "readback" / "s1", "s1")
    checks.equal("sideload.ok.books", count, 1)
    checks.equal("sideload.ok.sha", books[0]["sha256"], epub["sha256"])
    checks.equal("sideload.ok.bytes", books[0]["bytes"], epub["bytes"])
    row_clean(checks, "sideload.ok", row, {"lib.sqlite"})

    # S2: cancellation before any copy.
    row = work / "sideload-cancel-before"
    row.mkdir(parents=True)
    value = probe.run("s2-cancel", {"cmd": "import", "library": str(row / "lib.sqlite"),
                                   "file": small["path"], "format": "TXT",
                                   "title": "S11 cancel", "cancel_at": 1})
    checks.equal("sideload.cancel_before.status", value["status_name"], "CANCELLED")
    checks.equal("sideload.cancel_before.book_id", value["book_id"], 0)
    checks.equal("sideload.cancel_before.created", value["created"], 0)
    count, _ = readback(probe, checks, row / "lib.sqlite",
                        out / "readback" / "s2", "s2")
    checks.equal("sideload.cancel_before.books", count, 0)
    row_clean(checks, "sideload.cancel_before", row, {"lib.sqlite"})

    # S3: cancellation in the middle of the bounded copy.
    row = work / "sideload-cancel-mid"
    row.mkdir(parents=True)
    value = probe.run("s3-cancel-mid", {"cmd": "import", "library": str(row / "lib.sqlite"),
                                        "file": large["path"], "format": "TXT",
                                        "title": "S11 large cancel", "cancel_at": 5})
    checks.equal("sideload.cancel_mid.status", value["status_name"], "CANCELLED")
    checks.equal("sideload.cancel_mid.book_id", value["book_id"], 0)
    checks.check("sideload.cancel_mid.polls", value["polls"] >= 5, value["polls"])
    count, _ = readback(probe, checks, row / "lib.sqlite",
                        out / "readback" / "s3", "s3")
    checks.equal("sideload.cancel_mid.books", count, 0)
    row_clean(checks, "sideload.cancel_mid", row, {"lib.sqlite"})

    # S4: the PDF entry cannot be interrupted inside the SDK; it is refused first.
    row = work / "sideload-pdf-cancel"
    row.mkdir(parents=True)
    value = probe.run("s4-pdf-cancel", {"cmd": "import", "library": str(row / "lib.sqlite"),
                                        "file": pdf["path"], "format": "PDF",
                                        "title": "S11 pdf", "cancel_at": 1})
    checks.equal("sideload.pdf_cancel.status", value["status_name"], "CANCELLED")
    checks.equal("sideload.pdf_cancel.book_id", value["book_id"], 0)
    count, _ = readback(probe, checks, row / "lib.sqlite",
                        out / "readback" / "s4", "s4")
    checks.equal("sideload.pdf_cancel.books", count, 0)
    row_clean(checks, "sideload.pdf_cancel", row, {"lib.sqlite"})

    # S5: the original changes after the commit; the stored copy stays exact.
    row = work / "sideload-mutated"
    row.mkdir(parents=True)
    source = row / "src.epub"
    shutil.copyfile(epub["path"], source)
    value = probe.run("s5-import", {"cmd": "import", "library": str(row / "lib.sqlite"),
                                    "file": str(source), "format": "EPUB",
                                    "title": "S11 mutated"})
    checks.equal("sideload.mutated.status", value["status_name"], "OK")
    checks.equal("sideload.mutated.created", value["created"], 1)
    with open(source, "ab") as handle:
        handle.write(b"S11 post-commit mutation of the caller's original\n")
    mutated = sha256_file(source)
    checks.check("sideload.mutated.file_changed", mutated != epub["sha256"], mutated)
    count, books = readback(probe, checks, row / "lib.sqlite",
                            out / "readback" / "s5", "s5")
    checks.equal("sideload.mutated.books", count, 1)
    checks.equal("sideload.mutated.stored_sha", books[0]["sha256"], epub["sha256"])
    checks.equal("sideload.mutated.stored_bytes", books[0]["bytes"], epub["bytes"])
    row_clean(checks, "sideload.mutated", row, {"lib.sqlite", "src.epub"})

    # S6: the library volume itself runs out of space; the commit rolls back.
    row = work / "sideload-nospace"
    row.mkdir(parents=True)
    base = row / "base.sqlite"
    readback(probe, checks, base, out / "readback" / "s6-base", "s6base")
    volume = row / "small-volume"
    fault = faultdir.mount_tmpfs(volume, 512)
    if fault_supported(checks, "sideload.nospace", fault):
        try:
            target = volume / "lib.sqlite"
            shutil.copyfile(base, target)
            value = probe.run("s6-nospace", {"cmd": "import", "library": str(target),
                                             "file": large["path"], "format": "TXT",
                                             "title": "S11 no space"})
            checks.member("sideload.nospace.status", value["status_name"],
                          {"IO", "DATABASE"})
            checks.equal("sideload.nospace.book_id", value["book_id"], 0)
            checks.equal("sideload.nospace.created", value["created"], 0)
            count, _ = readback(probe, checks, target, out / "readback" / "s6-a", "s6a")
            checks.equal("sideload.nospace.books_after_reopen", count, 0)
            grown = faultdir.remount_tmpfs(volume, 64 * 1024)
            checks.check("sideload.nospace.remount", grown["ok"], grown["detail"])
            value = probe.run("s6-retry", {"cmd": "import", "library": str(target),
                                           "file": large["path"], "format": "TXT",
                                           "title": "S11 no space retry"})
            checks.equal("sideload.nospace.retry.status", value["status_name"], "OK")
            checks.equal("sideload.nospace.retry.created", value["created"], 1)
            count, books = readback(probe, checks, target,
                                    out / "readback" / "s6-b", "s6b")
            checks.equal("sideload.nospace.retry.books", count, 1)
            checks.equal("sideload.nospace.retry.sha", books[0]["sha256"], large["sha256"])
            checks.equal("sideload.nospace.retry.bytes", books[0]["bytes"], large["bytes"])
        finally:
            faultdir.unmount_tmpfs(volume)
        checks.equal("sideload.nospace.input_sha", sha256_file(large["path"]), large["sha256"])


def ld_setup(ctx, tag, fixture_name, fmt_name, extension, title):
    probe, checks, fx, work = ctx["probe"], ctx["checks"], ctx["fixtures"], ctx["work"]
    row = work / tag
    row.mkdir(parents=True)
    state = row / "state"
    state.mkdir()
    source = row / ("book." + extension)
    shutil.copyfile(fx[fixture_name]["path"], source)
    digest = sha256_file(source)
    size = source.stat().st_size
    value = probe.run(tag + "-setup", {
        "cmd": "ld-setup", "work": str(row), "file": str(source), "format": fmt_name,
        "title": title, "sha": digest, "bytes": size})
    checks.check(tag + ".setup.id", value["id"] > 0, value)
    return {"row": row, "state": state, "source": source, "sha": digest, "size": size,
            "id": value["id"], "key": fmt_name.lower() + ":" + digest}


def ld_call(probe, tag, command, row, **extra):
    spec = {"cmd": command, "work": str(row)}
    spec.update(extra)
    return probe.run(tag, spec)


def ld_catalog(probe, tag, row, key):
    return probe.run(tag + "-catalog", {"cmd": "ld-query", "work": str(row), "key": key})


def ld_pending(probe, tag, state):
    return probe.run(tag + "-pending", {"cmd": "ld-pending", "state": str(state)})


def state_files(state):
    return sorted(path.name for path in Path(state).rglob("*") if path.is_file())


def ld_rows(ctx):
    probe, checks, out = ctx["probe"], ctx["checks"], ctx["output"]

    # L1: the baseline local mapping and its readable stored original.
    case = ld_setup(ctx, "ld-basic", "epub/sample.epub", "EPUB", "epub",
                    "S11 local downloads")
    row, key = case["row"], case["key"]
    catalog = ld_catalog(probe, "l1", row, key)
    checks.equal("ld.basic.catalog.found", catalog["found"], 1)
    checks.equal("ld.basic.catalog.mapped", catalog["mapped"], case["id"])
    checks.equal("ld.basic.catalog.local", catalog["local"], 1)
    pending = ld_pending(probe, "l1", case["state"])
    checks.equal("ld.basic.pending", pending["pending"], 0)
    count, books = readback(probe, checks, row / "sdk.db", out / "readback" / "l1", "l1")
    checks.equal("ld.basic.books", count, 1)
    checks.equal("ld.basic.sha", books[0]["sha256"], case["sha"])
    row_clean(checks, "ld.basic", row,
              {"sdk.db", "catalog.db", "state", "book.epub"})

    # L2: the private state directory does not exist.
    case = ld_setup(ctx, "ld-state-missing", "cbz/comic.cbz", "CBZ", "cbz",
                    "S11 missing state")
    row, key = case["row"], case["key"]
    value = ld_call(probe, "l2-remove", "ld-remove", row, key=key,
                    state=str(row / "absent"))
    checks.equal("ld.missing.status", value["status"], "io")
    checks.equal("ld.missing.removed", value["removed"], 0)
    checks.check("ld.missing.state_not_created", not (row / "absent").exists(),
                 str(row / "absent"))
    catalog = ld_catalog(probe, "l2", row, key)
    checks.equal("ld.missing.catalog.local", catalog["local"], 1)
    count, books = readback(probe, checks, row / "sdk.db", out / "readback" / "l2", "l2")
    checks.equal("ld.missing.books", count, 1)
    checks.equal("ld.missing.sha", books[0]["sha256"], case["sha"])
    row_clean(checks, "ld.missing", row, {"sdk.db", "catalog.db", "state", "book.cbz"})

    # L3: a read-only state directory refuses before any destructive step.
    case = ld_setup(ctx, "ld-state-readonly", "epub/sample.epub", "EPUB", "epub",
                    "S11 read-only state")
    row, key, state = case["row"], case["key"], case["state"]
    fault = faultdir.make_readonly(state)
    if fault_supported(checks, "ld.readonly", fault):
        value = ld_call(probe, "l3-remove-blocked", "ld-remove", row, key=key,
                        state=str(state))
        checks.equal("ld.readonly.status", value["status"], "io")
        checks.equal("ld.readonly.removed", value["removed"], 0)
        checks.equal("ld.readonly.outcome", value["outcome"], "none")
        checks.equal("ld.readonly.no_files", state_files(state), [])
        catalog = ld_catalog(probe, "l3", row, key)
        checks.equal("ld.readonly.catalog.local", catalog["local"], 1)
        count, books = readback(probe, checks, row / "sdk.db",
                                out / "readback" / "l3", "l3")
        checks.equal("ld.readonly.books", count, 1)
        checks.equal("ld.readonly.sha", books[0]["sha256"], case["sha"])
        restored = faultdir.restore_writable(state, fault)
        checks.check("ld.readonly.restored", restored["restored"], restored["detail"])
        value = ld_call(probe, "l3-remove", "ld-remove", row, key=key, state=str(state))
        checks.equal("ld.readonly.retry.status", value["status"], "ok")
        checks.equal("ld.readonly.retry.outcome", value["outcome"], "removed")
        checks.check("ld.readonly.retry.removed", value["removed"] >= 1, value["removed"])
        count, _ = readback(probe, checks, row / "sdk.db",
                            out / "readback" / "l3-after", "l3a")
        checks.equal("ld.readonly.retry.books", count, 0)
        catalog = ld_catalog(probe, "l3-after", row, key)
        checks.equal("ld.readonly.retry.catalog.found", catalog["found"], 1)
        checks.equal("ld.readonly.retry.catalog.local", catalog["local"], 0)
        checks.equal("ld.readonly.retry.no_files", state_files(state), [])
        pending = ld_pending(probe, "l3", state)
        checks.equal("ld.readonly.retry.pending", pending["pending"], 0)
        row_clean(checks, "ld.readonly", row,
                  {"sdk.db", "catalog.db", "state", "state/originals", "book.epub"})

    # L4: a read-only state directory refuses the reimport staging copy.
    case = ld_setup(ctx, "ld-reimport", "epub/sample.epub", "EPUB", "epub",
                    "S11 reimport")
    row, key, state, source = case["row"], case["key"], case["state"], case["source"]
    value = ld_call(probe, "l4-remove", "ld-remove", row, key=key, state=str(state))
    checks.equal("ld.reimport.detach.status", value["status"], "ok")
    checks.equal("ld.reimport.detach.outcome", value["outcome"], "removed")
    count, _ = readback(probe, checks, row / "sdk.db",
                        out / "readback" / "l4-detach", "l4d")
    checks.equal("ld.reimport.detach.books", count, 0)
    fault = faultdir.make_readonly(state)
    if fault_supported(checks, "ld.reimport", fault):
        value = ld_call(probe, "l4-reimport-blocked", "ld-reimport", row, key=key,
                        state=str(state), file=str(source))
        checks.equal("ld.reimport.status", value["status"], "io")
        checks.equal("ld.reimport.removed", value["removed"], 0)
        checks.equal("ld.reimport.no_files", state_files(state), [])
        count, _ = readback(probe, checks, row / "sdk.db",
                            out / "readback" / "l4-blocked", "l4b")
        checks.equal("ld.reimport.books", count, 0)
        catalog = ld_catalog(probe, "l4", row, key)
        checks.equal("ld.reimport.catalog.local", catalog["local"], 0)
        restored = faultdir.restore_writable(state, fault)
        checks.check("ld.reimport.restored", restored["restored"], restored["detail"])
        value = ld_call(probe, "l4-reimport", "ld-reimport", row, key=key,
                        state=str(state), file=str(source))
        checks.equal("ld.reimport.retry.status", value["status"], "ok")
        checks.equal("ld.reimport.retry.outcome", value["outcome"], "attached")
        checks.check("ld.reimport.retry.id", value["id"] > 0, value["id"])
        count, books = readback(probe, checks, row / "sdk.db",
                                out / "readback" / "l4-after", "l4a")
        checks.equal("ld.reimport.retry.books", count, 1)
        checks.equal("ld.reimport.retry.sha", books[0]["sha256"], case["sha"])
        catalog = ld_catalog(probe, "l4-after", row, key)
        checks.equal("ld.reimport.retry.catalog.local", catalog["local"], 1)
        row_clean(checks, "ld.reimport", row,
                  {"sdk.db", "catalog.db", "state", "state/originals",
                   "state/originals/" + case["sha"] + ".orig", "book.epub"})

    # L5: cancellation before the first durable step.
    case = ld_setup(ctx, "ld-cancel-before", "epub/sample.epub", "EPUB", "epub",
                    "S11 cancel before")
    row, key, state = case["row"], case["key"], case["state"]
    value = ld_call(probe, "l5-remove", "ld-remove", row, key=key, state=str(state),
                    cancel_at_poll=1)
    checks.equal("ld.cancel_before.status", value["status"], "cancelled")
    checks.equal("ld.cancel_before.removed", value["removed"], 0)
    checks.equal("ld.cancel_before.stages", value["stages"], 0)
    catalog = ld_catalog(probe, "l5", row, key)
    checks.equal("ld.cancel_before.catalog.local", catalog["local"], 1)
    count, books = readback(probe, checks, row / "sdk.db",
                            out / "readback" / "l5", "l5")
    checks.equal("ld.cancel_before.books", count, 1)
    checks.equal("ld.cancel_before.sha", books[0]["sha256"], case["sha"])
    pending = ld_pending(probe, "l5", state)
    checks.equal("ld.cancel_before.pending", pending["pending"], 0)
    checks.equal("ld.cancel_before.no_files", state_files(state), [])
    row_clean(checks, "ld.cancel_before", row,
              {"sdk.db", "catalog.db", "state", "book.epub"})

    # L6: cancellation after the BEGUN record; recover leaves both databases intact.
    case = ld_setup(ctx, "ld-cancel-begun", "epub/sample.epub", "EPUB", "epub",
                    "S11 cancel begun")
    row, key, state = case["row"], case["key"], case["state"]
    value = ld_call(probe, "l6-remove", "ld-remove", row, key=key, state=str(state),
                    cancel_at="begun")
    checks.equal("ld.cancel_begun.status", value["status"], "cancelled")
    checks.equal("ld.cancel_begun.removed", value["removed"], 0)
    checks.equal("ld.cancel_begun.stage_seen", "begun" in value["stage_list"],
                 value["stage_list"])
    catalog = ld_catalog(probe, "l6", row, key)
    checks.equal("ld.cancel_begun.catalog.local", catalog["local"], 1)
    count, books = readback(probe, checks, row / "sdk.db",
                            out / "readback" / "l6", "l6")
    checks.equal("ld.cancel_begun.books", count, 1)
    checks.equal("ld.cancel_begun.sha", books[0]["sha256"], case["sha"])
    value = ld_call(probe, "l6-recover", "ld-recover", row, key=key, state=str(state))
    checks.equal("ld.cancel_begun.recover.status", value["status"], "ok")
    checks.member("ld.cancel_begun.recover.outcome", value["outcome"],
                  {"rolled_back", "nothing_pending"})
    pending = ld_pending(probe, "l6", state)
    checks.equal("ld.cancel_begun.recover.pending", pending["pending"], 0)
    checks.equal("ld.cancel_begun.recover.no_files", state_files(state), [])
    catalog = ld_catalog(probe, "l6-after", row, key)
    checks.equal("ld.cancel_begun.recover.catalog.local", catalog["local"], 1)
    count, books = readback(probe, checks, row / "sdk.db",
                            out / "readback" / "l6-after", "l6a")
    checks.equal("ld.cancel_begun.recover.books", count, 1)
    checks.equal("ld.cancel_begun.recover.sha", books[0]["sha256"], case["sha"])
    row_clean(checks, "ld.cancel_begun", row,
              {"sdk.db", "catalog.db", "state", "state/originals", "book.epub"})


def main():
    import platform
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--module-prefix", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true", "S11 runs in Actions only"
    probe_path = args.probe.resolve()
    fixtures_dir = args.fixtures.resolve()
    work = args.work.resolve()
    output = args.output.resolve()
    prefix = args.module_prefix.resolve()
    # The two writable roots are recreated per run; refuse anything that is not
    # this package's own build directory.
    for root in (work, output):
        assert "s11" in root.name.lower(), "refusing to clean " + str(root)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    checks = Checks()
    probe = Probe(probe_path, logs, checks)
    data = json.loads((fixtures_dir / "fixtures.json").read_text(encoding="utf-8"))
    assert (prefix / "include/reader_cloud_import.h").is_file(), str(prefix)
    installed = {}
    for path in sorted(prefix.rglob("*")):
        if path.is_file():
            installed[path.relative_to(prefix).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    ctx = {"probe": probe, "checks": checks, "fixtures": data["files"], "work": work,
           "output": output, "oversize_limit": data["oversize_limit"],
           "fixtures_dir": Path(data["root"])}
    environment = {
        "platform": sys.platform,
        "python": platform.python_version(),
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "sdk_version_expected": "3.41.0",
    }
    fixture = None
    failure = None
    accepted = False
    try:
        fixture = WebDAVFixture(output / "webdav-certificates")
        fixture.start()
        fixture.entries["/dav/books/book.epub"] = Path(
            data["files"]["epub/sample.epub"]["path"]).read_bytes()
        fixture.entries["/dav/books/large.txt"] = Path(
            data["files"]["text/large.txt"]["path"]).read_bytes()
        ctx["url"] = fixture.root_url()
        ctx["auth"] = fixture.authorization
        for name, row in (("batch", batch_rows), ("cloud", cloud_rows),
                          ("sideload", sideload_rows), ("local-downloads", ld_rows)):
            before = checks.count()
            row(ctx)
            print("S11 group " + name + ": " + str(checks.count() - before) +
                  " checks passed", flush=True)
        fixture.assert_secret_free(output)
        accepted = True
    except BaseException as exc:  # record even a hard abort, then re-raise
        failure = {"type": type(exc).__name__, "message": str(exc)[:4000]}
        raise
    finally:
        if fixture is not None:
            fixture.stop()
        report = {
            "package": "S11 persistence-failure regression",
            "accepted": accepted,
            "checks": checks.rows,
            "check_count": checks.count(),
            "pending": checks.pending,
            "failure": failure,
            "environment": environment,
            "probe": {"path": str(probe_path), "sha256": sha256_file(probe_path)},
            "invocations": probe.invocations,
            "installed_prefix": installed,
            "fixtures": data["files"],
        }
        (output / "result.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")
        summary = {
            "accepted": accepted,
            "checks": checks.count(),
            "pending": checks.pending,
            "failure": failure,
            "source_sha": environment["source_sha"],
            "run_id": environment["run_id"],
            "attempt": environment["attempt"],
            "job": environment["job"],
            "runner_os": environment["runner_os"],
        }
        print("S11_STRICT_SUMMARY " + json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())




