# SPDX-License-Identifier: MIT
"""Executable negative cases for the exact strict verifier, Actions only."""
import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import warnings
import zipfile

from evidence_contract import EXPECTED_CHECKS, package_sha256, required_assets
from strict_summary import artifact_name, require, select_artifact, select_job, validate_run, validate_zip


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    sha, run_id, attempt, runner_os = 'a' * 40, 41, 2, 'Linux'
    now = datetime.datetime(2026, 10, 25, tzinfo=datetime.timezone.utc)
    job = {'id': 51, 'name': 'installed explicit conflict actions (ubuntu-22.04)', 'head_sha': sha,
           'run_id': run_id, 'run_attempt': attempt, 'status': 'completed', 'conclusion': 'success',
           'started_at': '2026-10-24T01:00:00Z', 'completed_at': '2026-10-24T01:01:00Z'}
    run = {'id': run_id, 'head_sha': sha, 'run_attempt': attempt, 'path': '.github/workflows/reader-explicit-conflict-actions.yml'}
    files = {path: (b'\x7fELF executable fixture' if role.endswith('consumer') else b'installed file fixture')
             for path, role in required_assets(runner_os).items()}
    assets = [{'path': path, 'role': role, 'bytes': len(files[path]), 'sha256': hashlib.sha256(files[path]).hexdigest()}
              for path, role in required_assets(runner_os).items()]
    report = {'accepted': True, 'sha': sha, 'run_id': run_id, 'run_attempt': attempt, 'runner_os': runner_os,
              'os': 'Linux', 'job': 'conflict-actions', 'matrix_os': 'ubuntu-22.04', 'local_run': False,
              'checks': EXPECTED_CHECKS, 'assets': assets, 'installed_package_sha256': package_sha256(assets)}
    artifact = {'id': 61, 'name': artifact_name(runner_os, sha, run_id, attempt), 'expired': False,
                'created_at': '2026-10-24T01:00:30Z', 'expires_at': '2027-01-01T00:00:00Z',
                'workflow_run': {'id': run_id, 'head_sha': sha}}

    def bundle(value=None, members=None, extra=()):
        contents = dict(files if members is None else members)
        contents['evidence/evidence.json'] = json.dumps(report if value is None else value).encode()
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(stream, 'w') as archive:
                for path, raw in list(contents.items()) + list(extra):
                    archive.writestr(path, raw)
        raw = stream.getvalue()
        meta = copy.deepcopy(artifact)
        meta.update(size_in_bytes=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())
        return raw, meta

    raw, meta = bundle()
    checks = []

    def record(name):
        checks.append(name)
        print(json.dumps({'check': name, 'pass': True}), flush=True)

    def rejected(name, fn, message):
        try:
            fn()
        except ValueError as error:
            require(message in str(error), 'unexpected rejection in %s: %s' % (name, error))
            record(name)
        else:
            raise AssertionError('strict verifier accepted ' + name)

    def check_zip(data, metadata):
        return validate_zip(data, metadata, runner_os, sha, run_id, attempt)

    def check_job(jobs):
        return select_job(jobs, runner_os, sha, run_id, attempt)

    def check_artifact(values):
        return select_artifact(values, runner_os, sha, run_id, attempt, job, now)

    validate_run(run, sha, run_id, attempt)
    check_job([job]); check_artifact([meta]); check_zip(raw, meta)
    record('valid_same_source_attempt_job_zip_and_native_binary_fixture_is_accepted')
    rejected('wrong_run_source', lambda: validate_run(dict(run, head_sha='b' * 40), sha, run_id, attempt), 'wrong run identity')
    for field, value in (('head_sha', 'b' * 40), ('run_id', 42), ('run_attempt', 1)):
        rejected('wrong_job_' + field, lambda field=field, value=value: check_job([dict(job, **{field: value})]), 'wrong job identity')
    for field, value in (('status', 'in_progress'), ('conclusion', 'failure')):
        rejected('unsuccessful_job_' + field, lambda field=field, value=value: check_job([dict(job, **{field: value})]), 'did not complete successfully')
    rejected('missing_upstream_job', lambda: check_job([]), 'missing or duplicate')
    rejected('duplicate_upstream_job', lambda: check_job([job, job]), 'missing or duplicate')
    rejected('missing_artifact', lambda: check_artifact([]), 'missing or duplicate')
    rejected('duplicate_artifact_name', lambda: check_artifact([meta, dict(meta, id=62)]), 'missing or duplicate')
    for field, value, message in (
            ('size_in_bytes', 0, 'empty or oversized'), ('expired', True, 'expired'),
            ('expires_at', '2026-01-01T00:00:00Z', 'expired'), ('digest', None, 'missing API'),
            ('created_at', '2026-10-23T00:00:00Z', 'outside upstream job lifetime'),
            ('workflow_run', {'id': run_id, 'head_sha': 'b' * 40}, 'wrong artifact source/run')):
        rejected('bad_artifact_' + field, lambda field=field, value=value: check_artifact([dict(meta, **{field: value})]), message)
    rejected('artifact_previous_attempt_name', lambda: check_artifact([dict(meta, name=artifact_name(runner_os, sha, run_id, 1))]), 'missing or duplicate')
    rejected('zip_byte_count_tampered', lambda: check_zip(raw + b'x', meta), 'byte count differs')
    rejected('zip_digest_tampered', lambda: check_zip(raw[:-1] + bytes([raw[-1] ^ 1]), meta), 'digest differs')
    for name, extra, message in (
            ('duplicate_zip_member', [('consumer/conflict-consumer', files['consumer/conflict-consumer'])], 'duplicate ZIP member'),
            ('duplicate_report_member', [('second/evidence.json', json.dumps(report).encode())], 'missing or duplicate evidence'),
            ('zip_path_traversal', [('../outside', b'no')], 'unsafe ZIP member')):
        data, metadata = bundle(extra=extra)
        rejected(name, lambda data=data, metadata=metadata: check_zip(data, metadata), message)
    for field, value, message in (
            ('sha', 'b' * 40, 'wrong report source'), ('run_id', 42, 'wrong report source'),
            ('run_attempt', 1, 'wrong report source'), ('os', 'Windows', 'wrong report platform'),
            ('job', 'unrelated', 'wrong report job'), ('accepted', False, 'unaccepted report'),
            ('local_run', True, 'non-Actions'), ('checks', EXPECTED_CHECKS[:-1], 'named checks'),
            ('installed_package_sha256', '0' * 64, 'package manifest digest')):
        data, metadata = bundle(dict(report, **{field: value}))
        rejected('bad_report_' + field, lambda data=data, metadata=metadata: check_zip(data, metadata), message)
    altered = dict(files); del altered['consumer/conflict-c-consumer']
    data, metadata = bundle(members=altered)
    rejected('missing_actual_c_consumer', lambda: check_zip(data, metadata), 'missing bound binary')
    altered = dict(files); altered['consumer/conflict-consumer'] = b'x' * len(altered['consumer/conflict-consumer'])
    data, metadata = bundle(members=altered)
    rejected('consumer_binary_tampered_with_fresh_zip_digest', lambda: check_zip(data, metadata), 'changed consumer/package SHA-256')
    spoofed = copy.deepcopy(report)
    spoofed['assets'][0]['sha256'] = hashlib.sha256(altered['consumer/conflict-consumer']).hexdigest()
    data, metadata = bundle(spoofed, altered)
    rejected('text_is_not_an_executable_even_with_matching_manifest', lambda: check_zip(data, metadata), 'not a native platform binary')
    Path('strict-evidence').mkdir(exist_ok=True)
    Path('strict-evidence/rejection-checks.json').write_text(json.dumps({'accepted': True, 'checks': checks}, indent=2), encoding='utf-8')
    print(json.dumps({'rejection_checks': len(checks), 'pass': True}))


if __name__ == '__main__':
    main()
