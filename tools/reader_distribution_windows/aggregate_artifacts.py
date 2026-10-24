#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Re-aggregate one cloud artifact: metadata, recomputed ZIP digest, inner seal.

Runs where the download is legitimate (a GitHub Actions job). Every claim in the
uploaded summary is checked against the artifact bytes and the run identity; a
missing, expired, cross-run, cross-attempt or tampered artifact raises.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def gh_json(arguments):
    output = subprocess.check_output(['gh', 'api'] + arguments, text=True)
    return json.loads(output)


def list_artifacts(repo, run_id):
    found, page = [], 1
    while True:
        batch = gh_json(['repos/%s/actions/runs/%s/artifacts?per_page=100&page=%d' % (repo, run_id, page)])
        artifacts = batch.get('artifacts', [])
        found.extend(artifacts)
        if len(artifacts) < 100:
            return found
        page += 1
        distlib.require(page <= 20, 'artifact listing did not terminate')


def download(repo, artifact_id, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('wb') as stream:
        subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%s/zip' % (repo, artifact_id)],
                       stdout=stream, check=True)
    distlib.require(destination.is_file() and destination.stat().st_size > 0,
                    'downloaded artifact is empty')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--artifact-name', required=True)
    parser.add_argument('--download-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    distlib.require(os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'),
                    'GH_TOKEN is required to read run artifacts')
    run = gh_json(['repos/%s/actions/runs/%s' % (args.repo, args.run_id)])
    distlib.require(run.get('head_sha') == args.source_sha, 'run head SHA differs from the tested source')
    distlib.require(str(run.get('run_attempt')) == args.attempt, 'run attempt differs')
    artifacts = [item for item in list_artifacts(args.repo, args.run_id)
                 if item.get('name') == args.artifact_name]
    distlib.require(len(artifacts) == 1,
                    'expected exactly one artifact named %s, found %d' % (args.artifact_name, len(artifacts)))
    artifact = artifacts[0]
    results = []
    distlib.named(results, 'artifact-not-expired',
                  artifact.get('expired') is False and bool(artifact.get('expires_at')),
                  {'expires_at': artifact.get('expires_at')})
    distlib.named(results, 'artifact-nonempty',
                  int(artifact.get('size_in_bytes') or 0) > 0, artifact.get('size_in_bytes'))
    zip_path = download(args.repo, artifact['id'], args.download_dir / ('%s.zip' % artifact['id']))
    recomputed = distlib.digest(zip_path)
    claimed = str(artifact.get('digest') or '')
    distlib.require(claimed.startswith('sha256:'), 'artifact metadata has no sha256 digest')
    distlib.named(results, 'artifact-digest-recomputed', claimed == 'sha256:' + recomputed,
                  {'claimed': claimed, 'recomputed': recomputed})
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(args.download_dir / 'content')
    content = args.download_dir / 'content'
    summary_path = content / 'summary.json'
    distribution_path = content / 'distribution.json'
    distlib.require(summary_path.is_file() and distribution_path.is_file(),
                    'artifact does not contain the summary and distribution reports')
    summary = distlib.load_json(summary_path)
    distribution = distlib.load_json(distribution_path)
    distlib.named(results, 'summary-source-bound', summary.get('source_sha') == args.source_sha and
                  summary.get('accepted') is True, summary.get('source_sha'))
    distlib.named(results, 'summary-same-run-and-attempt',
                  str(summary.get('ci', {}).get('GITHUB_RUN_ID')) == args.run_id and
                  str(summary.get('ci', {}).get('GITHUB_RUN_ATTEMPT')) == args.attempt,
                  summary.get('ci', {}))
    named = summary.get('results', [])
    failed = [item['name'] for item in named if item.get('status') != 'pass']
    distlib.named(results, 'summary-named-results-pass', bool(named) and not failed,
                  {'count': len(named), 'failed': failed[:6]})
    sealed = list(content.rglob('EXReader-*.zip'))
    distlib.require(len(sealed) == 1, 'artifact does not contain exactly one sealed distribution')
    sealed_digest = distlib.digest(sealed[0])
    distlib.named(results, 'sealed-archive-digest-matches',
                  sealed_digest == distribution['archive']['sha256'] ==
                  summary['distribution']['sha256'] and
                  sealed[0].stat().st_size == distribution['archive']['bytes'],
                  {'sealed': sealed_digest, 'reported': distribution['archive']['sha256']})
    distlib.named(results, 'sealed-archive-entries-match',
                  len(distlib.read_zip(sealed[0])) == distribution['archive']['entries'] ==
                  summary['distribution']['entries'],
                  {'entries': distribution['archive']['entries']})
    distlib.named(results, 'seal-reproducible',
                  (distribution.get('reproducibility') or {}).get('identical') is True,
                  distribution.get('reproducibility'))
    record = {'schema': 'reader-distribution-windows-aggregate-v1', 'accepted': True,
              'source_sha': args.source_sha, 'run_id': int(args.run_id), 'attempt': int(args.attempt),
              'artifact': {'id': artifact['id'], 'name': artifact['name'],
                           'bytes': artifact['size_in_bytes'], 'digest': claimed,
                           'recomputed_sha256': recomputed,
                           'expires_at': artifact.get('expires_at'),
                           'head_sha': run.get('head_sha')},
              'distribution': summary['distribution'], 'results': results}
    distlib.write_json(args.output, record)
    distlib.require_named_pass(results, [item['name'] for item in results])
    print(json.dumps({'artifact': artifact['id'], 'sha256': recomputed, 'results': len(results)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
