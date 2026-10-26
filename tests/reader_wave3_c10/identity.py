# SPDX-License-Identifier: MIT
"""Bind this run's uploaded artifact to both packaged programs and every report.

Runs in the Actions authenticate job against the artifact this run uploaded: it
reads the artifact through the GitHub API (id, size, digest, expiry), hashes the
two real GTK programs inside it, and requires every retained business report to name
this source, run and attempt with the same program bytes.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED = {
    'wave3_tools': ('c10-wave3-ui', 'result.json', 'accepted', 'wave3', 10),
    'compact45': ('c10-compact-ui', 'report.json', 'accepted', 'wave3', 45),
    'g13_ten': ('c10-atspi-fixes', 'result.json', 'accepted', 'off', 10),
    'search': ('c10-search-ui', 'result.json', 'search_scope_passed', 'off', None),
    'navigation': ('c10-navigation-ui', 'result.json', 'navigation_scope_passed', 'off', None),
    'records': ('c10-records-ui', 'report.json', 'reading_records_scope_passed', 'off', None),
    'batch_import': ('c10-batch-ui', 'report.json', 'batch_import_scope_passed', 'off', None),
}
PROGRAMS = {'wave3': 'c10-compact-package', 'off': 'c10-package'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_report(root, folder, name):
    matches = [path for path in root.rglob(name) if path.parent.name == folder]
    assert len(matches) == 1, (folder, str(matches))
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    source = os.environ['GITHUB_SHA']
    name = 'reader-wave3-c10-%s-%s' % (run, attempt)
    listing = json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/%s/actions/runs/%s/artifacts' % (os.environ['GITHUB_REPOSITORY'], run)], text=True))
    matches = [row for row in listing['artifacts'] if row['name'] == name]
    assert len(matches) == 1, 'artifact %s count %d' % (name, len(matches))
    artifact = matches[0]
    identity = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'verified': False,
                'artifact': {'id': artifact['id'], 'name': artifact['name'],
                             'size_in_bytes': artifact['size_in_bytes'], 'digest': artifact.get('digest'),
                             'expires_at': artifact['expires_at'], 'expired': artifact['expired']}}
    problems = []
    try:
        assert artifact['expired'] is False, 'artifact already expired'
        if args.archive:
            archive_sha = sha(args.archive)
            archive_size = args.archive.stat().st_size
            identity['archive'] = {'sha256': archive_sha, 'size_in_bytes': archive_size}
            assert artifact.get('digest') == 'sha256:' + archive_sha, 'original ZIP digest'
            assert archive_size == artifact['size_in_bytes'], 'original ZIP size'
        root = args.artifact
        programs = {}
        for key, folder in PROGRAMS.items():
            found = [path for path in root.rglob('exreader-linux')
                     if path.parent.name == 'bin' and path.parent.parent.name == 'EXReader-Linux'
                     and path.parent.parent.parent.name == folder]
            assert len(found) == 1, (folder, [str(path) for path in found])
            programs[key] = {'path': str(found[0].relative_to(root)), 'sha256': sha(found[0])}
        identity['programs'] = programs
        reports = {}
        for key, (folder, filename, passed_field, program, expected_count) in REQUIRED.items():
            path = find_report(root, folder, filename)
            report = json.loads(path.read_text(encoding='utf-8'))
            assert report['source_sha'] == source, key + ' source'
            assert str(report['run_id']) == run and str(report['attempt']) == attempt, key + ' run'
            assert report.get(passed_field) is True, key + ' scope did not pass'
            assert not report.get('diagnostic_only'), key + ' diagnostic only'
            assert report.get('program_source_sha', source) == source, key + ' program source'
            assert report['program_sha256'] == programs[program]['sha256'], key + ' program'
            checks = report['checks']
            assert checks and all(row.get('pass', row.get('passed')) is True for row in checks), key + ' checks'
            count = report.get('count', report.get('checks_total', len(checks)))
            assert count == len(checks), key + ' count'
            if expected_count is not None:
                assert count == expected_count, (key, count, expected_count)
            reports[key] = {'report_sha256': sha(path), 'scope_passed': True,
                            'program_sha256': report['program_sha256'],
                            'checks': count,
                            'path': str(path.relative_to(root))}
        identity['reports'] = reports
        identity['verified'] = True
    except BaseException as error:
        problems.append(repr(error))
    identity['problems'] = problems
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(identity, indent=2), flush=True)
    if problems:
        sys.exit('artifact identity could not be bound')


if __name__ == '__main__':
    main()
