#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Accept only complete, same-run Apple evidence whose actual files revalidate."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import zipfile

from evidence_contract import (PLATFORMS, SDK_TARGET, cloud_identity, digest, load, require,
    validate_identity, validate_package, validate_platform, validate_review_reports, validate_sdk)


def assemble(args):
    expected = cloud_identity('summary')
    validate_identity(expected, args.source_sha, args.run_id, args.attempt, 'summary', 'summary')
    upstream = json.loads(args.upstream_results)
    require(set(upstream) == {'sdk', 'uitest', 'package'} and
            all(upstream[key].get('result') == 'success' for key in upstream),
            'upstream SDK, UI or package job did not succeed')
    sdks = {}
    for target in ('macos', 'iphonesimulator', 'iphoneos'):
        artifact = args.artifacts/('wp13-apple-sdk-' + target)
        sdk = load(artifact/'build/sdk-identity.json')
        validate_sdk(artifact/'stage'/target, sdk, args.source_sha, args.run_id, args.attempt, target)
        sdks[target] = sdk
    platforms = {}
    fixtures = None
    for platform in PLATFORMS:
        artifact = args.artifacts/('wp13-apple-' + platform)
        evidence = validate_platform(artifact/'evidence'/platform, platform,
            args.source_sha, args.run_id, args.attempt, sdks[SDK_TARGET[platform]], artifact/'results')
        manifest = load(artifact/'apple-resources/manifest.json')
        require(manifest == evidence['environment']['fixtures'], 'published fixture manifest mismatch')
        require(fixtures is None or manifest == fixtures, 'fixture identities differ across platforms')
        fixtures = manifest
        platforms[platform] = evidence
    package = args.package or args.artifacts/'wp13-apple-package'
    legacy, device = validate_package(package, args.source_sha, args.run_id, args.attempt, sdks)
    reviews = validate_review_reports(package, args.source_sha, args.run_id, args.attempt, sdks['macos'], fixtures)
    return {'schema': 2, 'package': 'WP13 Apple host', 'accepted': True,
        'source_sha': args.source_sha, 'date': args.date,
        'run': {'id': args.run_id, 'attempt': args.attempt, 'url': expected['run_url']},
        'platforms': {key: {'totals': value['totals'], 'attachment_count': value['attachments']['count'],
            'evidence_sha256': digest(args.artifacts/('wp13-apple-' + key)/'evidence'/key/'evidence.json')}
            for key, value in platforms.items()},
        'legacy_self_checks': legacy, 'device_package': device, 'review_suites': reviews,
        'physical_device_execution': False,
        'limitations': ['Device installation awaits owner signing.',
            'The system document picker is not driven by XCUITest.',
            'Library opens retain the 32 MiB host input limit.']}, platforms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--run-url')
    parser.add_argument('--date', default=datetime.datetime.now(datetime.timezone.utc).date().isoformat())
    parser.add_argument('--upstream-results', default=os.environ.get('WP13_APPLE_UPSTREAM_RESULTS', '{}'))
    parser.add_argument('--require-gate-review', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        summary, platforms = assemble(args)
        if args.require_gate_review:
            from review_evidence_gate import validate_review_result
            validate_review_result(args.require_gate_review)
            summary['gate_review_sha256'] = digest(args.require_gate_review)
        for key, value in platforms.items():
            value['legacy_self_checks'] = summary['legacy_self_checks'][key]
            (args.output/('wp13-apple-' + key + '.json')).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    except Exception as error:
        summary = {'schema': 2, 'accepted': False, 'source_sha': args.source_sha,
            'run': {'id': args.run_id, 'attempt': args.attempt},
            'problems': [type(error).__name__ + ': ' + str(error)[:500]]}
    (args.output/'wp13-apple-summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': summary['accepted'], 'platforms': summary.get('platforms'),
                      'problems': summary.get('problems', [])}))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
