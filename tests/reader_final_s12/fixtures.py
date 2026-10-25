#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Freeze the S12 request container and the independent expectation.

This script is the only input source for the two installed consumers. It emits

  cases.bin     one binary container of UTF-16LE code units (all Unicode text
                and every Unicode path component) plus ASCII identity records
  expected.json the exact per-record result derived from the published public
                contracts, never by running the implementation under test
  meta.json     digests of the two files above

The expectations come from the public headers and the published product
migration only: the schema-1 column checks, the catalog keyset/BINARY ordering
and ASCII-only lower() folding, the raw metadata 0.2 ownership contract, the
counted reader_command_utf16 boundary, the typed command wire document and the
account-profile field rules. Nothing is imported from apps/ or tests/.
"""
import argparse
import hashlib
import json
import os
import struct
import sys

# --------------------------------------------------------------------- texts
DIR_WORKSPACE = "库 S12 测试 📚"
DIR_SPACE = "café-组合 空格"
DIR_LIBRARY = "Café 书库"
DIR_BOOK = "原件 入口 📚"
DIR_ACCOUNTS = "账户 隔离 📁"
FILE_MAIN = "书库 S12.sqlite"
FILE_MIRROR = "镜像 书库.sqlite"
FILE_PROBE = "探针 书库.sqlite"
FILE_LONG = "长路径 书库.sqlite"
FILE_OVERLONG = "超长 书库.sqlite"
FILE_PENDING = "待提交 元数据.intent"
FILE_NOTADB = "不是数据库.bin"

SEGMENT_LONG = "长路径-0123456789abcdefghij"
SEGMENT_OVERLONG = "超长路径段-0123456789abcdefghij"

TITLE_NFC = "Café 特集 👩🏽‍💻"
TITLE_NFD = "Cafe\u0301 特集 👩🏽‍💻"
TITLE_UPPER = "ÜNÏ 书库"
TITLE_SPACES = "  前后 空格  "
TITLE_TAB = "tab\tinside"
TITLE_QUOTES = "quote\"back\\slash"
TITLE_LONG = "章" * 300 + " 长"
TITLE_EXTERNAL = "ÜNÏ 书库 v2"
AUTHOR_ASCII = "Author A"
AUTHOR_CJK = "作者：曹雪芹"
AUTHOR_UPPER = "Ünï"
AUTHOR_EMPTY = ""
PROBE_TITLE = "探针 一号"
PROBE_AUTHOR = "探针作者"

ACCOUNT_NAME_NFC = "书库 账户 é"
ACCOUNT_NAME_NFD = "书库 账户 e\u0301"
ACCOUNT_NAME_UPPER = "ÜNÏ 账户"
ACCOUNT_NAME_LOWER = "Ünï 账户"
ACCOUNT_NAME_RENAME = "改名 账户 📚"

QUERY_ASCII = "AUTHOR a"
QUERY_UNICODE = "ünï"

TEXT_ITEMS = {
    "dir.workspace": DIR_WORKSPACE,
    "dir.space": DIR_SPACE,
    "dir.library": DIR_LIBRARY,
    "dir.book": DIR_BOOK,
    "dir.accounts": DIR_ACCOUNTS,
    "file.main": FILE_MAIN,
    "file.mirror": FILE_MIRROR,
    "file.probe": FILE_PROBE,
    "file.long": FILE_LONG,
    "file.overlong": FILE_OVERLONG,
    "file.pending": FILE_PENDING,
    "file.notadb": FILE_NOTADB,
    "title.nfc": TITLE_NFC,
    "title.nfd": TITLE_NFD,
    "title.upper": TITLE_UPPER,
    "title.spaces": TITLE_SPACES,
    "title.tab": TITLE_TAB,
    "title.quotes": TITLE_QUOTES,
    "title.long": TITLE_LONG,
    "title.external": TITLE_EXTERNAL,
    "title.empty": "",
    "author.ascii": AUTHOR_ASCII,
    "author.cjk": AUTHOR_CJK,
    "author.upper": AUTHOR_UPPER,
    "author.empty": AUTHOR_EMPTY,
    "query.ascii": QUERY_ASCII,
    "query.unicode": QUERY_UNICODE,
    "account.name.nfc": ACCOUNT_NAME_NFC,
    "account.name.nfd": ACCOUNT_NAME_NFD,
    "account.name.upper": ACCOUNT_NAME_UPPER,
    "account.name.lower": ACCOUNT_NAME_LOWER,
    "account.name.rename": ACCOUNT_NAME_RENAME,
    "dir.long.segment": SEGMENT_LONG,
    "dir.overlong.segment": SEGMENT_OVERLONG,
    "probe.1.title": PROBE_TITLE,
    "probe.1.author": PROBE_AUTHOR,
    "probe.1.sort": PROBE_TITLE,
    "probe.2.title": "",
    "probe.2.author": "",
    "probe.2.sort": "",
    "utf16.pair": "📚",
    "utf16.long": "章" * 4096,
}

# Raw UTF-16LE payloads that are not valid UTF-16 strings on purpose.
UNIT_ITEMS = {
    "utf16.surrogate.high": [0xD83D],
    "utf16.surrogate.low": [0xDC00],
}

ASCII_ITEMS = {
    "dir.long.count": "4",
    "dir.overlong.count": "12",
}

def digest(seed):
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()

BOOKS = [
    dict(index=1, format="txt", title=TITLE_NFC, author=AUTHOR_ASCII, sort=TITLE_NFC,
         bytes=4096, favorite=1, sdk=11, loc="reflow_global"),
    dict(index=2, format="epub", title=TITLE_NFD, author=AUTHOR_CJK, sort=TITLE_NFD,
         bytes=8192, favorite=0, sdk=12, loc="epub_chapter"),
    dict(index=3, format="pdf", title=TITLE_UPPER, author=AUTHOR_UPPER, sort=TITLE_UPPER,
         bytes=16384, favorite=0, sdk=13, loc="fixed_page"),
    dict(index=4, format="cbz", title=TITLE_SPACES, author=AUTHOR_EMPTY, sort=TITLE_SPACES,
         bytes=32768, favorite=1, sdk=14, loc="fixed_page"),
    dict(index=5, format="txt", title=TITLE_TAB, author=AUTHOR_ASCII, sort=TITLE_TAB,
         bytes=65536, favorite=0, sdk=15, loc="reflow_global"),
    dict(index=6, format="epub", title=TITLE_QUOTES, author=AUTHOR_ASCII, sort=TITLE_QUOTES,
         bytes=131072, favorite=0, sdk=16, loc="epub_chapter"),
]
for book in BOOKS:
    book["sha"] = digest("s12:book:%d" % book["index"])
    book["key"] = "%s:%s" % (book["format"], book["sha"])

PROBE_BOOKS = [
    dict(index=1, format="txt", title=PROBE_TITLE, author=PROBE_AUTHOR, sort=PROBE_TITLE,
         bytes=1024, favorite=0, sdk=101, loc="reflow_global", sha=digest("s12:probe:1")),
    dict(index=2, format="txt", title="", author="", sort="",
         bytes=2048, favorite=0, sdk=102, loc="reflow_global", sha=digest("s12:probe:2")),
]
for book in PROBE_BOOKS:
    book["key"] = "%s:%s" % (book["format"], book["sha"])

ACCOUNTS = [
    dict(id="11111111-1111-4111-8111-111111111111", account="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
         url="https://sync.example.test/s12/", name=ACCOUNT_NAME_NFC),
    dict(id="22222222-2222-4222-8222-222222222222", account="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
         url="https://sync.example.test/s12-b/", name=ACCOUNT_NAME_NFD),
    dict(id="33333333-3333-4333-8333-333333333333", account="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
         url="https://sync.example.test/s12-c/", name=ACCOUNT_NAME_UPPER),
    dict(id="44444444-4444-4444-8444-444444444444", account="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
         url="https://sync.example.test/s12-d/", name=ACCOUNT_NAME_LOWER),
]
ACCOUNT_URLS = {
    "account.url.one": ACCOUNTS[0]["url"],
    "account.url.two": ACCOUNTS[1]["url"],
    "account.url.three": ACCOUNTS[2]["url"],
    "account.url.four": ACCOUNTS[3]["url"],
    "account.url.secret": "https://user:pass@sync.example.test/s12/",
    "account.url.query": "https://sync.example.test/s12/?token=1",
    "account.url.http": "http://sync.example.test/s12/",
    "account.url.space": "https://sync.example.test/s12 space/",
}
for index, account in enumerate(ACCOUNTS, start=1):
    ASCII_ITEMS["account.id.%d" % index] = account["id"]
    ASCII_ITEMS["account.acct.%d" % index] = account["account"]
ASCII_ITEMS["account.id.5"] = "55555555-5555-4555-8555-555555555555"
ASCII_ITEMS["account.id.6"] = "66666666-6666-4666-8666-666666666666"
ASCII_ITEMS["account.id.7"] = "77777777-7777-4777-8777-777777777777"
ASCII_ITEMS["account.acct.6"] = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
ASCII_ITEMS["account.acct.7"] = "ffffffff-ffff-4fff-8fff-ffffffffffff"
for key, value in ACCOUNT_URLS.items():
    ASCII_ITEMS[key] = value

for book in BOOKS:
    prefix = "book.%d" % book["index"]
    TEXT_ITEMS[prefix + ".title"] = book["title"]
    TEXT_ITEMS[prefix + ".author"] = book["author"]
    TEXT_ITEMS[prefix + ".sort"] = book["sort"]
    ASCII_ITEMS[prefix + ".key"] = book["key"]
    ASCII_ITEMS[prefix + ".format"] = book["format"]
    ASCII_ITEMS[prefix + ".sha"] = book["sha"]
    ASCII_ITEMS[prefix + ".loc"] = book["loc"]
    ASCII_ITEMS[prefix + ".bytes"] = str(book["bytes"])
    ASCII_ITEMS[prefix + ".fav"] = str(book["favorite"])
    ASCII_ITEMS[prefix + ".sdk"] = str(book["sdk"])
for book in PROBE_BOOKS:
    prefix = "probe.%d" % book["index"]
    ASCII_ITEMS[prefix + ".key"] = book["key"]
    ASCII_ITEMS[prefix + ".format"] = book["format"]
    ASCII_ITEMS[prefix + ".sha"] = book["sha"]
    ASCII_ITEMS[prefix + ".loc"] = book["loc"]
    ASCII_ITEMS[prefix + ".bytes"] = str(book["bytes"])
    ASCII_ITEMS[prefix + ".fav"] = str(book["favorite"])
    ASCII_ITEMS[prefix + ".sdk"] = str(book["sdk"])

REVISION_EXTERNAL = "00112233445566778899aabbccddeeff"
REVISION_COMPETE_ONE = "0f0f0f0f0f0f4f0f8f0f0f0f0f0f0f01"
REVISION_COMPETE_TWO = "0f0f0f0f0f0f4f0f8f0f0f0f0f0f0f02"
ASCII_ITEMS["revision.external"] = REVISION_EXTERNAL
ASCII_ITEMS["revision.compete.1"] = REVISION_COMPETE_ONE
ASCII_ITEMS["revision.compete.2"] = REVISION_COMPETE_TWO

# ------------------------------------------------------------- expectations
def hex_bytes(text):
    return text.encode("utf-8").hex()


def quote(value):
    """The published typed-command string escaping: quote, backslash and C0."""
    out = bytearray(b'"')
    for byte in value.encode("utf-8"):
        if byte == 0x22 or byte == 0x5C:
            out += b"\\" + bytes([byte])
        elif byte < 32:
            out += b"\\u00" + ("%02x" % byte).encode("ascii")
        else:
            out.append(byte)
    out += b'"'
    return out.decode("utf-8")


def wire_template(book):
    return ('{"version":1,"id":"@@ID@@","entity_kind":"book","entity_key":"%s",'
            '"operation":"put","location_kind":"none","parents":[],"payload":{'
            '"format":"%s","source_sha256":"%s","source_bytes":%d,"title":%s,"author":%s,'
            '"favorite":%s}}') % (book["key"], book["format"], book["sha"], book["bytes"],
                                  quote(book["title"]), quote(book["author"]),
                                  "true" if book["favorite"] else "false")


def lower_ascii(raw):
    return bytes((byte + 32) if 65 <= byte <= 90 else byte for byte in raw)


def contains(haystack, needle):
    if not needle:
        return True
    return lower_ascii(haystack.encode("utf-8")).find(lower_ascii(needle.encode("utf-8"))) >= 0


def row_text(book, sdk=None, location=None):
    return ("titlehex=%s;authorhex=%s;sorthex=%s;key=%s;format=%s;bytes=%d;fav=%d;sdk=%d;loc=%s;deleted=0"
            % (hex_bytes(book["title"]), hex_bytes(book["author"]), hex_bytes(book["sort"]),
               book["key"], book["format"], book["bytes"], book["favorite"],
               book["sdk"] if sdk is None else sdk,
               book["loc"] if location is None else location))


def ordered(books):
    return sorted(books, key=lambda item: (item["sort"].encode("utf-8"), item["key"].encode("utf-8")))


def forward_page(rows, cursor, limit):
    if cursor is None:
        return rows[:limit]
    index = rows.index(cursor)
    return rows[index + 1:index + 1 + limit]


def reverse_page(rows, cursor, limit):
    descending = list(reversed(rows))
    if cursor is None:
        return descending[:limit]
    index = descending.index(cursor)
    return descending[index + 1:index + 1 + limit]


def joined(page, sdk=None, location=None):
    return "|".join(row_text(book, sdk, location) for book in page)


RECORDS = {}


def put(name, **fields):
    if name in RECORDS:
        raise SystemExit("duplicate expected record " + name)
    RECORDS[name] = {key: str(value) for key, value in fields.items()}


CONVERSIONS = [
    "dir.workspace", "dir.space", "dir.library", "dir.book", "dir.accounts",
    "file.main", "file.mirror", "file.probe", "file.long", "file.pending",
    "title.nfc", "title.nfd", "title.upper", "title.spaces", "title.tab",
    "title.quotes", "title.long", "author.ascii", "author.cjk", "author.upper",
    "author.empty", "title.empty", "account.name.nfc", "account.name.nfd",
    "account.name.upper", "account.name.lower", "account.name.rename",
]

for item in CONVERSIONS:
    text = TEXT_ITEMS[item]
    put("utf16." + item, status=0, bytes=len(text.encode("utf-8")), hex=hex_bytes(text))
put("utf16.nul.rejected", status=1, bytes=0, hex="")
put("utf16.surrogate.high", status=1, bytes=0, hex="")
put("utf16.surrogate.low", status=1, bytes=0, hex="")
put("utf16.nonbmp.pair", status=0, bytes=4, hex=hex_bytes("📚"))
put("utf16.capacity.short", status=1, bytes=0)
put("utf16.capacity.exact", status=0, bytes=4, hex=hex_bytes("📚"))
put("utf16.units.over", status=1, bytes=0)
put("utf16.null.zero", status=0, bytes=0, hex="")
put("utf16.long", status=0, bytes=len(("章" * 4096).encode("utf-8")), hex=hex_bytes("章" * 4096))

# ------------------------------------------------------- account isolation
put("account.validate.nfc", status=0)
put("account.add.nfc", status=0, generation=1)
put("account.add.nfd", status=0, generation=2)
put("account.add.upper", status=0, generation=3)
put("account.add.lower", status=0, generation=4)
load_fields = dict(status=0, count=4, generation=4)
for index, account in enumerate(ACCOUNTS):
    load_fields["name.%d" % index] = hex_bytes(account["name"])
    load_fields["id.%d" % index] = account["id"]
put("account.load.base", **load_fields)
put("account.add.duplicate_pair", status=10, count_after=4, generation_after=4)
put("account.validate.userinfo", status=6)
put("account.validate.query", status=6)
put("account.validate.http", status=5)
put("account.validate.space", status=5)
put("account.validate.empty_name", status=5)
put("account.plan.one", status=0,
    product="profiles/%s/library.sqlite" % ACCOUNTS[0]["id"],
    private="profiles/%s/private" % ACCOUNTS[0]["id"],
    originals="profiles/%s/originals" % ACCOUNTS[0]["id"],
    profile=ACCOUNTS[0]["id"])
put("account.plan.two", status=0,
    product="profiles/%s/library.sqlite" % ACCOUNTS[1]["id"], distinct=1)
put("account.plan.verify", status=0)
put("account.plan.tampered", status=1)
put("account.rename", status=0, generation=5, **{"name.3": hex_bytes(ACCOUNT_NAME_RENAME)})
put("account.remove", status=0, generation=6, count_after=3)
put("account.store.relative", status=1)
put("account.nul.store", status=2, truncated_created=0)

# --------------------------------------------------- original book entries
put("attach.open", status=0, error=0)
for book in BOOKS:
    put("attach.seed.%d" % book["index"], status=0, error=0)
rows = ordered(BOOKS)
put("attach.page.all", status=0, error=0, rows=len(rows), joined=joined(rows))
page0 = forward_page(rows, None, 2)
page1 = forward_page(rows, page0[-1], 2)
page2 = forward_page(rows, page1[-1], 2)
put("attach.page.forward.0", status=0, error=0, rows=len(page0), joined=joined(page0))
put("attach.page.forward.1", status=0, error=0, rows=len(page1), joined=joined(page1))
put("attach.page.forward.2", status=0, error=0, rows=len(page2), joined=joined(page2))
descending = list(reversed(rows))
put("attach.page.reverse.all", status=0, error=0, rows=len(descending), joined=joined(descending))
rpage0 = reverse_page(rows, None, 2)
rpage1 = reverse_page(rows, rpage0[-1], 2)
put("attach.page.reverse.0", status=0, error=0, rows=len(rpage0), joined=joined(rpage0))
put("attach.page.reverse.1", status=0, error=0, rows=len(rpage1), joined=joined(rpage1))

def query_rows(query):
    return [book for book in rows if contains(book["title"], query) or contains(book["author"], query)]

put("attach.query.ascii", status=0, error=0, rows=len(query_rows(QUERY_ASCII)),
    joined=joined(query_rows(QUERY_ASCII)))
put("attach.query.unicode", status=0, error=0, rows=len(query_rows(QUERY_UNICODE)),
    joined=joined(query_rows(QUERY_UNICODE)))
put("attach.query.nfd", status=0, error=0, rows=len(query_rows(TITLE_NFD)),
    joined=joined(query_rows(TITLE_NFD)))
put("attach.query.empty", status=0, error=0, rows=len(rows), joined=joined(rows))
put("attach.query.null", status=0, error=0, rows=len(rows), joined=joined(rows))

def canonical_rows(nfc, nfd):
    return [book for book in rows
            if contains(book["sort"], nfc) or contains(book["author"], nfc) or contains(book["author"], nfd)]

NFC, NFD = BOOKS[0]["sort"], BOOKS[1]["sort"]
put("attach.canonical.nfc", status=0, error=0, rows=len(canonical_rows(NFC, NFD)),
    joined=joined(canonical_rows(NFC, NFD)))
put("attach.canonical.nfd", status=0, error=0, rows=len(canonical_rows(NFD, NFC)),
    joined=joined(canonical_rows(NFD, NFC)))
put("attach.canonical.null", status=21, error=21, rows=0, joined="")
put("attach.canonical.empty", status=0, error=0, rows=len(rows), joined=joined(rows))
put("attach.lookup.id", status=0, found=1, rows=1, joined=row_text(BOOKS[2]))
put("attach.lookup.title", status=0, found=1, rows=1, joined=row_text(BOOKS[3]))
put("attach.lookup.null", status=21, found=0)
put("attach.lookup.empty", status=0, found=0, rows=0)
put("attach.metadata.one", status=0, found=1, rows=1, joined=row_text(BOOKS[0]))
put("attach.metadata.two", status=0, found=1, rows=1, joined=row_text(BOOKS[1]))
put("attach.metadata.three", status=0, found=1, rows=1, joined=row_text(BOOKS[2]))
put("attach.metadata.missing", status=0, found=0, rows=0, joined="")
put("attach.metadata.null", status=21, found=0)
put("attach.metadata.empty", status=0, found=0)
put("attach.repeat", status=0, error=0)
put("stability.main.reattach", equal=1, reason="identical")

# ------------------------------------------------- raw metadata 0.2 profile
put("metadata.version", metadata="0.2.0", revisions="0.4.0", commands="0.2.0", raw=1)
put("metadata.open.legacy", status=6, handle=0)
put("metadata.open.raw", status=0)
put("metadata.open.same_path", status=6, handle=0)
put("metadata.open.second", status=7, handle=0)
put("metadata.prepare.book1.bootstrap", status=2, present=1, deleted=0, needs_bootstrap=1, heads=0,
    titlehex=hex_bytes(BOOKS[0]["title"]), authorhex=hex_bytes(BOOKS[0]["author"]),
    sorthex=hex_bytes(BOOKS[0]["sort"]), author_null=0)
put("metadata.stage.book1.ordinary", status=2, error=2)
put("metadata.pending.none", status=1)
put("metadata.stage.book1.badsource", status=6, error=6)
put("metadata.stage.book1.bootstrap", status=0, revision_len=32, key=BOOKS[0]["key"])
put("metadata.pending.staged", status=0, pending=1, committed=0, same_revision=1)
put("metadata.apply.book1", status=0, committed=1, created=1)
put("metadata.reopen.pending", status=0, sidecar_present=1, pending_status=0, pending=1, same_revision=1)
put("stability.sidecar", equal=1, reason="identical")
put("metadata.finish.book1", status=0, committed=1, pending=0, sidecar_absent=1)
put("metadata.pending.after_finish", status=1, pending=0)
put("metadata.prepare.book1.after", status=0, present=1, deleted=0, needs_bootstrap=0, heads=1,
    titlehex=hex_bytes(BOOKS[0]["title"]), authorhex=hex_bytes(BOOKS[0]["author"]),
    sorthex=hex_bytes(BOOKS[0]["sort"]), author_null=0, head_matches=1)
put("metadata.shared.open", status=0)
template_one = wire_template(BOOKS[0])
put("metadata.get.book1", status=0, bytes=len(template_one.replace("@@ID@@", "0" * 32)),
    entity="book", operation="put", parents=0, book_key=BOOKS[0]["key"])
put("metadata.book4.bootstrap", prepare=2, stage=0, revision_len=32, finish=0)
put("metadata.book4.null_author", prepare=0, status=6, error=6)
put("metadata.book4.empty_author", status=0, revision_len=32, finish=0)
put("metadata.book4.view", status=0, authorhex="", author_null=0, heads=1)
put("metadata.book2.bootstrap", prepare=2, stage=0, finish=0, revision_len=32)
put("metadata.book2.edit", status=0, revision_len=32, finish=0)
put("metadata.book2.retained_title", status=0, hex=hex_bytes(TITLE_NFD))
put("metadata.book2.new_title", status=0, hex=hex_bytes(TITLE_NFC))
put("metadata.book3.bootstrap", prepare=2, stage=0, revision_len=32, finish=0)
put("metadata.book3.stale", status=0, heads=1)
put("metadata.book3.external", revision=REVISION_EXTERNAL, created=1, status=0)
put("metadata.book3.stage", status=0, error=0)
put("metadata.book3.apply_conflict", status=3, committed=0, pending=1, error=3)
put("metadata.book3.pending_after_conflict", status=0, pending=1)
put("metadata.book3.row_after_conflict", status=0, titlehex=hex_bytes(TITLE_EXTERNAL),
    head_is_external=1, heads=1)
put("metadata.book3.abandon", status=0)
put("metadata.book3.pending_after_abandon", status=1, pending=0)
put("metadata.book5.bootstrap", prepare=2, stage=0, revision_len=32, finish=0)
put("metadata.book5.wire", status=0,
    bytes=len(wire_template(BOOKS[4]).replace("@@ID@@", "0" * 32)))
put("metadata.book5.receive.one", status=0, created=1, revision=REVISION_COMPETE_ONE)
put("metadata.book5.receive.two", status=0, created=1, revision=REVISION_COMPETE_TWO)
put("metadata.book5.prepare", status=3, heads=2,
    head0=min(REVISION_COMPETE_ONE, REVISION_COMPETE_TWO),
    head1=max(REVISION_COMPETE_ONE, REVISION_COMPETE_TWO),
    titlehex=hex_bytes(BOOKS[4]["title"]))
put("metadata.book5.stage", status=3, error=3)
put("metadata.book5.pending", status=1, pending=0)
put("metadata.reopen", status=0, pending_status=1, prepare=0, head_matches=1,
    titlehex=hex_bytes(BOOKS[0]["title"]), sidecar_absent=1)
put("stability.main.reopen", equal=1, reason="identical")
put("stability.wire.reopen", status=0, equal=1)

# --------------------------------------------------------- re-sync mirror
put("resync.open", status=0)
put("resync.receive.first", status=0, created=1, revision_len=32)
put("resync.receive.second", status=0, created=0)
put("stability.mirror.receive", equal=1, reason="identical")
put("resync.receive.badsha", status=6)
put("resync.receive.tampered", status=6)
put("resync.reopen", status=0, receive=0, created=0)
put("stability.mirror.reopen", equal=1, reason="identical")
put("resync.project", status=0, revision_len=32)
put("resync.heads", status=0, heads=1, head_is_primary=1)
put("resync.selected", status=0, selection=4, equal_wire=1)
put("resync.catalog", status=0)
put("resync.metadata", status=0, found=1, rows=1,
    joined=row_text(BOOKS[0], sdk=0, location="<null>"))
put("resync.local.rows", status=0, rows=0)

# ----------------------------------------------------- negative book entry
put("probe.open", status=0)
put("probe.seed", one=0, two=0)
probe_rows = ordered(PROBE_BOOKS)
put("probe.page", status=0, error=0, rows=len(probe_rows), joined=joined(probe_rows))
put("probe.upper_sha", status=21, error=21)
put("probe.zero_bytes", status=21, error=21)
put("probe.zero_sdk", status=21)
put("probe.null_title", status=21, error=21)
put("probe.conflict.bytes", status=19, error=19)
put("probe.conflict.sdk", status=19, error=19)
put("probe.after_negatives", status=0, error=0, rows=len(probe_rows), joined=joined(probe_rows))
put("probe.metadata.empty_title", status=0, found=1, rows=1, joined=row_text(PROBE_BOOKS[1]))

# ------------------------------------------------------------ long paths
put("path.long.create", status=0)
put("path.long.open", status=0, error=0)
put("path.long.attach", status=0)
put("path.long.reopen", status=0, rows=1)

# ------------------------------------------- embedded NUL in a path
put("nul.product", status="$nonzero", decoy_unchanged=1, metadata_status="$nonzero", handle=0)

# ------------------------------------------------------------- C consumer
C_RECORDS = {}


def c_put(name, **fields):
    if name in C_RECORDS:
        raise SystemExit("duplicate expected C record " + name)
    C_RECORDS[name] = {key: str(value) for key, value in fields.items()}

c_put("c.version", commands="0.2.0", revisions="0.4.0")
for item in ("title.nfc", "author.cjk", "file.main"):
    text = TEXT_ITEMS[item]
    c_put("c.utf16." + item.replace("file.", "file."), status=0, bytes=len(text.encode("utf-8")),
          hex=hex_bytes(text))
c_put("c.utf16.nul", status=1, bytes=0, hex="")
c_put("c.catalog.open", status=0, error=0)
c_put("c.page.all", status=0, error=0, rows=len(rows), joined=joined(rows))
c_put("c.rows", count=len(rows))
c_put("c.page.forward.0", status=0, error=0, rows=len(page0), joined=joined(page0))
c_put("c.query.ascii", status=0, error=0, rows=len(query_rows(QUERY_ASCII)),
      joined=joined(query_rows(QUERY_ASCII)))
c_put("c.query.unicode", status=0, error=0, rows=len(query_rows(QUERY_UNICODE)),
      joined=joined(query_rows(QUERY_UNICODE)))
c_put("c.canonical.nfc", status=0, error=0, rows=len(canonical_rows(NFC, NFD)),
      joined=joined(canonical_rows(NFC, NFD)))
c_put("c.canonical.null", status=21, error=21, rows=0, joined="")
c_put("c.lookup.id", status=0, found=1, rows=1, joined=row_text(BOOKS[2]))
c_put("c.metadata.one", status=0, found=1, rows=1, joined=row_text(BOOKS[0]))
c_put("c.metadata.two", status=0, found=1, rows=1, joined=row_text(BOOKS[1]))
c_put("c.metadata.empty", status=0, found=0, rows=0, joined="")
c_put("c.metadata.null", status=21, found=0, rows=0, joined="")

# ------------------------------------------------------------------ output
KINDS = {}


def write_container(path):
    payload = bytearray(b"S121")
    payload += struct.pack("<II", 1, 0)
    records = []
    for name, text in TEXT_ITEMS.items():
        records.append((name, 1, text.encode("utf-16-le")))
        KINDS[name] = 1
    records.append(("nul.product", 2, (FILE_NOTADB + "\x00" + "tail").encode("utf-16-le")))
    KINDS["nul.product"] = 2
    for name, units in UNIT_ITEMS.items():
        raw = b"".join(struct.pack("<H", unit) for unit in units)
        records.append((name, 1, raw))
        KINDS[name] = 1
    for name, text in ASCII_ITEMS.items():
        records.append((name, 0, text.encode("ascii")))
        KINDS[name] = 0
    body = bytearray()
    for name, kind, raw in records:
        name_bytes = name.encode("ascii")
        body += struct.pack("<I", len(name_bytes)) + name_bytes
        body += struct.pack("<II", kind, len(raw)) + raw
    payload[8:12] = struct.pack("<I", len(records))
    payload += body
    with open(path, "wb") as handle:
        handle.write(bytes(payload))
    return len(records)


def sha256_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    options = parser.parse_args()
    if not os.path.isdir(options.out):
        os.makedirs(options.out)

    case_path = os.path.join(options.out, "cases.bin")
    count = write_container(case_path)

    expected = {
        "format": "s12-1",
        "implementation": "S12 Unicode paths and library-state regression",
        "records": RECORDS,
        "required_consumer": sorted(RECORDS),
        "c_records": C_RECORDS,
        "required_c": sorted(C_RECORDS),
        "aliases": {},
        "derived": {
            "metadata.wire.book1": {
                "template": template_one,
                "id_field": "revision",
                "sha_field": "sha",
                "hex_field": "hex",
                "id_length": 32,
            }
        },
        "ownership": {
            "schema": 1,
            "wire": 1,
            "metadata_profile": "0.2.0",
            "revisions_profile": "0.4.0",
            "commands_profile": "0.2.0",
        },
    }
    expected_path = os.path.join(options.out, "expected.json")
    with open(expected_path, "w", encoding="ascii", newline="\n") as handle:
        json.dump(expected, handle, ensure_ascii=True, sort_keys=True, indent=1)
        handle.write("\n")

    meta = {
        "format": "s12-1",
        "records": count,
        "consumer_records": len(RECORDS),
        "c_records": len(C_RECORDS),
        "kinds": KINDS,
        "case_file_sha256": sha256_file(case_path),
        "expected_sha256": sha256_file(expected_path),
    }
    with open(os.path.join(options.out, "meta.json"), "w", encoding="ascii", newline="\n") as handle:
        json.dump(meta, handle, ensure_ascii=True, sort_keys=True, indent=1)
        handle.write("\n")
    print("S12 fixtures: %d container records, %d consumer expectations, %d C expectations"
          % (count, len(RECORDS), len(C_RECORDS)))
    print("cases.bin %s" % meta["case_file_sha256"])
    print("expected.json %s" % meta["expected_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
