#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance driver for the installed EXReaderBookInformation 0.1.0.

It generates the fixtures, seeds one product catalog and one SDK library through
the installed public APIs, then judges every named behaviour of the snapshot.
No local build, parse or fixture step happens outside GitHub Actions.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fixtures  # noqa: E402  (fixture generator lives beside this driver)

OK = 0
ARGUMENT = 1
NOT_FOUND = 2
CANCELLED = 3
REENTRANT = 4
CATALOG = 5
SDK_FAILURE = 6
MEMORY = 7

CLOUD_ONLY, LOCAL_UNCHECKED, LOCAL_PRESENT, LOCAL_MISSING, IDENTITY_MISMATCH = range(5)
NOT_CHECKED, SIZE_ONLY, SHA256_IDENTITY, MISMATCH = range(4)
PARSER_UNAVAILABLE, PARSER_NO_FIELDS, PARSER_OK, PARSER_PASSWORD, PARSER_FAILED = range(5)

FORMATS = ("epub", "pdf", "cbz", "txt", "html", "fb2", "docx", "rtf", "mobi")
LOCATION = {"pdf": "fixed_page", "cbz": "fixed_page", "epub": "epub_chapter"}

REQUIRED_CASES = (
    "nine-formats-cloud-metadata",
    "cloud-row-without-library",
    "local-identity-sha256",
    "local-identity-size-only",
    "local-unicode-fields",
    "local-overlong-fields",
    "cbz-property-cap",
    "pdf-pages-without-info",
    "epub-storage-modes",
    "reflow-no-public-fields",
    "local-mapping-missing",
    "wrong-book-size-mismatch",
    "wrong-book-bytes-mismatch",
    "size-only-identity-limit",
    "local-unchecked-without-library",
    "cancel-at-every-poll",
    "snapshot-readable-after-sdk-close",
    "independent-public-api-comparison",
    "foreign-thread-and-immutable-view",
    "reentrant-cancel-callback",
    "argument-and-error-contract",
    "stores-unchanged",
)

UNCOVERED = (
    "encrypted PDF PASSWORD_REQUIRED: the package generates no encrypted fixture",
    "soft-deleted product row: no public product API sets reader_books.deleted",
    "invalid UTF-8 product or SDK text: both providers reject it before this module sees it",
    "host information panel, editing and metadata module: root owns that wiring",
    "real device, simulator and accessibility passes: not granted by this package",
)


class Failure(Exception):
    pass


def file_digest(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class Asserts:
    def __init__(self):
        self.count = 0
        self.problems = []

    def eq(self, label, actual, expected):
        self.count += 1
        if actual != expected:
            self.problems.append("%s: %r != %r" % (label, actual, expected))

    def true(self, label, condition, detail=""):
        self.count += 1
        if not condition:
            self.problems.append(label + ((": " + str(detail)) if detail else ""))


def spawn(executable, arguments, accept=(0, 1)):
    completed = subprocess.run([executable, *[str(a) for a in arguments]],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode not in accept:
        raise Failure("%s %s exited %d: %s %s" % (Path(executable).name, arguments, completed.returncode,
                                                  completed.stdout.strip(), completed.stderr.strip()))
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise Failure("%s %s printed no JSON" % (Path(executable).name, arguments))
    return json.loads(lines[-1])


class World:
    def __init__(self, probe, compare, fixtures, work):
        self.probe = probe
        self.compare = compare
        self.fixtures = fixtures
        self.work = work
        self.manifest = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
        self.library = work / "library.sqlite"
        self.catalog = work / "catalog.sqlite"
        self.ids = {}
        self.keys = {}
        self.cloud_rows = []
        self.storage = []

    # --- setup -------------------------------------------------------------
    def import_book(self, name, fmt, mode, alias=None):
        result = spawn(self.probe, ["import", self.library, fmt, self.manifest["books"][name]["path"], mode])
        if result.get("status") != OK or int(result.get("id", 0)) <= 0:
            raise Failure("import %s failed: %s" % (name, result))
        self.ids[alias or name] = int(result["id"])

    def attach(self, fmt, digest, size, title, author, sdk_id, favorite=0, location=None):
        location = location or LOCATION.get(fmt, "reflow_global")
        result = spawn(self.probe, ["attach", self.catalog, fmt, digest, size, title, author, title,
                                    location, sdk_id, favorite])
        if result.get("status") != 0:
            raise Failure("attach %s failed: %s" % (digest, result))
        return "%s:%s" % (fmt, digest)

    def unmap(self, sdk_id):
        result = spawn(self.probe, ["unmap", self.catalog, sdk_id])
        if result.get("status") != 0:
            raise Failure("unmap %d failed: %s" % (sdk_id, result))

    def book(self, name):
        return self.manifest["books"][name]

    def build(self):
        self.work.mkdir(parents=True, exist_ok=True)
        for path in (self.library, self.catalog):
            if path.exists():
                path.unlink()
        for name, fmt, mode in (("plain.pdf", "pdf", "file"), ("unicode.pdf", "pdf", "memory"),
                                ("long.pdf", "pdf", "memory"), ("pages7.pdf", "pdf", "memory"),
                                ("collection.cbz", "cbz", "memory"), ("shelf.epub", "epub", "file"),
                                ("shelf2.epub", "epub", "memory"), ("small.txt", "txt", "memory"),
                                ("tiny.txt", "txt", "memory"), ("large.txt", "txt", "memory"),
                                ("swap-beta.pdf", "pdf", "memory")):
            self.import_book(name, fmt, mode)
        # A second, distinct SDK row for the same bytes: one local SDK ID can map
        # to only one product original, so the two wrong-book rows need two rows.
        self.import_book("swap-beta.pdf", "pdf", "memory", alias="swap-beta.pdf.2")

        # Nine product-only rows: no local mapping exists after unmap().
        for index, fmt in enumerate(FORMATS):
            digest = hashlib.sha256(("cloud:" + fmt).encode("utf-8")).hexdigest()
            size = 1000 + index
            title = "云端 %s 书籍" % fmt
            author = "作者 %s" % fmt
            key = self.attach(fmt, digest, size, title, author, 900000 + index)
            self.unmap(900000 + index)
            self.cloud_rows.append({"format": fmt, "key": key, "title": title, "author": author, "bytes": size})

        plain = self.book("plain.pdf")
        self.keys["plain"] = self.attach("pdf", plain["sha256"], plain["bytes"], "产品标题：平原",
                                         "产品作者：甲", self.ids["plain.pdf"], favorite=1)
        unicode_book = self.book("unicode.pdf")
        self.keys["unicode"] = self.attach("pdf", unicode_book["sha256"], unicode_book["bytes"],
                                           "产品标题：中文", "产品作者：乙", self.ids["unicode.pdf"])
        long_book = self.book("long.pdf")
        self.keys["long"] = self.attach("pdf", long_book["sha256"], long_book["bytes"], "书" * 500,
                                        "A" * 1500, self.ids["long.pdf"])
        pages = self.book("pages7.pdf")
        self.keys["pages7"] = self.attach("pdf", pages["sha256"], pages["bytes"], "七页无信息",
                                          "", self.ids["pages7.pdf"])
        comic = self.book("collection.cbz")
        self.keys["comic"] = self.attach("cbz", comic["sha256"], comic["bytes"], "合集产品标题",
                                         "产品作者：丙", self.ids["collection.cbz"])
        shelf = self.book("shelf.epub")
        self.keys["epub_file"] = self.attach("epub", shelf["sha256"], shelf["bytes"], "重排产品标题",
                                             "产品作者：丁", self.ids["shelf.epub"])
        shelf2 = self.book("shelf2.epub")
        self.keys["epub_memory"] = self.attach("epub", shelf2["sha256"], shelf2["bytes"], "重排产品标题二",
                                               "产品作者：戊", self.ids["shelf2.epub"])
        small = self.book("small.txt")
        self.keys["text"] = self.attach("txt", small["sha256"], small["bytes"], "纯文本产品标题",
                                        "产品作者：己", self.ids["small.txt"])
        large = self.book("large.txt")
        self.keys["large"] = self.attach("txt", large["sha256"], large["bytes"], "大文件产品标题",
                                         "产品作者：癸", self.ids["large.txt"])
        tiny = self.book("tiny.txt")
        self.keys["missing"] = self.attach("txt", tiny["sha256"], tiny["bytes"], "缺失映射",
                                           "产品作者：庚", 987654)
        beta = self.book("swap-beta.pdf")
        alpha = self.book("swap-alpha.pdf")
        self.keys["wrong_size"] = self.attach("pdf", hashlib.sha256(b"wrong-size").hexdigest(),
                                              beta["bytes"] + 1, "尺寸不符", "产品作者：辛",
                                              self.ids["swap-beta.pdf.2"])
        self.keys["wrong_bytes"] = self.attach("pdf", alpha["sha256"], alpha["bytes"], "内容不符",
                                               "产品作者：壬", self.ids["swap-beta.pdf"])

    # --- helpers -----------------------------------------------------------
    def read(self, key, verify, parser, cancel=0, library=None):
        target = "-" if library is False else self.library
        result = spawn(self.probe, ["read", self.catalog, target, key, verify, parser, cancel])
        if result.get("status", 0) == -1:
            raise Failure("read setup failed: %s" % result)
        storage = result.get("storage")
        if not isinstance(storage, dict):
            raise Failure("read did not report storage fingerprints: %s" % result)
        self.storage.append(("%s:v%d:p%d:c%d" % (key.split(":")[0] + ":" + key.split(":")[1][:8], verify, parser, cancel), storage))
        return result

    def compare_run(self, command, key, *extra):
        return spawn(self.compare, [command, self.catalog, self.library, key, *extra])


def view_of(asserts, result, label):
    asserts.eq(label + ".status", result.get("status"), OK)
    asserts.eq(label + ".out", result.get("out"), True)
    view = result.get("view") or {}
    if not view:
        asserts.true(label + ".view", False, "no view")
    return view


def expect_availability(asserts, view, label, availability, identity):
    asserts.eq(label + ".availability", view.get("availability"), availability)
    asserts.eq(label + ".identity", view.get("identity"), identity)


def expect_properties(asserts, view, label, expected):
    asserts.eq(label + ".property_count", view.get("property_count"), len(expected))
    asserts.eq(label + ".properties_omitted", view.get("properties_omitted"), 0)
    actual = view.get("properties") or []
    for index, (key, value) in enumerate(expected):
        if index >= len(actual):
            asserts.true(label + ".property[%d]" % index, False, "missing")
            continue
        asserts.eq(label + ".property[%d].key" % index, actual[index].get("key"), key)
        asserts.eq(label + ".property[%d].value" % index, actual[index].get("value"), value)
        asserts.eq(label + ".property[%d].cut" % index,
                   (actual[index].get("key_truncated"), actual[index].get("value_truncated")), (0, 0))


# ---------------------------------------------------------------------------
# Named cases
# ---------------------------------------------------------------------------
def case_nine_formats(world, a):
    for row in world.cloud_rows:
        view = view_of(a, world.read(row["key"], 1, 1), row["format"])
        expect_availability(a, view, row["format"], CLOUD_ONLY, NOT_CHECKED)
        a.eq(row["format"] + ".verified_bytes", view.get("verified_bytes"), 0)
        a.eq(row["format"] + ".verified_sha256", view.get("verified_sha256"), None)
        a.eq(row["format"] + ".parser_status", view.get("parser_status"), PARSER_UNAVAILABLE)
        a.eq(row["format"] + ".page_count_known", view.get("page_count_known"), 0)
        a.eq(row["format"] + ".property_count", view.get("property_count"), 0)
        a.eq(row["format"] + ".location_kind", view.get("location_kind"), "")
        a.eq(row["format"] + ".title", view.get("title"), row["title"])
        a.eq(row["format"] + ".author", view.get("author"), row["author"])
        a.eq(row["format"] + ".author_known", view.get("author_known"), 1)
        a.eq(row["format"] + ".source_bytes", view.get("product_source_bytes"), row["bytes"])


def case_cloud_without_library(world, a):
    view = view_of(a, world.read(world.cloud_rows[1]["key"], 1, 1, library=False), "cloud")
    expect_availability(a, view, "cloud", CLOUD_ONLY, NOT_CHECKED)
    a.eq("cloud.parser", view.get("parser_status"), PARSER_UNAVAILABLE)


def case_identity_sha256(world, a):
    book = world.book("plain.pdf")
    view = view_of(a, world.read(world.keys["plain"], 1, 1), "plain")
    expect_availability(a, view, "plain", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("plain.verified_sha256", view.get("verified_sha256"), book["sha256"])
    a.eq("plain.verified_bytes", view.get("verified_bytes"), book["bytes"])
    a.eq("plain.product_title", view.get("title"), "产品标题：平原")
    a.eq("plain.author", view.get("author"), "产品作者：甲")
    a.eq("plain.favorite", view.get("favorite"), 1)
    a.eq("plain.deleted", view.get("deleted"), 0)
    a.eq("plain.location_kind", view.get("location_kind"), "fixed_page")
    a.eq("plain.parser_status", view.get("parser_status"), PARSER_OK)
    a.eq("plain.page_count_known", view.get("page_count_known"), 1)
    a.eq("plain.page_count", view.get("page_count"), 3)
    # A PDF read from the library has no provider document title: the Info title
    # is a metadata property, not a fixed-document attribute.
    a.eq("plain.parser_title", view.get("parser_title"), None)
    a.eq("plain.parser_title_truncated", view.get("parser_title_truncated"), 0)
    a.eq("plain.epub_mode_known", view.get("epub_mode_known"), 0)
    keys = world.manifest["pdf_info_keys"]
    expect_properties(a, view, "plain", [(keys["title"], "Plain title"), (keys["author"], "Plain author"),
                                        (keys["subject"], "Plain subject"),
                                        (keys["keywords"], "one, two"),
                                        (keys["producer"], "fixture writer")])


def case_identity_size_only(world, a):
    view = view_of(a, world.read(world.keys["plain"], 0, 1), "size-only")
    expect_availability(a, view, "size-only", LOCAL_PRESENT, SIZE_ONLY)
    a.eq("size-only.verified_sha256", view.get("verified_sha256"), None)
    a.eq("size-only.verified_bytes", view.get("verified_bytes"), world.book("plain.pdf")["bytes"])
    a.eq("size-only.page_count", view.get("page_count"), 3)
    a.eq("size-only.property_count", view.get("property_count"), 5)


def case_unicode_fields(world, a):
    unicode_book = world.manifest["unicode"]
    view = view_of(a, world.read(world.keys["unicode"], 1, 1), "unicode")
    expect_availability(a, view, "unicode", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("unicode.product_title", view.get("title"), "产品标题：中文")
    a.eq("unicode.parser_title", view.get("parser_title"), None)
    a.eq("unicode.page_count", view.get("page_count"), 2)
    keys = world.manifest["pdf_info_keys"]
    expect_properties(a, view, "unicode", [(keys["title"], unicode_book["title"]),
                                           (keys["author"], unicode_book["author"]),
                                           (keys["subject"], unicode_book["subject"])])
    properties = view.get("properties") or []
    a.eq("unicode.info_title_bytes",
         len((properties[0].get("value") or "").encode("utf-8")) if properties else None,
         len(unicode_book["title"].encode("utf-8")))
    a.eq("unicode.info_title_scalars", properties[0].get("value") if properties else None,
         unicode_book["title"])


def case_overlong_fields(world, a):
    view = view_of(a, world.read(world.keys["long"], 1, 1), "long")
    expect_availability(a, view, "long", LOCAL_PRESENT, SHA256_IDENTITY)
    title = view.get("title") or ""
    a.eq("long.title_truncated", view.get("title_truncated"), 1)
    a.eq("long.title_bytes", len(title.encode("utf-8")), 1023)
    a.eq("long.title_scalars", title, "书" * 341)
    a.eq("long.author_truncated", view.get("author_truncated"), 1)
    a.eq("long.author_bytes", len(view.get("author", "")), 1024)
    a.eq("long.parser_title", view.get("parser_title"), None)
    a.eq("long.parser_title_truncated", view.get("parser_title_truncated"), 0)
    keys = world.manifest["pdf_info_keys"]
    a.eq("long.property_count", view.get("property_count"), 3)
    properties = view.get("properties") or []
    a.eq("long.title_value", properties[0].get("value") if properties else None, "A" * 1024)
    a.eq("long.title_value_cut", properties[0].get("value_truncated") if properties else None, 1)
    a.eq("long.subject_value", properties[1].get("value") if len(properties) > 1 else None, "short subject")
    a.eq("long.subject_key", properties[1].get("key") if len(properties) > 1 else None, keys["subject"])
    a.eq("long.keywords_value", properties[2].get("value") if len(properties) > 2 else None, "B" * 1024)
    a.eq("long.keywords_cut", properties[2].get("value_truncated") if len(properties) > 2 else None, 1)


def case_cbz_cap(world, a):
    comic = world.manifest["comic"]
    view = view_of(a, world.read(world.keys["comic"], 1, 1), "cbz")
    expect_availability(a, view, "cbz", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("cbz.page_count", view.get("page_count"), 3)
    a.eq("cbz.parser_title", view.get("parser_title"), "漫画：夜空 & 星")
    a.eq("cbz.product_title", view.get("title"), "合集产品标题")
    a.eq("cbz.property_count", view.get("property_count"), comic["kept"])
    a.eq("cbz.properties_omitted", view.get("properties_omitted"), comic["omitted"])
    properties = view.get("properties") or []
    expected_prefix = [("http://purl.org/dc/terms/title", "漫画：夜空 & 星"),
                       ("http://purl.org/dc/terms/creator", "脚本：林"),
                       ("http://purl.org/dc/terms/description", "合集测试")]
    for index, (key, value) in enumerate(expected_prefix):
        if index < len(properties):
            a.eq("cbz.property[%d]" % index, (properties[index].get("key"), properties[index].get("value")),
                 (key, value))
    if len(properties) > 3:
        long_key = "urn:comicinfo:" + comic["long_name"]
        a.eq("cbz.long_key", properties[3].get("key"), long_key[:128])
        a.eq("cbz.long_key_bytes", len(properties[3].get("key", "").encode("utf-8")), 128)
        a.eq("cbz.long_key_cut", properties[3].get("key_truncated"), 1)
    if len(properties) > 4:
        a.eq("cbz.long_value", properties[4].get("value"), "W" * 1024)
        a.eq("cbz.long_value_cut", properties[4].get("value_truncated"), 1)
    if len(properties) > 5:
        a.eq("cbz.first_extra", (properties[5].get("key"), properties[5].get("value")),
             ("urn:comicinfo:Field01", "value-01"))
    if len(properties) == comic["kept"]:
        a.eq("cbz.last_kept", properties[-1].get("key"), "urn:comicinfo:Field27")


def case_pages_without_info(world, a):
    view = view_of(a, world.read(world.keys["pages7"], 1, 1), "pages7")
    expect_availability(a, view, "pages7", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("pages7.page_count_known", view.get("page_count_known"), 1)
    a.eq("pages7.page_count", view.get("page_count"), 7)
    a.eq("pages7.parser_status", view.get("parser_status"), PARSER_OK)
    a.eq("pages7.parser_title", view.get("parser_title"), None)
    a.eq("pages7.property_count", view.get("property_count"), 0)
    a.eq("pages7.author_known", view.get("author_known"), 0)
    a.eq("pages7.author", view.get("author"), "")


def case_epub_modes(world, a):
    bounded = view_of(a, world.read(world.keys["epub_file"], 1, 1), "epub-file")
    expect_availability(a, bounded, "epub-file", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("epub-file.mode_known", bounded.get("epub_mode_known"), 1)
    a.eq("epub-file.bounded", bounded.get("epub_bounded_storage"), 1)
    a.eq("epub-file.extent", bounded.get("epub_global_extent_known"), 0)
    a.eq("epub-file.page_count_known", bounded.get("page_count_known"), 0)
    a.eq("epub-file.parser_title", bounded.get("parser_title"), None)
    a.eq("epub-file.parser_status", bounded.get("parser_status"), PARSER_OK)
    a.eq("epub-file.property_count", bounded.get("property_count"), 0)
    whole = view_of(a, world.read(world.keys["epub_memory"], 1, 1), "epub-memory")
    expect_availability(a, whole, "epub-memory", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("epub-memory.mode_known", whole.get("epub_mode_known"), 1)
    a.eq("epub-memory.bounded", whole.get("epub_bounded_storage"), 0)
    a.eq("epub-memory.extent", whole.get("epub_global_extent_known"), 1)


def case_reflow_no_fields(world, a):
    view = view_of(a, world.read(world.keys["text"], 1, 1), "text")
    expect_availability(a, view, "text", LOCAL_PRESENT, SHA256_IDENTITY)
    a.eq("text.parser_status", view.get("parser_status"), PARSER_NO_FIELDS)
    a.eq("text.page_count_known", view.get("page_count_known"), 0)
    a.eq("text.property_count", view.get("property_count"), 0)
    a.eq("text.parser_title", view.get("parser_title"), None)
    a.eq("text.epub_mode_known", view.get("epub_mode_known"), 0)


def case_mapping_missing(world, a):
    view = view_of(a, world.read(world.keys["missing"], 1, 1), "missing")
    expect_availability(a, view, "missing", LOCAL_MISSING, NOT_CHECKED)
    a.eq("missing.verified_bytes", view.get("verified_bytes"), 0)
    a.eq("missing.verified_sha256", view.get("verified_sha256"), None)
    a.eq("missing.parser_status", view.get("parser_status"), PARSER_UNAVAILABLE)


def case_wrong_size(world, a):
    view = view_of(a, world.read(world.keys["wrong_size"], 1, 1), "wrong-size")
    expect_availability(a, view, "wrong-size", IDENTITY_MISMATCH, MISMATCH)
    a.eq("wrong-size.verified_bytes", view.get("verified_bytes"), 0)
    a.eq("wrong-size.verified_sha256", view.get("verified_sha256"), None)
    a.eq("wrong-size.parser_status", view.get("parser_status"), PARSER_UNAVAILABLE)


def case_wrong_bytes(world, a):
    view = view_of(a, world.read(world.keys["wrong_bytes"], 1, 1), "wrong-bytes")
    expect_availability(a, view, "wrong-bytes", IDENTITY_MISMATCH, MISMATCH)
    a.eq("wrong-bytes.verified_bytes", view.get("verified_bytes"), 0)
    a.eq("wrong-bytes.verified_sha256", view.get("verified_sha256"), None)
    a.eq("wrong-bytes.parser_status", view.get("parser_status"), PARSER_UNAVAILABLE)


def case_size_only_limit(world, a):
    view = view_of(a, world.read(world.keys["wrong_bytes"], 0, 1), "weak")
    expect_availability(a, view, "weak", LOCAL_PRESENT, SIZE_ONLY)
    a.eq("weak.verified_sha256", view.get("verified_sha256"), None)
    a.eq("weak.verified_bytes", view.get("verified_bytes"), world.book("swap-alpha.pdf")["bytes"])


def case_unchecked(world, a):
    view = view_of(a, world.read(world.keys["plain"], 1, 1, library=False), "unchecked")
    expect_availability(a, view, "unchecked", LOCAL_UNCHECKED, NOT_CHECKED)
    a.eq("unchecked.verified_bytes", view.get("verified_bytes"), 0)
    a.eq("unchecked.parser_status", view.get("parser_status"), PARSER_UNAVAILABLE)


def case_cancel_at_every_poll(world, a):
    baseline = world.read(world.keys["plain"], 1, 1)
    a.eq("plain.baseline", baseline.get("status"), OK)
    polls = int(baseline.get("polls", 0))
    a.true("plain.poll_budget", 5 <= polls <= 64, polls)
    for limit in range(1, polls + 1):
        result = world.read(world.keys["plain"], 1, 1, cancel=limit)
        a.eq("plain.cancel[%d].status" % limit, result.get("status"), CANCELLED)
        a.eq("plain.cancel[%d].out" % limit, result.get("out"), False)
        a.eq("plain.cancel[%d].polls" % limit, result.get("polls"), limit)
    size = world.book("large.txt")["bytes"]
    chunks = (size + 65535) // 65536
    big = world.read(world.keys["large"], 1, 0)
    a.eq("large.baseline", big.get("status"), OK)
    large_polls = int(big.get("polls", 0))
    a.eq("large.poll_budget", large_polls, 4 + chunks)
    a.eq("large.identity", (big.get("view") or {}).get("identity"), SHA256_IDENTITY)
    a.true("large.chunks", chunks >= 4, chunks)
    for limit in (1, 2, 3, 2 + chunks // 2, large_polls - 1, large_polls):
        result = world.read(world.keys["large"], 1, 0, cancel=limit)
        a.eq("large.cancel[%d].status" % limit, result.get("status"), CANCELLED)
        a.eq("large.cancel[%d].out" % limit, result.get("out"), False)
        a.eq("large.cancel[%d].polls" % limit, result.get("polls"), limit)


def case_lifetime(world, a):
    result = world.compare_run("lifetime", world.keys["plain"])
    a.true("lifetime.ok", result.get("ok") is True, result.get("problems"))
    a.true("lifetime.strings", int(result.get("strings", 0)) >= 8, result.get("strings"))


def case_public_api(world, a):
    expectations = (
        ("plain", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("unicode", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("long", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("pages7", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("comic", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("epub_file", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("epub_memory", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_OK),
        ("text", LOCAL_PRESENT, SHA256_IDENTITY, PARSER_NO_FIELDS),
    )
    for name, availability, identity, parser in expectations:
        result = world.compare_run("fields", world.keys[name], availability, identity, parser)
        a.true("recompute." + name, result.get("ok") is True, result.get("problems"))


def case_threads(world, a):
    result = world.compare_run("threads", world.keys["plain"])
    a.true("threads.ok", result.get("ok") is True, result.get("problems"))
    a.true("threads.foreign_refused", int(result.get("foreign_status", 0)) != 0, result.get("foreign_status"))


def case_reentrant(world, a):
    result = world.compare_run("reentrant", world.keys["plain"])
    a.true("reentrant.ok", result.get("ok") is True, result.get("problems"))
    a.eq("reentrant.outer", result.get("outer"), CANCELLED)
    a.eq("reentrant.inner", result.get("inner"), REENTRANT)


def case_arguments(world, a):
    result = spawn(world.probe, ["argcheck", world.catalog, world.library, world.keys["plain"]])
    cases = {row.get("name"): row.get("status") for row in result.get("cases", [])}
    expected = {"null-catalog": ARGUMENT, "null-output": ARGUMENT, "empty-key": ARGUMENT,
                "overlong-key": ARGUMENT, "malformed-key": ARGUMENT, "missing-separator": ARGUMENT,
                "short-options": ARGUMENT, "absent-key": NOT_FOUND, "error-cleared": 0}
    a.eq("arguments.names", sorted(cases), sorted(expected))
    for name, status in expected.items():
        a.eq("arguments." + name, cases.get(name), status)
    a.eq("arguments.get-null", result.get("get-null"), True)
    a.eq("arguments.free-null", result.get("free-null"), True)


def case_stores(world, a):
    a.true("stores.observed", len(world.storage) >= 40, len(world.storage))
    for label, storage in world.storage:
        a.eq("stores." + label + ".catalog", storage.get("catalog_before"), storage.get("catalog_after"))
        if storage.get("library_before") == "-":
            a.eq("stores." + label + ".library_skipped", storage.get("library_after"), "-")
            continue
        a.true("stores." + label + ".measured", storage.get("library_before") not in (None, "unreadable"),
               storage.get("library_before"))
        a.eq("stores." + label + ".library", storage.get("library_before"), storage.get("library_after"))


CASES = (
    ("nine-formats-cloud-metadata", case_nine_formats),
    ("cloud-row-without-library", case_cloud_without_library),
    ("local-identity-sha256", case_identity_sha256),
    ("local-identity-size-only", case_identity_size_only),
    ("local-unicode-fields", case_unicode_fields),
    ("local-overlong-fields", case_overlong_fields),
    ("cbz-property-cap", case_cbz_cap),
    ("pdf-pages-without-info", case_pages_without_info),
    ("epub-storage-modes", case_epub_modes),
    ("reflow-no-public-fields", case_reflow_no_fields),
    ("local-mapping-missing", case_mapping_missing),
    ("wrong-book-size-mismatch", case_wrong_size),
    ("wrong-book-bytes-mismatch", case_wrong_bytes),
    ("size-only-identity-limit", case_size_only_limit),
    ("local-unchecked-without-library", case_unchecked),
    ("cancel-at-every-poll", case_cancel_at_every_poll),
    ("snapshot-readable-after-sdk-close", case_lifetime),
    ("independent-public-api-comparison", case_public_api),
    ("foreign-thread-and-immutable-view", case_threads),
    ("reentrant-cancel-callback", case_reentrant),
    ("argument-and-error-contract", case_arguments),
    ("stores-unchanged", None),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True)
    parser.add_argument("--compare", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fixtures = Path(args.fixtures)
    if not (fixtures / "manifest.json").exists():
        make_fixtures.write_fixtures(fixtures)
    world = World(args.probe, args.compare, fixtures, Path(args.work))
    checks = []
    setup_error = None
    try:
        world.build()
    except Failure as error:
        setup_error = str(error)

    if setup_error is not None:
        print(json.dumps({"setup_error": setup_error}, ensure_ascii=False))
    if setup_error is None:
        for name, function in CASES:
            if function is None:
                continue
            asserts = Asserts()
            try:
                function(world, asserts)
            except Failure as error:
                asserts.problems.append(str(error))
            except Exception as error:  # noqa: BLE001 - a harness crash is a named failure
                asserts.problems.append("%s: %s" % (type(error).__name__, error))
            checks.append({"name": name, "ok": not asserts.problems, "assertions": asserts.count,
                           "problems": asserts.problems, "stores_unchanged": None})
        asserts = Asserts()
        case_stores(world, asserts)
        checks.append({"name": "stores-unchanged", "ok": not asserts.problems, "assertions": asserts.count,
                       "problems": asserts.problems, "reads_measured": len(world.storage)})
    else:
        for name in REQUIRED_CASES:
            checks.append({"name": name, "ok": False, "assertions": 0,
                           "problems": ["setup failed: " + setup_error], "stores_unchanged": False})

    source = os.environ.get("GITHUB_SHA", "")
    report = {
        "ok": all(row["ok"] for row in checks) and len(checks) == len(REQUIRED_CASES),
        "package": "EXReaderBookInformation 0.1.0",
        "scope": "installed package snapshot fields on three desktop platforms",
        "source": source,
        "run_id": int(os.environ.get("GITHUB_RUN_ID", "0") or 0),
        "attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0") or 0),
        "platform": args.platform,
        "case_count": len(checks),
        "assertions": sum(row["assertions"] for row in checks),
        "checks": checks,
        "fixtures": world.manifest["books"] if hasattr(world, "manifest") else {},
        "database_sha256": {"catalog": file_digest(world.catalog), "library": file_digest(world.library)},
        "skipped": [],
        "uncovered": list(UNCOVERED),
        "complete_product": False,
        "host_ui_accepted": False,
        "physical_device_execution": False,
        "local_execution_outside_actions": False,
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "cases": report["case_count"], "assertions": report["assertions"],
                      "failed": [row["name"] for row in checks if not row["ok"]]}))
    for row in checks:
        if not row["ok"]:
            print(json.dumps({"case": row["name"], "problems": row["problems"][:12]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
