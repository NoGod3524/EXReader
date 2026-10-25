# SPDX-License-Identifier: MIT
"""Actions only. Strict same-run evidence for S19.

Every number here is recomputed from the artifacts this run produced: the tested
source, each platform report, the two program identities, the identical named
check set across platforms, and the ZIP size/digest/expiry that GitHub reports
for the very artifacts uploaded by this attempt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

EXPECTED_CHECKS = [
    'installed-sdk-is-the-reviewed-candidate',
    'installed-five-reviewed-packages',
    'host-dso-and-executable-built-from-installed-packages',
    'six-mixed-graphs-refused',
    'font-library-real-import-lease-and-removal',
    'original-export-real-original-bytes',
    'annotation-export-then-import-round-trip',
    'jump-history-real-landing-and-back',
    'sync-status-real-session-capture',
    'one-loaded-sdk-implementation',
    'host-executable-holds-no-sdk-module-or-store-copy',
    'product-dso-holds-no-sdk-object-copy',
    'one-sdk-shared-lib-per-image',
]
NEGATIVES = ['negative-dso-static-sdk', 'negative-two-feature-dso', 'negative-host-links-module',
             'negative-module-outside-prefix', 'negative-standalone-alongside-dso',
             'negative-private-store']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-source', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--attempt', required=True)
    options = parser.parse_args()

    api = json.loads(options.artifacts.read_text(encoding='utf-8'))
    recorded = {entry['name']: entry for entry in api['artifacts']}
    platforms = {}
    problems = []
    for folder in sorted(item for item in options.root.iterdir() if item.is_dir()):
        result_path = folder / 'result.json'
        if not result_path.exists():
            problems.append('missing result.json in ' + folder.name)
            continue
        result = json.loads(result_path.read_text(encoding='utf-8'))
        key = result.get('runner_os') or folder.name
        identity = (result['source_sha'], str(result['run_id']), str(result['attempt']))
        if identity != (options.expect_source, options.run, options.attempt):
            problems.append(key + ': source/run/attempt mismatch ' + repr(identity))
        if not result['accepted']:
            problems.append(key + ': not accepted')
        names = [item['name'] for item in result['checks']]
        if names != EXPECTED_CHECKS:
            problems.append(key + ': check set differs ' + repr(names))
        if result['count'] != len(result['checks']):
            problems.append(key + ': count mismatch')
        if result['negatives'] != NEGATIVES:
            problems.append(key + ': negative set differs ' + repr(result['negatives']))
        if not result['single_sdk_module'] or not result['exr_pointer_identity']:
            problems.append(key + ': single SDK identity not proven')
        sdk_modules = [name for name in result['modules_loaded']
                       if name.lower().startswith(('libexreader.so', 'libexreader.dylib', 'exreader.dll'))]
        if len(sdk_modules) != 1:
            problems.append(key + ': loaded SDK module count ' + repr(result['modules_loaded']))
        for name, recorded_program in result['programs'].items():
            candidates = [folder / name, folder / (name + '.exe'), folder / (name + '.dll'),
                          folder / (name + '.dylib'), folder / ('lib' + name + '.so'),
                          folder / ('lib' + name + '.dylib'), folder / ('lib' + name + '.a')]
            found = next((item for item in candidates if item.exists()), None)
            if found is None:
                problems.append(key + ': artifact missing for ' + name)
                continue
            if found.stat().st_size != recorded_program['bytes']:
                problems.append(key + ': size changed for ' + name)
            if sha256(found) != recorded_program['sha256']:
                problems.append(key + ': digest changed for ' + name)
        report = result['report']
        if report['font']['glyph_A'] != 1 or report['original']['bytes_match'] != 1:
            problems.append(key + ': business path did not produce real bytes')
        if report['annotations']['created'] != 2 or report['history']['resolve'] != 1:
            problems.append(key + ': module business path incomplete')
        if report['sync']['mirrored'] != 1 or report['sync']['outbox_included'] != 1:
            problems.append(key + ': sync view did not mirror the real session')
        platforms[key] = {
            'result_sha256': sha256(result_path),
            'count': result['count'],
            'checks': names,
            'programs': result['programs'],
            'negatives': result['negatives'],
            'report': report,
            'dav_requests': result['dav_requests'],
            'platform': result['platform'],
        }

    check_sets = {json.dumps(item['checks']) for item in platforms.values()}
    if len(check_sets) != 1:
        problems.append('check sets differ across platforms')
    if len(platforms) != 3:
        problems.append('expected three platform reports, got ' + str(len(platforms)))

    artifacts = {}
    for name, entry in recorded.items():
        artifacts[name] = {'id': entry['id'], 'size_in_bytes': entry['size_in_bytes'],
                           'digest': entry['digest'], 'expires_at': entry['expires_at'],
                           'expired': entry.get('expired')}
        if entry.get('expired'):
            problems.append('artifact expired: ' + name)
    if len(artifacts) < 4:
        problems.append('expected the three platform artifacts and the evidence artifact')

    payload = {
        'accepted': not problems,
        'problems': problems,
        'source_sha': options.expect_source,
        'run_id': options.run,
        'attempt': options.attempt,
        'platforms': platforms,
        'cross_platform_identical_checks': len(check_sets) == 1,
        'artifacts': artifacts,
        'host_ui': False,
        'actual_hosts': False,
        'complete_product': False,
    }
    options.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in payload.items() if key != 'platforms'}, indent=2))
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    main()
