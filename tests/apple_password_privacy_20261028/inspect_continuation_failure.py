#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned failed continuation evidence; fixed-output diagnosis, never acceptance."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qsl, urlsplit
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
CASE = 'testDiagnosticContinuationRememberUpdateRestart'
BUNDLE = 'org.exreader.password-privacy-20261028'
STATUS_TOKENS = {'finished': '本轮扫描完成', 'failed': '同步失败',
                 'missing-credential': '请重新输入此账号的授权信息', 'idle': '未同步',
                 'closed': '已关闭', 'preparing-original': '正在准备原书', 'receiving-shelf': '正在接收书架'}


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


def activity_timing(path):
    """Bounded XCTest activity markers, not arbitrary titles or product timing."""
    markers, state_queries = [], []
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            match = re.fullmatch(r'\s*t =\s*([0-9]{1,4}\.[0-9]{2})s\s+([^\r\n]*)\r?\n?', line)
            if not match or float(match.group(1)) > 4800: continue
            seconds, title = float(match.group(1)), match.group(2)
            kind = None
            if title == 'Launch ' + BUNDLE: kind = 'launch'
            elif title == 'Terminate ' + BUNDLE: kind = 'terminate'
            elif title in ('Tap "account.sync.start" Button', 'Tap "同步" Button'): kind = 'tap-sync'
            elif title.startswith('Find the "account.sync.state" '):
                state_queries.append(seconds)
            if kind: markers.append({'seconds': seconds, 'marker': kind})
    require(len(markers) <= 100, 'unexpected activity marker count')
    return {'markers': markers, 'state_query_count': len(state_queries),
            'first_state_query_seconds': state_queries[0] if state_queries else None,
            'last_state_query_seconds': state_queries[-1] if state_queries else None,
            'arbitrary_activity_titles_printed': False, 'product_performance_acceptance': False}


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


def network_summary(result, requests):
    """Only finite credential/method categories and shard counts leave Actions."""
    root = urlsplit(result['root'])
    require(root.scheme == 'https' and root.hostname == '127.0.0.1' and root.port is not None and
            not root.query and not root.fragment and not root.username and not root.password and
            re.fullmatch(r'/privacy-[0-9a-f]{24}/', root.path), 'unexpected fixture root')
    require(type(requests) is list and len(requests) <= 100000, 'unexpected request inventory')
    first = result['checkpoints']['remember_closed']['network_requests']
    require(type(first) is int and 0 <= first <= len(requests), 'unexpected first request boundary')
    methods = ('GET', 'MKCOL', 'PUT', 'PROPFIND')
    counts = {role: {method: 0 for method in methods} for role in ('remembered', 'session', 'unrecognized')}
    shards = {role: set() for role in counts}
    for index, row in enumerate(requests):
        require(type(row) is dict and set(row) == {'method', 'path', 'credential'} and
                row['method'] in methods and row['credential'] in ('remembered', 'session', None) and
                type(row['path']) is str and row['path'].startswith(root.path), 'unexpected request row')
        if index < first: continue
        role = row['credential'] or 'unrecognized'; counts[role][row['method']] += 1
        match = re.fullmatch(re.escape(root.path) + r'exreader-sync-v1/revisions/([0-9a-f]{2})/', row['path'])
        if row['method'] == 'PROPFIND' and match: shards[role].add(match.group(1))
    return {'total_requests': len(requests), 'before_first_checkpoint': first,
            'after_first_checkpoint': len(requests) - first, 'credential_method_counts_after_first': counts,
            'distinct_revision_shards_after_first': {role: len(value) for role, value in shards.items()},
            'raw_paths_headers_values_printed': False}


def xcresult_issues(payload):
    """Only failure-issue nodes; no arbitrary message, URL or test name output."""
    issues = []
    def value(row, name):
        item = row.get(name, {})
        return item.get('_value', '') if type(item) is dict else ''
    def walk(node):
        if type(node) is list:
            for item in node: walk(item)
        elif type(node) is dict:
            if node.get('_type', {}).get('_name') == 'TestFailureIssueSummary':
                message, name = value(node, 'message'), value(node, 'testCaseName')
                require(type(message) is str and type(name) is str, 'unexpected issue value')
                location = node.get('documentLocationInCreatingWorkspace', {})
                url = value(location, 'url') if type(location) is dict else ''
                require(type(url) is str, 'unexpected issue location')
                source_line = None
                prefix = 'file://' + SOURCE_PATH + '#'
                if url.startswith(prefix):
                    fields = parse_qsl(url[len(prefix):], keep_blank_values=True)
                    keys = {key for key, unused in fields}
                    allowed = {'StartingLineNumber', 'EndingLineNumber', 'StartingColumnNumber', 'EndingColumnNumber'}
                    if len(fields) == len(keys) and 'StartingLineNumber' in keys and keys <= allowed and all(
                            re.fullmatch(r'[0-9]{1,4}', item) and
                            (int(item) in range(1, 161) if key.endswith('LineNumber') else True)
                            for key, item in fields):
                        source_line = int(dict(fields)['StartingLineNumber'])
                assertion = re.search(r'\b(XCTAssert(?:True|False|Equal|Nil|NotNil)|XCTUnwrap)\b', message)
                issues.append({'case_matches': re.findall(r'\btest[A-Za-z0-9_]+\b', name) == [CASE],
                    'source_line': source_line, 'assertion': assertion.group(1) if assertion else None,
                    'static_messages': [token for token in STATIC_MESSAGES if token in message],
                    'static_controls': [token for token in CONTROLS if token in message],
                    'fixed_signatures': [key for key, token in SIGNATURES.items() if token in message],
                    'known_time_allowance': [seconds for seconds in (240, 360)
                        if re.search(r'Test exceeded execution time allowance of ' + str(seconds) + r'(?:\.0+)? seconds\b', message)]})
            for item in node.values(): walk(item)
    walk(payload)
    return {'failure_issue_count': len(issues), 'issues': issues,
            'arbitrary_issue_operands_printed': False, 'source_positions_not_authenticated_callsites': True}


def attachment_summary(directory):
    """Stream exported text only for fixed status tokens; never infer actual UI state."""
    groups = json.loads((directory / 'manifest.json').read_text())
    require(type(groups) is list, 'unexpected attachment manifest')
    rows, seen = [], set()
    extensions = ('.png', '.jpg', '.jpeg', '.heic', '.txt', '.log', '.json', '.plist', '.html', 'other')
    type_counts = {extension: 0 for extension in extensions}
    for group in groups:
        case = group.get('testIdentifier') or group.get('testName')
        require(type(case) is str and re.findall(r'\btest[A-Za-z0-9_]+\b', case) == [CASE], 'unexpected attachment case')
        for item in group['attachments']:
            filename, name = item['exportedFileName'], item['suggestedHumanReadableName']
            require(type(filename) is str and Path(filename).name == filename and filename not in seen and
                    type(name) is str, 'unexpected attachment identity')
            seen.add(filename); path = directory / filename
            require(path.is_file() and not path.is_symlink(), 'unexpected attachment entry')
            extension = path.suffix.lower()
            extension = extension if extension in extensions else 'other'
            type_counts[extension] += 1
            kind = next((stage for stage in STAGES if name.startswith('privacy-' + stage)), None)
            if kind is None:
                kind = 'hierarchy-named' if any(token in name.lower() for token in ('hierarchy', 'debug description', 'debugdescription')) else 'other'
            tokens = set()
            text_scanned = extension in ('.txt', '.log', '.json', '.plist', '.html')
            if text_scanned:
                encoded = {label: value.encode() for label, value in STATUS_TOKENS.items()}
                overlap = b''; width = max(map(len, encoded.values())) - 1
                with path.open('rb') as file:
                    for data in iter(lambda: file.read(1024 * 1024), b''):
                        combined = overlap + data
                        tokens.update(label for label, value in encoded.items() if value in combined)
                        overlap = combined[-width:]
            rows.append({'kind': kind, 'extension': extension, 'sha256': sha(path),
                         'text_scanned': text_scanned, 'status_token_presence': sorted(tokens)})
            require(len(rows) <= 5000, 'unexpected attachment count')
    text_count = sum(row['text_scanned'] for row in rows)
    return {'count': len(rows), 'type_counts': type_counts, 'text_attachment_count': text_count,
            'hierarchy_named_count': sum(row['kind'] == 'hierarchy-named' for row in rows),
            'text_status_tokens_absent': not any(row['status_token_presence'] for row in rows) if text_count else None,
            'attachments': rows, 'arbitrary_names_or_text_printed': False,
            'text_token_encoding': 'literal-utf8-only; UTF16 and XML escapes are not decoded',
            'token_presence_is_actual_ui_state_proof': False, 'images_not_ocr_interpreted': True}


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
        report['activity_timing'] = activity_timing(folder / 'native.log')
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
        require('requests.json' in files and any(name.startswith('privacy.xcresult/') for name in files),
                'original request or native-result evidence absent')
        report['network'] = network_summary(result, json.loads((folder / 'requests.json').read_text()))
        # xcresulttool may update metadata. Parse only a disposable copy after
        # every retained original member was authenticated above.
        with tempfile.TemporaryDirectory(prefix='privacy-xcresult-diagnostic-') as temporary:
            copied = shutil.copytree(folder / 'privacy.xcresult', os.path.join(temporary, 'privacy.xcresult'))
            done = subprocess.run(['xcrun', 'xcresulttool', 'get', 'object', '--legacy', '--path', copied,
                                   '--format', 'json'], capture_output=True, timeout=120)
            require(done.returncode == 0, 'native result parser refused')
            report['xcresult'] = xcresult_issues(json.loads(done.stdout))
            exported = Path(temporary) / 'attachments'
            done = subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', copied,
                                   '--output-path', str(exported)], capture_output=True, timeout=120)
            require(done.returncode == 0, 'native attachment exporter refused')
            report['exported_attachments'] = attachment_summary(exported)
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
