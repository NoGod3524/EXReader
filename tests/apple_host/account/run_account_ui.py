# SPDX-License-Identifier: MIT
"""Actions-only native SwiftUI account requests against the retained TLS fixture."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from check_account import with_fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    parser.add_argument('--udid', required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    assert command and command[0] == 'xcodebuild'
    folder = args.output.absolute(); folder.mkdir(parents=True, exist_ok=True)
    original = (args.resources / 'Sample.epub').read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()

    def consume(root, entries, requests, certificate):
        if args.platform != 'macos':
            subprocess.run(['xcrun', 'simctl', 'bootstatus', args.udid, '-b'], check=True)
            subprocess.run(['xcrun', 'simctl', 'keychain', args.udid, 'add-root-cert', str(certificate)], check=True)
        log = folder / (args.platform + '-xcodebuild.log')
        try:
            with log.open('w') as output:
                done = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=1200,
                                      env=dict(os.environ, TEST_RUNNER_EXR_ACCOUNT_UI_ROOT=root))
        finally:
            (folder / 'https-requests.json').write_text(json.dumps(requests, indent=2) + '\n')
            remote = folder / 'remote'; remote.mkdir()
            for index, (path, body) in enumerate(sorted(entries.items())):
                (remote / ('%04d.bin' % index)).write_bytes(body)
            (folder / 'remote-inventory.json').write_text(json.dumps([
                {'path': path, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                for path, body in sorted(entries.items())], indent=2) + '\n')
        assert done.returncode == 0, log.read_text()[-3000:]
        assert requests and all(row['authenticated'] for row in requests)
        shards = Counter(row['path'] for row in requests if row['method'] == 'PROPFIND' and
                         re.fullmatch(r'/dav/exreader-sync-v1/revisions/[0-9a-f]{2}/', row['path']))
        assert set(shards) == {'/dav/exreader-sync-v1/revisions/%02x/' % value for value in range(256)}
        assert min(shards.values()) >= 2, 'initial UI sweep and explicit retry must each visit every shard'
        assert sum(body == original for body in entries.values()) == 1, 'actual UI original differs'
        revisions = [json.loads(body) for path, body in entries.items()
                     if '/revisions/' in path and path.endswith('.json')]
        assert len(revisions) == 1 and revisions[0]['entity_kind'] == 'book'
        assert revisions[0]['entity_key'] == 'epub:' + original_sha
        report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'],
                  'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                  'platform': args.platform, 'root': root, 'actual_shards': len(shards),
                  'minimum_completed_sweeps': min(shards.values()), 'requests': len(requests),
                  'verified_original_sha256': original_sha, 'verified_original_bytes': len(original),
                  'remote_revisions': len(revisions), 'password_authentication_used': False}
        (folder / 'https-ui.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))

    with_fixture(folder / 'fixture', None, consume, shard_delay=4)


if __name__ == '__main__':
    main()
