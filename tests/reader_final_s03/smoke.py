#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Relocate one .app candidate and run the producer's original native smoke test.

The smoke test is the producer's own tools/check_apple_host.py with --device
macos, unmodified and invoked from the producer checkout. This module moves the
bundle to a path with spaces and non-ASCII characters, runs it once (open) and
again with the previous run's state still present (reopen), both inside a proven
network-denied envelope, and decides the result from the reports those runs wrote.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec

RUN_TIMEOUT = 900


def command(*arguments, timeout=RUN_TIMEOUT):
    try:
        done = subprocess.run([str(item) for item in arguments], capture_output=True,
                              text=True, errors='replace', timeout=timeout)
        return done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired:
        return None, 'timeout after %d seconds' % timeout


def application_support(home):
    return home / 'Library' / 'Application Support' / 'EXReaderHostTests'


def state_snapshot(roots):
    """Hash every file of the host test state under each candidate root."""
    snapshot = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*')):
            if path.is_file() and not path.is_symlink():
                snapshot[str(path)] = spec.digest(path)
    return snapshot


def run_check(producer, bundle, output, home, log, sandbox=None):
    home.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['HOME'] = str(home)
    env['CFFIXED_USER_HOME'] = str(home)
    argv = [sys.executable, str(producer / 'tools/check_apple_host.py'),
            '--bundle', str(bundle), '--device', 'macos', '--output', str(output)]
    if sandbox is not None:
        argv = ['sandbox-exec', '-f', str(sandbox)] + argv
    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors='replace',
                              env=env, cwd=str(producer), timeout=RUN_TIMEOUT)
        code, text = done.returncode, done.stdout + done.stderr
    except FileNotFoundError as error:
        code, text = None, 'missing tool: ' + str(error)
    except subprocess.TimeoutExpired:
        code, text = None, 'timeout after %d seconds' % RUN_TIMEOUT
    log.write_text('$ ' + ' '.join(argv) + '\n' + text, encoding='utf-8')
    report_path = output / 'report.json'
    report = None
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
        except ValueError:
            report = None
    return {'exit': code, 'log': log.name, 'argv': argv, 'output': str(output),
            'report_path': str(report_path) if report_path.is_file() else None,
            'report': report, 'previous_state': []}


def codesign_facts(bundle):
    verify_code, verify_text = command('codesign', '--verify', '--deep', '--strict',
                                       '--verbose=2', bundle, timeout=300)
    detail_code, detail_text = command('codesign', '-dv', '--verbose=4', bundle, timeout=300)
    gatekeeper_code, gatekeeper_text = command('spctl', '--assess', '--type', 'execute',
                                               '--verbose=4', bundle, timeout=300)
    staple_code, staple_text = command('xcrun', 'stapler', 'validate', bundle, timeout=300)
    return {
        'verify_exit': verify_code, 'verify': verify_text.strip(),
        'detail_exit': detail_code, 'detail': detail_text.strip(),
        'gatekeeper_exit': gatekeeper_code, 'gatekeeper': gatekeeper_text.strip(),
        'stapler_exit': staple_code, 'stapler': staple_text.strip(),
        'adhoc': 'Signature=adhoc' in detail_text,
        'authority': 'Authority=' in detail_text,
        'notarized': staple_code == 0,
        'quarantined': 'com.apple.quarantine' in (command('xattr', '-l', bundle, timeout=120)[1] or ''),
    }


def offline_envelope(evidence):
    profile = evidence / 'offline.sb'
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(spec.OFFLINE_PROFILE, encoding='utf-8')
    control_code, control_text = command(sys.executable, '-c', spec.OFFLINE_PROBE, timeout=120)
    denied_code, denied_text = command('sandbox-exec', '-f', profile, sys.executable,
                                       '-c', spec.OFFLINE_PROBE, timeout=120)
    mechanism = 'sandbox-exec' if denied_code == spec.OFFLINE_PROBE_DENIED else None
    return {'mechanism': mechanism, 'profile': spec.OFFLINE_PROFILE,
            'profile_path': str(profile),
            'control_exit': control_code, 'control_output': control_text.strip(),
            'control_reachable': control_code == 0,
            'denied_exit': denied_code, 'denied_output': denied_text.strip(),
            'denied': denied_code == spec.OFFLINE_PROBE_DENIED}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--candidate', choices=sorted(spec.CANDIDATES), required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--source-sha', default=spec.PRODUCER_SHA)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()

    app = args.app.absolute()
    producer = args.producer.absolute()
    evidence = args.evidence.absolute()
    evidence.mkdir(parents=True, exist_ok=True)
    name = args.candidate
    problems = []
    source_files, source_links = spec.file_map(app)

    # 1. Baseline on the path the producer built.
    baseline_home = evidence / 'homes' / name / 'baseline'
    baseline = run_check(producer, app, evidence / 'reports' / name / 'baseline',
                         baseline_home, evidence / ('smoke-' + name + '-baseline.log'))

    # 2. Relocate into a path with a space and non-ASCII characters.
    relocated_root = evidence / 'relocated' / spec.RELOCATED_SEGMENT
    relocated_root.mkdir(parents=True, exist_ok=True)
    relocated = relocated_root / 'EXReader.app'
    copy_code, copy_text = command('ditto', app, relocated, timeout=RUN_TIMEOUT)
    moved_files, moved_links = spec.file_map(relocated) if relocated.is_dir() else ({}, {})
    problems += spec.relocation_problems({p: e['sha256'] for p, e in source_files.items()},
                                         {p: e['sha256'] for p, e in moved_files.items()},
                                         str(relocated))
    if source_links != moved_links:
        problems.append('relocation_link_set')

    # 3. Proven network-denied envelope.
    offline = offline_envelope(evidence)
    problems += spec.offline_problems(offline)

    # 4. Offline open and then offline reopen on the moved bundle.
    offline_home = evidence / 'homes' / name / 'offline'
    state_roots = [application_support(offline_home),
                   Path.home() / 'Library' / 'Application Support' / 'EXReaderHostTests']
    before = state_snapshot(state_roots)
    open_run = run_check(producer, relocated, evidence / 'reports' / name / 'offline-open',
                         offline_home, evidence / ('smoke-' + name + '-offline-open.log'),
                         sandbox=Path(offline['profile_path']))
    after = state_snapshot(state_roots)
    created = sorted(path for path in after if before.get(path) != after[path])
    reopen_run = run_check(producer, relocated, evidence / 'reports' / name / 'offline-reopen',
                           offline_home, evidence / ('smoke-' + name + '-offline-reopen.log'),
                           sandbox=Path(offline['profile_path']))
    final = state_snapshot(state_roots)
    if not created:
        problems.append('reopen_without_previous_state')
    reopened = sorted(path for path in final if final[path] != after.get(path))

    phases = {'baseline': baseline, 'offline-open': open_run, 'offline-reopen': reopen_run}
    for phase in spec.SMOKE_PHASES:
        record = phases[phase]
        problems += [phase + ': ' + item for item in
                     spec.report_problems(record['report'], name, args.source_sha)]
        if record['exit'] != 0:
            problems.append(phase + ': checker_exit:' + str(record['exit']))
        if phase != 'baseline' and 'sandbox-exec' not in (record['argv'][0] if record['argv'] else ''):
            problems.append(phase + ': not_run_inside_offline_envelope')

    lists = {phase: (phases[phase]['report'] or {}).get('checks') for phase in spec.SMOKE_PHASES}
    if lists['baseline'] != lists['offline-open']:
        problems.append('relocation_changed_checks')
    if lists['offline-open'] != lists['offline-reopen']:
        problems.append('reopen_changed_checks')

    facts = codesign_facts(relocated)
    if facts['verify_exit'] != 0:
        problems.append('relocated_codesign_invalid')
    if not facts['adhoc']:
        problems.append('relocated_signature_not_adhoc')
    if facts['authority']:
        problems.append('relocated_bundle_carries_signing_authority')

    archive = evidence / ('EXReader-' + name + '-relocated.zip')
    zip_code, zip_text = command('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                                 relocated, archive, timeout=RUN_TIMEOUT)
    if zip_code != 0 or not archive.is_file():
        problems.append('relocated_archive_failed')

    report = {
        'schema': 1,
        'candidate': name,
        'verifier_package': 'tests/reader_final_s03',
        'producer_sha': args.source_sha,
        'sdk_version': spec.SDK_VERSION,
        'original_smoke_test': str(producer / 'tools/check_apple_host.py'),
        'original_smoke_test_argv': ['--bundle', '<bundle>', '--device', 'macos', '--output', '<dir>'],
        'source_bundle': str(app),
        'relocated_bundle': str(relocated),
        'relocation_segment': spec.RELOCATED_SEGMENT,
        'relocated_bytes': sum(entry['bytes'] for entry in moved_files.values()),
        'relocated_files': len(moved_files),
        'relocated_archive': {'path': archive.name, 'bytes': archive.stat().st_size,
                              'sha256': spec.digest(archive)} if archive.is_file() else None,
        'offline': offline,
        'phases': {phase: {'exit': phases[phase]['exit'], 'log': phases[phase]['log'],
                           'report': phases[phase]['report'],
                           'previous_state': phases[phase]['previous_state']}
                   for phase in spec.SMOKE_PHASES},
        'check_count': (open_run['report'] or {}).get('check_count'),
        'checks': lists['offline-open'],
        'reopen_state': {'roots': [str(root) for root in state_roots],
                         'files_before_open': len(before),
                         'files_created_by_open': created[:40],
                         'files_written_by_reopen': reopened[:40]},
        'codesign': facts,
        'problems': problems,
        'accepted': not problems,
    }
    target = evidence / ('smoke-' + name + '.json')
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'candidate': name, 'accepted': report['accepted'],
                      'check_count': report['check_count'],
                      'relocated': str(relocated),
                      'offline_denied': offline['denied'],
                      'adhoc': facts['adhoc'], 'gatekeeper_exit': facts['gatekeeper_exit'],
                      'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
