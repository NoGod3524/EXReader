#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Consolidate the S01 evidence and authenticate the uploaded candidate artifact.

Actions only. The artifact identity comes from the workflow API (id, bytes,
digest, expiry, run and source binding) and the downloaded container is re-hashed
here, so the manifest, the archive and the recorded program are tied to the same
run instead of being stitched together from different sources.
"""
import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from contract import (APPROVED_SDK, PRODUCER_SOURCE, read_json, require, sha256, write_json,
                      manifest_problems)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch

WORKFLOW = 'reader-final-s01.yml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--moved', type=Path, required=True)
    parser.add_argument('--artifact-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'consolidate S01 evidence in GitHub Actions only')
    require(os.environ.get('GH_TOKEN'), 'GH_TOKEN is required to authenticate the uploaded artifact')
    source = os.environ.get('GITHUB_SHA')
    run_id, attempt = os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT')
    manifest = read_json(args.manifest)
    moved = read_json(args.moved)
    problems = manifest_problems(manifest)
    if manifest['implementation_source'] != source:
        problems.append('the manifest implementation source differs from this run')
    if moved.get('implementation_source') != source:
        problems.append('the moved-package evidence belongs to another source')
    if moved.get('producer_source') != manifest['producer_source']:
        problems.append('the moved-package evidence belongs to another producer')
    if moved['program']['sha256'] != manifest['program']['sha256']:
        problems.append('the moved program differs from the assembled program')
    blockers = list(manifest.get('release_blockers') or [])
    for blocker in moved.get('release_blockers') or []:
        if blocker not in blockers:
            blockers.append(blocker)

    require(str(args.artifact_id).isdigit(), 'a positive artifact id is required')
    meta = fetch('actions/artifacts/' + str(int(args.artifact_id)))
    workflow_run = meta.get('workflow_run') or {}
    artifact = {'id': meta.get('id'), 'name': meta.get('name'), 'bytes': meta.get('size_in_bytes'),
                'digest': meta.get('digest'), 'expires_at': meta.get('expires_at'),
                'expired': meta.get('expired'), 'workflow_run_id': workflow_run.get('id'),
                'head_sha': workflow_run.get('head_sha')}
    if workflow_run.get('head_sha') != source:
        problems.append('the uploaded artifact belongs to another source')
    if str(workflow_run.get('id')) != str(run_id):
        problems.append('the uploaded artifact belongs to another run')
    if meta.get('expired') is not False:
        problems.append('the uploaded artifact is not valid')
    raw = bytes(download_artifact_zip(int(args.artifact_id)) or b'')
    require(raw, 'the artifact download returned nothing')
    artifact['download_bytes'] = len(raw)
    artifact['download_sha256'] = sha256(raw)
    if len(raw) != meta.get('size_in_bytes'):
        problems.append('the downloaded artifact size differs from the API record')
    if 'sha256:' + artifact['download_sha256'] != (meta.get('digest') or ''):
        problems.append('the downloaded artifact digest differs from the API record')
    member_digest = None
    with zipfile.ZipFile(io.BytesIO(raw)) as container:
        names = [name for name in container.namelist() if name.endswith('candidate.zip')]
        if len(names) != 1:
            problems.append('the uploaded artifact does not carry exactly one candidate archive')
        else:
            member = container.read(names[0])
            member_digest = sha256(member)
            artifact['candidate_member'] = names[0]
            artifact['candidate_bytes'] = len(member)
            artifact['candidate_sha256'] = member_digest
            if len(member) != manifest['zip']['bytes'] or member_digest != manifest['zip']['sha256']:
                problems.append('the archived candidate archive differs from the manifest')

    checks = [
        {'name': 'fixed-producer-and-approved-sdk-3.41', 'passed':
            manifest['producer_source'] == PRODUCER_SOURCE and
            manifest['sdk']['version'] == '3.41.0' and
            manifest['sdk']['approved_source'] == APPROVED_SDK},
        {'name': 'candidate-archive-authenticated-by-this-run', 'passed':
            artifact.get('candidate_sha256') == manifest['zip']['sha256'] and
            artifact.get('digest') == 'sha256:' + artifact.get('download_sha256', '')},
        {'name': 'program-is-the-unsigned-native-gui-image', 'passed':
            manifest['program']['authenticode'] == 'unsigned' and
            manifest['program']['pe']['subsystem'] == 'windows-gui'},
        {'name': 'every-package-file-declared-with-license-and-provenance', 'passed':
            not manifest['problems'] and len(manifest['files']) >= 9},
        {'name': 'dependencies-are-operating-system-dlls-only', 'passed':
            bool(manifest['dependencies']['entries']) and
            all(row['os_provided'] and not row['forbidden'] and not row['packaged']
                for row in manifest['dependencies']['entries'])},
        {'name': 'package-moved-to-unicode-path-with-spaces', 'passed':
            moved['destinations']['unicode'] and moved['destinations']['spaces'] and
            moved['move']['first_removed'] and not moved['move']['removed']},
        {'name': 'moved-program-self-test-complete', 'passed':
            moved['self_test']['exit_code'] == 0 and moved['self_test']['checks'] >= 26},
        {'name': 'retained-compact-acceptance-complete', 'passed':
            moved['compact']['accepted'] and moved['compact']['checks'] >= 22},
        {'name': 'no-test-secret-in-distributed-bytes', 'passed':
            not manifest['scans']['test_secrets']['hits']},
        {'name': 'no-build-machine-path-in-distributed-bytes', 'passed': not blockers},
    ]
    for check in checks:
        if not check['passed']:
            problems.append('failed check: ' + check['name'])

    result = {'schema': 1, 'accepted': not problems and not blockers,
              'release_ready': not problems and not blockers,
              'release_blockers': blockers,
              'source': {'implementation': source, 'producer': manifest['producer_source'],
                         'producer_tree': manifest['producer_tree'],
                         'sdk_approved': manifest['sdk']['approved_source'],
                         'sdk_version': manifest['sdk']['version']},
              'run': {'id': run_id, 'attempt': attempt, 'workflow': WORKFLOW},
              'artifact': artifact,
              'candidate': {'zip': manifest['zip'], 'program': manifest['program'],
                            'sdk': manifest['sdk'], 'licenses': manifest['licenses'],
                            'files': len(manifest['files']),
                            'retained_sources': len(manifest['retained'])},
              'moved': {'destinations': moved['destinations'], 'move': moved['move'],
                        'self_test': moved['self_test'], 'compact': moved['compact'],
                        'mutation': moved['mutation'], 'network': moved['network'],
                        'dependencies': moved['dependencies']},
              'checks': checks, 'problems': problems,
              'not_verified': moved['not_verified'] + [
                  'multi-package integration with the other reader platforms',
                  'release, tag, store publication, signing or notarisation'],
              'scope': ('S01 candidate package only: per-file identity, license attribution, '
                        'dependency provenance, Unicode path portability and the producer\'s own '
                        'compact acceptance on the moved program.')}
    write_json(args.output, result)
    print(json.dumps({'accepted': result['accepted'], 'artifact': artifact,
                      'checks': len(checks), 'problems': problems,
                      'release_blockers': blockers}), flush=True)
    require(not problems and not blockers,
            'S01 evidence refused: ' + json.dumps(problems + blockers))


if __name__ == '__main__':
    main()
