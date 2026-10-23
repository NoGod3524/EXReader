#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic metadata protocol checks, not SDK or real-document acceptance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reading_required import (GROUPS, ci_identity, expected_artifacts, verify_metadata,
                              expected_jobs, verify_jobs, workflow_identity, verify_publisher,
                              PACKAGE_ARCH, one, validate_candidates)
from reading_release import check_profile, digest, seal
from check_reading_release import fixture, write

source, run, attempt = 'a' * 40, '12', '3'
needs = {key: {'result': 'success'} for key in GROUPS}
artifacts = [{'id': index, 'name': name, 'expired': False, 'size_in_bytes': 10,
              'workflow_run': {'head_sha': source, 'id': int(run)}, 'digest': 'sha256:' + 'b' * 64}
             for index, name in enumerate(sorted(expected_artifacts(run, attempt)))]
assert len(verify_metadata(source, run, attempt, needs, artifacts)) == 18
checks = 1
mutations = [lambda n, a: n.pop('native'), lambda n, a: n.update(unexpected={'result': 'success'}),
             lambda n, a: a.pop(), lambda n, a: a.append(copy.deepcopy(a[0])),
             lambda n, a: a[0].update(expired=True), lambda n, a: a[0].update(size_in_bytes=0),
             lambda n, a: a[0].update(digest=None),
             lambda n, a: a[0]['workflow_run'].update(head_sha='c' * 40),
             lambda n, a: a[0]['workflow_run'].update(id=13),
             lambda n, a: a[0].update(name=a[0]['name'][:-1] + '2')]
for group in GROUPS:
    for status in ('failure', 'cancelled', 'skipped'):
        mutations.append(lambda n, a, g=group, s=status: n[g].update(result=s))
for change in mutations:
    n, a = copy.deepcopy((needs, artifacts)); change(n, a)
    try:
        verify_metadata(source, run, attempt, n, a)
    except (ValueError, KeyError, TypeError):
        checks += 1
    else:
        raise AssertionError('accepted invalid upstream evidence')
for nested in (False, True):
    row = {'source_sha': source, 'run_id': run, 'run_attempt': attempt,
           'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': attempt}}
    ci_identity(row, source, run, attempt, nested); checks += 1
    for field, value in (('source', 'c' * 40), ('run', '13'), ('attempt', '2')):
        changed = copy.deepcopy(row)
        if field == 'source': changed['source_sha'] = value
        elif nested: changed['ci']['GITHUB_RUN_ID' if field == 'run' else 'GITHUB_RUN_ATTEMPT'] = value
        else: changed['run_id' if field == 'run' else 'run_attempt'] = value
        try: ci_identity(changed, source, run, attempt, nested)
        except ValueError: checks += 1
        else: raise AssertionError('accepted foreign report identity')
record = {'id': int(run), 'run_attempt': int(attempt), 'path': '.github/workflows/reading-required.yml',
          'event': 'push', 'head_sha': source}
assert workflow_identity(record, source, run, attempt, ['b' * 40]) == source; checks += 1
record.update(event='pull_request', head_sha='c' * 40)
assert workflow_identity(record, source, run, attempt, ['b' * 40, 'c' * 40]) == 'c' * 40; checks += 1
pr_artifacts = copy.deepcopy(artifacts)
for item in pr_artifacts: item['workflow_run']['head_sha'] = 'c' * 40
assert len(verify_metadata(source, run, attempt, needs, pr_artifacts, 'c' * 40)) == 18; checks += 1
for changes, parents in [({}, ['b' * 40]), ({}, ['b' * 40, 'd' * 40]),
                         ({'run_attempt': 2}, ['b' * 40, 'c' * 40]),
                         ({'path': '.github/workflows/native.yml'}, ['b' * 40, 'c' * 40]),
                         ({'event': 'workflow_dispatch'}, ['b' * 40, 'c' * 40])]:
    mutant = dict(record, **changes)
    try: workflow_identity(mutant, source, run, attempt, parents)
    except ValueError: checks += 1
    else: raise AssertionError('accepted unrelated tested merge/run')
jobs = [{'id': index, 'name': name, 'run_id': int(run), 'run_attempt': int(attempt),
         'head_sha': source, 'status': 'completed', 'conclusion': 'success'}
        for index, name in enumerate(sorted(expected_jobs() | {'reading-required'}))]
assert len(verify_jobs(source, run, attempt, jobs)) == 17; checks += 1
for change in [lambda j: j.pop(), lambda j: j.append(copy.deepcopy(j[0])),
               lambda j: j[0].update(run_attempt=2), lambda j: j[0].update(run_id=13),
               lambda j: j[0].update(head_sha='d' * 40),
               lambda j: j[0].update(name='unexpected'),
               lambda j: j[0].update(status='in_progress'),
               lambda j: j[0].update(conclusion='failure'),
               lambda j: j[0].update(conclusion='skipped')]:
    mutant = copy.deepcopy(jobs); change(mutant)
    try: verify_jobs(source, run, attempt, mutant)
    except ValueError: checks += 1
    else: raise AssertionError('accepted missing or reused upstream job')
ruleset = json.loads((Path(__file__).resolve().parents[1] / 'docs/reading-required-ruleset.json').read_text())
publisher = {'id': 1, 'name': 'reading-required', 'head_sha': source,
             'app': {'id': 15368, 'slug': 'github-actions'}}
verify_publisher(publisher, source, ruleset); checks += 1
for change in [lambda p: p['app'].update(id=1), lambda p: p['app'].update(slug='foreign-app'),
               lambda p: p.update(head_sha='d' * 40), lambda p: p.update(name='other-check')]:
    mutant = copy.deepcopy(publisher); change(mutant)
    try: verify_publisher(mutant, source, ruleset)
    except ValueError: checks += 1
    else: raise AssertionError('accepted foreign check publisher')


def package(root, host='Windows', profile='reading-core'):
    name = f'reading-{profile}' if host == 'Linux' else f'reading-platform-{host}-{profile}'
    return root / f'{name}-{run}-{attempt}'


def package_fixture(root):
    for host, arch in PACKAGE_ARCH.items():
        for profile in ('reading-core', 'reading-library'):
            folder = package(root, host, profile)
            stage, evidence, runtime, database = fixture(folder, profile)
            identity = check_profile(profile, source, stage, evidence, runtime, database)
            ci = {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': attempt, 'RUNNER_OS': host, 'RUNNER_ARCH': arch}
            license_path = evidence / 'licenses.json'
            license_report = json.loads(license_path.read_text()); license_report['ci'] = ci
            write(license_path, license_report)
            seal(stage, folder / 'release-candidate', profile, source, identity, ci, 1000, host, arch)


def mutate_package(root, changes, name='candidate.json', rehash=False):
    folder = package(root); path = one(folder, name)
    value = json.loads(path.read_text()); value.update(changes); write(path, value)
    if rehash:
        candidate_path = one(folder, 'candidate.json')
        candidate = json.loads(candidate_path.read_text()); candidate['manifest_sha256'] = digest(path)
        write(candidate_path, candidate)


def mutate_pair(root, key, value, profile='reading-core'):
    folder = package(root, profile=profile); path = one(folder, 'candidate.json')
    candidate = json.loads(path.read_text()); candidate['identity'][key] = value
    manifest_path = one(folder, 'release-manifest.json')
    manifest = json.loads(manifest_path.read_text()); manifest['identity'] = candidate['identity']
    write(manifest_path, manifest); candidate['manifest_sha256'] = digest(manifest_path)
    name = f"EXReader-{profile}-{candidate['identity']['sdk_version']}-Windows-X64.tar.gz"
    (path.parent / candidate['archive']).rename(path.parent / name)
    candidate['archive'] = name; write(path, candidate)


def escape_archive(root):
    path = one(package(root), 'candidate.json'); candidate = json.loads(path.read_text())
    (path.parent / candidate['archive']).rename(root / 'outside.tar.gz')
    candidate['archive'] = '../../../outside.tar.gz'; write(path, candidate)


file_changes = [lambda r: one(package(r), 'candidate.json').unlink(),
                lambda r: one(package(r), 'licenses.json').unlink(),
                lambda r: next(package(r).rglob('*.tar.gz')).unlink(),
                lambda r: next(package(r).rglob('*.tar.gz')).write_bytes(b'altered archive'),
                lambda r: mutate_package(r, {'bytes': 1}),
                lambda r: mutate_package(r, {'sha256': '0' * 64}),
                lambda r: mutate_package(r, {'source_sha': 'b' * 40}),
                lambda r: mutate_package(r, {'host': 'Linux'}),
                lambda r: mutate_package(r, {'arch': 'ARM64'}),
                lambda r: mutate_package(r, {'ci': {'GITHUB_RUN_ID': '13', 'GITHUB_RUN_ATTEMPT': attempt}}),
                lambda r: mutate_package(r, {'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': '2'}}),
                lambda r: mutate_package(r, {'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': attempt,
                                                  'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'}}),
                lambda r: mutate_package(r, {'published': True}),
                lambda r: mutate_package(r, {'quality_accepted': True}),
                lambda r: mutate_package(r, {'manifest_sha256': '0' * 64}),
                lambda r: mutate_package(r, {'source_sha': 'b' * 40}, 'release-manifest.json', True),
                lambda r: mutate_package(r, {'host': 'Linux'}, 'release-manifest.json', True),
                lambda r: mutate_package(r, {'arch': 'ARM64'}, 'release-manifest.json', True),
                lambda r: mutate_package(r, {'ci': {}}, 'release-manifest.json', True),
                lambda r: mutate_package(r, {'file_count': 0}),
                lambda r: mutate_package(r, {'release_ready': False}, 'licenses.json'),
                lambda r: mutate_package(r, {'mandatory_missing': ['license']}, 'licenses.json'),
                lambda r: mutate_package(r, {'source_sha': 'b' * 40}, 'licenses.json'),
                lambda r: mutate_package(r, {'ci': {'GITHUB_RUN_ID': '13', 'GITHUB_RUN_ATTEMPT': attempt}}, 'licenses.json'),
                lambda r: mutate_package(r, {'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': '2'}}, 'licenses.json'),
                lambda r: mutate_pair(r, 'sdk_version', '3.41.0'),
                lambda r: mutate_pair(r, 'abi', 2),
                lambda r: mutate_pair(r, 'library_header_version', 'wrong'),
                lambda r: mutate_pair(r, 'library_schema', 8, 'reading-library'),
                lambda r: mutate_pair(r, 'library_header_version', '3.35.0', 'reading-library'),
                escape_archive]
for change in [None, *file_changes]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); package_fixture(root)
        if change is None:
            assert len(validate_candidates(root, source, run, attempt)) == 6; checks += 1
            continue
        change(root)
        try: validate_candidates(root, source, run, attempt)
        except (OSError, ValueError, KeyError, TypeError): checks += 1
        else: raise AssertionError('accepted incomplete or changed native package files')
print(json.dumps({'accepted': True, 'checks': checks, 'sdk_credit': 0, 'real_document_credit': 0}))
