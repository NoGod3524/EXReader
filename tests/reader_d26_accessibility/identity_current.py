# D26 strict current aggregate; original identity gate and raw failures are retained.
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
    'g13_complete': ('d26-g13-current', 'result.json', 'accessibility_accepted', 'off', 32),
    'account_a11y': ('d26-account', 'result.json', 'accepted', 'off', 3),
    'wave3_tools': ('d26-tools-current', 'result.json', 'accepted', 'wave3', 10),
    'compact45': ('c10-compact-ui', 'report.json', 'accepted', 'wave3', 45),
    'g13_ten': ('c10-atspi-fixes', 'result.json', 'accepted', 'off', 10),
    'search': ('c10-search-ui', 'result.json', 'search_scope_passed', 'off', None),
    'navigation': ('c10-navigation-ui', 'result.json', 'navigation_scope_passed', 'off', None),
    'records': ('c10-records-ui', 'report.json', 'reading_records_scope_passed', 'off', None),
    'batch_import': ('c10-batch-ui', 'report.json', 'batch_import_scope_passed', 'off', None),
    'drop_import': ('c10-drop-ui', 'report.json', 'drop_import_scope_passed', 'off', None),
    'drop_backend': ('c10-drop-backend', 'report.json', 'ok', 'drop_backend', None),
}
PROGRAMS = {'wave3': 'c10-compact-package', 'off': 'c10-package'}
AUXILIARIES = {'drop_backend': 'reader-gtk-drop-backend', 'drop_source': 'reader-gtk-drop-native-source'}


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
    parser.add_argument('--account-artifact', type=Path, required=True)
    parser.add_argument('--account-archive', type=Path, required=True)
    args = parser.parse_args()
    run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    source = os.environ['GITHUB_SHA']
    name = 'reader-wave3-c10-%s-%s' % (run, attempt)
    listing = json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/%s/actions/runs/%s/artifacts' % (os.environ['GITHUB_REPOSITORY'], run)], text=True))
    matches = [row for row in listing['artifacts'] if row['name'] == name]
    assert len(matches) == 1, 'artifact %s count %d' % (name, len(matches))
    artifact = matches[0]
    identity = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'current_verified': False, 'historical_accepted': False,
                'scope': 'complete corrected current audit, native regressions and account suite; historical outcomes separate',
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
        for key, filename in AUXILIARIES.items():
            found = [path for path in root.rglob(filename) if path.is_file()]
            assert len(found) == 1, (filename, [str(path) for path in found])
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
            program_sha = report['probe_sha256' if key == 'drop_backend' else 'program_sha256']
            assert program_sha == programs[program]['sha256'], key + ' program'
            checks = report['checks']
            assert checks and all(row.get('pass', row.get('passed')) is True for row in checks), key + ' checks'
            count = report.get('count', report.get('checks_total', len(checks)))
            assert count == len(checks), key + ' count'
            if expected_count is not None:
                assert count == expected_count, (key, count, expected_count)
            reports[key] = {'report_sha256': sha(path), 'scope_passed': True,
                            'program_sha256': program_sha,
                            'checks': count,
                            'path': str(path.relative_to(root))}
        identity['reports'] = reports
        # Original outcomes are independently authenticated and never relabeled green.
        historical = {}
        for key, folder, field, program in (
                ('full_g13', 'd26-g13', 'accessibility_accepted', 'off'),
                ('five_tools', 'c10-wave3-ui', 'accepted', 'wave3')):
            path = find_report(root, folder, 'result.json')
            report = json.loads(path.read_text())
            assert report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt
            assert report['program_sha256'] == programs[program]['sha256']
            execution_path = path.parent / 'execution.json'
            execution = json.loads(execution_path.read_text())
            assert execution['report_sha256'] == sha(path)
            assert execution['historical_accepted'] == report[field]
            if key == 'full_g13':
                assert report['audit_completed'] is True and len(report['checks']) == 32
            historical[key] = dict(accepted=report[field], exit_code=execution['exit_code'],
                checks=len(report['checks']), failed=[row['name'] for row in report['checks']
                                                     if not row.get('pass', row.get('passed'))],
                failure=report.get('failure'), report_sha256=sha(path),
                path=str(path.relative_to(root)))
        identity['historical'] = historical
        identity['historical_accepted'] = all(row['accepted'] for row in historical.values())
        account_name = 'reader-d26-account-retained-%s-%s' % (run, attempt)
        account_matches = [row for row in listing['artifacts'] if row['name'] == account_name]
        assert len(account_matches) == 1
        account_artifact = account_matches[0]
        assert not account_artifact['expired']
        assert account_artifact['digest'] == 'sha256:' + sha(args.account_archive)
        assert account_artifact['size_in_bytes'] == args.account_archive.stat().st_size
        raw_path = args.account_artifact / 'result.json'
        raw = json.loads(raw_path.read_text())
        assert raw['source_sha'] == source and str(raw['run_id']) == run and str(raw['attempt']) == attempt
        assert raw['accepted'] is True and raw['built'] is True
        for relative, recorded in raw['files'].items():
            file = args.account_artifact / relative
            assert file.stat().st_size == recorded['bytes'] and sha(file) == recorded['sha256'], relative
        owner_shas = {sha(args.account_artifact / name) for name in
                      ('raw-owner/gtk-raw3-owner', 'legacy-owner/gtk-raw3-owner')}
        for phase in raw['phases']:
            path = args.account_artifact / phase['report']
            assert sha(path) == phase['report_sha256'] and phase['program_sha256'] in owner_shas
            value = json.loads(path.read_text())
            assert value['accepted'] and len(value['checks']) == phase['checks']
            assert all(row['passed'] for row in value['checks'])
        ui_sha = sha(args.account_artifact / 'package/EXReader-Linux/bin/exreader-linux')
        for phase in raw['network']['phases']:
            ui = phase['session']
            assert ui['accepted'] and ui['actual_gtk_ui_executed']
            assert ui['source_sha'] == source and str(ui['run_id']) == run and str(ui['attempt']) == attempt
            assert ui['program_sha256'] == ui_sha and phase['remote_bytes_unchanged']
        identity['retained_account'] = dict(accepted=True, report_sha256=sha(raw_path),
            artifact_id=account_artifact['id'], digest=account_artifact['digest'],
            phases=len(raw['phases']), https_phases=len(raw['network']['phases']),
            scope=raw['scope'], historical_apple_packet_only=raw['network']['peer'])
        identity['current_verified'] = True
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
