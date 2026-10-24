# SPDX-License-Identifier: MIT
"""Strict cross-platform aggregate for the fault-boundary package.

This job downloads the three platform artifacts produced by the same workflow
run, re-reads every retained report and refuses the aggregate when a platform is
missing, when a report belongs to another source/run/attempt, when a named
boundary is missing or not reported as a pass, when the preserved 20-item
account-session suite is absent or has drifted, when a documented uncovered
limit was silently dropped, or when a private key survived into an artifact.

It records the digest of every retained report so the published evidence can be
matched to the exact bytes it was computed from.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boundaries import NEW_CHECKS, ORIGINAL_SESSION_CHECKS, UNCOVERED_LIMITS

EXPECTED_PLATFORMS = {'win32': 'Windows', 'linux': 'Linux', 'darwin': 'macOS'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('download', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source = os.environ['GITHUB_SHA']
    run = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    root = arguments.download.resolve()
    folder = arguments.output.resolve()
    folder.mkdir(parents=True)
    for path in root.rglob('*'):
        assert not path.is_file() or path.suffix != '.key', ('private key retained', path)

    platforms, artifacts = {}, []
    suffix = '-' + run + '-' + attempt
    for candidate in sorted(root.rglob('resilience-evidence/result.json')):
        artifact = candidate.parents[2].name
        # A re-run attempt re-downloads earlier attempts' artifacts from the same
        # run; only this attempt's producer is evidence for this attempt.
        if not artifact.endswith(suffix):
            continue
        report = json.loads(candidate.read_text(encoding='utf-8'))
        platform = report['platform']
        assert platform in EXPECTED_PLATFORMS, platform
        assert platform not in platforms, ('duplicate platform', platform)
        expected_name = 'reader-sync-resilience-' + EXPECTED_PLATFORMS[platform] + suffix
        assert artifact == expected_name, (artifact, expected_name)
        assert report['accepted'] is True, platform
        assert report['source_sha'] == source, (platform, report['source_sha'])
        assert str(report['run_id']) == run, (platform, report['run_id'])
        assert str(report['attempt']) == attempt, (platform, report['attempt'])
        assert report['three_platform_accepted'] is False, 'a platform report claimed the aggregate'
        assert report['count'] == len(NEW_CHECKS), (platform, report['count'])
        assert [check['id'] for check in report['checks']] == NEW_CHECKS, platform
        for check in report['checks']:
            assert check['pass'] is True, (platform, check['id'])
            assert isinstance(check['expected'], str) and check['expected'].strip(), check['id']
            assert isinstance(check['actual'], dict) and check['actual'], check['id']
        assert report['uncovered'] == UNCOVERED_LIMITS, (platform, report['uncovered'])
        assert report['fault_boundaries_accepted'] is True, platform
        assert report['original_session_suite_preserved'] is True, platform
        assert len(report['consumer_sha256']) == 64 and len(report['revision_consumer_sha256']) == 64
        session_candidates = sorted(candidate.parents[1].glob('session-evidence/result.json'))
        assert len(session_candidates) == 1, (platform, session_candidates)
        session = json.loads(session_candidates[0].read_text(encoding='utf-8'))
        assert session['accepted'] is True, platform
        assert session['source_sha'] == source, (platform, session['source_sha'])
        assert str(session['run_id']) == run and str(session['attempt']) == attempt, platform
        assert sorted(session['checks']) == sorted(ORIGINAL_SESSION_CHECKS), platform
        assert len(session['checks']) == 20, (platform, len(session['checks']))
        assert report['original_session_suite']['count'] == 20, platform
        platforms[platform] = {'artifact': artifact,
                               'boundaries': report['count'],
                               'original_session': len(session['checks']),
                               'checks': [check['id'] for check in report['checks']],
                               'consumer_sha256': report['consumer_sha256'],
                               'revision_consumer_sha256': report['revision_consumer_sha256'],
                               'report_sha256': digest(candidate),
                               'session_report_sha256': digest(session_candidates[0]),
                               'request_count': report['request_count'],
                               'duration_seconds': report['duration_seconds']}
        artifacts.append(artifact)

    assert set(platforms) == set(EXPECTED_PLATFORMS), sorted(platforms)
    assert len(set(artifacts)) == 3, artifacts
    for platform in EXPECTED_PLATFORMS:
        assert platforms[platform]['boundaries'] == len(NEW_CHECKS)
        assert platforms[platform]['original_session'] == 20

    report = {'schema': 'reader-sync-resilience-acceptance-v1', 'accepted': True,
              'source_sha': source, 'run_id': run, 'attempt': attempt,
              'frozen_sdk': '9854061be331fe603a1822d9b2b36ee357154927',
              'implementation_start': 'f43baf9182d75907c0cb5d6f77048f27bca8c950',
              'platforms': platforms,
              'boundaries_per_platform': len(NEW_CHECKS),
              'original_session_checks_per_platform': 20,
              'uncovered': list(UNCOVERED_LIMITS),
              'native_https': 'platform native HTTPS on IPv4 loopback with verified certificate IP SAN',
              'three_platform_accepted': True,
              'host_ui_accepted': False,
              'metadata_projection_accepted': False,
              'complete_product': False}
    (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'accepted': True, 'platforms': sorted(platforms),
                      'boundaries': len(NEW_CHECKS), 'source_sha': source}))


if __name__ == '__main__':
    main()
