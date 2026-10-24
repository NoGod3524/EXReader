#!/usr/bin/env python3
"""Create the batch-import fixture tree.

Only the generated build tree is written. The frozen repository fixtures are
read-only inputs. Every regular file that the enumerator must consider is
recorded with its exact bytes and SHA-256.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

NINE = [
    ("plain.txt", "sample.txt", "TXT"),
    ("sample.html", "sample.html", "HTML"),
    ("sample.fb2", "sample.fb2", "FB2"),
    ("sample.epub", "sample.epub", "EPUB"),
    ("sample.docx", "sample.docx", "DOCX"),
    ("sample.rtf", "sample.rtf", "RTF"),
    ("sample.mobi", "sample.mobi", "MOBI"),
    ("sample.azw3", "kf8-basic.azw3", "MOBI"),
    ("pdf-public-text.pdf", "pdf-public-text.pdf", "PDF"),
    ("comic.cbz", "comic.cbz", "CBZ"),
]


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def record(files, root, relative, fmt, valid=True, category="book",
           duplicate_group=None):
    path = os.path.join(root, *relative.split("/"))
    files.append({
        "relative": relative,
        "path": path,
        "format": fmt,
        "valid": valid,
        "category": category,
        "duplicate_group": duplicate_group,
        "sha256": digest(path),
        "size": os.path.getsize(path),
    })


def copy_fixture(fixtures, root, relative, source):
    target = os.path.join(root, *relative.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(os.path.join(fixtures, source), target)
    return target


def make_junction(link, target):
    if os.name != "nt":
        try:
            os.symlink(target, link, target_is_directory=True)
            return True, "symlink"
        except OSError as exc:
            return False, str(exc)
    try:
        result = subprocess.run(
            ["cmd", "/c", 'mklink /J "{}" "{}"'.format(link, target)],
            capture_output=True, text=True)
        return result.returncode == 0, (result.stderr or result.stdout).strip()
    except OSError as exc:
        return False, str(exc)


def make_file_link(link, target):
    try:
        os.symlink(target, link)
        return True, "symlink"
    except OSError as exc:
        return False, str(exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    fixtures = os.path.abspath(args.fixtures)
    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    root = os.path.join(out, "library")
    external = os.path.join(out, "external")
    os.makedirs(root)
    os.makedirs(external)
    files = []
    ignored = []

    for relative, source, fmt in NINE:
        copy_fixture(fixtures, root, relative, source)
        record(files, root, relative, fmt,
               duplicate_group="sample.epub" if relative == "sample.epub" else None)

    copy_fixture(fixtures, root, "重复/副本.epub", "sample.epub")
    record(files, root, "重复/副本.epub", "EPUB", duplicate_group="sample.epub")

    copy_fixture(fixtures, root, "小说 书库/第一层/中文 书名.epub",
                 "complex-text.epub")
    record(files, root, "小说 书库/第一层/中文 书名.epub", "EPUB")
    copy_fixture(fixtures, root, "小说 书库/第一层/第二层/深层 文档.txt",
                 "pager-golden.txt")
    record(files, root, "小说 书库/第一层/第二层/深层 文档.txt", "TXT")
    copy_fixture(fixtures, root, "子目录 空格/符号 #1.html", "complex-text.html")
    record(files, root, "子目录 空格/符号 #1.html", "HTML")

    depth = os.path.join(root, "深度", "一层", "二层", "三层")
    os.makedirs(depth)
    with open(os.path.join(depth, "四级.txt"), "w", encoding="utf-8") as f:
        f.write("deep level text\n")
    record(files, root, "深度/一层/二层/三层/四级.txt", "TXT",
           category="depth")

    many = os.path.join(root, "多文件")
    os.makedirs(many)
    for i in range(20):
        name = "{:03d}.txt".format(i)
        with open(os.path.join(many, name), "w", encoding="utf-8") as f:
            f.write("many file {}\n".format(i))
        record(files, root, "多文件/" + name, "TXT", category="many")

    post = os.path.join(root, "枚举后")
    os.makedirs(post)
    with open(os.path.join(post, "修改.txt"), "w", encoding="utf-8") as f:
        f.write("old-before-scan\n")
    record(files, root, "枚举后/修改.txt", "TXT", category="mutable")
    with open(os.path.join(post, "删除.txt"), "w", encoding="utf-8") as f:
        f.write("delete-before-scan\n")
    record(files, root, "枚举后/删除.txt", "TXT", category="deleted")
    with open(os.path.join(post, "替换.txt"), "w", encoding="utf-8") as f:
        f.write("replace-before-scan\n")
    record(files, root, "枚举后/替换.txt", "TXT", category="replaced")

    big = os.path.join(root, "大文件")
    os.makedirs(big)
    with open(os.path.join(big, "big.txt"), "wb") as f:
        f.write(b"A" * (8 * 1024 * 1024))
    record(files, root, "大文件/big.txt", "TXT", category="large")

    with open(os.path.join(root, "broken.epub"), "wb") as f:
        f.write(b"PK\x03\x04 this is not a valid EPUB package\n")
    record(files, root, "broken.epub", "EPUB", valid=False, category="corrupt")

    with open(os.path.join(root, "notes.log"), "w", encoding="utf-8") as f:
        f.write("not a book\n")
    ignored.append("notes.log")
    with open(os.path.join(root, "cover.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xd9")
    ignored.append("cover.jpg")
    os.makedirs(os.path.join(root, "fake.epub"))
    ignored.append("fake.epub/")

    shutil.copyfile(os.path.join(fixtures, "sample.epub"),
                    os.path.join(external, "outside.epub"))
    shutil.copyfile(os.path.join(fixtures, "sample.epub"),
                    os.path.join(external, "outside-link.epub"))
    links = {}
    ok, detail = make_junction(os.path.join(root, "link-out"), external)
    links["out"] = {"supported": ok, "detail": detail}
    ok, detail = make_file_link(os.path.join(root, "link-file.epub"),
                                os.path.join(external, "outside-link.epub"))
    links["file"] = {"supported": ok, "detail": detail}
    ok, detail = make_junction(os.path.join(root, "link-in"),
                               os.path.join(root, "小说 书库"))
    links["in"] = {"supported": ok, "detail": detail}

    data = {
        "root": root,
        "external": external,
        "files": files,
        "ignored": ignored,
        "links": links,
        "nine_formats": sorted({fmt for _, _, fmt in NINE}),
    }
    with open(os.path.join(out, "fixtures.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("fixtures:", out)
    print("files:", len(files), "links:", links)
    return 0


if __name__ == "__main__":
    sys.exit(main())
