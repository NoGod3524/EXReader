#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned prior native failure diagnosis in Actions; no native acceptance."""
import json
import os
import re
import subprocess
from contract import ROOT, STAGES, guard, require, sha
from archive_contract import safe_extract

RUN = '40777254345'
SOURCE = 'b45971a955446310d2e4fc85a94690aa5a6703dd'
SWIFT_SOURCE_SHA = '553ac20541f148098c2e668493359d021a276382e1ed23cf3146191fcb368d56'
SOURCE_PATH = '/Users/runner/work/EXReader/EXReader/tests/apple_password_privacy_20261028/ui/PasswordPrivacyUITests.swift'
ARTIFACTS = {
    'macos': (12855747895, 100829920, 'a84bb8d3402dc10baecdfbec04fc5caa72def4c6e2bdaa3cd52cf811f8c86e7a'),
    'ipad': (12856975050, 82520816, '2ec11a42daf457492183c5a6d9156f3054be0cdc1df7065c5a1e7e2365d9c80c'),
    'iphone': (12854559992, 69066452, '39d7a274ccf2c7016f6f33548f0b986f0b6ca411ee29ee8183334d6517968423'),
}
ROLES = {'fixtures', 'project', 'devices', 'erase', 'boot', 'boot-ready', 'build-for-testing',
         'trust-simulator', 'native', 'attachments', 'program-archive'}
MESSAGES = ('Native toggle value must be observable', 'Actual Remember control did not change',
            'Username field was prefilled', 'Secure field did not present an empty display',
            'Username field value unavailable', 'Secure field value unavailable',
            'Session-only restart must require credentials', 'Loopback observation failed',
            'Unavailable control:', 'Actual update field absent:')
CONTROLS = ('account.form', 'account.root', 'account.username', 'account.password', 'account.remember',
            'account.connect', 'account.choose', 'account.done', 'account.sync.start', 'account.sync.state',
            'library.import.epub', 'library.book.0', 'library.busy')


def log_locations(path):
    """Never print arbitrary log text, assertion operands, typed input or errors.

    Only a fixed source basename, decimal source line, XCTest assertion symbol
    and fixed source-authored message tokens can cross the diagnostic boundary.
    This avoids secrets even if XCTest truncates/escapes/encodes an operand.
    """
    found = []
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            location = re.match(re.escape(SOURCE_PATH) + r':([1-9][0-9]{0,2}): error:', line)
            if location and int(location.group(1)) not in range(1, 157): location = None
            if location:
                assertion = re.search(r'\b(XCTAssert(?:True|False|Equal|Nil|NotNil)|XCTUnwrap)\b', line)
                record = {'file': 'PasswordPrivacyUITests.swift', 'line': int(location.group(1)),
                          'assertion': assertion.group(1) if assertion else None,
                          'static_messages': [message for message in MESSAGES if message in line],
                          'static_controls': [control for control in CONTROLS if control in line]}
                if record not in found: found.append(record)
    return found


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    guard()
    require(sha(ROOT / 'tests/apple_password_privacy_20261028/ui/PasswordPrivacyUITests.swift') ==
            SWIFT_SOURCE_SHA, 'frozen diagnostic source-line map changed')
    out = ROOT / 'build/apple-password-privacy-native-diagnostic'; out.mkdir(parents=True, exist_ok=False)
    reports = []
    for platform, (identifier, size, digest) in ARTIFACTS.items():
        endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(identifier)
        record = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
        require(record['id'] == identifier and record['name'] == 'password-native-' + platform + '-' + RUN + '-1' and
                str(record['workflow_run']['id']) == RUN and record['workflow_run']['head_sha'] == SOURCE and
                record['digest'] == 'sha256:' + digest and record['size_in_bytes'] == size and
                record['expired'] is False, 'prior native artifact identity differs')
        original = out / (platform + '-original-upload.zip')
        with original.open('wb') as file: subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=file, check=True)
        require(original.stat().st_size == size and sha(original) == digest, 'prior original ZIP differs')
        folder = out / platform; safe_extract(original, folder)
        result = json.loads((folder / 'result.json').read_text())
        require((result['source_sha'], result['run_id'], result['attempt'], result['platform'], result['accepted']) ==
                (SOURCE, RUN, '1', platform, False), 'prior failed native result differs')
        files = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
        require(files == set(result['files']) | {'result.json'}, 'prior native inventory differs')
        for name, item in result['files'].items():
            path = folder / name
            require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'prior native member differs')
        commands = result['commands']
        require(all(set(row) == {'role', 'exit'} and row['role'] in ROLES and type(row['exit']) is int for row in commands), 'unexpected command shape')
        require(set(result['checkpoints']) <= set(STAGES), 'unexpected checkpoint')
        require(result['failure'] in ('RuntimeError', 'AssertionError', 'CalledProcessError', 'TimeoutExpired'), 'unexpected failure class')
        report = {'diagnostic_only': True, 'native_accepted': False, 'full_f10_accepted': False,
                  'old_source_sha': SOURCE, 'old_run_id': RUN, 'old_attempt': 1, 'platform': platform,
                  'artifact_id': identifier, 'original_bytes': size, 'original_sha256': digest,
                  'verified_member_count': len(files), 'commands': commands, 'failure_class': result['failure'],
                  'completed_checkpoints': [stage for stage in STAGES if stage in result['checkpoints']],
                  'native_failure_locations': log_locations(folder / 'native.log') if 'native.log' in files else [],
                  'arbitrary_log_text_printed': False}
        for stage in STAGES:
            name = stage + '-privacy-scan.json'
            if name in files:
                scans = json.loads((folder / name).read_text())
                require(all(label in {'profile', 'product-log', 'preferences', 'cache', 'saved-state', 'container'} for label in scans), 'unexpected scan root')
                require(all(type(proof['accepted']) is bool and type(proof['file_count']) is int and
                            type(proof['bytes']) is int for proof in scans.values()), 'unexpected scan summary types')
                report.setdefault('scan_summary', {})[stage] = {label: {'accepted': proof['accepted'],
                    'files': proof['file_count'], 'bytes': proof['bytes'],
                    'hit_count': sum(len(item['hits']) + len(item['path_hits']) for item in proof['files']) +
                                 sum(len(item['path_hits']) for item in proof['directories'])}
                    for label, proof in scans.items()}
        if 'fixture-failures.json' in files:
            failures = json.loads((folder / 'fixture-failures.json').read_text())
            require(all(item in ('RuntimeError', 'AssertionError', 'FileNotFoundError', 'OperationalError',
                                'PermissionError', 'TimeoutExpired', 'KeyError', 'OSError') for item in failures),
                    'unexpected fixture failure type')
            report['fixture_failure_classes'] = failures
        reports.append(report)
        print(json.dumps(report, sort_keys=True), flush=True)
    (out / 'diagnostic.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__': main()
