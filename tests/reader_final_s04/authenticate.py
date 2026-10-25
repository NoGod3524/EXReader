"""Authenticate the frozen producer run and its artifacts, then inventory them.

No producer claim is trusted on its own: the run, attempt, job and artifact ids
are re-read from the Actions API, the downloaded ZIP bytes must equal the
sealed digest and size, and every APK inside is hashed here.
"""
import argparse
from datetime import datetime, timezone
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common


def api_time(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=pathlib.Path,
                        default=pathlib.Path('docs/reader-final-s04/apk-contract.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/s04-authenticate'))
    parser.add_argument('--role', action='append', default=None,
                        help='artifact role to authenticate (default: every role)')
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    common.require_actions()
    contract = common.read_json(args.contract)
    producer = contract['producer']
    source_sha = producer['source_sha']
    run_id = str(producer['run_id'])
    attempt = str(producer['attempt'])
    roles = args.role or [row['role'] for row in producer['artifacts']]
    args.output.mkdir(parents=True, exist_ok=True)

    record = common.gh_api('actions/runs/' + run_id + '/attempts/' + attempt)
    if record['head_sha'] != source_sha:
        raise SystemExit('producer run head differs from the sealed source')
    if str(record['run_attempt']) != attempt or record['conclusion'] != producer['conclusion']:
        raise SystemExit('producer run attempt/conclusion changed: %r' % (
            record.get('conclusion'), record.get('run_attempt')))
    jobs = common.gh_api('actions/runs/' + run_id + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    job_rows = {}
    for name, job_id in producer['jobs'].items():
        matches = [job for job in jobs if job['id'] == job_id]
        if not matches:
            raise SystemExit('producer job %s (%s) is absent from the sealed attempt' % (name, job_id))
        job = matches[0]
        if job['head_sha'] != source_sha or str(job['run_attempt']) != attempt or job['conclusion'] != 'success':
            raise SystemExit('producer job %s is not a successful same-attempt job' % name)
        job_rows[name] = {'id': job['id'], 'name': job['name'], 'conclusion': job['conclusion'],
                          'head_sha': job['head_sha'], 'run_attempt': job['run_attempt'],
                          'html_url': job.get('html_url')}

    artifacts = []
    inventory = {'candidate': None, 'baseline': None, 'test_apk': None, 'release_apk': None,
                 'sdk_stage': None, 'apks': [], 'artifacts': artifacts}
    now = datetime.now(timezone.utc)
    for row in producer['artifacts']:
        if row['role'] not in roles:
            continue
        meta = common.gh_api('actions/artifacts/' + str(row['id']))
        checks = {
            'id': meta['id'] == row['id'],
            'name': meta['name'] == row['name'],
            'bytes': meta['size_in_bytes'] == row['bytes'],
            'digest': meta['digest'] == row['digest'],
            'expired': meta['expired'] is False,
            'run': meta['workflow_run']['id'] == producer['run_id'],
            'head': meta['workflow_run']['head_sha'] == source_sha,
            'expires_at': meta['expires_at'] == row['expires_at'],
            'still_valid': api_time(meta['expires_at']) > now,
        }
        if not all(checks.values()):
            raise SystemExit('artifact %s metadata refused: %r' % (row['id'], checks))
        body = common.gh_api_bytes('actions/artifacts/' + str(row['id']) + '/zip')
        downloaded = {'bytes': len(body), 'sha256': common.sha256_bytes(body)}
        if downloaded['bytes'] != row['bytes'] or 'sha256:' + downloaded['sha256'] != row['digest']:
            raise SystemExit('artifact %s ZIP bytes differ from the sealed digest' % row['id'])
        root = args.output / 'artifacts' / row['role']
        common.safe_extract(body, root)
        apks = []
        for apk in common.find_suffix(root, '.apk'):
            apks.append({'relative': apk.relative_to(root).as_posix(),
                         'bytes': apk.stat().st_size,
                         'sha256': common.sha256_file(apk),
                         'path': str(apk)})
        jni = common.find_suffix(root, 'lib/libexreader_jni.so')
        entry = {'role': row['role'], 'id': row['id'], 'name': row['name'],
                 'sealed_bytes': row['bytes'], 'sealed_digest': row['digest'],
                 'expires_at': row['expires_at'], 'downloaded': downloaded,
                 'checks': checks, 'apks': apks, 'extract_root': str(root),
                 'sdk_jni': ([{'path': str(path), 'sha256': common.sha256_file(path),
                               'bytes': path.stat().st_size} for path in jni] if jni else [])}
        artifacts.append(entry)
        inventory['apks'].extend(dict(apk, role=row['role']) for apk in apks)
        for apk in apks:
            relative = apk['relative']
            if relative.endswith('apks/host-debug.apk') and inventory['candidate'] is None:
                inventory['candidate'] = apk
            elif relative.endswith('baseline/host-debug.apk') and inventory['baseline'] is None:
                inventory['baseline'] = apk
            elif relative.endswith('apks/raw3-test.apk') and inventory['test_apk'] is None:
                inventory['test_apk'] = apk
            elif relative.endswith('apks/host-release.apk') and inventory['release_apk'] is None:
                inventory['release_apk'] = apk
        if jni:
            stage = jni[0].parents[1]
            inventory['sdk_stage'] = {'path': str(stage),
                                      'jni': str(jni[0]),
                                      'jni_sha256': common.sha256_file(jni[0]),
                                      'headers': sorted(p.relative_to(stage).as_posix()
                                                        for p in common.find_suffix(stage, 'include/exreader.h'))}

    if 'raw3' in roles and inventory['candidate'] is None:
        raise SystemExit('the authenticated artifact carries no build/android-raw3 apks/host-debug.apk')
    if any(row['role'] == 'page-theme' for row in producer['artifacts'] if row['role'] in roles):
        if not inventory['sdk_stage']:
            raise SystemExit('the authenticated SDK staging artifact carries no libexreader_jni.so')

    attestation = {'identity': common.identity(), 'producer': {
        'source_sha': source_sha, 'run_id': producer['run_id'], 'attempt': producer['attempt'],
        'conclusion': record['conclusion'], 'event': record.get('event'),
        'url': 'https://github.com/' + common.repo_slug() + '/actions/runs/' + run_id,
        'jobs': job_rows}, 'artifacts': artifacts,
        'inventory': {key: inventory[key] for key in ('candidate', 'baseline', 'test_apk',
                                                     'release_apk', 'sdk_stage')},
        'apks': inventory['apks'],
        'accepted': True, 'roles': roles}
    common.write_json(args.output / 'attestation.json', attestation)
    common.write_json(args.output / 'inventory.json', inventory)
    print(common.read_json(args.output / 'inventory.json')['candidate'])
    print('authenticated %d artifact(s), %d APK(s)' % (len(artifacts), len(inventory['apks'])))


if __name__ == '__main__':
    main()
