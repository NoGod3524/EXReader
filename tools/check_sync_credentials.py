#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove the WebDAV password and user name are not stored in plain text.

Usage: python -I tools/check_sync_credentials.py <data-dir> <password> [<username> ...]

Scans every file under <data-dir> (default: %APPDATA%\\EXReader) for the secret
as UTF-8, UTF-16LE and as the base64 "user:password" Authorization value. Exit 0 and "PASS" only when there are no hits and sync.cred exists.
"""
import base64
import os
import sys


def needles(secrets):
    out = []
    for s in secrets:
        out.append(("utf-8", s.encode("utf-8")))
        out.append(("utf-16le", s.encode("utf-16-le")))
    if len(secrets) >= 2:
        pair = (secrets[1] + ":" + secrets[0]).encode("utf-8")
        out.append(("basic-b64", base64.b64encode(pair)))
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    root, password, users = argv[1], argv[2], argv[3:]
    wanted = needles([password] + users) if users else needles([password])
    files = hits = 0
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            files += 1
            for label, needle in wanted:
                if needle and needle in data:
                    hits += 1
                    print("HIT  %s  (%s)" % (path, label))
    cred = os.path.join(root, "sync.cred")
    print("scanned %d files under %s; hits=%d; sync.cred %s" % (
        files, root, hits, "present (%d bytes)" % os.path.getsize(cred) if os.path.exists(cred) else "MISSING"))
    ok = hits == 0 and os.path.exists(cred)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
