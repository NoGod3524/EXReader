#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate this run's own C02 artifacts and aggregate them (Actions only).

Separates four sources and records each: the consumer source (this branch head,
GITHUB_SHA, which owns the tools), the Windows producer (the same checkout, apps
tree equal to the fixed start), the GTK producer (a second checkout at the pinned
compact commit) and the SDK each host was linked against. Every uploaded ZIP is
re-downloaded through the API, its size and SHA-256 compared with the API digest,
its members compared with the round's own bundle.json, and the program hash in
each round compared with the build artifact it was consumed from.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aggregate as A  # noqa: E402
import common as K  # noqa: E402

JOBS = ('preflight', 'windows-build', 'gtk-build', 'windows-measure', 'gtk-measure')


def gh(path):
    done = subprocess.run(['gh', 'api', '--paginate', '--slurp', path], capture_output=True, text=True, timeout=600)
    K.require(done.returncode == 0, 'gh api %s failed: %s' % (path, done.stderr[-400:]))
    pages = json.loads(done.stdout)
    return pages


def artifacts_of(run_id):
    pages = gh('repos/%s/actions/runs/%s/artifacts?per_page=100' % (os.environ['GITHUB_REPOSITORY'], run_id))
    found = []
    for page in pages:
        found.extend(page.get('artifacts', []))
    return found


def download(artifact, directory):
    archive = directory / (artifact['name'] + '.zip')
    with archive.open('wb') as handle:
        done = subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%d/zip' % (
            os.environ['GITHUB_REPOSITORY'], artifact['id'])], stdout=handle, stderr=subprocess.PIPE, timeout=1800)
    K.require(done.returncode == 0, 'artifact download failed: %s' % done.stderr[-400:])
    return archive


def extract(archive, destination):
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            target = (destination / info.filename).resolve()
            K.require(str(target).startswith(str(destination.resolve())), 'zip member escapes: ' + info.filename)
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    K.require(os.environ.get('GITHUB_ACTIONS') == 'true', 'run the verifier on a GitHub Actions runner')
    source, run_id, attempt = os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    repo = os.environ['GITHUB_REPOSITORY']
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run = gh('repos/%s/actions/runs/%s' % (repo, run_id))[0]
    K.require(run['head_sha'] == source and int(run['run_attempt']) == int(attempt), 'run head/attempt differ')
    suffix = '%s-%s' % (run_id, attempt)
    wanted = {'win-build': 'c02-win-build-' + suffix, 'gtk-build': 'c02-gtk-build-' + suffix}
    for number in (1, 2):
        wanted['win-r%d' % number] = 'c02-win-round%d-%s' % (number, suffix)
        wanted['gtk-r%d' % number] = 'c02-gtk-round%d-%s' % (number, suffix)
    listing = {item['name']: item for item in artifacts_of(run_id)}
    record = {'schema': K.SCHEMA, 'source': source, 'run_id': run_id, 'attempt': attempt, 'artifacts': {},
              'problems': []}
    extracted = {}
    scratch = output / 'download'
    scratch.mkdir(exist_ok=True)
    for key, name in wanted.items():
        item = listing.get(name)
        if item is None:
            record['problems'].append('artifact missing: ' + name)
            continue
        try:
            K.require(not item.get('expired'), 'artifact expired: ' + name)
            K.require(item['workflow_run']['id'] == int(run_id) and item['workflow_run']['head_sha'] == source,
                      'artifact belongs to another run/source: ' + name)
            digest = (item.get('digest') or '')
            K.require(digest.startswith('sha256:'), 'artifact has no sha256 digest: ' + name)
            archive = download(item, scratch)
            actual = K.sha256_file(archive)
            K.require(actual == digest[7:], 'artifact ZIP digest differs from the API digest: ' + name)
            K.require(archive.stat().st_size == item['size_in_bytes'], 'artifact ZIP size differs: ' + name)
            extract(archive, output / 'extracted' / key)
            extracted[key] = output / 'extracted' / key
            record['artifacts'][key] = {'name': name, 'id': item['id'], 'size_in_bytes': item['size_in_bytes'],
                                        'sha256': actual, 'created_at': item['created_at'],
                                        'expires_at': item['expires_at']}
        except K.Rejected as error:
            record['problems'].append(str(error))
    loaded = []
    expected = {'source': source, 'run': run_id, 'attempt': attempt}
    builds = {}
    for platform_name, key in (('windows', 'win-build'), ('gtk', 'gtk-build')):
        if key in extracted:
            builds[platform_name] = K.read_json(extracted[key] / 'build-identity.json')
    for platform_name, prefix in (('windows', 'win'), ('gtk', 'gtk')):
        for number in (1, 2):
            key = '%s-r%d' % (prefix, number)
            if key not in extracted:
                continue
            try:
                item = A.load_round(extracted[key], platform_name, expected)
                build = builds.get(platform_name)
                K.require(build is not None, platform_name + ' build identity is unavailable')
                K.require(item['identity']['program_sha256'] == build['program_sha256'],
                          '%s round %d program differs from the build artifact it consumed' % (platform_name, number))
                loaded.append(item)
            except K.Rejected as error:
                record['problems'].append('%s round %d: %s' % (platform_name, number, error))
    summary = A.build_summary(loaded, expected)
    summary['problems'] = record['problems'] + summary['problems']
    summary['measurement_complete'] = not summary['problems']
    summary['builds'] = builds
    summary['jobs_required'] = list(JOBS)
    K.write_json(output / 'summary.json', summary)
    record['measurement_complete'] = summary['measurement_complete']
    K.write_json(output / 'artifact-identity.json', record)
    print(json.dumps({'measurement_complete': summary['measurement_complete'], 'problems': summary['problems'],
                      'artifacts': {key: value['id'] for key, value in record['artifacts'].items()}}, indent=2))
    if not summary['measurement_complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
