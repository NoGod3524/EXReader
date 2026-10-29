#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned failed continuation evidence; fixed-output diagnosis, never acceptance."""
import json
import os
import re
import subprocess
from contract import ROOT, STAGES, guard, require, sha
from archive_contract import safe_extract
from inspect_native import CONTROLS, MESSAGES, ROLES, variant_labels

RUN = '40794326091'
SOURCE = '0533fadf8d5cc41959a7ae81ef1dbd294c7d096e'
SOURCE_FILE = 'tests/apple_password_privacy_20261028/continuation_ui/PasswordPrivacyContinuationUITests.swift'
SOURCE_SHA = '01f9eeeafa9a5f1102d933cea31d51f55179af8053a4949f84b4f13c40a56b8f'
SOURCE_PATH = '/Users/runner/work/EXReader/EXReader/' + SOURCE_FILE
# All three producers and their attempt-1 uploads are terminal and immutable.
ARTIFACTS = {
    'macos': (12863262861, 116474070, 'b78ac6348cfff1869d939a0ac81e15b25d262766a79f27c58482761a4d48cef3'),
    'iphone': (12863842315, 81573493, 'f8964f59140ca2b5be1d014b8185de115cee04db682a268c22eb7df45226e89c'),
    'ipad': (12863184834, 87090148, 'dec7612196ddced56ceea8e9dfab8b1e0292ec2262d6ff1f588de9a389d46d44'),
}
FAILURES = ('RuntimeError', 'AssertionError', 'CalledProcessError', 'TimeoutExpired',
            'FileNotFoundError', 'OperationalError', 'PermissionError', 'KeyError', 'OSError')
STATIC_MESSAGES = MESSAGES + ('Complete evidence and strict verdict must be recorded before diagnostic continuation',
                             'Asynchronous wait failed', 'Exceeded timeout')
SIGNATURES = {'url-request-timeout': 'NSURLErrorDomain Code=-1001',
              'xctest-asynchronous-timeout': 'Asynchronous wait failed',
              'xctest-test-timeout': 'Test exceeded execution time allowance'}


def locations(path):
    """Source positions and fixed signatures, not arbitrary operands/callsite proof."""
    found = []
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            match = re.match(re.escape(SOURCE_PATH) + r':([1-9][0-9]{0,2}): error:', line)
            if not match or int(match.group(1)) not in range(1, 161): continue
            assertion = re.search(r'\b(XCTAssert(?:True|False|Equal|Nil|NotNil)|XCTUnwrap)\b', line)
            record = {'file': 'PasswordPrivacyContinuationUITests.swift', 'line': int(match.group(1)),
                      'assertion': assertion.group(1) if assertion else None,
                      'static_messages': [value for value in STATIC_MESSAGES if value in line],
                      'static_controls': [value for value in CONTROLS if value in line],
                      'fixed_signatures': [key for key, value in SIGNATURES.items() if value in line]}
            if record not in found: found.append(record)
    return found


def safe_progress(result, files):
    require(result['accepted'] is False and result['diagnostic_only'] is True and
            result['full_f10_accepted'] is False and result['sequence_complete'] is False,
            'prior continuation verdict differs')
    checks = result['strict_privacy_checks']
    require(type(checks) is dict and set(checks) <= set(STAGES) and
            all(type(value) is bool for value in checks.values()), 'unexpected strict checks')
    require(type(result['checkpoints']) is dict and set(result['checkpoints']) <= set(STAGES), 'unexpected checkpoint')
    commands = result['commands']
    require(type(commands) is list and all(type(row) is dict and set(row) == {'role', 'exit'} and
            row['role'] in ROLES and type(row['exit']) is int and -128 <= row['exit'] <= 255 for row in commands),
            'unexpected command shape')
    require(result['failure'] in FAILURES, 'unexpected failure class')
    return {'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False,
            'sequence_complete': False, 'strict_privacy_checks': {stage: checks[stage] for stage in STAGES if stage in checks},
            'completed_checkpoints': [stage for stage in STAGES if stage in result['checkpoints']],
            'snapshot_archives_present': {stage: stage + '-product.zip' in files for stage in STAGES},
            'commands': commands, 'failure_class': result['failure']}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    guard()
    require(sha(ROOT / SOURCE_FILE) == SOURCE_SHA, 'frozen diagnostic source positions changed')
    require(set(ARTIFACTS) == {'macos', 'iphone', 'ipad'}, 'all original artifact pins required')
    out = ROOT / 'build/apple-password-continuation-diagnostic'; out.mkdir(parents=True, exist_ok=False)
    reports = []
    for platform, (identifier, size, digest) in ARTIFACTS.items():
        endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(identifier)
        record = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
        require(record['id'] == identifier and record['name'] == 'password-continuation-native-' + platform + '-' + RUN + '-1' and
                str(record['workflow_run']['id']) == RUN and record['workflow_run']['head_sha'] == SOURCE and
                record['digest'] == 'sha256:' + digest and record['size_in_bytes'] == size and
                record['expired'] is False, 'prior continuation artifact identity differs')
        original = out / (platform + '-original.zip')
        with original.open('wb') as file: subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=file, check=True)
        require(original.stat().st_size == size and sha(original) == digest, 'prior original ZIP differs')
        folder = out / platform; safe_extract(original, folder)
        result = json.loads((folder / 'result.json').read_text())
        require((result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
                (SOURCE, RUN, '1', platform), 'prior continuation identity differs')
        files = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
        require(files == set(result['files']) | {'result.json'}, 'prior continuation inventory differs')
        for name, item in result['files'].items():
            path = folder / name
            require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'prior continuation member differs')
        report = safe_progress(result, files)
        report.update(old_source_sha=SOURCE, old_run_id=RUN, old_attempt=1, platform=platform,
                      artifact_id=identifier, original_bytes=size, original_sha256=digest,
                      verified_member_count=len(files), arbitrary_log_text_printed=False,
                      source_positions_not_authenticated_callsites=True,
                      native_failure_locations=locations(folder / 'native.log') if 'native.log' in files else [])
        for stage in STAGES:
            name = stage + '-privacy-scan.json'
            if name not in files: continue
            scans = json.loads((folder / name).read_text())
            require(set(scans) <= {'profile', 'product-log', 'preferences', 'cache', 'saved-state', 'container'}, 'unexpected scan root')
            require(all(type(proof['accepted']) is bool for proof in scans.values()), 'unexpected scan verdict')
            report.setdefault('scan_summary', {})[stage] = {label: {'accepted': proof['accepted'],
                'hit_variant_labels': variant_labels(proof)} for label, proof in scans.items()}
        if 'fixture-failures.json' in files:
            failures = json.loads((folder / 'fixture-failures.json').read_text())
            require(type(failures) is list and all(item in FAILURES for item in failures), 'unexpected fixture failure type')
            report['fixture_failure_classes'] = failures
        reports.append(report)
        print(json.dumps(report, sort_keys=True), flush=True)
    (out / 'diagnostic.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # An OS/parser exception may embed a synthetic value in its operands.
        # Refuse without relaying that exception text or chained traceback.
        raise RuntimeError('pinned continuation diagnosis refused; arbitrary error details withheld') from None
