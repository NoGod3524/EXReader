#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate this exact attempt's producer jobs and raw artifact ZIPs.

The strict summary must never mix another source, run or attempt: every role
job has to be completed successfully on GITHUB_SHA in this attempt, and the
downloaded ZIP bytes must match the reported size and digest before anything
inside is trusted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

ROLES = ('guards', 'android', 'apple', 'desktop')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('artifact authentication runs in Actions only')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    repo = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/'

    def api(path):
        return json.loads(subprocess.check_output(['gh', 'api', repo + path]))

    identity = api('actions/runs/' + run)
    assert identity['head_sha'] == source and identity['run_attempt'] == int(attempt)
    jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    verified = []
    for role in ROLES:
        producers = [job for job in jobs if job['name'] == role]
        assert len(producers) == 1, 'missing or duplicate job for ' + role
        producer = producers[0]
        assert producer['head_sha'] == source and producer['status'] == 'completed'
        assert producer['conclusion'] == 'success', role + ' did not conclude successfully'
        name = 'reader-final-s10-' + role + '-' + run + '-' + attempt
        matches = [row for row in artifacts if row['name'] == name]
        assert len(matches) == 1, 'missing or duplicate artifact ' + name
        metadata = matches[0]
        assert metadata['workflow_run']['id'] == int(run) and metadata['workflow_run']['head_sha'] == source
        assert not metadata['expired'] and 0 < metadata['size_in_bytes'] <= 512 * 1024 ** 2
        assert datetime.fromisoformat(metadata['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        raw = subprocess.check_output(['gh', 'api', repo + 'actions/artifacts/' + str(metadata['id']) + '/zip'])
        assert len(raw) == metadata['size_in_bytes']
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == metadata['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            assert len(infos) <= 30000 and len(infos) == len({row.filename for row in infos})
            assert sum(row.file_size for row in infos) <= 1024 ** 3
            for row in infos:
                path = PurePosixPath(row.filename)
                assert not path.is_absolute() and '..' not in path.parts
                assert '\\' not in row.filename and ':' not in row.filename
                assert not stat.S_ISLNK(row.external_attr >> 16)
            archive.extractall(args.output / role)
        verified.append({**{key: metadata[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                         'producer_job': producer['id'], 'producer_name': producer['name'],
                         'producer_html_url': producer['html_url']})
    report = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'authenticated': True,
              'roles': list(ROLES), 'artifacts': verified}
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
