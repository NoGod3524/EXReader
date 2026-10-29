#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned failed continuation evidence; fixed-output diagnosis, never acceptance."""
import json
import base64
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import parse_qsl, urlsplit
from contract import ROOT, STAGES, guard, require, sha
from archive_contract import safe_extract
from inspect_native import CONTROLS, MESSAGES, ROLES, variant_labels
from continuation_lifecycle import verify_lifecycle, seal_files
from continuation_contract import APPLEDOUBLE_LIMIT, appledouble_content
from privacy_scan import inventory, scan_file, needles, identity
from authenticate_continuation import verify_ios_admission

RUN = '40858915090'
SOURCE = '6803602e5791eafa69a6e61bc5499d36cd31d92e'
SOURCE_FILE = 'tests/apple_password_privacy_20261028/continuation_ui/PasswordPrivacyContinuationUITests.swift'
SOURCE_SHA = '92629443887d6218722d65b9c4a545f90341fa65167ff8cdd73bde52921cca5f'
SOURCE_LAST_LINE = 301
SOURCE_PATH = '/Users/runner/work/EXReader/EXReader/' + SOURCE_FILE
# Exact terminal three-platform attempt-1 uploads; all originals stay retained.
# Timing/member integrity already replayed; exact failed native operations remain
# unknown. Four/three/three checkpoints are progress, never sequence acceptance.
ARTIFACTS = {
    'macos': (12890808734, 73495841, 'dbe04fd8546e3f287e7255e7cee01532479a0c24ca3c55ac5ddbb1d49fa984f2'),
    'iphone': (12891029288, 201548440, '737c604cde22560e045c5b5edebc6ed5a7a8cbfea9423b1b991550eb2161a60c'),
    'ipad': (12892140802, 204032016, '792bc99aeda70476c54e040dce57c326f8833edb1ad99c01eb723253c5c9053d'),
}
# The completed profile remains bound to its historical inputs, not the newly
# repinned default diagnosis. This does not authorize another profile run.
PROFILE_RUN = '40839064448'
PROFILE_SOURCE = 'abd16571fda41b5bc936fcbcfb9a125554992c2e'
PROFILE_ARTIFACTS = {
    'macos': (12882218229, 165944812, '8e57858429168377b890a533de823b66dd215fe5279a402c4fd103fbda196987'),
    'iphone': (12882548477, 215120884, '3375a7fbbd91697532c6447b3f336715a8512039c6f89efad736342a60a3133b'),
    'ipad': (12883131501, 160391222, '001a9b42d19044057fcc5ecf580cffa60050a837b1d9a6a38f46d49277365dda'),
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
DIAGNOSTIC_STAGES = ('entry', 'scope-and-source', 'artifact-metadata', 'artifact-download',
    'archive-bytes', 'archive-extract', 'result-identity', 'member-inventory', 'member-bytes',
    'lifecycle-receipt', 'admission-replay', 'progress-and-native-log', 'scan-summaries', 'fixture-failures', 'network-summary',
    'xcresult-copy', 'xcresult-parser', 'xcresult-issues', 'attachment-export',
    'attachment-summary', 'safe-report')
CURRENT_DIAGNOSTIC_STAGE = 'entry'
CURRENT_MEMBER_INTEGRITY = None
CURRENT_PLATFORM = None
CURRENT_SAFE_REPORT = None
COMPLETED_REPORTS = []
ADMISSION_COMMAND_ROLES = {'admission-pre-sign-archive', 'admission-host-sign',
    'admission-post-sign-display', 'admission-post-sign-verify', 'admission-post-sign-archive',
    'admission-installed-path', 'admission-installed-display', 'admission-installed-verify', 'admission-installed-archive'}
REFUSAL_CODES = {
    'checkout differs': 'checkout-identity',
    'old or foreign path changed': 'source-scope',
    'dirty source': 'dirty-source',
    'frozen diagnostic source positions changed': 'source-hash',
    'frozen diagnostic source extent changed': 'source-extent',
    'prior continuation artifact identity differs': 'artifact-metadata',
    'prior original ZIP differs': 'archive-bytes',
    'unsafe or duplicate ZIP entry': 'archive-path',
    'ambiguous ZIP component': 'archive-component',
    'linked or special ZIP entry': 'archive-entry-type',
    'unsupported or oversized ZIP member': 'archive-member-resource',
    'oversized ZIP total': 'archive-total-resource',
    'ZIP case/Unicode alias or file-directory collision': 'archive-alias-collision',
    'prior continuation identity differs': 'result-identity',
    'prior continuation inventory differs': 'member-inventory',
    'prior continuation member differs': 'member-bytes',
    'unexpected member metadata': 'member-metadata',
    'producer evidence was not sealed': 'unsealed-evidence',
    'lifecycle receipt shape differs': 'lifecycle-shape',
    'lifecycle ownership incomplete': 'lifecycle-ownership',
    'lifecycle cleanup incomplete': 'lifecycle-cleanup',
    'admission phase evidence incomplete': 'admission-phases',
    'admission original archive differs': 'admission-archive',
    'admission archive namespace differs': 'admission-namespace',
    'admission archive members differ': 'admission-members',
    'admission identity replay differs': 'admission-identity-replay',
    'retained signature summary differs': 'admission-signature-summary',
    'actual signature replay differs': 'admission-signature-replay',
    'expected ad-hoc host signature absent': 'admission-signature-invalid',
    'admission verifier changed original extracted app': 'admission-verifier-mutation',
    'admission comparison claim differs': 'admission-comparison',
    'admission build sign native installed order differs': 'admission-command-order',
    'admission app resource substitution': 'admission-resource-substitution',
    'built or installed admission bytes differ': 'admission-byte-substitution',
    'signed or installed admission unverified': 'admission-unverified',
    'admission app identity differs': 'admission-app-identity',
    'linked entitlement source differs': 'admission-entitlement-source',
    'entitlement section absent or duplicate': 'admission-entitlement-section',
    'unsupported simulator executable': 'admission-executable-format',
    'simulator platform identity differs': 'admission-executable-platform',
    'pinned source metadata differs': 'source-metadata',
    'pinned source bytes differ': 'source-bytes',
    'pinned source line extent differs': 'source-extent',
    'prior continuation verdict differs': 'prior-verdict',
    'unexpected strict checks': 'strict-check-shape',
    'unexpected checkpoint': 'checkpoint-shape',
    'unexpected command shape': 'command-shape',
    'unexpected failure class': 'failure-class',
    'unexpected activity marker count': 'activity-count',
    'unexpected scan root': 'scan-root',
    'unexpected scan verdict': 'scan-verdict',
    'unexpected fixture failure type': 'fixture-failure-shape',
    'original request or native-result evidence absent': 'required-evidence-absent',
    'unexpected fixture root': 'fixture-root',
    'unexpected request inventory': 'request-inventory',
    'unexpected first request boundary': 'request-boundary',
    'unexpected request row': 'request-row',
    'native result parser refused': 'xcresult-tool',
    'unexpected issue value': 'xcresult-issue-value',
    'unexpected issue location': 'xcresult-issue-location',
    'native attachment exporter refused': 'attachment-tool',
    'unexpected attachment manifest': 'attachment-manifest',
    'unexpected attachment case': 'attachment-case',
    'unexpected attachment identity': 'attachment-identity',
    'unexpected attachment entry': 'attachment-entry',
    'unexpected attachment count': 'attachment-count',
}


def diagnostic_stage(value):
    global CURRENT_DIAGNOSTIC_STAGE
    require(value in DIAGNOSTIC_STAGES, 'invalid diagnostic stage')
    CURRENT_DIAGNOSTIC_STAGE = value


def refusal_report(error, stage):
    """Exact finite labels only; never format exception text, args or traceback."""
    classes = {RuntimeError: 'runtime', FileNotFoundError: 'file-not-found',
        PermissionError: 'permission', OSError: 'os', KeyError: 'key',
        ValueError: 'value', TypeError: 'type', json.JSONDecodeError: 'json',
        zipfile.BadZipFile: 'zip', subprocess.CalledProcessError: 'command',
        subprocess.TimeoutExpired: 'command-timeout'}
    code = 'unclassified'
    if type(error) is RuntimeError and len(error.args) == 1 and type(error.args[0]) is str:
        code = REFUSAL_CODES.get(error.args[0], 'unclassified')
    return {'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False,
        'diagnostic_refused': True, 'stage': stage if type(stage) is str and stage in DIAGNOSTIC_STAGES else 'unknown',
        'exception_class': classes.get(type(error), 'other'), 'refusal_code': code,
        'arbitrary_error_details_printed': False}


def member_role(name):
    """Finite location category only; no arbitrary member name leaves Actions."""
    fixed = {'native.log': 'native-log', 'requests.json': 'network-requests',
        'fixture-failures.json': 'fixture-failures', 'checkpoints.json': 'checkpoints',
        'synthetic-oracle-input.json': 'synthetic-input', 'source.epub': 'original-source',
        'resource-manifest.json': 'resource-manifest', 'sdk-identity.json': 'sdk-identity',
        'EXReaderHost.link.map': 'provider-map', 'privacy.xcresult/Info.plist': 'xcresult-info'}
    if name in fixed: return fixed[name]
    if name.startswith('privacy.xcresult/Data/'): return 'xcresult-data'
    if name.startswith('privacy.xcresult/'): return 'xcresult-other'
    if name.startswith('adapter/'): return 'adapter'
    for stage in STAGES:
        if name == stage + '-product.zip': return 'product-snapshot'
        if name == stage + '-privacy-scan.json': return 'privacy-scan'
        if name == stage + '-product-log-manifest.json': return 'product-log-manifest'
        if name == stage + '-safe-log-attribution.json': return 'log-attribution'
        prefix = 'sensitive-synthetic-product-logs/' + stage + '/'
        if name == prefix + 'host-unified.json': return 'product-log'
        if name == prefix + 'capture-stderr.txt': return 'product-log-stderr'
    return 'other'


def member_integrity(directory, manifest):
    """Check every member, report only grouped size/hash equality booleans."""
    require(type(manifest) is dict and len(manifest) <= 100000, 'unexpected member metadata')
    groups, mismatches = {}, 0
    for name, item in manifest.items():
        require(type(name) is str and type(item) is dict and set(item) == {'bytes', 'sha256'} and
                type(item['bytes']) is int and 0 <= item['bytes'] <= 8 * 1024 ** 3 and
                type(item['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is not None,
                'unexpected member metadata')
        path = directory / name
        size_matches, hash_matches = path.stat().st_size == item['bytes'], sha(path) == item['sha256']
        if not (size_matches and hash_matches):
            mismatches += 1
            key = (member_role(name), size_matches, hash_matches)
            groups[key] = groups.get(key, 0) + 1
    return {'complete': True, 'member_count': len(manifest), 'mismatch_count': mismatches,
        'mismatch_groups': [{'role': role, 'size_matches': size, 'hash_matches': digest, 'count': count}
            for (role, size, digest), count in sorted(groups.items())],
        'arbitrary_member_names_or_bytes_printed': False, 'acceptance': False}


def sealed_lifecycle(result, platform):
    require(result.get('evidence_sealed') is True, 'producer evidence was not sealed')
    receipt = result['lifecycle']
    verify_lifecycle(receipt, platform)
    # verify_lifecycle permits only fixed keys, booleans, bounded counts and
    # fixed cleanup states. This receipt is not an authenticated event trace.
    return receipt


def verify_frozen_ui_source(record, expected_sha=SOURCE_SHA, expected_lines=SOURCE_LAST_LINE):
    """Bind old line positions to the immutable original source, not new UI edits."""
    require(type(record) is dict and record.get('type') == 'file' and record.get('path') == SOURCE_FILE and
            record.get('encoding') == 'base64' and type(record.get('size')) is int and
            0 < record['size'] <= 256 * 1024 and type(record.get('content')) is str and
            len(record['content']) <= 512 * 1024, 'pinned source metadata differs')
    data = base64.b64decode(record['content'].replace('\n', ''), validate=True)
    require(len(data) == record['size'] and hashlib.sha256(data).hexdigest() == expected_sha, 'pinned source bytes differ')
    require(len(data.decode('utf-8', errors='strict').splitlines()) == expected_lines, 'pinned source line extent differs')
    return {'immutable_source_bytes_verified': True, 'source_positions_not_authenticated_callsites': True}


def admission_namespaces(directory):
    """Observe finite root categories only; this never admits an extra namespace."""
    manifest = json.loads((directory / 'ios-admission/manifest.json').read_text())
    require(type(manifest) is dict and set(manifest) == {'pre-sign', 'post-sign', 'installed'}, 'admission phase evidence incomplete')
    reports = []
    for phase in ('pre-sign', 'post-sign', 'installed'):
        archive = directory / 'ios-admission' / (phase + '.zip'); record = manifest[phase]
        require(type(record['archive_bytes']) is int and archive.stat().st_size == record['archive_bytes'] and
                sha(archive) == record['archive_sha256'], 'admission original archive differs')
        with tempfile.TemporaryDirectory(prefix='privacy-namespace-diagnostic-') as temporary:
            root = Path(temporary); safe_extract(archive, root)
            entries = list(root.iterdir())
            counts = {'host-app': {'directories': 0, 'files': 0},
                      'metadata-named': {'directories': 0, 'files': 0}, 'other': {'directories': 0, 'files': 0}}
            for path in entries:
                role = 'host-app' if path.name == 'EXReaderHost.app' else 'metadata-named' if path.name == '__MACOSX' else 'other'
                counts[role]['directories' if path.is_dir() else 'files'] += 1
            reports.append({'phase': phase, 'root_entry_count': len(entries), 'root_categories': counts,
                'all_member_count': sum(1 for path in root.rglob('*') if path.is_file()),
                'namespace_accepted': False, 'arbitrary_names_or_bytes_printed': False})
    return reports


def metadata_variants(directory):
    oracle = json.loads((directory / 'synthetic-oracle-input.json').read_text())
    require(type(oracle) is dict and oracle.get('synthetic_only') is True and
            (oracle.get('source_sha'), oracle.get('run_id'), oracle.get('attempt')) == (SOURCE, RUN, '1'),
            'metadata oracle identity differs')
    user, passwords = oracle.get('user'), oracle.get('passwords')
    require(type(user) is str and re.fullmatch(r'privacy-user-[0-9a-f]{32}', user) is not None and
            type(passwords) is dict and set(passwords) == {'remembered', 'session'} and
            all(type(value) is str and re.fullmatch(r'Privacy-[0-9a-f]{64}!%:\+', value) is not None
                for value in passwords.values()) and passwords['remembered'] != passwords['session'],
            'metadata synthetic inputs differ')
    values = {'user': user.encode()}
    for role, password in passwords.items():
        pair = (user + ':' + password).encode()
        values[role] = password.encode(); values[role + '-pair'] = pair
        values[role + '-authorization'] = b'Basic ' + base64.b64encode(pair)
    return needles(values)


def classify_metadata_tree(root, variants):
    """All bytes scanned, then exact pairing/content observed; no root is waived."""
    before = inventory(root); records, all_hits, metadata = {}, set(), []
    paths = sorted(path for path in before if path != '.')
    files, directories = {}, set()
    for name in paths:
        path = root / name; mode = path.lstat().st_mode
        path_hits = {label for label, value in variants.items() if value in name.encode('utf-8')}
        all_hits.update(path_hits)
        if stat.S_ISDIR(mode):
            directories.add(name); continue
        proof = scan_file(path, variants)
        all_hits.update(proof['hits']); files[name] = proof
        records[name] = {'bytes': proof['bytes'], 'sha256': proof['sha256']}
    require(inventory(root) == before, 'metadata tree changed during scan')
    paired = set()
    for name, proof in files.items():
        if not name.startswith('__MACOSX/'):
            continue  # Still fully scanned/hashed and resealed above/below.
        row = {'path_sha256': hashlib.sha256(name.encode()).hexdigest(),
            'bytes': proof['bytes'], 'sha256': proof['sha256'],
            'hit_variant_labels': sorted(set(proof['hits']) | {label for label, value in variants.items()
                if value in name.encode('utf-8')}),
            'paired_host': False, 'target_kind': 'unpaired', 'content': None,
            'classification': 'unsupported-pair', 'namespace_accepted': False}
        metadata.append(row)
        relative = Path(name).relative_to('__MACOSX')
        if not relative.name.startswith('._') or len(relative.name) <= 2: continue
        target = relative.with_name(relative.name[2:]).as_posix()
        if not (target == 'EXReaderHost.app' or target.startswith('EXReaderHost.app/')) or \
                target not in files and target not in directories or target in paired: continue
        paired.add(target); row['paired_host'] = True
        row['target_kind'] = 'app-root' if target == 'EXReaderHost.app' else \
            'directory' if target in directories else 'executable' if target == 'EXReaderHost.app/EXReaderHost' else \
            'signature' if target.startswith('EXReaderHost.app/_CodeSignature/') else \
            'framework' if target.startswith('EXReaderHost.app/Frameworks/') else 'app-file'
        row['target_path_sha256'] = hashlib.sha256(target.encode()).hexdigest()
        if proof['bytes'] > APPLEDOUBLE_LIMIT:
            row['classification'] = 'unsupported-size-after-complete-scan'; continue
        descriptor = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode) and
                    identity(os.fstat(stream.fileno())) == before[name], 'metadata opened identity differs')
            data = stream.read(APPLEDOUBLE_LIMIT + 1)
            require(identity(os.fstat(stream.fileno())) == before[name], 'metadata read identity differs')
        require(len(data) == proof['bytes'] and hashlib.sha256(data).hexdigest() == proof['sha256'],
                'metadata parse bytes differ')
        try:
            row['content'] = appledouble_content(data)
            row['classification'] = 'paired-supported-structure-content-opaque'
        except RuntimeError as error:
            allowed = {'metadata unsupported ' + suffix for suffix in ('size', 'header', 'entries',
                'attribute header', 'attribute entry', 'attribute name', 'attribute range',
                'attribute padding', 'attribute overlap')}
            require(type(error) is RuntimeError and len(error.args) == 1 and
                    type(error.args[0]) is str and error.args[0] in allowed, 'metadata classifier refused')
            row['classification'] = error.args[0].replace('metadata ', '').replace(' ', '-')
    # Complete double byte replay catches late mutation of a scanned prefix or
    # earlier file. Unknown roots, app executable/data and metadata all remain.
    require(inventory(root) == before and seal_files(root) == records and inventory(root) == before,
            'metadata final replay differs')
    from inspect_native import VARIANT_LABELS
    require(all(type(label) is str and label in VARIANT_LABELS for label in all_hits), 'unexpected variant label')
    metadata_dirs = {name for name in directories if name == '__MACOSX' or name.startswith('__MACOSX/')}
    used_dirs = {parent.as_posix() for name in files if name.startswith('__MACOSX/')
                 for parent in Path(name).parents if parent.as_posix() != '.'}
    return {'all_file_count': len(files), 'all_bytes': sum(value['bytes'] for value in records.values()),
        'all_files_fully_scanned_and_replayed': True, 'size_skips': 0,
        'hit_variant_labels': sorted(all_hits), 'metadata_members': metadata,
        'unpaired_metadata_directory_count': len(metadata_dirs - used_dirs),
        'other_root_count': len({Path(name).parts[0] for name in paths} - {'EXReaderHost.app', '__MACOSX'}),
        'namespace_accepted': False, 'content_semantics_verified': False,
        'signature_replay_credited': False, 'full_f10_accepted': False}


def admission_metadata(directory):
    manifest = json.loads((directory / 'ios-admission/manifest.json').read_text())
    require(type(manifest) is dict and set(manifest) == {'pre-sign', 'post-sign', 'installed'},
            'admission phase evidence incomplete')
    variants = metadata_variants(directory); reports = []
    for phase in ('pre-sign', 'post-sign', 'installed'):
        archive = directory / 'ios-admission' / (phase + '.zip'); record = manifest[phase]
        require(type(record['archive_bytes']) is int and archive.stat().st_size == record['archive_bytes'] and
                sha(archive) == record['archive_sha256'], 'admission original archive differs')
        with tempfile.TemporaryDirectory(prefix='privacy-metadata-diagnostic-') as temporary:
            root = Path(temporary); safe_extract(archive, root)
            report = classify_metadata_tree(root, variants)
            require(seal_files(root / 'EXReaderHost.app') == record['files'], 'admission archive members differ')
            report['host_app_all_file_manifest_matches'] = True
            report['phase'] = phase
            reports.append(report)
    return reports


def locations(path):
    """Source positions and fixed signatures, not arbitrary operands/callsite proof."""
    found = []
    with path.open('r', encoding='utf-8', errors='replace') as file:
        for line in file:
            match = re.match(re.escape(SOURCE_PATH) + r':([1-9][0-9]{0,2}): error:', line)
            if not match or int(match.group(1)) not in range(1, SOURCE_LAST_LINE + 1): continue
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
            row['role'] in ROLES | ADMISSION_COMMAND_ROLES and type(row['exit']) is int and -128 <= row['exit'] <= 255 for row in commands),
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
    checkpoints = result['checkpoints']
    require(type(checkpoints) is dict and list(checkpoints) == STAGES[:len(checkpoints)], 'unexpected first request boundary')
    first = checkpoints['remember_closed']['network_requests'] if checkpoints else None
    require(first is None if not checkpoints else type(first) is int and 0 <= first <= len(requests),
            'unexpected first request boundary')
    methods = ('GET', 'MKCOL', 'PUT', 'PROPFIND')
    counts = {role: {method: 0 for method in methods} for role in ('remembered', 'session', 'unrecognized')}
    shards = {role: set() for role in counts}
    for index, row in enumerate(requests):
        require(type(row) is dict and set(row) == {'method', 'path', 'credential'} and
                row['method'] in methods and row['credential'] in ('remembered', 'session', None) and
                type(row['path']) is str and row['path'].startswith(root.path), 'unexpected request row')
        if first is None or index < first: continue
        role = row['credential'] or 'unrecognized'; counts[role][row['method']] += 1
        match = re.fullmatch(re.escape(root.path) + r'exreader-sync-v1/revisions/([0-9a-f]{2})/', row['path'])
        if row['method'] == 'PROPFIND' and match: shards[role].add(match.group(1))
    return {'total_requests': len(requests), 'first_checkpoint_observed': first is not None, 'before_first_checkpoint': first,
            'after_first_checkpoint': len(requests) - first if first is not None else None,
            'credential_method_counts_after_first': counts if first is not None else None,
            'distinct_revision_shards_after_first': {role: len(value) for role, value in shards.items()} if first is not None else None,
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
                            (int(item) in range(1, SOURCE_LAST_LINE + 1) if key.endswith('LineNumber') else True)
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


def inspect_native_result(folder, files, report):
    """Independent native extraction AFTER byte/lifecycle admission only.

    Later scan/fixture/network/admission refusals remain fatal and retain this
    validated partial report. No raw output or exception operand is returned.
    """
    diagnostic_stage('xcresult-copy')
    require(any(name.startswith('privacy.xcresult/') for name in files),
            'original request or native-result evidence absent')
    # xcresulttool may update metadata. Parse only a disposable copy after
    # every retained original member was authenticated above.
    with tempfile.TemporaryDirectory(prefix='privacy-xcresult-diagnostic-') as temporary:
        copied = shutil.copytree(folder / 'privacy.xcresult', os.path.join(temporary, 'privacy.xcresult'))
        diagnostic_stage('xcresult-parser')
        done = subprocess.run(['xcrun', 'xcresulttool', 'get', 'object', '--legacy', '--path', copied,
                               '--format', 'json'], capture_output=True, timeout=120)
        require(done.returncode == 0, 'native result parser refused')
        diagnostic_stage('xcresult-issues')
        report['xcresult'] = xcresult_issues(json.loads(done.stdout))
        exported = Path(temporary) / 'attachments'
        diagnostic_stage('attachment-export')
        done = subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', copied,
                               '--output-path', str(exported)], capture_output=True, timeout=120)
        require(done.returncode == 0, 'native attachment exporter refused')
        diagnostic_stage('attachment-summary')
        report['exported_attachments'] = attachment_summary(exported)


def diagnose_platform(out, platform, identifier, size, digest):
    global CURRENT_MEMBER_INTEGRITY, CURRENT_PLATFORM, CURRENT_SAFE_REPORT
    CURRENT_PLATFORM = platform
    CURRENT_MEMBER_INTEGRITY = None
    diagnostic_stage('artifact-metadata')
    endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(identifier)
    record = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    require(record['id'] == identifier and record['name'] == 'password-continuation-native-' + platform + '-' + RUN + '-1' and
            str(record['workflow_run']['id']) == RUN and record['workflow_run']['head_sha'] == SOURCE and
            record['digest'] == 'sha256:' + digest and record['size_in_bytes'] == size and
            record['expired'] is False, 'prior continuation artifact identity differs')
    original = out / (platform + '-original.zip')
    diagnostic_stage('artifact-download')
    with original.open('wb') as file: subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=file, check=True)
    diagnostic_stage('archive-bytes')
    require(original.stat().st_size == size and sha(original) == digest, 'prior original ZIP differs')
    diagnostic_stage('archive-extract')
    folder = out / platform; safe_extract(original, folder)
    diagnostic_stage('result-identity')
    result = json.loads((folder / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
            (SOURCE, RUN, '1', platform), 'prior continuation identity differs')
    diagnostic_stage('member-inventory')
    files = {path.relative_to(folder).as_posix() for path in folder.rglob('*') if path.is_file()}
    require(files == set(result['files']) | {'result.json'}, 'prior continuation inventory differs')
    diagnostic_stage('member-bytes')
    CURRENT_MEMBER_INTEGRITY = member_integrity(folder, result['files'])
    require(CURRENT_MEMBER_INTEGRITY['mismatch_count'] == 0, 'prior continuation member differs')
    diagnostic_stage('lifecycle-receipt')
    lifecycle = sealed_lifecycle(result, platform)
    diagnostic_stage('progress-and-native-log')
    report = safe_progress(result, files)
    CURRENT_SAFE_REPORT = report
    report.update(old_source_sha=SOURCE, old_run_id=RUN, old_attempt=1, platform=platform,
                  artifact_id=identifier, original_bytes=size, original_sha256=digest,
                  verified_member_count=len(files), arbitrary_log_text_printed=False,
                  source_positions_not_authenticated_callsites=True,
                  native_failure_locations=locations(folder / 'native.log') if 'native.log' in files else [])
    report['member_integrity'] = CURRENT_MEMBER_INTEGRITY
    report['producer_lifecycle_receipt'] = lifecycle
    report['producer_receipt_is_event_trace_proof'] = False
    report['activity_timing'] = activity_timing(folder / 'native.log')
    inspect_native_result(folder, files, report)
    diagnostic_stage('scan-summaries')
    for stage in STAGES:
        name = stage + '-privacy-scan.json'
        if name not in files: continue
        scans = json.loads((folder / name).read_text())
        require(set(scans) <= {'profile', 'product-log', 'preferences', 'cache', 'saved-state', 'container'}, 'unexpected scan root')
        require(all(type(proof['accepted']) is bool for proof in scans.values()), 'unexpected scan verdict')
        report.setdefault('scan_summary', {})[stage] = {label: {'accepted': proof['accepted'],
            'hit_variant_labels': variant_labels(proof)} for label, proof in scans.items()}
    diagnostic_stage('fixture-failures')
    if 'fixture-failures.json' in files:
        failures = json.loads((folder / 'fixture-failures.json').read_text())
        require(type(failures) is list and all(item in FAILURES for item in failures), 'unexpected fixture failure type')
        report['fixture_failure_classes'] = failures
    diagnostic_stage('network-summary')
    require('requests.json' in files and any(name.startswith('privacy.xcresult/') for name in files),
            'original request or native-result evidence absent')
    report['network'] = network_summary(result, json.loads((folder / 'requests.json').read_text()))
    diagnostic_stage('admission-replay')
    report['independent_ios_admission_replay'] = None
    if platform != 'macos':
        report['admission_namespace_observations'] = admission_namespaces(folder)
        report['retained_metadata_classification'] = admission_metadata(folder)
        report['independent_ios_admission_replay'] = verify_ios_admission(folder, SOURCE, result, require_program=False)
    diagnostic_stage('safe-report')
    return report


def current_refusal(error):
    report = refusal_report(error, CURRENT_DIAGNOSTIC_STAGE)
    report['member_integrity'] = CURRENT_MEMBER_INTEGRITY
    report['platform'] = CURRENT_PLATFORM if CURRENT_PLATFORM in ('macos', 'iphone', 'ipad') else None
    report['validated_partial_report'] = CURRENT_SAFE_REPORT
    return report


def run_platforms(out, diagnoser=diagnose_platform):
    global CURRENT_MEMBER_INTEGRITY, CURRENT_PLATFORM, CURRENT_SAFE_REPORT
    failed = False
    for platform, (identifier, size, digest) in ARTIFACTS.items():
        CURRENT_PLATFORM, CURRENT_MEMBER_INTEGRITY, CURRENT_SAFE_REPORT = platform, None, None
        try:
            report = diagnoser(out, platform, identifier, size, digest)
        except Exception as error:
            report = current_refusal(error)
            failed = True
        COMPLETED_REPORTS.append(report)
        print(json.dumps(report, sort_keys=True), flush=True)
        (out / 'diagnostic.json').write_text(json.dumps(COMPLETED_REPORTS, indent=2) + '\n')
    return not failed


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    diagnostic_stage('scope-and-source')
    guard()
    endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/contents/' + SOURCE_FILE + '?ref=' + SOURCE
    source_record = json.loads(subprocess.check_output(['gh', 'api', endpoint], timeout=30))
    verify_frozen_ui_source(source_record)
    require(set(ARTIFACTS) == {'macos', 'iphone', 'ipad'}, 'exact three-platform diagnostic artifact pins required')
    out = ROOT / 'build/apple-password-continuation-diagnostic'; out.mkdir(parents=True, exist_ok=False)
    return run_platforms(out)


def capture_profile_main():
    from continuation_log_capture import retained_profile
    report = retained_profile(ROOT / 'build/apple-password-capture-profile', PROFILE_ARTIFACTS, PROFILE_SOURCE, PROFILE_RUN)
    print(json.dumps(report, sort_keys=True), flush=True)
    return report['profile_complete'] and report['performance_gate'] and not report['profile_refused']


if __name__ == '__main__' and sys.argv[1:] == ['--capture-profile']:
    try:
        raise SystemExit(0 if capture_profile_main() else 1)
    except Exception:
        print(json.dumps({'diagnostic_only': True, 'profile_refused': True,
            'refusal_code': 'retained-profile-entry-refused', 'native_acceptance': False,
            'full_f10_accepted': False, 'arbitrary_values_printed': False}), flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    try:
        if not main(): raise SystemExit(1)
    except Exception as error:
        # An OS/parser exception may embed a synthetic value in its operands.
        # Refuse without relaying that exception text or chained traceback.
        report = current_refusal(error)
        print(json.dumps(report, sort_keys=True), flush=True)
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            try:
                out = ROOT / 'build/apple-password-continuation-diagnostic'
                out.mkdir(parents=True, exist_ok=True)
                (out / 'diagnostic.json').write_text(json.dumps(COMPLETED_REPORTS + [report], indent=2) + '\n')
            except OSError:
                pass  # Console still contains the fixed refusal; never echo I/O operands.
        raise RuntimeError('pinned continuation diagnosis refused; arbitrary error details withheld') from None
