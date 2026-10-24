#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record the uploaded artifact identity from the run's artifact listing.

Runs after the evidence upload: it requires the artifact to exist, to be
non-empty, to carry a sha256 digest and an expiry, and it binds that identity to
the same source/run/attempt as the measurement.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True,
                        help='JSON listing downloaded from the run artifacts endpoint')
    parser.add_argument('--name', required=True, help='expected artifact name')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    listing = json.loads(args.artifacts.read_text(encoding='utf-8'))
    matches = [item for item in listing.get('artifacts', []) if item.get('name') == args.name]
    if len(matches) != 1:
        raise SystemExit('expected exactly one artifact named %r, found %d'
                         % (args.name, len(matches)))
    artifact = matches[0]
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
                'problems': problems, 'accepted': not problems}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(identity, ensure_ascii=False, indent=2))
    return 0 if identity['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
