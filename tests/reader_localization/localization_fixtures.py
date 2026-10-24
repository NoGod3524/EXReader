#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fixed expectations for the J20 zh-CN/en-US localization package.

The table below is the acceptance oracle, not a copy of the library: the
checker compares the installed library's own enumeration and rendering against
these rows, and recomputes the catalog digest from them. A row changed here
without changing the resource pack fails, and the reverse fails too.
"""
import hashlib
import json
from pathlib import Path

COMMON_START = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
PACKAGE = "EXReaderLocalization 0.1.0"
VERSION_STRING = "0.1.0"
ABI_VERSION = 1
CATALOG_FORMAT_VERSION = 1

MAX_MESSAGE_ID = 96
MAX_SLOTS = 8
MAX_VALUE_BYTES = 1024
MAX_OUTPUT_BYTES = 2048

LOCALES = ("zh-CN", "en-US")
GROUPS = ("a11y", "error", "import", "organize", "reading", "shelf", "sync")

# Nothing user-facing may carry a stack frame, a filesystem path, a credential
# label or a platform localization API name.
FORBIDDEN = ("/home/", "C:\\", "0x", "Exception", "stack", "password", "secret",
             "token", "cookie", "Authorization", "errno", "NSLocalizedString",
             "NSError", "SQLite", "GetLastError")

STRING_ARGS = ("Caf\u00e9 \u66f8\u540d \U0001f4da", "\u4f5c\u8005 Author",
               "\u7b2c\u4e09\u7ae0 Chapter 3")
INT_ARGS = (-1234, 57, 0)
UINT_ARGS = (18446744073709551615, 7, 0)

MESSAGES = (
    ("reader.a11y.bookmark_toggle", "a11y", "s",
     "书签，{0}",
     "Bookmark, {0}"),
    ("reader.a11y.error.announce", "a11y", "s",
     "错误：{0}",
     "Error: {0}"),
    ("reader.a11y.import.progress", "a11y", "dd",
     "正在导入第 {0} 个文件，共 {1} 个",
     "Importing file {0} of {1}"),
    ("reader.a11y.organize.tag", "a11y", "s",
     "标签 {0}，已应用",
     "Tag {0}, applied"),
    ("reader.a11y.reader.close", "a11y", "",
     "关闭阅读器",
     "Close reader"),
    ("reader.a11y.reader.page_control", "a11y", "dd",
     "第 {0} 页，共 {1} 页",
     "Page {0} of {1}"),
    ("reader.a11y.shelf.actions", "a11y", "",
     "书籍操作",
     "Book actions"),
    ("reader.a11y.shelf.book", "a11y", "ssd",
     "《{0}》，{1}，已读 {2}%",
     "{0} by {1}, {2}% read"),
    ("reader.a11y.shelf.book_unread", "a11y", "ss",
     "《{0}》，{1}",
     "{0} by {1}"),
    ("reader.a11y.sync.state", "a11y", "sd",
     "同步 {0}，{1} 项等待",
     "Sync {0}, {1} waiting"),
    ("reader.error.account", "error", "",
     "请重新登录以同步",
     "Sign in again to sync"),
    ("reader.error.busy", "error", "",
     "请稍后再试",
     "Try again in a moment"),
    ("reader.error.format", "error", "",
     "这本书的文件已损坏",
     "This book's file is damaged"),
    ("reader.error.import", "error", "s",
     "{0} 需要其他格式",
     "{0} needs a different format"),
    ("reader.error.io", "error", "",
     "书架数据读取失败",
     "The library could not be read"),
    ("reader.error.limit", "error", "d",
     "一次最多添加 {0} 本",
     "Only {0} books can be added at once"),
    ("reader.error.network", "error", "",
     "网络连接失败",
     "The server could not be reached"),
    ("reader.error.permission", "error", "",
     "没有访问此文件的权限",
     "Access to this file is not allowed"),
    ("reader.error.storage", "error", "",
     "存储空间不足",
     "There is not enough space"),
    ("reader.error.unknown", "error", "",
     "出现了一点问题",
     "Something went wrong"),
    ("reader.import.cancelled", "import", "",
     "已取消导入",
     "Import cancelled"),
    ("reader.import.done", "import", "",
     "导入完成",
     "Import finished"),
    ("reader.import.duplicate", "import", "s",
     "{0} 已在书架中",
     "{0} is already in the library"),
    ("reader.import.failed", "import", "s",
     "{0} 导入失败",
     "{0} could not be imported"),
    ("reader.import.file", "import", "s",
     "正在导入 {0}",
     "Importing {0}"),
    ("reader.import.progress", "import", "dd",
     "第 {0} 个，共 {1} 个",
     "{0} of {1}"),
    ("reader.import.title", "import", "",
     "导入",
     "Import"),
    ("reader.import.unsupported", "import", "s",
     "{0} 不是受支持的书籍",
     "{0} is not a supported book"),
    ("reader.organize.author", "organize", "s",
     "作者 {0}",
     "By {0}"),
    ("reader.organize.collection", "organize", "s",
     "藏书集 {0}",
     "Collection {0}"),
    ("reader.organize.count", "organize", "d",
     "{0} 项",
     "{0} items"),
    ("reader.organize.move", "organize", "ss",
     "把 {0} 移到 {1}",
     "Move {0} to {1}"),
    ("reader.organize.remove", "organize", "s",
     "移除 {0}",
     "Remove {0}"),
    ("reader.organize.series", "organize", "s",
     "系列 {0}",
     "Series {0}"),
    ("reader.organize.tag", "organize", "s",
     "标签 {0}",
     "Tag {0}"),
    ("reader.organize.title", "organize", "",
     "整理",
     "Organize"),
    ("reader.reading.bookmark.add", "reading", "",
     "添加书签",
     "Add bookmark"),
    ("reader.reading.chapter", "reading", "s",
     "章节 {0}",
     "Chapter {0}"),
    ("reader.reading.font_size", "reading", "d",
     "字号 {0}",
     "Text size {0}"),
    ("reader.reading.line_spacing", "reading", "d",
     "行距 {0}%",
     "Line spacing {0}%"),
    ("reader.reading.note", "reading", "s",
     "笔记：{0}",
     "Note: {0}"),
    ("reader.reading.page", "reading", "dd",
     "第 {0} 页，共 {1} 页",
     "Page {0} of {1}"),
    ("reader.reading.percent", "reading", "d",
     "{0}%",
     "{0}%"),
    ("reader.reading.theme.dark", "reading", "",
     "深色",
     "Dark"),
    ("reader.reading.theme.light", "reading", "",
     "浅色",
     "Light"),
    ("reader.reading.toc", "reading", "",
     "目录",
     "Contents"),
    ("reader.shelf.book.missing", "shelf", "s",
     "{0} 不可用",
     "{0} is unavailable"),
    ("reader.shelf.book.progress", "shelf", "d",
     "已读 {0}%",
     "{0}% read"),
    ("reader.shelf.count", "shelf", "d",
     "{0} 本",
     "{0} books"),
    ("reader.shelf.empty", "shelf", "",
     "书架还是空的",
     "No books yet"),
    ("reader.shelf.empty_hint", "shelf", "",
     "添加一本书即可开始阅读。",
     "Add a book to start reading."),
    ("reader.shelf.filter.active", "shelf", "s",
     "筛选：{0}",
     "Filter: {0}"),
    ("reader.shelf.sort.label", "shelf", "",
     "排序",
     "Sort"),
    ("reader.shelf.title", "shelf", "",
     "书架",
     "Library"),
    ("reader.sync.account", "sync", "s",
     "账户 {0}",
     "Account {0}"),
    ("reader.sync.conflict", "sync", "s",
     "{0} 在两处被修改",
     "{0} was changed in two places"),
    ("reader.sync.done", "sync", "",
     "同步完成",
     "Sync complete"),
    ("reader.sync.idle", "sync", "",
     "已是最新",
     "Up to date"),
    ("reader.sync.last", "sync", "s",
     "上次同步 {0}",
     "Last synced {0}"),
    ("reader.sync.offline", "sync", "",
     "离线：更改已保存在本机",
     "Offline: changes are saved locally"),
    ("reader.sync.pending", "sync", "d",
     "{0} 项等待同步",
     "{0} waiting to sync"),
    ("reader.sync.running", "sync", "d",
     "正在同步 {0} 项",
     "Syncing {0} items"),
)

def slots(kinds):
    return len(kinds)

def spec_for(kinds):
    parts = []
    for index, kind in enumerate(kinds):
        if kind == "s":
            parts.append("s:" + STRING_ARGS[index].encode("utf-8").hex())
        elif kind == "d":
            parts.append("d:%d" % INT_ARGS[index])
        elif kind == "u":
            parts.append("u:%d" % UINT_ARGS[index])
        else:
            raise ValueError("unknown kind " + kind)
    return "|".join(parts) if parts else "-"

def args_for(kinds):
    values = []
    for index, kind in enumerate(kinds):
        if kind == "s":
            values.append(STRING_ARGS[index])
        elif kind == "d":
            values.append(str(INT_ARGS[index]))
        elif kind == "u":
            values.append(str(UINT_ARGS[index]))
    return values

def render(template, kinds):
    values = args_for(kinds)
    out = []
    index = 0
    while index < len(template):
        character = template[index]
        if character == "{":
            close = template.index("}", index)
            out.append(values[int(template[index + 1:close])])
            index = close + 1
        else:
            out.append(character)
            index += 1
    return "".join(out)

def canonical_digest():
    digest = hashlib.sha256()
    digest.update(b"reader-localization-catalog\t1\n")
    for message_id, group, kinds, _zh, _en in sorted(MESSAGES):
        digest.update(("M\t%s\t%s\t%s\n" % (message_id, group, kinds)).encode("utf-8"))
    for message_id, group, kinds, zh_text, en_text in sorted(MESSAGES):
        digest.update(("T\t%s\tzh-CN\t%s\n" % (message_id, zh_text)).encode("utf-8"))
        digest.update(("T\t%s\ten-US\t%s\n" % (message_id, en_text)).encode("utf-8"))
    return digest.hexdigest()

def message_rows():
    return [(message_id, group, kinds, zh_text, en_text)
            for message_id, group, kinds, zh_text, en_text in MESSAGES]

def matrix_lines():
    lines = []
    for message_id, _group, kinds, _zh, _en in MESSAGES:
        for locale in LOCALES:
            lines.append("\t".join((message_id, locale, spec_for(kinds), "-")))
    return lines

def refusal_rows():
    rows = []
    page = "reader.reading.page"          # 'dd'
    title = "reader.shelf.title"          # no slots
    missing = "reader.shelf.book.missing" # 's'
    move = "reader.organize.move"         # 'ss'

    rows.append((page, "en-US", "-", "4096", "PARAMETER_COUNT"))
    rows.append((page, "zh-CN", "d:1|d:2|d:3", "4096", "PARAMETER_COUNT"))
    rows.append((title, "en-US", "d:1", "4096", "PARAMETER_COUNT"))
    rows.append((page, "en-US", "s:78|d:2", "4096", "PARAMETER_TYPE"))
    rows.append((page, "en-US", "d:1|u:2", "4096", "PARAMETER_TYPE"))
    rows.append((move, "en-US", "s:78|u:2", "4096", "PARAMETER_TYPE"))
    rows.append(("reader.reading.bookmark.add", "en-US", "-", "4096", "OK"))
    rows.append(("reader.does.not.exist", "en-US", "-", "4096", "UNKNOWN_MESSAGE"))
    rows.append(("x" * 120, "en-US", "-", "4096", "ARGUMENT"))
    for payload in ("c0af", "eda080", "f5808080", "e282", "80"):
        rows.append((missing, "en-US", "s:" + payload, "4096", "VALUE_INVALID"))
    rows.append((missing, "zh-CN", "s:c0af", "4096", "VALUE_INVALID"))
    rows.append((missing, "en-US", "s:" + ("78" * MAX_VALUE_BYTES), "4096", "OK"))
    rows.append((missing, "en-US", "s:" + ("78" * (MAX_VALUE_BYTES + 1)), "4096", "VALUE_TOO_LONG"))
    rows.append((move, "en-US", "s:" + ("61" * MAX_VALUE_BYTES) + "|s:" + ("62" * MAX_VALUE_BYTES),
                 "4096", "LIMIT"))
    rows.append((missing, "en-US", spec_for("s"), "8", "CAPACITY"))
    rows.append((missing, "en-US", "s:78", "1", "CAPACITY"))
    rows.append((title, "en-US", "-", "0", "CAPACITY"))
    return rows

def capacity_exact_rows():
    rows = []
    for message_id, _group, kinds, _zh, _en in MESSAGES:
        length = len(render(_zh, kinds)) + 1
        rows.append((message_id, "zh-CN", spec_for(kinds), str(length), "OK"))
    return rows

def write_fixtures(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    expectations = {
        "package": PACKAGE,
        "version": VERSION_STRING,
        "abi": ABI_VERSION,
        "catalog_format": CATALOG_FORMAT_VERSION,
        "limits": {"message_id": MAX_MESSAGE_ID, "slots": MAX_SLOTS,
                   "value_bytes": MAX_VALUE_BYTES, "output_bytes": MAX_OUTPUT_BYTES},
        "digest": canonical_digest(),
        "groups": list(GROUPS),
        "forbidden": list(FORBIDDEN),
        "messages": [{"id": row[0], "group": row[1], "kinds": row[2], "zh-CN": row[3],
                      "en-US": row[4], "expected": {"zh-CN": render(row[3], row[2]),
                                                    "en-US": render(row[4], row[2])}}
                     for row in MESSAGES],
    }
    (directory / "expectations.json").write_text(
        json.dumps(expectations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "matrix.tsv").write_text("\n".join(matrix_lines()) + "\n", encoding="utf-8")
    (directory / "refusals.tsv").write_text(
        "\n".join("\t".join(row) for row in refusal_rows() + capacity_exact_rows()) + "\n",
        encoding="utf-8")
    return directory
