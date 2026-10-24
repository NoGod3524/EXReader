#!/usr/bin/env python3
"""Cloud acceptance for EXReaderBatchImport.

The C probe uses only the installed public header, the installed EXReader
library and the installed EXReaderSideload package. This script creates the
scenario, drives both independent phases, and checks exact bytes and metadata.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys

EXR_OK = 0
EXR_IO = 3
EXR_FORMAT = 5
EXR_LIMIT = 6
EXR_CANCELLED = 9


class CheckFailure(RuntimeError):
    pass


class Checks:
    def __init__(self):
        self.items = []
        self.failures = []

    def check(self, name, condition, detail=""):
        ok = bool(condition)
        self.items.append({"name": name, "ok": ok, "detail": str(detail)})
        if not ok:
            self.failures.append(name)
        return ok

    def equal(self, name, actual, expected):
        return self.check(name, actual == expected,
                          "actual={!r} expected={!r}".format(actual, expected))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(command, expect=0):
    process = subprocess.run(command, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if process.returncode != expect:
        raise CheckFailure("command failed ({}): {}\nstdout:\n{}\nstderr:\n{}"
                           .format(process.returncode, " ".join(command),
                                   process.stdout, process.stderr))
    return process


def load_tsv(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    return rows


def parse_scan(path):
    meta = {}
    candidates = {}
    for row in load_tsv(path):
        if row[0] == "candidate":
            candidates[row[3]] = {
                "format": row[1],
                "size_hint": int(row[2]),
                "relative": row[3],
                "path": row[4],
            }
        else:
            meta[row[0]] = row[1:]
    return meta, candidates


def parse_import(path):
    meta = {}
    results = []
    originals = []
    for row in load_tsv(path):
        if row[0] == "result":
            results.append({
                "index": int(row[1]),
                "status": row[2],
                "committed": int(row[3]),
                "created": int(row[4]),
                "book_id": int(row[5]),
                "format": row[6],
                "relative": row[7],
                "status_code": int(row[8]),
                "message": row[9] if len(row) > 9 else "",
            })
        elif row[0] == "original":
            originals.append({
                "book_id": int(row[1]),
                "path": row[2],
                "bytes": int(row[3]),
            })
        else:
            meta.setdefault(row[0], []).append(row[1:])
    return meta, results, originals


def parse_books(path):
    meta = {}
    books = {}
    for row in load_tsv(path):
        if row[0] == "book":
            books[int(row[1])] = {
                "id": int(row[1]),
                "format": row[2],
                "title": row[3],
                "author": row[4],
                "favorite": int(row[5]),
                "status": int(row[6]),
                "position": int(row[7]),
            }
        else:
            meta[row[0]] = row[1:]
    return meta, books


def parse_kv(path):
    meta = {}
    for row in load_tsv(path):
        meta.setdefault(row[0], []).append(row[1:])
    return meta


def write_subset_scan(source, destination, relatives):
    wanted = set(relatives)
    with open(source, "r", encoding="utf-8") as src, \
            open(destination, "w", encoding="utf-8", newline="\n") as dst:
        dst.write("# batch-enumerate v1\n")
        for line in src:
            if line.startswith("candidate\t"):
                fields = line.rstrip("\n").split("\t")
                if len(fields) >= 5 and fields[3] in wanted:
                    dst.write(line)


def result_map(results):
    return {r["relative"]: r for r in results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True)
    parser.add_argument("--cxx", required=False)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe = os.path.abspath(args.probe)
    cxx = os.path.abspath(args.cxx) if args.cxx else None
    fixtures_dir = os.path.abspath(args.fixtures)
    staging = os.path.abspath(args.staging)
    work = os.path.abspath(args.work)
    output = os.path.abspath(args.output)
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(output, ignore_errors=True)
    os.makedirs(work)
    os.makedirs(staging)
    os.makedirs(output)

    checks = Checks()
    report = {
        "package": "EXReaderBatchImport",
        "version": "0.1.0",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "source": os.environ.get("GITHUB_SHA", ""),
        "checks": checks.items,
    }
    try:
        with open(os.path.join(fixtures_dir, "fixtures.json"), "r",
                  encoding="utf-8") as f:
            fixture = json.load(f)
        root = fixture["root"]
        expected = {item["relative"]: item for item in fixture["files"]}
        expected_relatives = set(expected)
        links = fixture.get("links", {})

        scan_all = os.path.join(work, "scan-all.tsv")
        run([probe, "enumerate", "--root", root, "--recursive", "--out", scan_all])
        meta, candidates = parse_scan(scan_all)
        checks.equal("scan.complete", meta.get("complete"), ["1"])
        checks.equal("scan.truncated", meta.get("truncated"), ["0"])
        checks.equal("scan.cancelled", meta.get("cancelled"), ["0"])
        checks.equal("scan.candidates.exact", set(candidates), expected_relatives)
        checks.check("scan.max_batch.bounded", int(meta["max_batch"][0]) <= 32,
                     meta.get("max_batch"))
        for relative, item in expected.items():
            row = candidates.get(relative)
            if row:
                checks.equal("scan.format." + relative, row["format"], item["format"])
                checks.check("scan.path.absolute." + relative,
                             os.path.isabs(row["path"]), row["path"])
                checks.check("scan.path.under_root." + relative,
                             os.path.commonpath([root, row["path"]]) == root,
                             row["path"])
                checks.check("scan.relative.separator." + relative,
                             "\\" not in relative and "\\" not in row["relative"],
                             row["relative"])
        for relative in candidates:
            checks.check("scan.no_link_follow." + relative,
                         not relative.startswith("link-") and
                         "outside" not in relative, relative)

        scan_flat = os.path.join(work, "scan-flat.tsv")
        run([probe, "enumerate", "--root", root, "--out", scan_flat])
        flat_meta, flat_candidates = parse_scan(scan_flat)
        checks.equal("flat.complete", flat_meta.get("complete"), ["1"])
        checks.equal("flat.truncated", flat_meta.get("truncated"), ["0"])
        checks.equal("flat.exact", set(flat_candidates),
                     {r for r in expected_relatives if "/" not in r})
        checks.check("flat.no_nested",
                     all("/" not in r for r in flat_candidates), flat_candidates)

        scan_depth = os.path.join(work, "scan-depth.tsv")
        run([probe, "enumerate", "--root", root, "--recursive", "--max-depth", "1",
             "--out", scan_depth])
        depth_meta, depth_candidates = parse_scan(scan_depth)
        checks.equal("depth.truncated", depth_meta.get("truncated"), ["1"])
        checks.equal("depth.complete", depth_meta.get("complete"), ["0"])
        checks.check("depth.no_deeper",
                     all(not r.startswith("深度/一层/二层") for r in depth_candidates),
                     depth_candidates)

        scan_c3 = os.path.join(work, "scan-c3.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--max-candidates", "3", "--out", scan_c3])
        c3_meta, c3_candidates = parse_scan(scan_c3)
        checks.equal("candidates.limit.count", len(c3_candidates), 3)
        checks.equal("candidates.limit.truncated", c3_meta.get("truncated"), ["1"])
        checks.equal("candidates.limit.complete", c3_meta.get("complete"), ["0"])

        scan_d1 = os.path.join(work, "scan-d1.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--max-dirs", "1", "--out", scan_d1])
        d1_meta, d1_candidates = parse_scan(scan_d1)
        checks.equal("directories.limit.truncated", d1_meta.get("truncated"), ["1"])
        checks.check("directories.limit.flat",
                     all("/" not in r for r in d1_candidates), d1_candidates)

        root_bytes = len(root.encode("utf-8"))
        max_path = max(64, root_bytes + 1)
        scan_path = os.path.join(work, "scan-path.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--max-path", str(max_path), "--out", scan_path])
        path_meta, path_candidates = parse_scan(scan_path)
        checks.equal("path.limit.truncated", path_meta.get("truncated"), ["1"])
        checks.check("path.limit.respected",
                     all(len(r.encode("utf-8")) <= max_path for r in path_candidates),
                     max_path)

        scan_pending = os.path.join(work, "scan-pending.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--max-pending", str(root_bytes + 128), "--out", scan_pending])
        pending_meta, _ = parse_scan(scan_pending)
        checks.equal("pending.limit.truncated", pending_meta.get("truncated"), ["1"])

        scan_b1 = os.path.join(work, "scan-b1.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--batch-size", "1", "--out", scan_b1])
        b1_meta, b1_candidates = parse_scan(scan_b1)
        checks.equal("batch.one.complete", b1_meta.get("complete"), ["1"])
        checks.equal("batch.one.max_batch", b1_meta.get("max_batch"), ["1"])
        checks.equal("batch.one.count", len(b1_candidates), len(candidates))

        invalid = run([probe, "enumerate", "--root", root, "--recursive",
                       "--batch-size", "101", "--out",
                       os.path.join(work, "scan-invalid.tsv")], expect=2)
        checks.check("batch.101.rejected", invalid.returncode == 2,
                     invalid.stderr.strip())

        scan_cancel = os.path.join(work, "scan-cancel.tsv")
        run([probe, "enumerate", "--root", root, "--recursive",
             "--batch-size", "5", "--cancel-after-batches", "1",
             "--out", scan_cancel])
        cancel_meta, _ = parse_scan(scan_cancel)
        checks.equal("scan.cancel.cancelled", cancel_meta.get("cancelled"), ["1"])
        checks.equal("scan.cancel.complete", cancel_meta.get("complete"), ["0"])

        main_dir = os.path.join(work, "main")
        os.makedirs(main_dir)
        db = os.path.join(main_dir, "library.sqlite")
        originals_dir = os.path.join(main_dir, "originals")
        os.makedirs(originals_dir)
        import1 = os.path.join(main_dir, "import1.tsv")
        run([probe, "import", "--library", db, "--staging", staging,
             "--scan", scan_all, "--batch", "7", "--export-dir", originals_dir,
             "--out", import1])
        import_meta, results, originals = parse_import(import1)
        checks.check("import.aggregate",
                     all(row == ["OK"] for row in import_meta.get("aggregate", [])),
                     import_meta.get("aggregate"))
        checks.equal("import.result.count", len(results), len(candidates))
        rmap = result_map(results)
        checks.equal("import.result.exact", set(rmap), set(candidates))
        for relative, item in expected.items():
            result = rmap[relative]
            if item["valid"]:
                if item.get("duplicate_group"):
                    checks.check("import.duplicate.member." + relative,
                                 result["status"] in ("IMPORTED", "DUPLICATE"),
                                 result)
                else:
                    checks.equal("import.created." + relative, result["status"],
                                 "IMPORTED")
                    checks.equal("import.committed." + relative,
                                 result["committed"], 1)
                    checks.equal("import.created_flag." + relative,
                                 result["created"], 1)
                    checks.check("import.book_id." + relative,
                                 result["book_id"] > 0, result["book_id"])
            else:
                checks.equal("import.corrupt.status." + relative, result["status"],
                             "FAILED")
                checks.equal("import.corrupt.committed." + relative,
                             result["committed"], 0)
                checks.equal("import.corrupt.code." + relative,
                             result["status_code"], EXR_FORMAT)
        duplicate_results = [rmap[r] for r, item in expected.items()
                             if item.get("duplicate_group")]
        checks.equal("import.duplicate.count",
                     len([r for r in duplicate_results if r["status"] == "DUPLICATE"]),
                     1)
        checks.equal("import.duplicate.imported",
                     len([r for r in duplicate_results if r["status"] == "IMPORTED"]),
                     1)
        if duplicate_results:
            ids = {r["book_id"] for r in duplicate_results}
            checks.equal("import.duplicate.same_id", len(ids), 1)
            checks.equal("import.duplicate.created_zero",
                         [r["created"] for r in duplicate_results if
                          r["status"] == "DUPLICATE"], [0])

        committed_ids = {r["book_id"] for r in results if r["committed"]}
        checks.equal("import.originals.count", len(originals),
                     len([r for r in results if r["committed"]]))
        book_to_relative = {r["book_id"]: r["relative"] for r in results
                            if r["committed"]}
        for original in originals:
            source_relative = book_to_relative.get(original["book_id"])
            checks.check("import.original.known." + str(original["book_id"]),
                         source_relative is not None, original)
            if source_relative:
                source = expected[source_relative]["path"]
                checks.equal("import.original.sha." + source_relative,
                             sha256(original["path"]), sha256(source))
                checks.equal("import.original.bytes." + source_relative,
                             original["bytes"], os.path.getsize(source))

        books_path = os.path.join(main_dir, "books.tsv")
        run([probe, "list", "--library", db, "--out", books_path])
        books_meta, books = parse_books(books_path)
        checks.equal("books.count", int(books_meta["count"][0]), len(committed_ids))
        checks.check("books.all_committed",
                     committed_ids.issubset(set(books)), committed_ids - set(books))
        checks.check("books.titles", all(b["title"] for b in books.values()), books)
        formats = {b["format"] for b in books.values()}
        checks.check("books.nine_formats",
                     set(fixture["nine_formats"]).issubset(formats),
                     sorted(formats))

        epub_result = rmap["sample.epub"]
        info_path = os.path.join(main_dir, "epub-info.tsv")
        run([probe, "epub-info", "--library", db, "--book",
             str(epub_result["book_id"]), "--out", info_path])
        info = parse_kv(info_path)
        checks.equal("storage.epub.bounded", info["epub-info"][0][1], "1")
        checks.equal("storage.epub.global_unknown", info["epub-info"][0][2], "0")

        with sqlite3.connect(db) as connection:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
        forbidden = [name for name in tables if name.lower().startswith(
            ("catalog", "reader_", "revision", "outbox", "projection", "sync_"))]
        checks.equal("product.sql.absent", forbidden, [])

        sentinel_id = epub_result["book_id"]
        before_meta = os.path.join(main_dir, "meta-before.tsv")
        run([probe, "set-metadata", "--library", db, "--book", str(sentinel_id),
             "--title", "Sentinel Title", "--favorite", "1", "--out", before_meta])
        before = parse_kv(before_meta)["metadata"][0]
        checks.equal("metadata.before.title", before[1], "Sentinel Title")
        checks.equal("metadata.before.favorite", before[2], "1")

        import2 = os.path.join(main_dir, "import2.tsv")
        run([probe, "import", "--library", db, "--staging", staging,
             "--scan", scan_all, "--batch", "7", "--out", import2])
        import2_meta, results2, _ = parse_import(import2)
        checks.check("reimport.aggregate",
                     all(row == ["OK"] for row in import2_meta.get("aggregate", [])),
                     import2_meta.get("aggregate"))
        rmap2 = result_map(results2)
        for relative, item in expected.items():
            if not item["valid"]:
                continue
            checks.equal("reimport.duplicate." + relative, rmap2[relative]["status"],
                         "DUPLICATE")
            checks.equal("reimport.created_zero." + relative,
                         rmap2[relative]["created"], 0)
            checks.equal("reimport.same_id." + relative,
                         rmap2[relative]["book_id"], rmap[relative]["book_id"])
        after_meta = os.path.join(main_dir, "meta-after.tsv")
        run([probe, "get-metadata", "--library", db, "--book", str(sentinel_id),
             "--out", after_meta])
        after = parse_kv(after_meta)["metadata"][0]
        checks.equal("metadata.after.title", after[1], "Sentinel Title")
        checks.equal("metadata.after.favorite", after[2], "1")
        books2_path = os.path.join(main_dir, "books2.tsv")
        run([probe, "list", "--library", db, "--out", books2_path])
        books2_meta, books2 = parse_books(books2_path)
        checks.equal("reimport.books.count", int(books2_meta["count"][0]),
                     len(committed_ids))

        memory_dir = os.path.join(work, "memory")
        os.makedirs(memory_dir)
        memory_db = os.path.join(memory_dir, "library.sqlite")
        preimport_out = os.path.join(memory_dir, "preimport.tsv")
        run([probe, "preimport-memory", "--library", memory_db, "--format", "EPUB",
             "--path", expected["sample.epub"]["path"], "--out", preimport_out])
        preimport = parse_kv(preimport_out)["preimport"][0]
        memory_id = int(preimport[0])
        memory_info_path = os.path.join(memory_dir, "info-before.tsv")
        run([probe, "epub-info", "--library", memory_db, "--book", str(memory_id),
             "--out", memory_info_path])
        memory_info = parse_kv(memory_info_path)["epub-info"][0]
        checks.equal("storage.memory.before", memory_info[1], "0")
        memory_scan = os.path.join(memory_dir, "scan.tsv")
        write_subset_scan(scan_all, memory_scan, ["sample.epub"])
        memory_import = os.path.join(memory_dir, "import.tsv")
        run([probe, "import", "--library", memory_db, "--staging", staging,
             "--scan", memory_scan, "--batch", "1", "--out", memory_import])
        _, memory_results, _ = parse_import(memory_import)
        checks.equal("storage.memory.duplicate", memory_results[0]["status"],
                     "DUPLICATE")
        checks.equal("storage.memory.same_id", memory_results[0]["book_id"],
                     memory_id)
        checks.equal("storage.memory.created_zero", memory_results[0]["created"], 0)
        memory_after_path = os.path.join(memory_dir, "info-after.tsv")
        run([probe, "epub-info", "--library", memory_db, "--book", str(memory_id),
             "--out", memory_after_path])
        memory_after = parse_kv(memory_after_path)["epub-info"][0]
        checks.equal("storage.memory.after", memory_after[1], "0")

        cancel_dir = os.path.join(work, "cancel")
        os.makedirs(cancel_dir)
        cancel_db = os.path.join(cancel_dir, "library.sqlite")
        cancel_scan = os.path.join(cancel_dir, "scan.tsv")
        cancel_subset = [r for r in candidates if expected[r]["valid"]][:5]
        write_subset_scan(scan_all, cancel_scan, cancel_subset)
        cancel_out = os.path.join(cancel_dir, "import.tsv")
        run([probe, "import", "--library", cancel_db, "--staging", staging,
             "--scan", cancel_scan, "--batch", "5", "--cancel-after-commits", "2",
             "--out", cancel_out])
        cancel_meta, cancel_results, _ = parse_import(cancel_out)
        checks.check("cancel.aggregate",
                     all(row == ["CANCELLED"] for row in
                         cancel_meta.get("aggregate", [])),
                     cancel_meta.get("aggregate"))
        checks.equal("cancel.imported",
                     len([r for r in cancel_results if r["committed"]]), 2)
        checks.equal("cancel.cancelled",
                     len([r for r in cancel_results if r["status"] == "CANCELLED"]),
                     3)
        cancel_books_path = os.path.join(cancel_dir, "books.tsv")
        run([probe, "list", "--library", cancel_db, "--out", cancel_books_path])
        checks.equal("cancel.books", int(parse_books(cancel_books_path)[0]["count"][0]),
                     2)
        cancel_retry = os.path.join(cancel_dir, "retry.tsv")
        run([probe, "import", "--library", cancel_db, "--staging", staging,
             "--scan", cancel_scan, "--batch", "5", "--out", cancel_retry])
        _, retry_results, _ = parse_import(cancel_retry)
        retry_map = result_map(retry_results)
        first_two = {r["relative"] for r in cancel_results if r["committed"]}
        for relative in cancel_subset:
            expected_status = "DUPLICATE" if relative in first_two else "IMPORTED"
            checks.equal("cancel.retry." + relative, retry_map[relative]["status"],
                         expected_status)
        cancel_books2 = os.path.join(cancel_dir, "books2.tsv")
        run([probe, "list", "--library", cancel_db, "--out", cancel_books2])
        checks.equal("cancel.retry.books",
                     int(parse_books(cancel_books2)[0]["count"][0]),
                     len(cancel_subset))

        copy_dir = os.path.join(work, "cancel-copy")
        os.makedirs(copy_dir)
        copy_db = os.path.join(copy_dir, "library.sqlite")
        copy_scan = os.path.join(copy_dir, "scan.tsv")
        write_subset_scan(scan_all, copy_scan, ["大文件/big.txt"])
        copy_out = os.path.join(copy_dir, "import.tsv")
        run([probe, "import", "--library", copy_db, "--staging", staging,
             "--scan", copy_scan, "--batch", "1", "--cancel-after-calls", "3",
             "--out", copy_out])
        _, copy_results, _ = parse_import(copy_out)
        checks.equal("cancel.copy.status", copy_results[0]["status"], "CANCELLED")
        checks.equal("cancel.copy.committed", copy_results[0]["committed"], 0)
        copy_books_path = os.path.join(copy_dir, "books.tsv")
        run([probe, "list", "--library", copy_db, "--out", copy_books_path])
        checks.equal("cancel.copy.books",
                     int(parse_books(copy_books_path)[0]["count"][0]), 0)
        leftovers = [name for name in os.listdir(staging)
                     if name.startswith("reader-batch-")]
        checks.equal("cancel.copy.no_temp", leftovers, [])

        scan_post = os.path.join(work, "scan-post.tsv")
        run([probe, "enumerate", "--root", root, "--recursive", "--out", scan_post])
        modified = expected["枚举后/修改.txt"]["path"]
        with open(modified, "wb") as f:
            f.write(b"new-after-scan " + b"B" * 2048)
        modified_sha = sha256(modified)
        os.remove(expected["枚举后/删除.txt"]["path"])
        replaced = expected["枚举后/替换.txt"]["path"]
        os.remove(replaced)
        replaced_as_link = False
        if links.get("out", {}).get("supported"):
            try:
                os.symlink(os.path.join(fixture["external"], "outside.epub"),
                           replaced)
                replaced_as_link = True
            except OSError:
                pass
        post_dir = os.path.join(work, "post")
        os.makedirs(post_dir)
        post_db = os.path.join(post_dir, "library.sqlite")
        post_originals = os.path.join(post_dir, "originals")
        os.makedirs(post_originals)
        post_out = os.path.join(post_dir, "import.tsv")
        run([probe, "import", "--library", post_db, "--staging", staging,
             "--scan", scan_post, "--batch", "6", "--export-dir", post_originals,
             "--out", post_out])
        _, post_results, post_originals_rows = parse_import(post_out)
        post_map = result_map(post_results)
        checks.equal("post.modified.status",
                     post_map["枚举后/修改.txt"]["status"], "IMPORTED")
        modified_original = [r for r in post_originals_rows
                             if r["book_id"] == post_map["枚举后/修改.txt"]["book_id"]]
        checks.check("post.modified.original", bool(modified_original),
                     modified_original)
        if modified_original:
            checks.equal("post.modified.sha", sha256(modified_original[0]["path"]),
                         modified_sha)
        checks.equal("post.deleted.status",
                     post_map["枚举后/删除.txt"]["status"], "FAILED")
        checks.equal("post.deleted.committed",
                     post_map["枚举后/删除.txt"]["committed"], 0)
        checks.equal("post.replaced.status",
                     post_map["枚举后/替换.txt"]["status"], "FAILED")
        checks.equal("post.replaced.committed",
                     post_map["枚举后/替换.txt"]["committed"], 0)
        checks.check("post.replaced.mode",
                     replaced_as_link or not os.path.exists(replaced),
                     "symlink" if replaced_as_link else "deleted")

        limits_dir = os.path.join(work, "limits")
        os.makedirs(limits_dir)
        limits_db = os.path.join(limits_dir, "library.sqlite")
        limits_out = os.path.join(limits_dir, "limits.tsv")
        run([probe, "limits", "--library", limits_db, "--staging", staging,
             "--out", limits_out])
        limits = parse_kv(limits_out)
        for name in ("scan-batch-101", "scan-depth-17",
                     "scan-candidates-10001", "import-count-0",
                     "import-count-101"):
            checks.equal("limits." + name, limits[name][0][0], "ARGUMENT")
        checks.equal("limits.status_names", limits["status-names"][0],
                     ["OK", "DUPLICATE", "MOBI"])

        if cxx:
            self_test = run([cxx, "--selftest"])
            checks.check("cxx.selftest", "batch-import-cpp-selftest" in
                         self_test.stdout, self_test.stdout)

        report["fixtures"] = {
            "files": len(expected),
            "links": {name: bool(value.get("supported"))
                      for name, value in links.items()},
            "replacement_link": replaced_as_link,
        }
        report["results"] = {
            "scan_candidates": len(candidates),
            "imported": import_meta.get("imported"),
            "duplicate": import_meta.get("duplicate"),
            "failed": import_meta.get("failed"),
        }
        report["ok"] = not checks.failures
        report["failures"] = checks.failures
    except Exception as exc:  # keep the original failure and evidence
        report["ok"] = False
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
        report["failures"] = checks.failures + ["exception"]
        checks.check("exception", False, report["error"])
    finally:
        report["checks"] = checks.items
        with open(os.path.join(output, "report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    if not report.get("ok"):
        print("FAILED:", report.get("error", ""), report.get("failures"))
        for item in checks.items:
            if not item["ok"]:
                print(" -", item["name"], item["detail"])
        return 1
    print("batch import checks:", len(checks.items), "all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
