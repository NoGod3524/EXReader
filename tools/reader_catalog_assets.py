#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package complete SQLite statements for Android; run during cloud builds."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "apps/reader/store/001_catalog.sql"
MAX_BYTES = 128 * 1024
MAX_STATEMENTS = 128


def build_asset(source):
    if not 0 < len(source) <= MAX_BYTES:
        raise ValueError("catalog migration exceeds its byte limit")
    sql = source.decode("utf-8", errors="strict")
    if sql.startswith("\ufeff") or "\0" in sql:
        raise ValueError("catalog migration has a BOM or NUL")
    statements = []
    start = 0
    for index, char in enumerate(sql):
        if char == ";" and sqlite3.complete_statement(sql[start:index + 1]):
            statements.append(sql[start:index + 1])
            start = index + 1
    tail = sql[start:]
    # Preserve comments and whitespace byte-for-byte without inventing an
    # executable trailing statement. Trigger bodies stay a single statement.
    if re.sub(r"--[^\n]*(?:\n|$)|/\*.*?\*/", "", tail,
              flags=re.DOTALL).strip():
        raise ValueError("catalog migration has an incomplete trailing statement")
    if not statements or len(statements) > MAX_STATEMENTS:
        raise ValueError("catalog migration has an invalid statement count")
    statements[-1] += tail
    return {
        "asset_version": 1,
        "application_id": 1163416144,
        "schema_version": 1,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_bytes": len(source),
        "statements": statements,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SCHEMA)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asset = build_asset(args.source.read_bytes())
    encoded = (json.dumps(asset, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("packaged migration exceeds its byte limit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(json.dumps({"source_sha256": asset["source_sha256"],
                      "source_bytes": asset["source_bytes"],
                      "statements": len(asset["statements"])}))


if __name__ == "__main__":
    main()
