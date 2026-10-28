#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only actual account authorization failure and recovery evidence."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import subprocess
import sys

from check_account import with_fixture
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import load_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    parser.add_argument('--udid', required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    assert command and command[0] == 'xcodebuild'
    output = args.output.absolute(); output.mkdir(parents=True, exist_ok=True)
    original = (args.resources / 'Sample.epub').read_bytes()
    authorization = 'Basic ' + base64.b64encode(b'reader:failure-fixture-password').decode()
    boundary = []
    active_root = [None]

    def account_folder():
        if args.platform == 'macos':
            return Path.home() / 'Library/Application Support/EXReader'
        return Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.udid,
                                             'org.exreader.host', 'data'], text=True).strip()) / 'Library/Application Support/EXReader'

    def on_unauthorized():
        # Snapshot the actual owner database before the fixture sends its 401.
        # Keep the record even if inspection fails; the HTTP response still reaches the UI.
        try:
            folder = account_folder()
            profiles = [p for p in json.loads((folder / 'accounts.json').read_bytes()) if p['root'] == active_root[0]]
            assert len(profiles) == 1
            dbpath = folder / 'accounts' / profiles[0]['id'] / 'reader-catalog.db'
            with sqlite3.connect(dbpath.resolve().as_uri() + '?mode=ro', uri=True) as db:
                rows = db.execute('SELECT o.revision_id, r.body_sha256 FROM reader_outbox o JOIN reader_revisions r ON r.revision_id = o.revision_id').fetchall()
                books = db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0]
            boundary.append({'pending_revisions': rows, 'local_books': books})
        except Exception as error:
            boundary.append({'error': repr(error)})
        (output / 'failure-boundary.json').write_text(json.dumps(boundary, indent=2) + '\n')

    def consume(root, entries, requests, certificate):
        active_root[0] = root
        if args.platform != 'macos':
            subprocess.run(['xcrun', 'simctl', 'bootstatus', args.udid, '-b'], check=True)
            subprocess.run(['xcrun', 'simctl', 'keychain', args.udid, 'add-root-cert', str(certificate)], check=True)
        log = output / 'xcodebuild.log'
        try:
            with log.open('w') as stream:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=1200,
                                        env=dict(os.environ, TEST_RUNNER_EXR_FAILURE_UI_ROOT=root))
        finally:
            (output / 'https-requests.json').write_text(json.dumps(requests, indent=2) + '\n')
            (output / 'remote-inventory.json').write_text(json.dumps([
                {'path': path, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                for path, body in sorted(entries.items())], indent=2) + '\n')
        assert result.returncode == 0, log.read_text()[-3000:]
        cases = load_results(output / 'failure.xcresult')
        assert len(cases) == 1 and 'testAuthorizationFailurePreservesBookAndRetry' in cases[0]['name'] and cases[0]['result'] == 'Passed', cases
        info = args.app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
        assert plistlib.loads(info.read_bytes())['EXRSourceSHA'] == os.environ['GITHUB_SHA']
        assert requests and any(not row['authenticated'] for row in requests), 'real authorization failure missing'
        first_good = next(i for i, row in enumerate(requests) if row['authenticated'])
        assert any(not row['authenticated'] for row in requests[:first_good]), 'failure must precede recovery'
        shards = {row['path'] for row in requests[first_good:] if row['authenticated'] and row['method'] == 'PROPFIND' and
                  re.fullmatch(r'/dav/exreader-sync-v1/revisions/[0-9a-f]{2}/', row['path'])}
        assert shards == {'/dav/exreader-sync-v1/revisions/%02x/' % n for n in range(256)}, 'recovery sweep incomplete'
        assert sum(body == original for body in entries.values()) == 1, 'retried original differs'
        revisions = [json.loads(body) for path, body in entries.items() if '/revisions/' in path and path.endswith('.json')]
        assert len(revisions) == 1 and revisions[0]['entity_kind'] == 'book'
        assert revisions[0]['entity_key'] == 'epub:' + hashlib.sha256(original).hexdigest()
        folder = account_folder()
        metadata = (folder / 'accounts.json').read_bytes()
        assert 0 < len(metadata) <= 64 * 1024 and b'failure-fixture-password' not in metadata
        profiles = [profile for profile in json.loads(metadata) if profile['root'] == root]
        assert len(profiles) == 1 and profiles[0]['anonymous'] is False
        dbpath = folder / 'accounts' / profiles[0]['id'] / 'reader-catalog.db'
        with sqlite3.connect(dbpath.resolve().as_uri() + '?mode=ro', uri=True) as db:
            assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM reader_outbox').fetchone()[0] == 0
            assert boundary and all('error' not in item for item in boundary), boundary
            assert boundary[0]['local_books'] == 1 and len(boundary[0]['pending_revisions']) == 1, boundary
            for revision, digest in boundary[0]['pending_revisions']:
                assert db.execute('SELECT body_sha256 FROM reader_revisions WHERE revision_id = ?', (revision,)).fetchone() == (digest,)
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                  'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': args.platform, 'case': cases[0],
                  'failure_requests': sum(not row['authenticated'] for row in requests), 'recovery_shards': len(shards),
                  'original_sha256': hashlib.sha256(original).hexdigest(), 'outbox_after_retry': 0,
                  'scope': 'actual account UI authorization failure, credential update and HTTPS retry'}
        (output / 'failure-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))

    with_fixture(output / 'fixture', authorization, consume, shard_delay=0.25, on_unauthorized=on_unauthorized)


if __name__ == '__main__':
    main()
