# SPDX-License-Identifier: MIT
"""Bind this run's uploaded artifact to both packaged programs and every report.

Runs in the Actions authenticate job against the artifact this run uploaded: it
reads the artifact through the GitHub API (id, size, digest, expiry), hashes the
two real GTK programs inside it, and requires the three deciding reports to name
this source, run and attempt with the same program bytes.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED = {'wave3_tools': ('c10-wave3-ui', 'result.json'),
            'compact45': ('c10-compact-ui', 'report.json'),
            'g13_ten': ('c10-atspi-fixes', 'result.json')}
OPTIONAL = {'search': 'c10-search-ui', 'navigation': 'c10-navigation-ui',
            'records': 'c10-records-ui', 'batch_import': 'c10-batch-ui'}
PROGRAMS = {'wave3': 'c10-compact-package', 'off': 'c10-package'}
REPORT_FILES = ('result.json', 'report.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_report(root, folder, name):
    matches = [path for path in root.rglob(name) if path.parent.name == folder]
    assert len(matches) == 1, (folder, str(matches))
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
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
        for key, (folder, filename) in REQUIRED.items():
            path = find_report(root, folder, filename)
            report = json.loads(path.read_text(encoding='utf-8'))
            assert report['source_sha'] == source, key + ' source'
            assert str(report['run_id']) == run and str(report['attempt']) == attempt, key + ' run'
            assert report.get('accepted') is True, key + ' not accepted'
            reports[key] = {'report_sha256': sha(path), 'accepted': True,
                            'program_sha256': report['program_sha256'],
                            'checks': report.get('count', len(report.get('checks', []))),
                            'path': str(path.relative_to(root))}
        assert reports['wave3_tools']['program_sha256'] == programs['wave3']['sha256'], 'wave3 program'
        assert reports['compact45']['program_sha256'] == programs['wave3']['sha256'], 'compact45 program'
        assert reports['g13_ten']['program_sha256'] == programs['off']['sha256'], 'g13 program'
        identity['reports'] = reports
        optional = {}
        for key, folder in OPTIONAL.items():
            directory = [path for path in root.rglob(folder) if path.is_dir()]
            if not directory:
                optional[key] = {'present': False}
                continue
            files = {path.name: sha(path) for path in sorted(directory[0].glob('*.json'))}
            optional[key] = {'present': True, 'files': files}
        identity['optional_suites'] = optional
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
