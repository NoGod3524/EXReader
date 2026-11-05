#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate a designated Apple mobile producer and stage its app bundles.

The producer is identified by its run, attempt, workflow, head commit and
artifact bytes. The artifact ZIP is downloaded from GitHub Actions, hashed and
compared with the digest the artifact API reported, extracted with ditto, and
searched for installable .app bundles. The staged bundle is recorded with its
executable and Info.plist hashes so the verifier can prove that the bytes it
installs are the bytes that were authenticated.

A producer whose run did not succeed, or whose artifact is missing, is staged as
diagnostic material only: the record names the blocking reasons and no
acceptance can be derived from it.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zip_stage
import bundle_copy
import identity


def require(condition, message):
    if not condition:
        raise ValueError(message)


def api(path):
    proc = subprocess.run(['gh', 'api', path], capture_output=True, text=True)
    require(proc.returncode == 0, 'gh api failed for %s: %s' % (path, (proc.stderr or '')[-2000:]))
    return json.loads(proc.stdout)


def download(repository, artifact_id, destination):
    destination = Path(destination)
    with open(destination, 'wb') as stream:
        proc = subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%s/zip' % (repository, artifact_id)],
                              stdout=stream, stderr=subprocess.PIPE)
    require(proc.returncode == 0, 'artifact download failed: '
            + (proc.stderr or b'').decode('utf-8', 'replace')[-2000:])
    with open(destination, 'rb') as stream:
        require(stream.read(4) == b'PK\x03\x04', 'downloaded artifact is not a ZIP archive')
    return destination


PREFERENCE = ('program-raw', 'failed-program-raw', 'program-legacy', 'failed-program-legacy',
              'program-control', 'failed-program-control')


def rank(app):
    path = app['path']
    for index, token in enumerate(PREFERENCE):
        if token in path:
            return (index, path)
    return (len(PREFERENCE), path)


def choose(apps, device_class):
    wanted = 1 if device_class == 'iphone' else 2
    candidates = [app for app in apps
                  if isinstance(app.get('family'), list) and wanted in app['family']]
    if not candidates:
        candidates = list(apps)
    require(candidates, 'artifact contains no .app bundle for ' + device_class)
    return sorted(candidates, key=rank)[0]


def stage(app, output, device_class):
    destination = Path(output) / 'staging' / device_class / Path(app['path']).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(), 'staged app already exists: ' + str(destination))
    if sys.platform == 'darwin':
        subprocess.run(['ditto', str(app['path']), str(destination)], check=True, capture_output=True)
    else:
        import shutil
        shutil.copytree(app['path'], str(destination), symlinks=True)
    staged = zip_stage.app_facts(destination)
    bundle_copy.same(bundle_copy.snapshot(destination), bundle_copy.snapshot(app['path']))
    require(staged['executable_sha256'] == app['executable_sha256'],
            'staged executable differs from the extracted bundle')
    require(staged['info_plist_sha256'] == app['info_plist_sha256'],
            'staged Info.plist differs from the extracted bundle')
    staged['staged'] = destination.relative_to(Path(output)).as_posix()
    staged['snapshot'] = bundle_copy.snapshot(destination)
    staged['original_binding'] = app.get('original_binding')
    return staged


def write(output, record):
    record['blocked_by'] = sorted(set(record['blocked_by']))
    (Path(output) / 'producer-source.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'kind': record['kind'], 'eligible': record['eligible'],
                      'blocked_by': record['blocked_by'],
                      'run': (record['run'] or {}).get('id'),
                      'conclusion': (record['run'] or {}).get('conclusion'),
                      'artifact': (record['artifact'] or {}).get('name'),
                      'artifact_bytes': (record['artifact'] or {}).get('size_in_bytes'),
                      'apps': len(record['apps']),
                      'chosen': {key: value['executable_sha256']
                                 for key, value in record['chosen'].items()}}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'NoGod3524/EXReader'))
    parser.add_argument('--run-id', type=int, default=identity.RUN)
    parser.add_argument('--sha', default=identity.SOURCE)
    parser.add_argument('--attempt', type=int, default=identity.ATTEMPT)
    parser.add_argument('--workflow', default=identity.WORKFLOW)
    parser.add_argument('--artifact')
    parser.add_argument('--expect-digest')
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--expect-bytes', type=int)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--implementation-sha', required=True)
    parser.add_argument('--branch', default=os.environ.get('GITHUB_REF_NAME'))
    parser.add_argument('--device-classes', default='iphone,ipad')
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists(), 'choose a new intake directory: ' + str(output))
    output.mkdir(parents=True)
    classes = [value.strip() for value in args.device_classes.split(',') if value.strip()]
    require(classes and len(classes) == len(set(classes)) and set(classes) <= {'iphone', 'ipad'}, 'unsupported/duplicate device classes')
    implementation = identity.implementation(args.implementation_sha, args.branch)
    record = {
        'schema': 1,
        'kind': 'reader-final-s05-producer-source',
        'repository': args.repository,
        'implementation': implementation,
        'designation': {'run_id': args.run_id, 'attempt': args.attempt, 'head_sha': args.sha, 'workflow': args.workflow,
                        'artifact': args.artifact, 'expect_digest': args.expect_digest},
        'run': None,
        'artifact': None,
        'apps': [],
        'chosen': {},
        'eligible': False,
        'blocked_by': [],
        'grants': {'device_signing': False, 'app_store': False, 'physical_device': False,
                   'simulator': True},
        'limits': ['simulator installation only',
                   'no signing identity, provisioning profile or notarization',
                   'no App Store or TestFlight delivery',
                   'file sharing only as the actual Info.plist declares'],
    }
    archive = None
    if args.zip is not None:
        archive = args.zip.absolute()
        require(args.expect_digest, 'an external ZIP needs --expect-digest')
        record['kind'] = 'reader-final-s05-external-zip'
        record['external'] = {'zip': str(archive), 'bytes': archive.stat().st_size,
                              'sha256': zip_stage.sha256(archive), 'expect_digest': args.expect_digest}
        digest = record['external']['sha256']
        expected = args.expect_digest.replace('sha256:', '').strip().lower()
        require(digest == expected, 'external ZIP sha256 %s differs from %s' % (digest, expected))
        if args.expect_bytes is not None:
            require(archive.stat().st_size == args.expect_bytes,
                    'external ZIP size %d differs from %d' % (archive.stat().st_size, args.expect_bytes))
        record['blocked_by'].append('producer_run_not_authenticated')
    else:
        require(args.run_id is not None and args.sha and args.artifact,
                'designate --run-id, --sha and --artifact (or pass --zip)')
        run = api('repos/%s/actions/runs/%s/attempts/%s' % (args.repository, args.run_id, args.attempt))
        pinned = (args.run_id, args.sha, args.attempt, args.workflow) == (identity.RUN, identity.SOURCE, identity.ATTEMPT, identity.WORKFLOW)
        if pinned:
            run, record['producer_jobs'] = identity.producer_jobs(args.repository)
        else:
            record['blocked_by'].append('not_the_frozen_successful_producer')
        record['run'] = {key: run.get(key) for key in
                         ('id', 'name', 'path', 'head_sha', 'head_branch', 'event', 'status',
                          'conclusion', 'run_attempt', 'created_at', 'updated_at', 'html_url')}
        listing = api('repos/%s/actions/runs/%s/artifacts?per_page=100' % (args.repository, args.run_id))
        candidates = [item for item in listing.get('artifacts') or [] if item.get('name') == args.artifact]
        require(len(candidates) <= 1, 'duplicate designated producer artifact')
        if not candidates:
            record['blocked_by'].append('producer_artifact_missing')
        else:
            artifact = candidates[0]
            identity.metadata(artifact, args.sha, args.run_id)
            if pinned:
                require(len(classes) == 1, 'one exact producer artifact per device class')
                expected_pin = identity.ARTIFACTS[classes[0]]
                require(all(artifact.get(key) == value for key, value in expected_pin.items()), 'producer artifact differs from fixed device pin')
            record['artifact'] = {key: artifact.get(key) for key in
                                  ('id', 'name', 'size_in_bytes', 'digest', 'created_at',
                                   'expires_at', 'expired', 'workflow_run')}
            archive = download(args.repository, artifact['id'], output / 'artifact.zip')
            digest = zip_stage.sha256(archive)
            reported = str(artifact.get('digest') or '')
            expected = args.expect_digest or reported
            record['artifact']['download'] = {
                'bytes': archive.stat().st_size,
                'sha256': digest,
                'reported_digest': reported,
                'expected_digest': expected,
                'matches_api_digest': bool(reported) and digest == reported.replace('sha256:', '').strip().lower(),
                'matches_expected_digest': digest == expected.replace('sha256:', '').strip().lower(),
                'bytes_match_api': archive.stat().st_size == artifact.get('size_in_bytes'),
            }
            require(record['artifact']['download']['matches_api_digest'],
                    'downloaded artifact bytes do not match the artifact API digest')
            require(record['artifact']['download']['matches_expected_digest'],
                    'downloaded artifact bytes do not match the designated digest')
            if not record['artifact']['download']['bytes_match_api']:
                record['blocked_by'].append('producer_artifact_size_mismatch')
            if run.get('status') != 'completed' or run.get('conclusion') != 'success':
                record['blocked_by'].append('producer_run_conclusion_failure')
            if run.get('run_attempt') != args.attempt:
                record['blocked_by'].append('producer_attempt_mismatch')
            if run.get('head_sha') != args.sha:
                record['blocked_by'].append('producer_source_mismatch')
            if run.get('path') != args.workflow:
                record['blocked_by'].append('producer_workflow_mismatch')
            if artifact.get('expired'):
                record['blocked_by'].append('producer_artifact_expired')
    if archive is None:
        write(output, record)
        return 0
    extraction = output / 'extract'
    identity.inspect_zip(archive.read_bytes())
    record['extraction'] = zip_stage.extract(archive, extraction)
    if args.zip is None:
        archive.unlink()
    apps = [zip_stage.app_facts(path) for path in zip_stage.find_apps(extraction)]
    record['apps'] = apps
    if not apps:
        record['blocked_by'].append('producer_app_bundle_missing')
    for device_class in classes:
        try:
            if not record['blocked_by']:
                actual_app = extraction / 'program-raw/EXReaderHost.app'
                value = identity.unique([app for app in apps if Path(app['path']) == actual_app], 'exact successful raw app missing/duplicated')
                require((1 if device_class == 'iphone' else 2) in value.get('family', []), 'raw app device family differs')
                value['original_binding'] = bundle_copy.authenticate_original(extraction, actual_app, device_class)
            else:
                value = choose(apps, device_class)
        except ValueError as failure:
            record['blocked_by'].append('producer_app_bundle_missing_' + device_class)
            record.setdefault('intake_failures', {})[device_class] = str(failure)
            continue
        record['chosen'][device_class] = stage(value, output, device_class)
    if len(record['chosen']) != len(classes):
        record['blocked_by'].append('producer_app_incomplete')
    if record['chosen']:
        # A tar keeps the bundle modes and symlinks when the staged bytes cross a
        # second artifact upload; the ZIP container does not guarantee them.
        subprocess.run(['tar', '-cf', str(output / 'staging.tar'), '-C', str(output), 'staging'],
                       check=True, capture_output=True)
        record['staging_tar'] = dict(bytes=(output / 'staging.tar').stat().st_size,
                                     sha256=zip_stage.sha256(output / 'staging.tar'))
    record['eligible'] = not record['blocked_by'] and len(record['chosen']) == len(classes)
    write(output, record)
    return 0


if __name__ == '__main__':
    sys.exit(main())
