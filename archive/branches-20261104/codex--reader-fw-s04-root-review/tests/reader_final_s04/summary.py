"""Cross-job authentication of the S04 result.

The static and emulator jobs authenticate the producer artifact independently.
Only identical source, artifact digest and APK bytes may be joined; a partially
successful run is reported as accepted=false.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common


def load(path):
    path = pathlib.Path(path)
    return common.read_json(path) if path.is_file() else None


def application_persisted(emulator):
    observed = emulator.get('observed', {})
    checks = [row for row in emulator.get('checks', [])
              if row.get('name') == 'app_persisted_reader_selection']
    return (observed.get('restore_input') == 'app'
            and observed.get('open_path') == 'ui_tap'
            and observed.get('preferences_injected') is False
            and len(checks) == 1 and checks[0].get('pass') is True
            and checks[0].get('mandatory') is True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--static', type=pathlib.Path, default=pathlib.Path('build/in/s04-static'))
    parser.add_argument('--emulator', type=pathlib.Path, default=pathlib.Path('build/in/s04-emulator'))
    parser.add_argument('--static-auth', type=pathlib.Path, default=pathlib.Path('build/in/s04-authenticate'))
    parser.add_argument('--emulator-auth', type=pathlib.Path,
                        default=pathlib.Path('build/in/s04-authenticate-emulator'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/s04-summary'))
    args = parser.parse_args()
    common.require_actions()
    args.output.mkdir(parents=True, exist_ok=True)

    static = load(args.static / 'static-report.json')
    emulator = load(args.emulator / 'emulator-report.json')
    static_auth = load(args.static_auth / 'attestation.json')
    emulator_auth = load(args.emulator_auth / 'attestation.json')
    problems = []
    if static is None:
        problems.append('static report is missing')
    if emulator is None:
        problems.append('emulator report is missing')
    elif not application_persisted(emulator):
        problems.append('app-persisted selection is missing, injected or not mandatory')
    if static_auth is None:
        problems.append('static artifact authentication is missing')
    if emulator_auth is None:
        problems.append('emulator artifact authentication is missing')

    joined = {}
    if not problems:
        candidate = static['observed_pins']['candidate_sha256']
        static_roles = {row['role']: {'id': row['id'], 'digest': row['sealed_digest']}
                        for row in static_auth['artifacts']}
        emulator_roles = {row['role']: {'id': row['id'], 'digest': row['sealed_digest']}
                          for row in emulator_auth['artifacts']}
        same = {
            'producer_source': static['producer_source'] == emulator['producer_source'] ==
                               static_auth['producer']['source_sha'] ==
                               emulator_auth['producer']['source_sha'],
            'artifact_identity': bool(emulator_roles) and all(
                static_roles.get(role) == value for role, value in emulator_roles.items()),
            'apk_bytes': (static['observed_pins']['candidate_bytes'], candidate) ==
                         (emulator['apk']['bytes'], emulator['apk']['sha256']),
            'emulator_apk_is_the_static_candidate':
                any(row['relative'].endswith('apks/host-debug.apk') and row['sha256'] == candidate
                    for row in emulator_auth['apks']),
        }
        joined = same
        for name, value in same.items():
            if not value:
                problems.append('cross-job identity mismatch: ' + name)

    static_checks = static['checks'] if static else []
    emulator_checks = emulator['checks'] if emulator else []
    failed = [row['name'] for row in static_checks + emulator_checks
              if not row['pass'] and row.get('mandatory', True)]
    accepted = (not problems and not failed and bool(static and static['accepted'])
                and bool(emulator and emulator['accepted']))
    result = {
        'package': 'S04',
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'producer': static_auth['producer'] if static_auth else None,
        'artifacts': static_auth['artifacts'] if static_auth else None,
        'apk': ({'sha256': static['observed_pins']['candidate_sha256'],
                 'bytes': static['observed_pins']['candidate_bytes'],
                 'jni_sha256': static['observed_pins']['sdk_jni_sha256'],
                 'baseline_sha256': static['observed_pins']['baseline_sha256'],
                 'test_apk_sha256': static['observed_pins']['test_apk_sha256'],
                 'release_apk_sha256': static['observed_pins']['release_apk_sha256']}
                if static else None),
        'fixture': emulator['fixture'] if emulator else None,
        'checks': {'static': static_checks, 'emulator': emulator_checks},
        'checks_total': len(static_checks) + len(emulator_checks),
        'checks_passed': sum(1 for row in static_checks + emulator_checks if row['pass']),
        'failed_checks': failed,
        'problems': problems,
        'joined_identity': joined,
        'emulator_observed': emulator['observed'] if emulator else None,
        'accepted': accepted,
        'scope': {'debug_candidate_only': True, 'store_channel': False,
                  'physical_device': False, 'signing_authority': False,
                  'emulator_only': True, 'native_error_analysis': False,
                  'independent_public_sdk_readback': False},
        'pending': ['independent public SDK original/progress value readback; SQL and private-copy hashes are diagnostic only'],
    }
    common.write_json(args.output / 'result.json', result)

    producer_sha = result['producer']['source_sha'] if result['producer'] else 'missing'
    apk_sha = result['apk']['sha256'] if result['apk'] else 'missing'
    lines = ['# S04 Android delivered-APK verification', '',
             '- source: @@%s@@' % result['source_sha'],
             '- run/attempt: %s/%s' % (result['run_id'], result['attempt']),
             '- producer source: @@%s@@' % producer_sha,
             '- APK sha256: @@%s@@' % apk_sha,
             '- checks: %d/%d, accepted=%s' % (result['checks_passed'], result['checks_total'],
                                               result['accepted']),
             '- problems: %s' % (problems or 'none'),
             '- failed checks: %s' % (failed or 'none')]
    if result['artifacts']:
        for row in result['artifacts']:
            lines.append('- artifact %s @@%s@@ bytes=%d digest=%s expires=%s' % (
                row['id'], row['name'], row['sealed_bytes'], row['sealed_digest'], row['expires_at']))
    if emulator:
        lines.append('- offline reopen: %s' % json.dumps(emulator['observed'].get('offline_reopen_page')))
        lines.append('- pages: %s' % json.dumps(emulator['observed'].get('pages')))
    report = ('\n'.join(lines) + '\n').replace('@@', chr(96))
    (args.output / 'summary.md').write_text(report, encoding='utf-8')
    step_summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if step_summary:
        with open(step_summary, 'a', encoding='utf-8') as handle:
            handle.write(report)
    print(report)
    if not accepted:
        raise SystemExit('S04 result is not accepted')


if __name__ == '__main__':
    main()
