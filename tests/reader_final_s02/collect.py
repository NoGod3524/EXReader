#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate the pinned GTK compact producer artefact through the Actions API.

The producer source is a different branch (codex/reader-gtk-compact). This tool
never checks out that branch: it reads the completed run, verifies the artefact
digest GitHub reports against the downloaded bytes, extracts only the compact
payload and its producer evidence, and records every identity S02 needs.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import common

PRODUCER_SOURCE = '57203a52aee439be5194ee0a4b13563a975e8daf'
PRODUCER_SEAL = '9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
PRODUCER_RUN = 40206458217
PAYLOAD_ROOT = 'EXReader-Linux'


def gh(*arguments, binary=False):
    result = subprocess.run(['gh', *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise common.S02Error('gh %s failed (%d): %s' % (
            ' '.join(arguments), result.returncode, result.stderr.decode('utf-8', 'replace')[-2000:]))
    return result.stdout if binary else result.stdout.decode('utf-8')


def gh_json(path):
    return json.loads(gh('api', path))


def gh_bytes(path):
    return gh('api', path, binary=True)


def segments(name):
    return [part for part in name.split('/') if part not in ('', '.')]


def find_member(members, *tail):
    """Locate the single zip member whose trailing segments equal tail."""
    matches = [name for name in members if segments(name)[-len(tail):] == list(tail)]
    if len(matches) > 1:
        exact = [name for name in matches if segments(name) == list(tail)]
        matches = exact or matches
    return matches[0] if matches else None


def read_member(archive, name):
    with archive.open(name) as stream:
        return stream.read()


def iso(value):
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--run', type=int, default=PRODUCER_RUN)
    parser.add_argument('--source', default=PRODUCER_SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common.need(args.repository, 'GITHUB_REPOSITORY is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = common.Checks()

    run = gh_json('repos/%s/actions/runs/%d' % (args.repository, args.run))
    attempt = int(run.get('run_attempt') or 1)
    head_sha = run.get('head_sha') or ''
    checks.add('producer_run_completed',
               run.get('status') == 'completed' and run.get('conclusion') == 'success',
               'run %s attempt %s %s/%s' % (args.run, attempt, run.get('status'), run.get('conclusion')))
    checks.add('producer_source_matches_pin', head_sha == args.source,
               'run head_sha %s pinned %s' % (head_sha, args.source))

    listing = gh_json('repos/%s/actions/runs/%d/artifacts?per_page=100' % (args.repository, args.run))
    artifacts = listing.get('artifacts') or []
    rows = [{'id': item['id'], 'name': item['name'], 'size_in_bytes': item['size_in_bytes'],
             'digest': item.get('digest'), 'expired': item.get('expired'),
             'expires_at': item.get('expires_at'), 'created_at': item.get('created_at')}
            for item in artifacts]
    wanted = 'reader-gtk-341-final-%d-%d' % (args.run, attempt)
    selected = next((row for row in rows if row['name'] == wanted), None)
    if selected is None:
        candidates = [row for row in rows
                      if row['name'].startswith('reader-gtk-341-final-')
                      and 'summary' not in row['name']]
        selected = candidates[0] if candidates else None
    checks.add('producer_artifact_present', selected is not None,
               'artifact %r from %s' % (wanted, [row['name'] for row in rows]))
    common.need(selected is not None, 'the producer run has no compact artefact')

    archive_path = output / 'producer-artifact.zip'
    payload_bytes = gh_bytes('repos/%s/actions/artifacts/%d/zip' % (args.repository, selected['id']))
    archive_path.write_bytes(payload_bytes)
    digest = hashlib.sha256(payload_bytes).hexdigest()
    reported = (selected.get('digest') or '').split(':', 1)[-1]
    checks.add('producer_zip_digest', digest == reported and len(payload_bytes) == selected['size_in_bytes'],
               'sha256 %s api %s, bytes %d api %d' % (digest, reported, len(payload_bytes),
                                                      selected['size_in_bytes']))
    expires = iso(selected['expires_at']) if selected.get('expires_at') else None
    checks.add('producer_zip_not_expired',
               bool(expires) and not selected.get('expired') and expires > datetime.now(timezone.utc),
               'expires_at %s expired=%s' % (selected.get('expires_at'), selected.get('expired')))

    with zipfile.ZipFile(str(archive_path)) as archive:
        members = archive.namelist()
        summary = {}
        for name in members:
            parts = segments(name)
            key = '/'.join(parts[:2])
            summary[key] = summary.get(key, 0) + 1
        tar_member = find_member(members, 'compact-package', PAYLOAD_ROOT + '.tar.gz')
        build_member = find_member(members, 'compact-package', 'build.json')
        deps_member = find_member(members, 'compact-package', 'runtime-dependencies.txt')
        report_member = find_member(members, 'compact-ui', 'report.json')
        checks.add('producer_members_present',
                   bool(tar_member and build_member and report_member),
                   'tar=%r build=%r deps=%r report=%r members=%d' % (
                       tar_member, build_member, deps_member, report_member, len(members)))
        common.need(tar_member and build_member, 'producer payload members are missing')

        tar_bytes = read_member(archive, tar_member)
        (output / 'producer-payload.tar.gz').write_bytes(tar_bytes)
        tar_sha = hashlib.sha256(tar_bytes).hexdigest()
        build = json.loads(read_member(archive, build_member).decode('utf-8'))
        (output / 'producer-build.json').write_bytes(read_member(archive, build_member))
        if deps_member:
            (output / 'producer-runtime-dependencies.txt').write_bytes(read_member(archive, deps_member))
        report = None
        if report_member:
            raw = read_member(archive, report_member)
            (output / 'producer-compact-report.json').write_bytes(raw)
            report = json.loads(raw.decode('utf-8'))

        extracted = common.safe_extract_tar(output / 'producer-payload.tar.gz',
                                            output / 'payload', expect_root=PAYLOAD_ROOT)

        loose = {}
        for name in members:
            parts = segments(name)
            if 'compact-package' in parts:
                index = parts.index('compact-package')
                if len(parts) > index + 2 and parts[index + 1] == PAYLOAD_ROOT:
                    loose['/'.join(parts[index + 2:])] = read_member(archive, name)
        loose_ok = bool(loose) and all(
            record['path'] in loose
            and hashlib.sha256(loose[record['path']]).hexdigest() == record['sha256']
            for record in extracted['members'])
        checks.add('producer_loose_payload_matches_tar', loose_ok,
                   '%d loose members for %d tar members' % (len(loose), len(extracted['members'])))

    payload = output / 'payload'
    files = common.walk_tree(payload)
    by_path = {record['path']: record for record in files}
    declared = build.get('files') or {}
    missing = sorted(set(declared) - set(by_path))
    unlisted = sorted(set(by_path) - set(declared))
    changed = sorted(name for name, expected in declared.items()
                     if name in by_path and by_path[name]['sha256'] != expected)
    checks.add('producer_build_json_matches_payload',
               not missing and not unlisted and not changed,
               'declared %d, walked %d, missing %s, unlisted %s, changed %s' % (
                   len(declared), len(files), missing[:6], unlisted[:6], changed[:6]))
    checks.add('producer_build_identity',
               build.get('source_sha') == args.source
               and str(build.get('sdk_version')) == '3.41.0'
               and int(build.get('abi') or 0) == 1,
               'source %s sdk %s abi %s gtk %s' % (build.get('source_sha'),
                                                   build.get('sdk_version'),
                                                   build.get('abi'), build.get('gtk_version')))

    program = by_path.get('bin/exreader-linux') or {}
    identity = common.run(payload / 'bin/exreader-linux', '--version', check=False,
                          env=common.minimal_env({}))
    version = identity.stdout.strip()
    checks.add('producer_program_version', version == '3.41.0 1',
               'version %r exit %d stderr %r' % (version, identity.returncode,
                                                 identity.stderr.strip()[-200:]))

    producer_checks = (report or {}).get('checks') or []
    passed = [row for row in producer_checks if row.get('passed') is True]
    checks.add('producer_self_evidence',
               bool(report) and report.get('accepted') is True
               and int(report.get('run_id') or 0) == args.run
               and report.get('source_sha') == args.source
               and report.get('program_sha256') == program.get('sha256')
               and len(passed) == len(producer_checks) and len(passed) >= 40,
               'report accepted=%r source=%r run=%r program=%r checks=%d/%d' % (
                   (report or {}).get('accepted'), (report or {}).get('source_sha'),
                   (report or {}).get('run_id'), (report or {}).get('program_sha256'),
                   len(passed), len(producer_checks)))

    document = {
        'schema': 1,
        'kind': 's02-producer-authentication',
        'verifier_source': os.environ.get('GITHUB_SHA', ''),
        'repository': args.repository,
        'run': {'id': run.get('id'), 'name': run.get('name'), 'path': run.get('path'),
                'head_sha': head_sha, 'head_branch': run.get('head_branch'),
                'event': run.get('event'), 'status': run.get('status'),
                'conclusion': run.get('conclusion'), 'attempt': attempt,
                'created_at': run.get('created_at'), 'updated_at': run.get('updated_at'),
                'html_url': run.get('html_url')},
        'pinned': {'source': args.source, 'evidence_seal': PRODUCER_SEAL,
                   'artifact_name': wanted},
        'artifacts': rows,
        'selected_artifact': selected,
        'zip': {'name': archive_path.name, 'bytes': len(payload_bytes), 'sha256': digest,
                'api_digest': selected.get('digest'), 'members': len(members),
                'top_level': dict(sorted(summary.items(), key=lambda item: -item[1])[:24])},
        'members': {'payload_tar': tar_member, 'payload_tar_sha256': tar_sha,
                    'build_json': build_member, 'runtime_dependencies': deps_member,
                    'producer_report': report_member, 'payload_root': extracted['root']},
        'build': build,
        'payload': {'files': files, 'totals': {'files': len(files),
                                               'bytes': sum(item['bytes'] for item in files)}},
        'program': {'path': 'bin/exreader-linux', 'bytes': program.get('bytes'),
                    'sha256': program.get('sha256'), 'mode': program.get('mode'),
                    'version': version},
        'producer_self_evidence': {'accepted': (report or {}).get('accepted'),
                                   'source_sha': (report or {}).get('source_sha'),
                                   'run_id': (report or {}).get('run_id'),
                                   'program_sha256': (report or {}).get('program_sha256'),
                                   'checks': len(producer_checks),
                                   'passed': len(passed),
                                   'scope': (report or {}).get('scope'),
                                   'screenshots': len((report or {}).get('screenshots') or {})},
        'checks': checks.items,
        'problems': checks.failed(),
        'ok': checks.accepted(),
    }
    common.write_json(output / 'producer.json', document)
    print(json.dumps({'producer_run': args.run, 'attempt': attempt, 'zip_bytes': len(payload_bytes),
                      'zip_sha256': digest, 'artifact_id': selected['id'],
                      'program_sha256': program.get('sha256'),
                      'payload_files': len(files), 'ok': checks.accepted(),
                      'failed': checks.failed()}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
