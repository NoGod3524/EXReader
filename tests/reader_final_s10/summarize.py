#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict S10 summary: refuse a mixed, partial or unauthenticated result.

Only this attempt's authenticated artifacts are read.  Every report must name
the same source, run and attempt, every delivery must carry the same fixture
bytes, and each platform is reported with what was actually executed.
"""
import argparse
import json
import os
from pathlib import Path

EXPECTED_POSITIVE_CHECKS = 20
EXPECTED_MUTATIONS = 13
DECLARED_PLATFORMS = ['android', 'ios', 'ipados', 'linux-gtk', 'macos', 'windows']
EXECUTED = ['android-emulator', 'ios-simulator', 'ipados-simulator', 'linux-desktop']
DECLARED_ONLY = ['windows-desktop', 'macos-desktop']
PENDING = [
    {'id': 'physical-android-handset-and-usb-mtp',
     'detail': 'No Android handset and no USB cable exist in Actions: the MTP copy described for users '
               'was not executed. Only the emulator delivery through a real DocumentsProvider was.'},
    {'id': 'physical-apple-device-and-files-transfer',
     'detail': 'No iPhone/iPad hardware and no Finder/iTunes or iCloud Files transfer: the Documents '
               'container copy was performed by CI on the simulator, not by Files.app on a device.'},
    {'id': 'system-picker-ui',
     'detail': 'The Files document picker and the Android SAF picker UI were not driven. The Android grant '
               'and the Apple security-scoped call execute the same code path, but the picker surface '
               'itself is unproven.'},
    {'id': 'windows-desktop-execution',
     'detail': 'The Windows host open dialog and shell path entry are proven only by the static contract '
               'check in this run; the Windows executable was not built or executed.'},
    {'id': 'macos-desktop-execution',
     'detail': 'The macOS host document importer is proven only by the static contract check in this run; '
               'the macOS application was not launched.'},
]


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guards', type=Path, required=True)
    parser.add_argument('--android', type=Path, required=True)
    parser.add_argument('--apple', type=Path, required=True)
    parser.add_argument('--desktop', type=Path, required=True)
    parser.add_argument('--authenticated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    source = os.environ['GITHUB_SHA']
    run = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']

    guards = load(args.guards / 'entry-contract.json')
    ownership = load(args.guards / 'guards.json')
    fixtures = load(args.guards / 'fixtures-manifest.json')
    android = load(args.android / 'report.json')
    apple_runs = {'ios-simulator': load(args.apple / 'iphone/report.json'),
                  'ipados-simulator': load(args.apple / 'ipad/report.json')}
    desktop = load(args.desktop / 'report.json')
    authenticated = load(args.authenticated)

    checks = []

    def check(check_id, ok, detail=''):
        checks.append({'id': check_id, 'passed': bool(ok), 'detail': detail})

    check('producer.four-roles-authenticated',
          authenticated.get('authenticated') is True
          and sorted(authenticated.get('roles', [])) == ['android', 'apple', 'desktop', 'guards']
          and len(authenticated.get('artifacts', [])) == 4,
          json.dumps([row['name'] for row in authenticated.get('artifacts', [])]))
    check('producer.same-source-run-attempt',
          authenticated.get('source_sha') == source and authenticated.get('run_id') == run
          and authenticated.get('attempt') == attempt,
          'source=' + source + ' run=' + run + ' attempt=' + attempt)

    reports = {'android': android, 'desktop': desktop,
               'ios-simulator': apple_runs['ios-simulator'],
               'ipados-simulator': apple_runs['ipados-simulator']}
    for name, report in reports.items():
        check('report.' + name + '.identity',
              report.get('source_sha') == source and str(report.get('run_id')) == run
              and str(report.get('attempt')) == attempt,
              json.dumps({key: report.get(key) for key in ('source_sha', 'run_id', 'attempt')}))
        check('report.' + name + '.accepted',
              report.get('accepted') is True and not report.get('problems'),
              json.dumps(report.get('problems')))
        check('report.' + name + '.checks-passed',
              bool(report.get('checks')) and all(row.get('passed') for row in report.get('checks', [])),
              json.dumps([row.get('id') for row in report.get('checks', []) if not row.get('passed')]))

    check('guards.ownership-accepted', ownership.get('accepted') is True and not ownership.get('problems'),
          json.dumps(ownership.get('problems')))
    check('guards.entry-contract-accepted',
          guards.get('accepted') is True and not guards.get('problems'), json.dumps(guards.get('problems')))
    check('guards.positive-checks-complete',
          guards.get('positive_checks') == EXPECTED_POSITIVE_CHECKS, str(guards.get('positive_checks')))
    check('guards.negative-mutations-complete',
          len(guards.get('negative_mutations', [])) == EXPECTED_MUTATIONS,
          str(len(guards.get('negative_mutations', []))))
    check('guards.declared-six-platforms',
          sorted(guards.get('declared_platforms', [])) == DECLARED_PLATFORMS,
          json.dumps(guards.get('declared_platforms')))

    fixture_shas = {name: report.get('fixture', {}).get('sha256') for name, report in reports.items()}
    check('fixtures.one-delivered-identity',
          len(set(fixture_shas.values())) == 1 and None not in fixture_shas.values(),
          json.dumps(fixture_shas))
    epub = fixtures.get('S10-Transfer.epub', {})
    check('fixtures.match-guards-manifest', epub.get('sha256') in set(fixture_shas.values()),
          json.dumps(epub))

    platform_evidence = {
        'android': {
            'executed': 'android-emulator',
            'platform': android.get('platform'),
            'emulator': android.get('emulator'),
            'entry': android.get('entry'),
            'delivery': android.get('delivery'),
            'stored_source': android.get('stored_source'),
            'checks': [row.get('id') for row in android.get('checks', [])],
        },
        'ios': {
            'executed': 'ios-simulator',
            'simulator': apple_runs['ios-simulator'].get('simulator'),
            'entry': apple_runs['ios-simulator'].get('entry'),
            'delivery': apple_runs['ios-simulator'].get('delivery'),
            'stored_source': apple_runs['ios-simulator'].get('driver_report', {}).get('stored_source'),
            'checks': [row.get('id') for row in apple_runs['ios-simulator'].get('checks', [])],
        },
        'ipados': {
            'executed': 'ipados-simulator',
            'simulator': apple_runs['ipados-simulator'].get('simulator'),
            'entry': apple_runs['ipados-simulator'].get('entry'),
            'delivery': apple_runs['ipados-simulator'].get('delivery'),
            'stored_source': apple_runs['ipados-simulator'].get('driver_report', {}).get('stored_source'),
            'checks': [row.get('id') for row in apple_runs['ipados-simulator'].get('checks', [])],
        },
        'linux-gtk': {
            'executed': 'linux-desktop',
            'entry': desktop.get('entry'),
            'delivery': desktop.get('delivery'),
            'checks': [row.get('id') for row in desktop.get('checks', [])],
        },
        'windows': {'executed': None, 'declared_only': True,
                    'checks': [row.get('id') for row in guards.get('checks', [])
                               if row.get('platform') == 'windows']},
        'macos': {'executed': None, 'declared_only': True,
                  'checks': [row.get('id') for row in guards.get('checks', [])
                             if row.get('platform') == 'macos']},
    }

    problems = [row['id'] + ': ' + row['detail'] for row in checks if not row['passed']]
    validation = {
        'schema': 1,
        'package': 'S10',
        'title': 'computer transfer entries and capability evidence',
        'accepted': not problems,
        'source_sha': source,
        'run_id': run,
        'attempt': attempt,
        'authenticated_artifacts': authenticated.get('artifacts', []),
        'entry_contract': {
            'positive_checks': guards.get('positive_checks'),
            'negative_mutations': guards.get('negative_mutations'),
            'declared_platforms': guards.get('declared_platforms'),
            'static_checks': guards.get('checks'),
        },
        'ownership_guards': ownership,
        'fixtures': fixtures,
        'platform_evidence': platform_evidence,
        'executed': EXECUTED,
        'declared_only': DECLARED_ONLY,
        'pending': PENDING,
        'physical_device_execution': False,
        'usb_cable_execution': False,
        'checks': checks,
        'problems': problems,
        'note': ('Static entry declarations are proven for six platforms. Real byte delivery and read-back '
                 'were executed on an Android emulator, an iPhone simulator, an iPad simulator and the '
                 'Linux desktop entry. No physical device, USB cable, MTP copy, Files app or picker UI ran, '
                 'so those stay pending and are not claimed.'),
    }
    (output / 'validation.json').write_text(json.dumps(validation, indent=2, sort_keys=True) + '\n')
    summary = {
        'schema': 1,
        'package': 'S10',
        'source_sha': source,
        'run_id': run,
        'attempt': attempt,
        'checks': checks,
        'problems': problems,
        'accepted': not problems,
        'executed_platforms': EXECUTED,
        'pending': [row['id'] for row in PENDING],
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checks': len(checks), 'problems': problems}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
