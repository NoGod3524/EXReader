#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record the uploaded artifact identity from the run's artifact listing.

Runs after the evidence upload. It requires the artifact to exist, to be
non-empty, to carry a sha256 digest and an expiry, and it binds that identity to
the same source/run/attempt as the measurement. The listing is re-fetched so a
short upload-listing delay cannot turn into a false negative.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def fetch(url, token, attempts, delay):
    last = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'exreader-perf-windows',
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            last = 'HTTP %d %s' % (error.code, error.read()[:400].decode('utf-8', 'replace'))
            if error.code not in (404, 429, 500, 502, 503, 504):
                raise
        except urllib.error.URLError as error:
            last = 'URL error: %s' % error
        if attempt < attempts:
            time.sleep(delay)
    raise SystemExit('could not read the artifact listing: %s' % last)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True, help='run artifacts endpoint')
    parser.add_argument('--name', required=True, help='expected artifact name')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attempts', type=int, default=8)
    parser.add_argument('--delay', type=float, default=10.0)
    args = parser.parse_args()

    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        raise SystemExit('GITHUB_TOKEN is not available in this step')

    listing = None
    artifact = None
    for attempt in range(1, args.attempts + 1):
        listing = fetch(args.api_url, token, 1, 1)
        matches = [item for item in listing.get('artifacts', []) if item.get('name') == args.name]
        if len(matches) == 1:
            artifact = matches[0]
            break
        print('listing attempt %d: found %d matching artifacts' % (attempt, len(matches)))
        if attempt < args.attempts:
            time.sleep(args.delay)
    if artifact is None:
        raise SystemExit('expected exactly one artifact named %r, found %d'
                         % (args.name, len([item for item in (listing or {}).get('artifacts', [])
                                            if item.get('name') == args.name])))

    problems = []
    if not isinstance(artifact.get('id'), int) or artifact['id'] <= 0:
        problems.append('artifact id missing')
    if not isinstance(artifact.get('size_in_bytes'), int) or artifact['size_in_bytes'] <= 0:
        problems.append('artifact size is not a positive byte count')
    if not str(artifact.get('digest') or '').startswith('sha256:'):
        problems.append('artifact digest is not sha256')
    if not artifact.get('expires_at'):
        problems.append('artifact expiry missing')
    if artifact.get('expired') is True:
        problems.append('artifact is already expired')

    head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    source = os.environ.get('GITHUB_SHA', '')
    if head != source:
        problems.append('artifact recorded at %r while HEAD is %r' % (source, head))

    identity = {'schema': 1, 'artifact_name': args.name,
                'artifact_id': artifact.get('id'),
                'size_in_bytes': artifact.get('size_in_bytes'),
                'digest': artifact.get('digest'),
                'expires_at': artifact.get('expires_at'),
                'created_at': artifact.get('created_at'),
                'workflow_run': {'id': os.environ.get('GITHUB_RUN_ID', ''),
                                 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
                                 'source_sha': source,
                                 'repository': os.environ.get('GITHUB_REPOSITORY', ''),
                                 'job': os.environ.get('GITHUB_JOB', '')},
                'listing_artifact_count': len((listing or {}).get('artifacts', [])),
                'problems': problems, 'accepted': not problems}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(identity, ensure_ascii=False, indent=2))
    return 0 if identity['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
