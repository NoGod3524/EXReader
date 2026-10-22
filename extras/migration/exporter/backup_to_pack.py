#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Convert a legacy EXReader backup archive (the .zip made by the old app's "back up library" action:
`library.json` {version:1, books, notes} plus `files/<book id>`) into a migration pack.

This is the second real legacy input path: it needs no browser and no access to the old origin.
The archive is only read. Limits mirror the old restore code (1 GiB archive, 2 GiB expanded)."""
import hashlib
import json
import re
import struct
import sys
import zipfile

MAGIC = b"EXRLGP1\n"
TRAILER = b"EXRLGPT1"
ID = re.compile(r"^[\w-]{1,100}$")


class BackupError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def convert(backup_path, pack_path):
    with zipfile.ZipFile(backup_path) as z:
        total = sum(i.file_size for i in z.infolist())
        if total > 2 * 1024 ** 3:
            raise BackupError("backup-limit", "backup expands beyond 2 GiB")
        if "library.json" not in z.namelist():
            raise BackupError("backup-not-exreader", "library.json is missing; this is not an EXReader backup")
        data = json.loads(z.read("library.json").decode("utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("books"), list) or not isinstance(data.get("notes"), list):
            raise BackupError("backup-unknown-version", "backup version or structure is not the documented version 1")
        out = open(pack_path, "wb")
        try:
            offset = len(MAGIC)
            out.write(MAGIC)
            books, seen = [], set()
            for record in data["books"]:
                bid = record.get("id")
                if not isinstance(bid, str) or not ID.match(bid) or bid in seen:
                    raise BackupError("backup-invalid-book", "book id %r is invalid or repeated" % (bid,))
                seen.add(bid)
                entry = {"legacy_id": bid, "record": record, "file": {"present": False}}
                name = "files/" + bid
                if name in z.namelist():
                    blob = z.read(name)  # one original at a time
                    entry["file"] = {"present": True, "offset": offset, "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
                                     "name": record.get("filename", ""), "type": "", "modified": record.get("modified", record.get("added")), "shape": "backup"}
                    out.write(blob)
                    offset += len(blob)
                books.append(entry)
            notes = []
            for n in data["notes"]:
                if not isinstance(n.get("id"), str):
                    raise BackupError("backup-invalid-note", "note without a string id")
                notes.append({"legacy_id": n["id"], "record": n})
            manifest = {"format": "exreader-legacy-pack", "version": 1,
                        "exporter": {"name": "backup_to_pack.py", "version": "1", "read_only": True},
                        "source": {"kind": "backup-zip", "database": None, "version": data["version"], "stores": ["books", "files", "notes"]},
                        "counts": {"books": len(books), "notes": len(notes)}, "books": books, "notes": notes, "orphans": {"files": []}, "warnings": []}
            text = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            out.write(text)
            out.write(TRAILER + struct.pack("<QQ", offset, len(text)) + hashlib.sha256(text).digest())
        finally:
            out.close()
    return {"books": len(books), "notes": len(notes)}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: backup_to_pack.py LEGACY_BACKUP.zip OUTPUT.exrpack")
    try:
        print(json.dumps(convert(sys.argv[1], sys.argv[2])))
    except (BackupError, zipfile.BadZipFile, ValueError) as e:
        print(json.dumps({"error": getattr(e, "code", "backup-unreadable"), "message": str(e)}), file=sys.stderr)
        sys.exit(2)
