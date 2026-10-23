#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the six original reading SDK archives from accepted cloud evidence."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import urllib.error
import zipfile

from check_parallel_integration import fetch, pages, require
from reading_required import expected_artifacts, verify_jobs, verify_metadata, verify_publisher

HOSTS = {'Linux': 'X64', 'Windows': 'X64', 'macOS': 'ARM64'}
PROFILES = ('reading-core', 'reading-library')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(raw):
    value = json.loads(raw)
    require(isinstance(value, dict), 'JSON report must be an object')
    return value


def zip_members(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    require(len(set(names)) == len(names), 'duplicate ZIP members')
    require(all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and
                '\\' not in name for name in names), 'unsafe ZIP member path')
    return archive


def one(archive, basename):
    names = [name for name in archive.namelist() if PurePosixPath(name).name == basename]
    require(len(names) == 1, 'missing or duplicate ZIP member: ' + basename)
    return archive.read(names[0])


def verify_run(record, source, run, jobs):
    require(record['id'] == run and record['head_sha'] == source and
            record['path'].split('@')[0] == '.github/workflows/reading-required.yml' and
            record['event'] in ('push', 'workflow_dispatch') and
            record['status'] == 'completed' and record['conclusion'] == 'success',
            'release requires a successful exact-source non-PR reading-required run')
    attempt = record['run_attempt']
    result = verify_jobs(source, run, attempt, jobs)
    require(len(result) == 17 and all(item['status'] == 'completed' and item['conclusion'] == 'success'
                                    for item in result), 'all 17 jobs must finish successfully')
    return result


def verify_ancestry(compare, source, tag_exists, releases, tag):
    require(compare['merge_base_commit']['sha'] == source and compare['status'] in ('ahead', 'identical'),
            'tested source is not an ancestor of the remote default branch')
    require(not tag_exists and not any(item['tag_name'] == tag for item in releases),
            'release tag or release already exists')


def verify_summary(summary, needs, artifacts, source, run, attempt, jobs, publisher):
    require(summary.get('schema') == 1 and summary.get('accepted') is True and summary.get('problems') == [] and
            summary.get('source_sha') == source and str(summary.get('run_id')) == str(run) and
            str(summary.get('run_attempt')) == str(attempt) and summary.get('workflow_head_sha') == source and
            summary.get('published') is False and summary.get('complete_product') is False and
            summary.get('wp16_cpu_credit_seconds') == 0, 'accepted summary identity or declaration changed')
    current = verify_metadata(source, run, attempt, needs, artifacts, source)
    require(sorted(summary['artifacts'], key=lambda item: item['name']) == sorted(current, key=lambda item: item['name']),
            'accepted artifact registry differs from current GitHub metadata')
    fields = ('id', 'name', 'run_attempt', 'head_sha')
    recorded = summary['jobs']
    require(len(recorded) == 17 and sorted([tuple(item[key] for key in fields) for item in recorded]) ==
            sorted([tuple(item[key] for key in fields) for item in jobs]), 'accepted job registry changed')
    require(summary['publisher'] == publisher, 'accepted check publisher changed')
    return current


def verify_candidate(raw_zip, source, run, attempt, host, profile, identity):
    with zip_members(raw_zip) as archive:
        candidate = json_bytes(one(archive, 'candidate.json'))
        manifest_raw = one(archive, 'release-manifest.json')
        manifest = json_bytes(manifest_raw)
        arch = HOSTS[host]
        sdk = identity['sdk_version']
        name = f'EXReader-{profile}-{sdk}-{host}-{arch}.tar.gz'
        for record in (candidate, manifest):
            require(record.get('schema') == 1 and record.get('source_sha') == source and
                    record.get('profile') == profile and record.get('host') == host and record.get('arch') == arch and
                    record.get('published') is False, 'candidate source/profile/platform declaration differs')
            ci = record['ci']
            require(str(ci['GITHUB_RUN_ID']) == str(run) and str(ci['GITHUB_RUN_ATTEMPT']) == str(attempt) and
                    ci['GITHUB_REPOSITORY'] == os.environ['GITHUB_REPOSITORY'] and ci['RUNNER_OS'] == host and
                    ci['RUNNER_ARCH'] == arch, 'candidate run/attempt/runner identity differs')
            expected = {'sdk_version': sdk, 'abi': identity['abi'],
                        'library_schema': identity['library_schema'] if profile == 'reading-library' else None,
                        'library_header_version': identity['library_header_version'] if profile == 'reading-library' else None}
            require(record['identity'] == expected, 'candidate SDK/ABI/library identity differs')
        require(candidate.get('accepted') is True and candidate.get('quality_accepted') is False and
                candidate.get('archive') == name and candidate.get('manifest_sha256') == sha(manifest_raw),
                'candidate seal was not accepted or manifest changed')
        require(candidate['ci'] == manifest['ci'], 'candidate and manifest CI differ')
        payload = one(archive, name)
        require(len(payload) == candidate['bytes'] and sha(payload) == candidate['sha256'], 'sealed tar changed')
    files = manifest['files']
    require(len(files) == candidate['file_count'] > 0 and len({item['path'] for item in files}) == len(files),
            'manifest files empty or duplicated')
    prefix = name[:-7]
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as tar:
        members = tar.getmembers()
        expected_names = {prefix + '/' + item['path'] for item in files} | {prefix + '/release-manifest.json'}
        require(len(members) == len(expected_names) and {item.name for item in members} == expected_names and
                all(item.isfile() and not item.issym() and not item.islnk() and
                    not PurePosixPath(item.name).is_absolute() and '..' not in PurePosixPath(item.name).parts and
                    '\\' not in item.name for item in members), 'tar path, type or member inventory changed')
        require(tar.extractfile(prefix + '/release-manifest.json').read() == manifest_raw, 'inner manifest differs')
        for item in files:
            path = PurePosixPath(item['path'])
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in item['path'] and
                    item['path'] != 'release-manifest.json', 'unsafe manifest path')
            member = tar.getmember(prefix + '/' + item['path'])
            require(member.size == item['bytes'] and bool(member.mode & 0o111) == item['executable'],
                    'tar file size or executable mode changed')
            stream = tar.extractfile(member)
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
            require(digest.hexdigest() == item['sha256'], 'tar file digest changed')
    return name, payload, {'host': host, 'arch': arch, 'profile': profile, 'bytes': len(payload),
                           'sha256': sha(payload), 'manifest_sha256': sha(manifest_raw)}


def download(item):
    repository = os.environ['GITHUB_REPOSITORY']
    raw = subprocess.check_output(['gh', 'api', f'repos/{repository}/actions/artifacts/{item["id"]}/zip'])
    require(sha(raw) == item['digest'].removeprefix('sha256:'), 'downloaded artifact ZIP digest changed')
    return raw


def source_text(source, path):
    record = fetch(f'contents/{path}?ref={source}')
    require(record['encoding'] == 'base64', 'source header is not base64 content')
    return base64.b64decode(record['content']).decode('utf-8')


def prepare(source, run, output):
    require(re.fullmatch('[0-9a-f]{40}', source) and run > 0, 'full source SHA and positive accepted run ID required')
    record = fetch(f'actions/runs/{run}')
    attempt = record['run_attempt']
    jobs = verify_run(record, source, run, pages(f'actions/runs/{run}/attempts/{attempt}/jobs', 'jobs'))
    own = next(item for item in jobs if item['name'] == 'reading-required')
    check_id = fetch(f'actions/jobs/{own["id"]}')['check_run_url'].rsplit('/', 1)[1]
    require(check_id.isdecimal(), 'invalid check ID')
    ruleset = json.loads(source_text(source, 'docs/reading-required-ruleset.json'))
    publisher = verify_publisher(fetch(f'check-runs/{check_id}'), source, ruleset)
    artifacts = pages(f'actions/runs/{run}/artifacts', 'artifacts')
    summary_name = f'reading-required-{run}-{attempt}'
    require(len(artifacts) == 19 and {item['name'] for item in artifacts} == expected_artifacts(run, attempt) | {summary_name},
            'release requires exactly 18 upstream artifacts and the accepted summary')
    summary_artifact = next(item for item in artifacts if item['name'] == summary_name)
    require(summary_artifact['expired'] is False and summary_artifact['size_in_bytes'] > 0 and
            summary_artifact['workflow_run']['head_sha'] == source and summary_artifact['workflow_run']['id'] == run and
            re.fullmatch('sha256:[0-9a-f]{64}', summary_artifact.get('digest', '')), 'summary artifact invalid')
    with zip_members(download(summary_artifact)) as archive:
        summary = json_bytes(one(archive, 'summary.json'))
        needs = json_bytes(one(archive, 'needs.json'))
    verify_summary(summary, needs, artifacts, source, run, attempt, jobs, publisher)
    header = source_text(source, 'include/exr/base.h')
    sdk = re.search(r'^#define EXR_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', header, re.M)
    abi = re.search(r'^#define EXR_ABI_VERSION ([0-9]+)u?$', header, re.M)
    library = re.search(r'^#define EXR_LIBRARY_VERSION "([^"]+)"$', source_text(source, 'include/exr/library.h'), re.M)
    require(sdk and abi and library, 'source SDK/library version declarations missing')
    identity = {'sdk_version': sdk[1], 'abi': int(abi[1]), 'library_schema': 7, 'library_header_version': library[1]}
    require(all(summary['identity'][key] == identity[key] for key in ('sdk_version', 'abi', 'library_schema')),
            'accepted summary version/ABI/schema differs from target source')
    tag = 'reading-sdk-v' + sdk[1]
    repo = fetch('')
    default = fetch('git/ref/heads/' + repo['default_branch'])['object']['sha']
    tag_exists = True
    try:
        fetch('git/ref/tags/' + tag)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        tag_exists = False
    releases = []
    page = 1
    while True:
        batch = fetch(f'releases?per_page=100&page={page}')
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    verify_ancestry(fetch(f'compare/{source}...{default}'), source, tag_exists, releases, tag)
    archives = []
    for host in HOSTS:
        for profile in PROFILES:
            artifact_name = (f'reading-{profile}-{run}-{attempt}' if host == 'Linux' else
                             f'reading-platform-{host}-{profile}-{run}-{attempt}')
            item = next(item for item in artifacts if item['name'] == artifact_name)
            name, payload, sealed = verify_candidate(download(item), source, run, attempt, host, profile, identity)
            (output / name).write_bytes(payload)
            archives.append(dict(sealed, name=name, artifact={key: item[key] for key in ('id', 'name', 'digest', 'size_in_bytes')}))
    (output / 'SHA256SUMS').write_text(''.join(f'{item["sha256"]}  {item["name"]}\n' for item in archives), encoding='utf-8')
    return {'schema': 1, 'prepared': True, 'published': False, 'source_sha': source, 'accepted_run_id': run,
            'accepted_run_attempt': attempt, 'tag': tag, 'default_branch': repo['default_branch'],
            'default_branch_head': default, 'identity': identity, 'publisher': publisher,
            'accepted_summary_artifact': {key: summary_artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes')},
            'archives': archives, 'problems': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--accepted-run-id', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'release plans run only in cloud CI')
    require(not args.output.exists(), 'release plan output already exists')
    args.output.mkdir(parents=True)
    result = {'schema': 1, 'prepared': False, 'published': False, 'source_sha': args.source_sha,
              'accepted_run_id': args.accepted_run_id, 'problems': []}
    try:
        result = prepare(args.source_sha, args.accepted_run_id, args.output)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile) as error:
        result['problems'].append(str(error))
    (args.output / 'plan.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, allow_nan=False))
    return 0 if result['prepared'] else 1


if __name__ == '__main__':
    sys.exit(main())
