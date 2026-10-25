#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same-run report: re-authenticate both artefacts from the Actions API.

Runs in a fresh job after the relocation job uploaded its evidence. It reads the
jobs, artefacts and digests GitHub reports, re-downloads the producer ZIP and the
S02 evidence ZIP, recomputes their SHA-256, and only then publishes a result.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import common

PRODUCER_SOURCE = '57203a52aee439be5194ee0a4b13563a975e8daf'
PRODUCER_RUN = 40206458217


def gh(*arguments, binary=False):
    result = subprocess.run(['gh', *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise common.S02Error('gh %s failed (%d): %s' % (
            ' '.join(arguments), result.returncode,
            result.stderr.decode('utf-8', 'replace')[-2000:]))
    return result.stdout if binary else result.stdout.decode('utf-8')


def gh_json(path):
    return json.loads(gh('api', path))


def seg(name):
    return [part for part in name.split('/') if part not in ('', '.')]


def artifact(rows, name):
    return next((row for row in rows if row.get('name') == name), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--run', type=int, default=int(os.environ.get('GITHUB_RUN_ID', '0')))
    parser.add_argument('--producer-run', type=int, default=PRODUCER_RUN)
    parser.add_argument('--producer-source', default=PRODUCER_SOURCE)
    parser.add_argument('--evidence-name', default='')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common.need(args.repository and args.run, 'repository and run id are required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = common.Checks()

    run = gh_json('repos/%s/actions/runs/%d' % (args.repository, args.run))
    attempt = int(run.get('run_attempt') or 1)
    checks.add('s02_run_source',
               run.get('head_sha') == os.environ.get('GITHUB_SHA'),
               'run %s attempt %s head %s status %s' % (args.run, attempt,
                                                        run.get('head_sha'), run.get('status')))
    jobs = gh_json('repos/%s/actions/runs/%d/jobs?per_page=100' % (args.repository, args.run))
    rows = [{'name': job.get('name'), 'conclusion': job.get('conclusion'),
             'status': job.get('status')} for job in jobs.get('jobs') or []]
    current = os.environ.get('GITHUB_JOB', 'report')
    finished = [row for row in rows if row['name'] != current]
    checks.add('s02_jobs_succeeded',
               {'preflight', 'relocate'} <= {row['name'] for row in rows}
               and all(row['conclusion'] == 'success' for row in finished),
               json.dumps(rows))

    evidence_name = args.evidence_name or 'reader-final-s02-evidence-%d-%d' % (args.run, attempt)
    listing = gh_json('repos/%s/actions/runs/%d/artifacts?per_page=100'
                      % (args.repository, args.run)).get('artifacts') or []
    evidence = artifact(listing, evidence_name)
    checks.add('s02_evidence_artifact_present', evidence is not None,
               'artifact %r from %s' % (evidence_name, [row.get('name') for row in listing]))
    summary = {}
    if evidence is not None:
        payload = gh('api', 'repos/%s/actions/artifacts/%d/zip' % (args.repository, evidence['id']),
                     binary=True)
        path = output / 'evidence.zip'
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        checks.add('s02_evidence_digest',
                   digest == (evidence.get('digest') or '').split(':', 1)[-1]
                   and len(payload) == evidence.get('size_in_bytes'),
                   'sha256 %s api %s bytes %d' % (digest, evidence.get('digest'), len(payload)))
        with zipfile.ZipFile(str(path)) as archive:
            matches = [name for name in archive.namelist()
                       if seg(name)[-1:] == ['summary.json']]
            checks.add('s02_summary_present', len(matches) == 1,
                       'summary members %s' % matches[:4])
            if len(matches) == 1:
                summary = json.loads(archive.read(matches[0]).decode('utf-8'))
    checks.add('s02_summary_accepted',
               summary.get('accepted') is True
               and summary.get('verifier_source') == os.environ.get('GITHUB_SHA'),
               'accepted %r verifier %r' % (summary.get('accepted'),
                                            summary.get('verifier_source')))
    summary_artifact = (summary.get('producer') or {}).get('artifact') or {}
    summary_zip = (summary.get('producer') or {}).get('zip') or {}

    producer = gh_json('repos/%s/actions/runs/%d' % (args.repository, args.producer_run))
    checks.add('producer_run_identity',
               producer.get('head_sha') == args.producer_source
               and producer.get('conclusion') == 'success'
               and int(producer.get('run_attempt') or 0) == int(
                   (summary.get('producer') or {}).get('run', {}).get('attempt') or 0),
               'head %s attempt %s conclusion %s' % (producer.get('head_sha'),
                                                     producer.get('run_attempt'),
                                                     producer.get('conclusion')))
    producer_rows = gh_json('repos/%s/actions/runs/%d/artifacts?per_page=100'
                            % (args.repository, args.producer_run)).get('artifacts') or []
    producer_artifact = artifact(
        [{'id': row['id'], 'name': row['name'], 'size_in_bytes': row['size_in_bytes'],
          'digest': row.get('digest'), 'expired': row.get('expired'),
          'expires_at': row.get('expires_at'), 'created_at': row.get('created_at')}
         for row in producer_rows],
        summary_artifact.get('name') or '')
    checks.add('producer_artifact_reauthenticated',
               producer_artifact is not None
               and producer_artifact.get('digest') == summary_artifact.get('digest')
               and producer_artifact.get('expires_at') == summary_artifact.get('expires_at'),
               'artifact %r digest %s' % (summary_artifact.get('name'),
                                          summary_artifact.get('digest')))
    if producer_artifact is not None:
        payload = gh('api', 'repos/%s/actions/artifacts/%d/zip'
                     % (args.repository, producer_artifact['id']), binary=True)
        path = output / 'producer.zip'
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        checks.add('producer_zip_redownloaded',
                   digest == summary_zip.get('sha256')
                   and len(payload) == summary_zip.get('bytes')
                   and digest == (producer_artifact.get('digest') or '').split(':', 1)[-1],
                   'sha256 %s recorded %s bytes %d recorded %s' % (
                       digest, summary_zip.get('sha256'), len(payload), summary_zip.get('bytes')))

    document = {
        'schema': 1,
        'kind': 's02-same-run-report',
        'verifier_source': os.environ.get('GITHUB_SHA', ''),
        'run': {'id': args.run, 'attempt': attempt, 'head_sha': run.get('head_sha'),
                'jobs': rows},
        'evidence_artifact': evidence,
        'producer': {'run': args.producer_run, 'head_sha': producer.get('head_sha'),
                     'artifact': producer_artifact,
                     'zip_sha256': summary_zip.get('sha256')},
        'summary': summary,
        'accepted': checks.accepted() and summary.get('accepted') is True,
        'checks': checks.items,
        'problems': checks.failed(),
    }
    common.write_json(output / 'result.json', document)
    print(json.dumps({'accepted': document['accepted'], 'checks': len(checks.items),
                      'failed': checks.failed()}))
    return 0 if document['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
