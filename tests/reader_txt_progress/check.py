#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate the installed TXT position probe: report plus retained database state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

EXPECTED = [
    'store_open', 'history_open', 'capture_bounds', 'capture_scalar_boundary',
    'capture_utf8_rejected', 'book_bootstrap_created', 'book_bootstrap_idempotent',
    'book_identity_mismatch', 'save_created', 'save_unchanged_no_duplicate',
    'load_roundtrip', 'match_window', 'conflict_refused', 'legacy_preserved',
    'pending_refused', 'raw_capability_refused',
]
EXPECTED_OUTBOX = 8          # 3 book bootstraps + 5 local progress writes
EXPECTED_RECEIVED = 1        # the pending-parent record is received, never queued
EXPECTED_BOOKS = 3
EXPECTED_PROGRESS = 6        # 1 save + 2 siblings + 1 legacy v1 + 1 append + 1 pending


def heads(rows):
    referenced = {parent for row in rows for parent in json.loads(row['body_json'])['parents']}
    return [row['revision_id'] for row in rows if row['revision_id'] not in referenced]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--raw', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Actions only')
    report = json.loads(args.report.read_text(encoding='utf-8'))
    checks = {row['name']: row for row in report['checks']}
    problems = []
    if report.get('ok') is not True:
        problems.append('probe report is not accepted')
    if sorted(checks) != sorted(EXPECTED):
        problems.append('probe checks differ from the required set')
    for name in EXPECTED:
        row = checks.get(name)
        if row is None or row.get('pass') is not True:
            problems.append('probe check failed: ' + name)
    db = sqlite3.connect(str(args.db))
    db.row_factory = sqlite3.Row
    revisions = db.execute('SELECT revision_id, entity_kind, entity_key, operation, body_json, body_sha256 '
                           'FROM reader_revisions').fetchall()
    outbox = db.execute('SELECT revision_id FROM reader_outbox').fetchall()
    books = [row for row in revisions if row['entity_kind'] == 'book']
    progress = [row for row in revisions if row['entity_kind'] == 'progress']
    if len(books) != EXPECTED_BOOKS:
        problems.append('retained book revisions: %d != %d' % (len(books), EXPECTED_BOOKS))
    if len(progress) != EXPECTED_PROGRESS:
        problems.append('retained progress revisions: %d != %d' % (len(progress), EXPECTED_PROGRESS))
    if len(outbox) != EXPECTED_OUTBOX:
        problems.append('outbox rows: %d != %d' % (len(outbox), EXPECTED_OUTBOX))
    if any(row['operation'] != 'put' for row in revisions):
        problems.append('retained history contains a non-put operation')
    expected_bytes = {row['revision_id']: row['body_sha256'] for row in revisions}
    if any(len(value) != 64 for value in expected_bytes.values()):
        problems.append('retained bodies lack a SHA-256')
    by_key = {}
    for row in progress:
        by_key.setdefault(row['entity_key'], []).append(row)
    conflict_key = None
    legacy_row = None
    pending_heads = 0
    for key, rows in by_key.items():
        bodies = [json.loads(row['body_json']) for row in rows]
        versions = sorted({body['payload']['location']['anchor_version'] for body in bodies})
        current = heads(rows)
        if 1 in versions:
            legacy_row = rows[[body['payload']['location']['anchor_version'] for body in bodies].index(1)]
        if len(current) >= 2:
            conflict_key = key
        if any(body['parents'] and all(parent not in {r['revision_id'] for r in revisions}
                                       for parent in body['parents']) for body in bodies):
            pending_heads = len(current)
    if conflict_key is None:
        problems.append('no concurrent head pair was retained')
    if pending_heads != 1:
        problems.append('pending-parent head count: %d != 1' % pending_heads)
    if legacy_row is None:
        problems.append('anchor v1 progress record is missing')
        legacy_sha = None
    else:
        legacy = json.loads(legacy_row['body_json'])
        if legacy['payload']['location']['anchor_version'] != 1 or not legacy['payload']['location']['selector']['exact']:
            problems.append('anchor v1 record lost its quote selector')
        legacy_sha = hashlib.sha256(legacy_row['body_json'].encode('utf-8')).hexdigest()
        if legacy_sha != legacy_row['body_sha256']:
            problems.append('anchor v1 record bytes changed after later writes')
        if json.loads(legacy_row['body_json'])['operation'] != 'put':
            problems.append('anchor v1 record is not a retained put')
    point_versions = [json.loads(row['body_json'])['payload']['location']['anchor_version']
                      for row in progress if row is not legacy_row]
    if any(version != 2 for version in point_versions):
        problems.append('new TXT positions are not anchor v2 points')
    if any(json.loads(row['body_json'])['payload']['location']['selector']['exact'] for row in progress
           if json.loads(row['body_json'])['payload']['location']['anchor_version'] == 2):
        problems.append('a new TXT position invented quote bytes')
    db.close()
    evidence = {
        'schema': 1,
        'raw_family': bool(args.raw),
        'source_sha': os.environ.get('GITHUB_SHA'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'accepted': not problems,
        'problems': problems,
        'probe_checks': len(checks),
        'retained_book_revisions': len(books),
        'retained_progress_revisions': len(progress),
        'outbox_rows': len(outbox),
        'conflict_entity': conflict_key,
        'legacy_body_sha256': legacy_sha,
        'report_sha256': hashlib.sha256(args.report.read_bytes()).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence))
    if problems:
        for problem in problems:
            print('PROBLEM ' + problem, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
