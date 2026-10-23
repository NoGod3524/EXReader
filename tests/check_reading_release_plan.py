#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic release-plan protocol tests; never real SDK/release evidence."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from prepare_reading_release import (HOSTS, PROFILES, sha, verify_ancestry, verify_candidate,
                                    verify_run, verify_summary, zip_members)
from reading_required import GROUPS, expected_artifacts, expected_jobs

SOURCE = 'a' * 40
IDENTITY = {'sdk_version': '3.40.0', 'abi': 1, 'library_schema': 7, 'library_header_version': '3.34.0'}


def fixture(host='Linux', profile='reading-core', mutation=None):
    arch = HOSTS[host]
    name = f'EXReader-{profile}-3.40.0-{host}-{arch}.tar.gz'
    prefix = name[:-7]
    content = b'synthetic SDK file, no executable SDK\n'
    identity = dict(IDENTITY)
    if profile == 'reading-core':
        identity.update(library_schema=None, library_header_version=None)
    manifest = {'schema': 1, 'source_sha': SOURCE, 'host': host, 'arch': arch, 'profile': profile,
                'published': False, 'identity': identity,
                'ci': {'GITHUB_REPOSITORY': os.environ['GITHUB_REPOSITORY'], 'GITHUB_RUN_ID': '123',
                       'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'synthetic', 'RUNNER_OS': host, 'RUNNER_ARCH': arch},
                'files': [{'path': 'include/test.h', 'bytes': len(content), 'sha256': sha(content), 'executable': False}]}
    mode, extra, duplicate, inner = 0o644, None, False, None
    candidate_extra = {}
    if mutation == 'wrong_source':
        manifest['source_sha'] = 'b' * 40
    elif mutation == 'wrong_arch':
        manifest['arch'] = 'ARM64' if arch == 'X64' else 'X64'
    elif mutation == 'wrong_runner':
        manifest['ci']['RUNNER_OS'] = 'unexpected'
    elif mutation == 'wrong_attempt':
        manifest['ci']['GITHUB_RUN_ATTEMPT'] = '2'
    elif mutation == 'wrong_repository':
        manifest['ci']['GITHUB_REPOSITORY'] = 'another/repository'
    elif mutation == 'wrong_abi':
        manifest['identity']['abi'] = 2
    elif mutation == 'wrong_schema':
        manifest['identity']['library_schema'] = 6
    elif mutation == 'published':
        manifest['published'] = True
    elif mutation == 'file_digest':
        manifest['files'][0]['sha256'] = '0' * 64
    elif mutation == 'file_size':
        manifest['files'][0]['bytes'] += 1
    elif mutation == 'mode':
        mode = 0o755
    elif mutation == 'extra':
        extra = prefix + '/extra'
    elif mutation == 'path_escape':
        manifest['files'][0]['path'] = '../escape'
    elif mutation == 'symlink':
        extra = 'symlink'
    elif mutation == 'duplicate_tar':
        duplicate = True
    elif mutation == 'inner_manifest':
        inner = b'{}'
    elif mutation == 'quality_granted':
        candidate_extra['quality_accepted'] = True
    elif mutation == 'unaccepted':
        candidate_extra['accepted'] = False
    raw_manifest = json.dumps(manifest).encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for path, data in [(prefix + '/' + manifest['files'][0]['path'], content),
                           (prefix + '/release-manifest.json', raw_manifest if inner is None else inner)]:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = mode if path.endswith('test.h') else 0o644
            tar.addfile(info, io.BytesIO(data))
            if duplicate:
                tar.addfile(info, io.BytesIO(data))
        if extra:
            info = tarfile.TarInfo(extra)
            if extra == 'symlink':
                info.type, info.linkname = tarfile.SYMTYPE, '/etc/passwd'
            tar.addfile(info)
    payload = stream.getvalue()
    candidate = {key: copy.deepcopy(manifest[key]) for key in
                 ('schema', 'source_sha', 'host', 'arch', 'profile', 'published', 'identity', 'ci')}
    candidate.update(accepted=True, quality_accepted=False, archive=name, bytes=len(payload),
                     sha256=sha(payload), manifest_sha256=sha(raw_manifest), file_count=len(manifest['files']))
    candidate.update(candidate_extra)
    if mutation == 'tar_digest':
        candidate['sha256'] = '0' * 64
    elif mutation == 'manifest_digest':
        candidate['manifest_sha256'] = '0' * 64
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode='w') as archive:
        archive.writestr('release-candidate/candidate.json', json.dumps(candidate))
        archive.writestr('release-candidate/release-manifest.json', raw_manifest)
        archive.writestr('release-candidate/' + name, payload)
    return output.getvalue()


def main():
    os.environ.setdefault('GITHUB_REPOSITORY', 'synthetic/protocol')
    cases = []

    def positive(name, operation):
        operation()
        cases.append({'name': name, 'passed': True})

    def rejected(name, operation):
        try:
            operation()
        except (ValueError, KeyError, TypeError):
            cases.append({'name': name, 'passed': True})
            return
        raise AssertionError('accepted invalid protocol fixture: ' + name)

    record = {'id': 123, 'run_attempt': 1, 'head_sha': SOURCE, 'event': 'push', 'status': 'completed',
              'conclusion': 'success', 'path': '.github/workflows/reading-required.yml'}
    jobs = [dict(id=index + 1, name=name, run_id=123, run_attempt=1, head_sha=SOURCE,
                 status='completed', conclusion='success') for index, name in enumerate(sorted(expected_jobs() | {'reading-required'}))]
    positive('completed_same_source_17_jobs', lambda: verify_run(record, SOURCE, 123, jobs))
    for key, value in [('event', 'pull_request'), ('status', 'in_progress'), ('conclusion', 'failure'),
                       ('head_sha', 'b' * 40), ('path', '.github/workflows/other.yml')]:
        changed = dict(record, **{key: value})
        rejected('run_' + key, lambda changed=changed: verify_run(changed, SOURCE, 123, jobs))
    for key, value in [('conclusion', 'skipped'), ('status', 'in_progress'), ('run_attempt', 2), ('head_sha', 'b' * 40)]:
        changed = copy.deepcopy(jobs)
        next(item for item in changed if item['name'] == 'reading-required')[key] = value
        rejected('own_job_' + key, lambda changed=changed: verify_run(record, SOURCE, 123, changed))
    rejected('missing_job', lambda: verify_run(record, SOURCE, 123, jobs[:-1]))
    compare = {'merge_base_commit': {'sha': SOURCE}, 'status': 'ahead'}
    positive('default_branch_ancestor', lambda: verify_ancestry(compare, SOURCE, False, [], 'reading-sdk-v3.40.0'))
    rejected('not_default_ancestor', lambda: verify_ancestry({'merge_base_commit': {'sha': 'b'*40}, 'status': 'diverged'}, SOURCE, False, [], 'tag'))
    rejected('tag_exists', lambda: verify_ancestry(compare, SOURCE, True, [], 'tag'))
    rejected('draft_release_exists', lambda: verify_ancestry(compare, SOURCE, False, [{'tag_name': 'tag', 'draft': True}], 'tag'))
    needs = {group: {'result': 'success'} for group in GROUPS}
    artifacts = [dict(id=index + 1, name=name, size_in_bytes=100, digest='sha256:' + 'b'*64,
                      expired=False, workflow_run={'head_sha': SOURCE, 'id': 123})
                 for index, name in enumerate(sorted(expected_artifacts(123, 1)))]
    publisher = {'integration_id': 15368, 'publisher': 'github-actions', 'check_id': 999}
    summary = {'schema': 1, 'accepted': True, 'problems': [], 'source_sha': SOURCE, 'run_id': '123',
               'run_attempt': '1', 'workflow_head_sha': SOURCE, 'published': False, 'complete_product': False,
               'wp16_cpu_credit_seconds': 0, 'publisher': publisher,
               'jobs': [{key: item[key] for key in ('id', 'name', 'run_attempt', 'head_sha', 'status', 'conclusion')} for item in jobs],
               'artifacts': [{key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest')} for item in artifacts]}
    next(item for item in summary['jobs'] if item['name'] == 'reading-required').update(status='in_progress', conclusion=None)
    positive('accepted_summary_closure', lambda: verify_summary(summary, needs, artifacts, SOURCE, 123, 1, jobs, publisher))
    for key, value in [('accepted', False), ('problems', ['rejected']), ('source_sha', 'b'*40),
                       ('run_attempt', '2'), ('publisher', {'integration_id': 1}), ('artifacts', [])]:
        changed = dict(summary, **{key: value})
        rejected('summary_' + key, lambda changed=changed: verify_summary(changed, needs, artifacts, SOURCE, 123, 1, jobs, publisher))
    changed = copy.deepcopy(artifacts)
    changed[0]['expired'] = True
    rejected('expired_artifact', lambda: verify_summary(summary, needs, changed, SOURCE, 123, 1, jobs, publisher))
    for host in HOSTS:
        for profile in PROFILES:
            positive(host + '_' + profile, lambda host=host, profile=profile:
                     verify_candidate(fixture(host, profile), SOURCE, 123, 1, host, profile, IDENTITY))
    for mutation in ('wrong_source', 'wrong_arch', 'wrong_runner', 'wrong_attempt', 'wrong_repository',
                     'wrong_abi', 'wrong_schema', 'published', 'file_digest', 'file_size', 'mode', 'extra',
                     'path_escape', 'symlink', 'duplicate_tar', 'inner_manifest', 'quality_granted',
                     'unaccepted', 'tar_digest', 'manifest_digest'):
        rejected('candidate_' + mutation, lambda mutation=mutation:
                 verify_candidate(fixture(mutation=mutation), SOURCE, 123, 1, 'Linux', 'reading-core', IDENTITY))
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode='w') as archive:
        archive.writestr('../escape', b'x')
    rejected('zip_path_escape', lambda: zip_members(output.getvalue()))
    print(json.dumps({'protocol_only': True, 'published': False, 'cases': len(cases),
                      'passed': len(cases), 'results': cases}, allow_nan=False))


if __name__ == '__main__':
    main()
