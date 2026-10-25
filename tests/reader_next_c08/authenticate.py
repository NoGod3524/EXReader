"""Authenticate the frozen producer run/artifacts and the S04 protocol run.

The original APK and the SDK staging tree are read only from the sealed producer
artifacts; nothing is rebuilt. Every id, size and digest is re-read from the
Actions API and the downloaded ZIP bytes must equal the sealed digest.
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
                        default=pathlib.Path('tests/reader_next_c08/contract.json'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-authenticate'))
    args = parser.parse_args()
    common.require_actions()
    contract = common.read_json(args.contract)
    producer = contract['producer']
    source_sha = producer['source_sha']
    run_id = str(producer['run_id'])
    attempt = str(producer['attempt'])
    args.output.mkdir(parents=True, exist_ok=True)

    record = common.gh_api('actions/runs/' + run_id + '/attempts/' + attempt)
    if record['head_sha'] != source_sha or str(record['run_attempt']) != attempt \
            or record['conclusion'] != producer['conclusion']:
        raise SystemExit('producer run identity changed: %r' % {
            key: record.get(key) for key in ('head_sha', 'run_attempt', 'conclusion')})
    jobs = common.gh_api('actions/runs/' + run_id + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    job_rows = {}
    for name, job_id in producer['jobs'].items():
        job = next((row for row in jobs if row['id'] == job_id), None)
        if job is None or job['head_sha'] != source_sha or str(job['run_attempt']) != attempt \
                or job['conclusion'] != 'success':
            raise SystemExit('producer job %s is not the sealed successful job' % name)
        job_rows[name] = {'id': job['id'], 'name': job['name'], 'conclusion': job['conclusion'],
                          'head_sha': job['head_sha'], 'run_attempt': job['run_attempt']}

    # S04 protocol run: identity evidence only; a mismatch is reported, never hidden.
    s04 = contract['s04']
    s04_record = {'run_id': s04['run_id'], 'attempt': s04['attempt'], 'matches': False}
    try:
        run = common.gh_api('actions/runs/%d/attempts/%d' % (s04['run_id'], s04['attempt']))
        s04_jobs = common.gh_api('actions/runs/%d/attempts/%d/jobs?per_page=100'
                                 % (s04['run_id'], s04['attempt']))['jobs']
        found = {name: next((job for job in s04_jobs if job['id'] == job_id), None)
                 for name, job_id in s04['jobs'].items()}
        s04_record.update({'head_sha': run['head_sha'], 'conclusion': run['conclusion'],
                           'jobs': {name: (job and {'id': job['id'], 'conclusion': job['conclusion']})
                                    for name, job in found.items()}})
        s04_record['matches'] = (run['head_sha'] == s04['tested_source']
                                 and all(job is not None for job in found.values()))
    except Exception as error:
        s04_record['error'] = '%s: %s' % (type(error).__name__, error)

    now = datetime.now(timezone.utc)
    artifacts = []
    inventory = {'apk': None, 'sdk_stage': None}
    for row in producer['artifacts']:
        meta = common.gh_api('actions/artifacts/' + str(row['id']))
        checks = {
            'id': meta['id'] == row['id'], 'name': meta['name'] == row['name'],
            'bytes': meta['size_in_bytes'] == row['bytes'], 'digest': meta['digest'] == row['digest'],
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
        entry = {key: row[key] for key in ('role', 'id', 'name', 'bytes', 'digest', 'expires_at')}
        entry.update({'downloaded': downloaded, 'checks': checks})
        artifacts.append(entry)
        if row['role'] == 'raw3':
            apks = common.find_suffix(root, producer['apk_member'])
            if len(apks) != 1:
                raise SystemExit('expected exactly one %s, found %d' % (producer['apk_member'], len(apks)))
            apk = {'path': str(apks[0]), 'bytes': apks[0].stat().st_size,
                   'sha256': common.sha256_file(apks[0])}
            if apk['bytes'] != producer['apk_bytes'] or apk['sha256'] != producer['apk_sha256']:
                raise SystemExit('original APK identity differs from the sealed pin: %r' % apk)
            inventory['apk'] = apk
        else:
            jni = common.find_suffix(root, 'lib/libexreader_jni.so')
            if not jni:
                raise SystemExit('SDK staging carries no lib/libexreader_jni.so')
            stage = jni[0].parents[1]
            listing = sorted(path.relative_to(stage).as_posix()
                             for path in stage.rglob('*') if path.is_file())
            inventory['sdk_stage'] = {
                'path': str(stage), 'files': listing[:400], 'file_count': len(listing),
                'libs': [{'path': item, 'sha256': common.sha256_file(stage / item)}
                         for item in listing if item.endswith('.so')],
                'has_library_header': any(item.endswith('exr/library.h') for item in listing)}

    attestation = {'identity': common.identity(),
                   'producer': {'source_sha': source_sha, 'run_id': producer['run_id'],
                                'attempt': producer['attempt'], 'conclusion': record['conclusion'],
                                'jobs': job_rows},
                   's04_protocol_run': s04_record, 'artifacts': artifacts}
    common.write_json(args.output / 'attestation.json', attestation)
    common.write_json(args.output / 'inventory.json', inventory)
    print('authenticated %d artifacts; apk=%s' % (len(artifacts), inventory['apk']))
    print('sdk_stage libs: %s' % [item['path'] for item in inventory['sdk_stage']['libs']])


if __name__ == '__main__':
    main()
