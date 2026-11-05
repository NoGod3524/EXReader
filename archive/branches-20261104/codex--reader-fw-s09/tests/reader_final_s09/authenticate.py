#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate one published distribution-inventory artifact and extract it.

The closure in this package never builds the candidate itself when it consumes a
published one: it authenticates the artifact first. That means the artifact is named,
its recorded size and SHA-256 digest are compared with the downloaded bytes, its
expiry is still in the future, its workflow run and head commit are the named
producer's, and the producing job's own upload log names the same artifact id and
digest. Only then are the bytes unpacked for the closure.

The producer source and this verifier source are recorded separately, because they
are different commits.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests' / 'reader_distribution_inventory'))
sys.path.insert(0, str(HERE))
import contract

PRODUCER_WORKFLOW = '.github/workflows/reader-distribution-inventory.yml'


def api(path):
    done = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path],
                          capture_output=True, timeout=180)
    if done.returncode != 0:
        raise contract.InventoryError('github_api', path + ': '
                                      + done.stderr.decode('utf-8', 'replace')[:400])
    return contract.decode_json(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 21):
        body = api(path + '?per_page=100&page=%d' % page)
        contract.need(contract.integer(body.get('total_count')) and type(body.get(field)) is list
                      and len(body[field]) <= 100, 'api_pagination')
        result.extend(body[field])
        if len(result) >= body['total_count']:
            contract.need(len(result) == body['total_count'], 'api_page_count')
            return result
        contract.need(bool(body[field]), 'api_incomplete_page')
    raise contract.InventoryError('api_page_limit')


def normalise(payload):
    """Accept both layouts: contents at the archive root, or one shared prefix."""
    if any(name.startswith('stage/') for name in payload):
        return payload
    prefixes = {name.split('/')[0] for name in payload if '/' in name}
    if len(prefixes) == 1:
        prefix = prefixes.pop() + '/'
        return {name[len(prefix):]: data for name, data in payload.items()
                if name.startswith(prefix)}
    return payload


def extract(payload, directory):
    for name, data in sorted(payload.items()):
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-id', required=True, type=int)
    parser.add_argument('--artifact-name', required=True)
    parser.add_argument('--job-name', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--attempt', required=True, type=int)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--extract', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    repo = os.environ['GITHUB_REPOSITORY']
    prefix = '/repos/%s/actions/runs/%d' % (repo, args.run_id)
    run = api('%s/attempts/%d' % (prefix, args.attempt))
    contract.need(run.get('id') == args.run_id and run.get('run_attempt') == args.attempt,
                  'run_identity')
    contract.need(run.get('head_sha') == args.source_sha, 'run_source')
    contract.need(run.get('path') == PRODUCER_WORKFLOW, 'run_workflow')
    contract.need(run.get('repository', {}).get('full_name') == repo
                  and contract.integer(run['repository'].get('id'), 1)
                  and run.get('head_repository', {}).get('id') == run['repository']['id'],
                  'run_repository')
    contract.need(run.get('status') == 'completed' and run.get('conclusion') == 'success',
                  'run_conclusion')
    jobs = pages('%s/attempts/%d/jobs' % (prefix, args.attempt), 'jobs')
    contract.unique(jobs, 'job_duplicate')
    job = contract.select(jobs, args.job_name)
    contract.need(job.get('run_id') == args.run_id and job.get('run_attempt') == args.attempt
                  and job.get('head_sha') == args.source_sha
                  and job.get('status') == 'completed' and job.get('conclusion') == 'success',
                  'job_origin')
    artifacts = pages(prefix + '/artifacts', 'artifacts')
    contract.unique(artifacts, 'artifact_duplicate')
    artifact = [row for row in artifacts if row.get('id') == args.artifact_id]
    contract.need(len(artifact) == 1 and artifact[0].get('name') == args.artifact_name,
                  'named_evidence_missing_or_duplicate')
    artifact = artifact[0]
    now = datetime.now(timezone.utc)
    contract.artifact_identity(artifact, run, now)

    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / ('%d.zip' % artifact['id'])
    with path.open('wb') as target:
        done = subprocess.run(['gh', 'api', '/repos/%s/actions/artifacts/%d/zip'
                               % (repo, artifact['id'])], stdout=target,
                              stderr=subprocess.PIPE, timeout=600)
    contract.need(done.returncode == 0, 'archive_download')
    data = path.read_bytes()
    payload = normalise(contract.archive_files(data, artifact))

    done = subprocess.run(['gh', 'api', '--allow-escape-sequences',
                           '/repos/%s/actions/jobs/%d/logs' % (repo, job['id'])],
                          capture_output=True, timeout=300)
    contract.need(done.returncode == 0 and 0 < len(done.stdout) <= contract.MAX_EXPANDED,
                  'job_log_download')
    log_path = args.output / ('job-%d.log' % job['id'])
    log_path.write_bytes(done.stdout)
    log_sha = contract.upload_binding(done.stdout, artifact)

    contract.need('licenses.json' in payload, 'licenses_missing')
    contract.need(any(name in payload for name in ('inventory.json', 'combined.json')),
                  'inventory_missing')
    extract(payload, args.extract)
    stage = [name for name in payload if name.startswith('stage/')]
    record = {'schema': 1,
              'producer': {'workflow': PRODUCER_WORKFLOW, 'run_id': args.run_id,
                           'attempt': args.attempt, 'source_sha': args.source_sha,
                           'conclusion': run.get('conclusion'),
                           'job_id': job['id'], 'job_name': job['name'],
                           'job_conclusion': job.get('conclusion'),
                           'producer_log_sha256': log_sha},
              'verifier': {'source_sha': os.environ.get('GITHUB_SHA'),
                           'run_id': os.environ.get('GITHUB_RUN_ID'),
                           'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                           'job': os.environ.get('GITHUB_JOB')},
              'artifact': {field: artifact.get(field) for field in
                           ('id', 'name', 'size_in_bytes', 'digest', 'expired', 'expires_at',
                            'created_at', 'updated_at')},
              'zip': {'bytes': len(data), 'sha256': contract.digest(data)},
              'payload': {'files': len(payload), 'stage_files': len(stage),
                          'stage_bytes': sum(len(payload[name]) for name in stage)},
              'authenticated': True}
    (args.output / 'artifact.json').write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(record, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except contract.InventoryError as error:
        print(json.dumps({'authenticated': False, 'error': error.code,
                          'detail': str(error.detail or '')}, indent=2))
        raise SystemExit(1)
