#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble WP13 Apple acceptance JSON from downloaded cloud artifacts."""
import argparse
import hashlib
import json
from pathlib import Path

PLATFORMS = {'macos': 'macOS', 'iphone': 'iPhone simulator', 'ipad': 'iPad simulator'}


def digest(path):
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-url', required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    legacy = {}
    device_package = {}
    if args.package and args.package.exists():
        for name, device in [('evidence-macos', 'macos'), ('evidence-iphone', 'iphone'),
                             ('evidence-ipad', 'ipad')]:
            report = args.package/name/'report.json'
            if report.exists():
                payload = load(report)
                legacy[device] = {'checks': payload.get('check_count', 0),
                                  'passed': payload.get('passed') is True,
                                  'sha256': digest(report),
                                  'path': str(report.relative_to(args.package))}
        build = args.package/'device'/'build.json'
        ipa = args.package/'device'/'EXReader-iOS-unsigned.ipa'
        if build.exists():
            device_package = {'build': str(build.relative_to(args.package)),
                              'sha256': digest(build),
                              'installation_status': 'owner_signing_required'}
        if ipa.exists():
            device_package['ipa_sha256'] = digest(ipa)
    platforms = {}
    for key, label in PLATFORMS.items():
        evidence_path = args.artifacts/key/'evidence'/key/'evidence.json'
        if not evidence_path.exists():
            continue
        evidence = load(evidence_path)
        environment = evidence.get('environment', {})
        attachments = evidence.get('attachments', {})
        screenshots = [name for name in attachments.get('files', []) if name.endswith('.png')]
        entry = {
            'schema': 1,
            'package': 'WP13-APPLE',
            'platform': key,
            'platform_label': label,
            'date': args.date,
            'source_sha': args.source_sha,
            'run': {'id': args.run_id, 'url': args.run_url, 'job': environment.get('platform', '')},
            'environment': {
                'xcode': environment.get('xcode', ''),
                'host': environment.get('host', ''),
                'device': environment.get('device', ''),
                'runtime': environment.get('runtime', ''),
                'destination': environment.get('destination', ''),
                'sdk': environment.get('sdk', {}),
                'app': environment.get('app', {}),
                'font_sha256': environment.get('font_sha256', ''),
                'input_driver': environment.get('input_driver', ''),
                'fixtures': environment.get('fixtures', {}),
            },
            'tests': evidence.get('tests', []),
            'totals': evidence.get('totals', {}),
            'state': evidence.get('state', {}),
            'artifacts': {
                'attachment_files': attachments.get('file_count', 0),
                'screenshots': screenshots[:40],
                'element_tree_present': any('tree' in str(name) for name in attachments.get('files', [])),
                'xcresult': 'build/results/%s.xcresult' % key,
                'xcodebuild_log': 'build/results/%s-xcodebuild.log' % key,
            },
            'physical_device_execution': False,
            'scope': 'real controls, touches and keyboard events on macOS and both simulators',
        }
        if key in legacy:
            entry['legacy_self_checks'] = legacy[key]
        platforms[key] = entry
        (args.output/('wp13-apple-%s.json' % key)).write_text(
            json.dumps(entry, indent=2, sort_keys=True) + '\n')
    summary = {
        'schema': 1,
        'package': 'WP13 Apple host',
        'branch': 'codex/wp13-apple',
        'source_sha': args.source_sha,
        'date': args.date,
        'run': {'id': args.run_id, 'url': args.run_url},
        'platforms': {key: {'cases': entry['totals'].get('cases', 0),
                            'passed': entry['totals'].get('passed', 0),
                            'failed': entry['totals'].get('failed', 0),
                            'steps': entry['totals'].get('steps', 0),
                            'legacy_checks': entry.get('legacy_self_checks', {}).get('checks')}
                      for key, entry in platforms.items()},
        'legacy_self_checks': legacy,
        'device_package': device_package,
        'physical_device_execution': False,
        'limitations': [
            'Physical device installation is deferred by user request; the unsigned package stays uninstalled.',
            'The system document picker is not driven by XCUITest; fixture import exercises the same host import path.',
            'Whole-document library opens are bounded by the 32 MiB host input limit.',
        ],
    }
    (args.output/'wp13-apple-summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps(summary['platforms'], indent=2))


if __name__ == '__main__':
    main()
