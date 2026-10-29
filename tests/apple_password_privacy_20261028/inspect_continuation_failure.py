#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned failed continuation evidence; fixed-output diagnosis, never acceptance."""
import json
import base64
import copy
from decimal import Decimal
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from urllib.parse import parse_qsl, urlsplit
from contract import ROOT, STAGES, guard, require, sha
from archive_contract import safe_extract
from inspect_native import CONTROLS, MESSAGES, ROLES, variant_labels
from continuation_lifecycle import verify_lifecycle, seal_files
import continuation_lifecycle as lifecycle_reader
from continuation_contract import APPLEDOUBLE_LIMIT, appledouble_content
from privacy_scan import inventory, scan_file, needles, identity
from authenticate_continuation import verify_ios_admission
from ui_observations import parse_ui_observations

# New current case: never substitute these pins into historical helper replay.
CURRENT_CASE_SOURCE = '2e8ef281dc1c790427ee4a5c60cae3d880750d3a'
CURRENT_CASE_RUN = '40877286914'
CURRENT_CASE_ARTIFACTS = {
    'macos': (12898598312, 104208231, 'a42f6c78ea576042c54eb12951c4e608aa641f2a1fc5c6148ac8eabc5be96ae8'),
    'iphone': (12899507875, 176407990, '5232cee7ddf98f6bc1cba6d16dec705956cb666e898af516e7ecd832518f277f'),
    'ipad': (12900935511, 187645675, 'b043a78b1adee48a1b1b92fa8f5956898c6fdc1dabbf0d9ce519dea25229af37'),
}

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
ATTACHMENT_SOURCE_HASHES = {
    'continuation_contract.py': '03a72ae6666b59f829ddd3427067dd2963a3664235f1e5d168041b28cee4e7d1',
    'contract.py': '3bbc7fca067c77b91ad5d4e3fa96a4e98e1d7ade6bfc5c90dd329b56f7eae3af',
}
CURRENT_ATTACHMENT_SOURCE_SHA = '5353da16bd5f8c9bc06b4168ef930840d92dce88060551a713bcec6b2bef8ce3'
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
    'attachment-summary', 'current-ui-replay', 'current-original-recheck', 'attachment-contract-reference', 'attachment-contract-replay',
    'attachment-contract-predicates', 'attachment-identity-candidate', 'attachment-current-replay', 'attachment-contract-final', 'safe-report')
CURRENT_DIAGNOSTIC_STAGE = 'entry'
CURRENT_MEMBER_INTEGRITY = None
CURRENT_PLATFORM = None
CURRENT_SAFE_REPORT = None
COMPLETED_REPORTS = []
ADMISSION_COMMAND_ROLES = {'admission-pre-sign-archive', 'admission-host-sign',
    'admission-post-sign-display', 'admission-post-sign-verify', 'admission-post-sign-archive',
    'admission-installed-path', 'admission-installed-display', 'admission-installed-verify', 'admission-installed-archive'}
REFUSAL_CODES = {
    'current diagnostic verdict differs': 'current-verdict',
    'current diagnostic command differs': 'current-command',
    'current diagnostic checkpoint differs': 'current-checkpoint',
    'current diagnostic identity differs': 'current-identity',
    'current macOS producer completion differs': 'current-macos-completion',
    'current iOS failed progress differs': 'current-ios-failure',
    'current UI replay differs': 'current-ui-replay',
    'current original evidence changed': 'current-original-changed',
    'candidate attachment original proof absent': 'attachment-candidate-original-proof',
    'candidate attachment JSON duplicate key': 'attachment-candidate-json-duplicate',
    'candidate attachment JSON nonfinite': 'attachment-candidate-json-nonfinite',
    'candidate attachment JSON numeric loss': 'attachment-candidate-json-number',
    'candidate attachment manifest invalid': 'attachment-candidate-manifest',
    'candidate attachment name unsupported': 'attachment-candidate-name',
    'candidate attachment selection ambiguous': 'attachment-candidate-ambiguous',
    'candidate attachment payload invalid': 'attachment-candidate-payload',
    'candidate attachment profile differs': 'attachment-candidate-profile',
    'candidate attachment copy differs': 'attachment-candidate-copy',
    'candidate attachment result differs': 'attachment-candidate-result',
    'candidate attachment original changed': 'attachment-candidate-original-changed',
    'candidate attachment replay refused': 'attachment-candidate-refused',
    'current attachment JSON duplicate key': 'attachment-current-json-duplicate',
    'current attachment JSON nonfinite': 'attachment-current-json-nonfinite',
    'current attachment JSON numeric loss': 'attachment-current-json-number',
    'current attachment name unsupported': 'attachment-current-name',
    'current attachment manifest invalid': 'attachment-current-manifest',
    'current attachment case differs': 'attachment-current-case',
    'current attachment member differs': 'attachment-current-member',
    'current attachment file invalid': 'attachment-current-file',
    'current attachment file changed': 'attachment-current-file-changed',
    'current attachment namespace changed': 'attachment-current-namespace',
    'current attachment payload invalid': 'attachment-current-payload',
    'current attachment source differs': 'attachment-current-source',
    'current attachment candidate unqualified': 'attachment-current-candidate',
    'current attachment result differs': 'attachment-current-result',
    'current attachment profile differs': 'attachment-current-profile',
    'current attachment replay refused': 'attachment-current-refused',
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
    'original attachment source differs': 'attachment-source',
    'original attachment import differs': 'attachment-import',
    'original attachment export missing': 'attachment-original-missing',
    'original attachment bytes differ': 'attachment-original-bytes',
    'original attachment namespace changed': 'attachment-original-namespace',
    'original attachment predicate shape differs': 'attachment-predicate-shape',
    'original attachment predicate contradicts helper': 'attachment-predicate-contradiction',
    'original attachment profile shape differs': 'attachment-profile-shape',
    'original attachment contract refused': 'attachment-contract-refused',
    'unsafe attachment': 'attachment-original-unsafe',
    'duplicate native stages': 'attachment-original-duplicate-stages',
    'invalid native screenshot': 'attachment-original-screenshot',
    'native stages/screenshots incomplete': 'attachment-original-incomplete',
    'invalid actual profile': 'attachment-original-profile',
    'diagnostic operation mislabeled': 'attachment-original-operation',
    'unexpected diagnostic case identity': 'attachment-original-case',
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


def metadata_variants(directory, *, source=SOURCE, run=RUN):
    oracle = json.loads((directory / 'synthetic-oracle-input.json').read_text())
    require(type(oracle) is dict and oracle.get('synthetic_only') is True and
            (oracle.get('source_sha'), oracle.get('run_id'), oracle.get('attempt')) == (source, run, '1'),
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


def admission_metadata(directory, *, source=SOURCE, run=RUN):
    manifest = json.loads((directory / 'ios-admission/manifest.json').read_text())
    require(type(manifest) is dict and set(manifest) == {'pre-sign', 'post-sign', 'installed'},
            'admission phase evidence incomplete')
    variants = metadata_variants(directory, source=source, run=run); reports = []
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


def attachment_reference(directory):
    """Execute only immutable repository source, never artifact-provided code."""
    import contract
    directory = Path(directory)
    for name, expected in ATTACHMENT_SOURCE_HASHES.items():
        done = subprocess.run(['git', 'show', SOURCE + ':tests/apple_password_privacy_20261028/' + name],
                              cwd=ROOT, capture_output=True, timeout=30)
        require(done.returncode == 0 and hashlib.sha256(done.stdout).hexdigest() == expected,
                'original attachment source differs')
        (directory / name).write_bytes(done.stdout)
        require(sha(directory / name) == expected, 'original attachment source differs')
    require(sha(Path(contract.__file__)) == ATTACHMENT_SOURCE_HASHES['contract.py'], 'original attachment import differs')
    spec = importlib.util.spec_from_file_location('pinned_attachment_contract', directory / 'continuation_contract.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    require(module.require is contract.require and module.sha is contract.sha,
            'original attachment import differs')
    return module


def attachment_predicates(directory, checkpoints=None):
    """Finite independent observations; the original helper is authoritative."""
    groups = json.loads((directory / 'manifest.json').read_text())
    require(type(groups) is list and len(groups) <= 100000, 'original attachment predicate shape differs')
    rows = {stage: {'bare_role': 0, 'exact_png': 0, 'underscore_prefix': 0,
                    'eligible': 0, 'png_magic': 0} for stage in STAGES}
    total, cases, safe_names, other, documents = 0, True, True, 0, []
    for group in groups:
        require(type(group) is dict and type(group.get('attachments')) is list,
                'original attachment predicate shape differs')
        case = group.get('testIdentifier') or group.get('testName')
        cases = cases and type(case) is str and re.findall(r'\btest[A-Za-z0-9_]+\b', case) == [CASE]
        for item in group['attachments']:
            total += 1
            require(total <= 100000 and type(item) is dict and type(item.get('exportedFileName')) is str and
                    type(item.get('suggestedHumanReadableName')) is str, 'original attachment predicate shape differs')
            filename, name = item['exportedFileName'], item['suggestedHumanReadableName']
            safe = Path(filename).name == filename
            safe_names = safe_names and safe
            if name.startswith('privacy-stages.json'):
                documents.append(json.loads((directory / filename).read_text()) if safe else None)
            recognized = False
            for stage in STAGES:
                role = 'privacy-' + stage
                form = 'bare_role' if name == role else 'exact_png' if name == role + '.png' else \
                       'underscore_prefix' if name.startswith(role + '_') else None
                if form is not None: rows[stage][form] += 1; recognized = True
                if form in ('exact_png', 'underscore_prefix'):
                    rows[stage]['eligible'] += 1
                    if safe:
                        with (directory / filename).open('rb') as file: magic = file.read(8)
                        rows[stage]['png_magic'] += int(magic == b'\x89PNG\r\n\x1a\n')
            if not recognized: other += 1
    document = documents[0] if len(documents) == 1 and type(documents[0]) is dict else None
    predicates = {'exact_stage_order': None, 'profile_uuid_format': None, 'diagnostic_flag': None, 'operation_value': None}
    if document is not None:
        predicates = {'exact_stage_order': document.get('stages') == STAGES,
            'profile_uuid_format': type(document.get('profile')) is str and
                re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', document['profile']) is not None,
            'diagnostic_flag': document.get('diagnostic_continuation') is True,
            'operation_value': document.get('operation') == 'real Remember off and Update; not a dedicated Forget action'}
    accepted = cases and safe_names and len(documents) == 1 and all(value is True for value in predicates.values()) and \
               all(row['eligible'] == row['png_magic'] == 1 for row in rows.values())
    relation = None
    if predicates['profile_uuid_format'] is True and type(checkpoints) is dict and list(checkpoints) == STAGES and all(
            type(value) is dict and type(value.get('profile_id')) is str and
            re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value['profile_id']) is not None
            for value in checkpoints.values()):
        relation = all(value['profile_id'] == document['profile'] for value in checkpoints.values())
    return {'entry_count': total, 'case_identity_matches': cases, 'all_single_filenames': safe_names,
            'stage_document_count': len(documents), 'stage_document_predicates': predicates,
            'screenshot_name_forms': rows, 'other_name_count': other, 'model_helper_accepts': accepted,
            'independent_document_profile_relation': relation, 'relation_is_original_next_predicate_execution': False,
            'arbitrary_names_profiles_or_values_printed': False}


def replay_original_attachments(folder, result, report):
    """Latch real helper outcome before any independent or later refusal."""
    proof = {'original_export_status': 'absent', 'original_helper_outcome': 'unavailable',
        'original_helper_refusal': None, 'next_profile_predicate': None, 'predicates': None,
        'original_export_replayed': False, 'source_and_import_rechecked': False,
        'fatal_refusal': False, 'native_acceptance': False, 'full_f10_accepted': False,
        'producer_export_command_succeeded': any(row == {'role': 'attachments', 'exit': 0} for row in result['commands'])}
    report['original_attachment_contract'] = proof
    directory = folder / 'attachments'
    expected = {name[len('attachments/'):]: item for name, item in result['files'].items() if name.startswith('attachments/')}
    if not expected and not directory.exists():
        require(not proof['producer_export_command_succeeded'], 'original attachment export missing')
        return True
    proof['original_export_status'] = 'invalid'
    require('manifest.json' in expected and seal_files(directory) == expected, 'original attachment bytes differ')
    before = inventory(directory); proof['original_export_status'] = 'present'
    diagnostic_stage('attachment-contract-reference')
    with tempfile.TemporaryDirectory(prefix='privacy-original-attachment-source-') as temporary:
        module = attachment_reference(temporary)
        diagnostic_stage('attachment-contract-replay')
        try:
            native_stages, unused_images = module.attachments(directory)
        except Exception as error:
            failure = refusal_report(error, 'attachment-contract-replay')
            proof.update(original_helper_outcome='refused', fatal_refusal=True,
                original_helper_refusal={key: failure[key] for key in ('exception_class', 'refusal_code')})
        else:
            proof['original_helper_outcome'] = 'passed'
            checkpoints = result['checkpoints']
            require(type(checkpoints) is dict and list(checkpoints) == STAGES and all(type(value) is dict and
                type(value.get('profile_id')) is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
                value['profile_id']) is not None for value in checkpoints.values()), 'original attachment profile shape differs')
            proof['next_profile_predicate'] = all(value['profile_id'] == native_stages['profile'] for value in checkpoints.values())
            proof['fatal_refusal'] = not proof['next_profile_predicate']
        # The proof is already the report's live partial object. An observer,
        # later parser or scan failure cannot erase the reproduced outcome.
        diagnostic_stage('attachment-contract-predicates')
        proof['predicates'] = attachment_predicates(directory, result['checkpoints'])
        require(proof['predicates']['model_helper_accepts'] == (proof['original_helper_outcome'] == 'passed'),
                'original attachment predicate contradicts helper')
        require(inventory(directory) == before and seal_files(directory) == expected and inventory(directory) == before,
                'original attachment namespace changed')
        import contract
        require(all(sha(Path(temporary) / name) == digest for name, digest in ATTACHMENT_SOURCE_HASHES.items()) and
                sha(Path(contract.__file__)) == ATTACHMENT_SOURCE_HASHES['contract.py'], 'original attachment source differs')
        proof.update(original_export_replayed=True, source_and_import_rechecked=True)
    return not proof['fatal_refusal']


def attachment_json(data):
    """Reject coercive/ambiguous JSON before any disposable metadata rewrite."""
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'candidate attachment JSON duplicate key')
            result[key] = value
        return result
    def constant(unused):
        raise RuntimeError('candidate attachment JSON nonfinite')
    def number(text):
        value = float(text)
        require(math.isfinite(value), 'candidate attachment JSON nonfinite')
        exact, emitted = Decimal(text), Decimal(json.dumps(value, allow_nan=False))
        require(exact == emitted and (not exact.is_zero() or exact.is_signed() == emitted.is_signed()),
                'candidate attachment JSON numeric loss')
        return value
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def attachment_same_value(left, right):
    """Type-exact metadata equality, including signed zero and unknown fields."""
    if type(left) is not type(right): return False
    if type(left) is dict:
        return list(left) == list(right) and all(attachment_same_value(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(attachment_same_value(a, b) for a, b in zip(left, right))
    if type(left) is float: return left.hex() == right.hex()
    return left == right


def attachment_name_category(name):
    if type(name) is not str: return 'unsupported'
    if name == 'privacy-stages.json': return 'literal'
    lower = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
    upper = r'[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}'
    if re.fullmatch(r'privacy-stages_(?:0|[1-9][0-9]{0,5})_(?:' + lower + '|' + upper + r')\.json', name):
        return 'ordinal-uuid'
    return 'unsupported' if name.startswith('privacy-stages') else 'other'


def attachment_identity_selection(directory, expected, checkpoints, proof):
    groups = attachment_json((directory / 'manifest.json').read_bytes())
    require(type(groups) is list and 0 < len(groups) <= 100000, 'candidate attachment manifest invalid')
    seen, aliases, candidates = set(), set(), []
    counts = dict.fromkeys(('literal', 'ordinal-uuid', 'unsupported', 'other'), 0)
    proof['name_categories'] = counts
    for group_index, group in enumerate(groups):
        require(type(group) is dict and type(group.get('attachments')) is list, 'candidate attachment manifest invalid')
        cases = [group[key] for key in ('testIdentifier', 'testName') if key in group]
        require(cases and all(type(case) is str and case and re.findall(r'\btest[A-Za-z0-9_]+\b', case) == [CASE]
                              for case in cases), 'candidate attachment manifest invalid')
        for entry_index, entry in enumerate(group['attachments']):
            require(type(entry) is dict and type(entry.get('exportedFileName')) is str and
                    type(entry.get('suggestedHumanReadableName')) is str, 'candidate attachment manifest invalid')
            filename = entry['exportedFileName']
            alias = unicodedata.normalize('NFC', filename).casefold()
            require(filename not in ('', '.', '..', 'manifest.json') and Path(filename).name == filename and
                    '\\' not in filename and filename not in seen and alias not in aliases and
                    filename in expected and len(seen) < 100000, 'candidate attachment manifest invalid')
            seen.add(filename); aliases.add(alias)
            category = attachment_name_category(entry['suggestedHumanReadableName'])
            counts[category] += 1
            if category in ('literal', 'ordinal-uuid'): candidates.append((group_index, entry_index, filename, category))
    require(seen == set(expected) - {'manifest.json'}, 'candidate attachment manifest invalid')
    require(counts['unsupported'] == 0, 'candidate attachment name unsupported')
    require(len(candidates) == 1, 'candidate attachment selection ambiguous')
    group_index, entry_index, filename, category = candidates[0]
    proof['selected_name_category'] = category
    require(expected[filename]['bytes'] <= 1024 * 1024, 'candidate attachment payload invalid')
    with (directory / filename).open('rb') as file: data = file.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, 'candidate attachment payload invalid')
    document = attachment_json(data)
    predicates = {'exact_keys': type(document) is dict and set(document) ==
        {'stages', 'profile', 'operation', 'diagnostic_continuation'}, 'exact_stages': False,
        'profile_uuid': False, 'exact_operation': False, 'boolean_flag': False}
    proof['payload_predicates'] = predicates
    if type(document) is dict:
        predicates.update(exact_stages=attachment_same_value(document.get('stages'), STAGES),
            profile_uuid=type(document.get('profile')) is str and
                re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', document['profile']) is not None,
            exact_operation=document.get('operation') == 'real Remember off and Update; not a dedicated Forget action',
            boolean_flag=document.get('diagnostic_continuation') is True)
    require(all(predicates.values()), 'candidate attachment payload invalid')
    require(type(checkpoints) is dict and list(checkpoints) == STAGES and all(type(value) is dict and
            type(value.get('profile_id')) is str and value['profile_id'] == document['profile']
            for value in checkpoints.values()), 'candidate attachment profile differs')
    proof['original_document_matches_checkpoints'] = True
    return groups, (group_index, entry_index), document, category


def attachment_namespace(directory):
    before = inventory(directory)
    namespace = {}
    for name in before:
        if name == '.': continue
        mode = (directory / name).lstat().st_mode
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'candidate attachment copy differs')
        namespace[name] = 'directory' if stat.S_ISDIR(mode) else 'file'
    require(inventory(directory) == before, 'candidate attachment copy differs')
    return namespace


def attachment_copy_proof(original, copied, expected, groups, position):
    """Exactly one selected semantic field; every other original byte retained."""
    group_index, entry_index = position
    transformed = copy.deepcopy(groups)
    transformed[group_index]['attachments'][entry_index]['suggestedHumanReadableName'] = 'privacy-stages.json'
    observed = attachment_json((copied / 'manifest.json').read_bytes())
    require(attachment_same_value(observed, transformed), 'candidate attachment copy differs')
    copied_files = seal_files(copied)
    require(set(copied_files) == set(expected) and
            all(copied_files[name] == item for name, item in expected.items() if name != 'manifest.json'),
            'candidate attachment copy differs')
    require(seal_files(original) == expected, 'candidate attachment original changed')
    require(attachment_namespace(copied) == attachment_namespace(original), 'candidate attachment copy differs')
    return int(groups[group_index]['attachments'][entry_index]['suggestedHumanReadableName'] != 'privacy-stages.json')


def attachment_identity_trial(folder, result, report, compared=None):
    """Candidate only; the unchanged original outcome remains independently fatal."""
    proof = {'status': 'unavailable', 'name_categories': None, 'selected_name_category': None,
        'payload_predicates': None, 'original_document_matches_checkpoints': False,
        'candidate_helper_outcome': 'unavailable', 'next_profile_predicate': None,
        'allowed_changed_field_count': None, 'original_bytes_preserved': False,
        'copy_nonmanifest_bytes_preserved': False, 'source_and_import_rechecked': False,
        'copy_namespace_preserved': False,
        'candidate_qualified': False, 'fatal_refusal': False, 'refusal': None,
        'accepted': False, 'native_acceptance': False, 'full_f10_accepted': False,
        'arbitrary_names_profiles_or_values_printed': False}
    report['attachment_identity_candidate'] = proof
    original_proof = report['original_attachment_contract']
    if original_proof['original_export_status'] == 'absent': return True
    diagnostic_stage('attachment-identity-candidate')
    try:
        proof['status'] = 'checking'
        require(original_proof['original_export_replayed'] is True and
                original_proof['source_and_import_rechecked'] is True, 'candidate attachment original proof absent')
        original = folder / 'attachments'
        expected = {name[len('attachments/'):]: item for name, item in result['files'].items() if name.startswith('attachments/')}
        before = inventory(original)
        require(seal_files(original) == expected, 'candidate attachment original changed')
        groups, position, document, category = attachment_identity_selection(original, expected, result['checkpoints'], proof)
        with tempfile.TemporaryDirectory(prefix='privacy-attachment-identity-') as temporary:
            temporary = Path(temporary); source = temporary / 'source'; source.mkdir()
            module = attachment_reference(source)
            copied = temporary / 'attachments'; shutil.copytree(original, copied)
            require(seal_files(copied) == expected, 'candidate attachment copy differs')
            transformed = copy.deepcopy(groups)
            transformed[position[0]]['attachments'][position[1]]['suggestedHumanReadableName'] = 'privacy-stages.json'
            if category != 'literal': (copied / 'manifest.json').write_text(json.dumps(transformed, ensure_ascii=True, allow_nan=False))
            proof['allowed_changed_field_count'] = attachment_copy_proof(original, copied, expected, groups, position)
            try: native_stages, images = module.attachments(copied)
            except Exception:
                proof['candidate_helper_outcome'] = 'refused'
                raise
            proof['candidate_helper_outcome'] = 'passed'
            proof['next_profile_predicate'] = all(value['profile_id'] == native_stages['profile'] for value in result['checkpoints'].values())
            require(proof['next_profile_predicate'] and attachment_same_value(native_stages, document) and
                    set(images) == set(STAGES), 'candidate attachment result differs')
            original_images = {}
            for group in groups:
                for entry in group['attachments']:
                    for stage in STAGES:
                        role, name = 'privacy-' + stage, entry['suggestedHumanReadableName']
                        if name == role + '.png' or name.startswith(role + '_'):
                            require(stage not in original_images, 'candidate attachment result differs')
                            original_images[stage] = entry['exportedFileName']
            require(set(original_images) == set(STAGES), 'candidate attachment result differs')
            for stage, image in images.items():
                require(type(image) is dict and set(image) == {'file', 'sha256'} and type(image['file']) is str and
                        image['file'] == 'attachments/' + original_images[stage] and
                        image['sha256'] == expected[original_images[stage]]['sha256'], 'candidate attachment result differs')
            require(attachment_copy_proof(original, copied, expected, groups, position) == proof['allowed_changed_field_count'],
                    'candidate attachment copy differs')
            require(inventory(original) == before and seal_files(original) == expected and inventory(original) == before,
                    'candidate attachment original changed')
            import contract
            require(all(sha(source / name) == digest for name, digest in ATTACHMENT_SOURCE_HASHES.items()) and
                    sha(Path(contract.__file__)) == ATTACHMENT_SOURCE_HASHES['contract.py'], 'original attachment source differs')
        proof.update(status='qualified', candidate_qualified=True, original_bytes_preserved=True,
            copy_nonmanifest_bytes_preserved=True, copy_namespace_preserved=True, source_and_import_rechecked=True)
        if compared is not None:
            compared.update(stages=copy.deepcopy(native_stages), images=copy.deepcopy(images))
        return True
    except Exception as error:
        refusal = refusal_report(error, 'attachment-identity-candidate')
        proof.update(status='refused', fatal_refusal=True,
            refusal={key: refusal[key] for key in ('exception_class', 'refusal_code')})
        return False


def replay_current_attachments(folder, result, report, compared):
    """Actual corrected shared helper on originals; never historical acceptance."""
    import continuation_contract as current
    proof = {'status': 'unavailable', 'helper_outcome': 'unavailable', 'next_profile_predicate': None,
        'matches_original_payload': False, 'matches_pinned_counterfactual': False,
        'matches_original_screenshots': False, 'original_bytes_preserved': False,
        'original_namespace_preserved': False, 'source_rechecked': False,
        'current_helper_verified': False, 'fatal_refusal': False, 'refusal': None,
        'accepted': False, 'native_acceptance': False, 'full_f10_accepted': False,
        'arbitrary_names_profiles_or_values_printed': False}
    report['current_attachment_helper'] = proof
    if report['original_attachment_contract']['original_export_status'] == 'absent': return True
    diagnostic_stage('attachment-current-replay')
    try:
        proof['status'] = 'checking'
        require(report['attachment_identity_candidate']['candidate_qualified'] is True and
                type(compared) is dict and set(compared) == {'stages', 'images'}, 'current attachment candidate unqualified')
        source = ROOT / 'tests/apple_password_privacy_20261028/continuation_contract.py'
        require(Path(current.__file__).resolve() == source.resolve() and sha(source) == CURRENT_ATTACHMENT_SOURCE_SHA,
                'current attachment source differs')
        original = folder / 'attachments'; before = inventory(original)
        expected = {name[len('attachments/'):]: item for name, item in result['files'].items() if name.startswith('attachments/')}
        require(seal_files(original) == expected, 'current attachment file changed')
        selection = {}
        groups, position, document, unused = attachment_identity_selection(original, expected, result['checkpoints'], selection)
        try: stages, images = current.attachments(original)
        except Exception:
            proof['helper_outcome'] = 'refused'
            raise
        proof['helper_outcome'] = 'passed'
        proof['next_profile_predicate'] = all(value['profile_id'] == stages['profile'] for value in result['checkpoints'].values())
        require(proof['next_profile_predicate'], 'current attachment profile differs')
        proof['matches_original_payload'] = attachment_same_value(stages, document)
        proof['matches_pinned_counterfactual'] = attachment_same_value(stages, compared['stages']) and attachment_same_value(images, compared['images'])
        require(proof['matches_original_payload'] and proof['matches_pinned_counterfactual'] and
                set(images) == set(STAGES), 'current attachment result differs')
        original_images = {}
        for group in groups:
            for entry in group['attachments']:
                for stage in STAGES:
                    role, name = 'privacy-' + stage, entry['suggestedHumanReadableName']
                    if name == role + '.png' or name.startswith(role + '_'):
                        require(stage not in original_images, 'current attachment result differs')
                        filename = entry['exportedFileName']
                        original_images[stage] = {'file': 'attachments/' + filename, 'sha256': expected[filename]['sha256']}
        proof['matches_original_screenshots'] = attachment_same_value(images, original_images)
        require(proof['matches_original_screenshots'], 'current attachment result differs')
        require(inventory(original) == before and seal_files(original) == expected and inventory(original) == before,
                'current attachment namespace changed')
        require(sha(source) == CURRENT_ATTACHMENT_SOURCE_SHA, 'current attachment source differs')
        proof.update(status='verified', current_helper_verified=True, original_bytes_preserved=True,
            original_namespace_preserved=True, source_rechecked=True)
        return True
    except Exception as error:
        refusal = refusal_report(error, 'attachment-current-replay')
        proof.update(status='refused', fatal_refusal=True,
            refusal={key: refusal[key] for key in ('exception_class', 'refusal_code')})
        return False


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
    attachment_contract_ok = replay_original_attachments(folder, result, report)
    compared = {}
    attachment_candidate_ok = attachment_identity_trial(folder, result, report, compared)
    attachment_current_ok = replay_current_attachments(folder, result, report, compared)
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
    diagnostic_stage('attachment-contract-final')
    require(attachment_contract_ok, 'original attachment contract refused')
    require(attachment_candidate_ok, 'candidate attachment replay refused')
    require(attachment_current_ok, 'current attachment replay refused')
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


def current_progress(result, files, platform):
    """Current-only producer scope; historical failed-progress defaults stay exact."""
    require(platform in CURRENT_CASE_ARTIFACTS and
            (result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
            (CURRENT_CASE_SOURCE, CURRENT_CASE_RUN, '1', platform), 'current diagnostic identity differs')
    require(result['accepted'] is False and result['diagnostic_only'] is True and
            result['full_f10_accepted'] is False, 'current diagnostic verdict differs')
    checks, checkpoints = result['strict_privacy_checks'], result['checkpoints']
    require(type(checkpoints) is dict and list(checkpoints) == STAGES[:len(checkpoints)] and
            type(checks) is dict and list(checks) == STAGES[:len(checks)] and set(checkpoints) <= set(checks) and
            all(type(value) is bool for value in checks.values()), 'current diagnostic checkpoint differs')
    checkpoint_keys = {'profile_id', 'network_requests', 'scans', 'strict_privacy_passed',
        'absent_mac_roots', 'archive', 'archive_sha256', 'sdk_original_sha256', 'original_bytes'}
    for stage, row in checkpoints.items():
        require(type(row) is dict and set(row) == checkpoint_keys and
                type(row['profile_id']) is str and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', row['profile_id']) and
                type(row['network_requests']) is int and 0 <= row['network_requests'] <= 100000 and
                type(row['scans']) is dict and type(row['absent_mac_roots']) is list and
                all(type(value) is str for value in row['absent_mac_roots']) and
                type(row['strict_privacy_passed']) is bool and row['strict_privacy_passed'] is checks[stage] and
                row['archive'] == stage + '-product.zip' and row['archive'] in files and
                all(type(row[key]) is str and re.fullmatch(r'[0-9a-f]{64}', row[key]) for key in ('archive_sha256', 'sdk_original_sha256')) and
                type(row['original_bytes']) is int and 0 < row['original_bytes'] <= 8 * 1024 ** 3,
                'current diagnostic checkpoint differs')
    commands = result['commands']
    require(type(commands) is list and len(commands) <= len(ROLES | ADMISSION_COMMAND_ROLES) and
            all(type(row) is dict and set(row) == {'role', 'exit'} and type(row['role']) is str and
                row['role'] in ROLES | ADMISSION_COMMAND_ROLES and type(row['exit']) is int and
                -128 <= row['exit'] <= 255 for row in commands) and
            len({row['role'] for row in commands}) == len(commands), 'current diagnostic command differs')
    by_role = {row['role']: row['exit'] for row in commands}
    if platform == 'macos':
        required = {'fixtures', 'project', 'build-for-testing', 'native', 'attachments', 'program-archive'}
        require(result['sequence_complete'] is True and result['failure'] is None and
                list(checkpoints) == STAGES and set(by_role) == required and all(value == 0 for value in by_role.values()) and
                'program.zip' in files, 'current macOS producer completion differs')
    else:
        require(result['sequence_complete'] is False and type(result['failure']) is str and
                result['failure'] in FAILURES, 'current iOS failed progress differs')
    return {'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False,
        'sequence_complete': result['sequence_complete'], 'failure_class': result['failure'],
        'strict_privacy_checks': dict(checks),
        'completed_checkpoints': list(checkpoints),
        'snapshot_archives_present': {stage: stage + '-product.zip' in files for stage in STAGES},
        'commands': commands, 'native_command_observed': 'native' in by_role,
        'native_command_exit': by_role.get('native'),
        'nonzero_command_exits': [row for row in commands if row['exit'] != 0],
        'scope': 'producer-completion-only' if platform == 'macos' else 'failed-producer-progress-only',
        'program_archive_present': 'program.zip' in files,
        'provider_map_present': 'EXReaderHost.link.map' in files,
        'sdk_identity_present': 'sdk-identity.json' in files,
        'full_validate_executed': False, 'full_program_signature_credit': False,
        'native_acceptance': False}


def replay_current_ui(folder, result, report):
    diagnostic_stage('current-ui-replay')
    replayed = parse_ui_observations(folder / 'native.log')
    require(attachment_same_value(replayed, result['ui_state_observations']), 'current UI replay differs')
    report['independent_ui_observations'] = replayed
    report['ui_observations_match_producer'] = True


def current_ancillary(folder, files, result, report, platform):
    """Same later predicates as historical diagnosis; none is an acceptance waiver."""
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
        report['retained_metadata_classification'] = admission_metadata(folder, source=CURRENT_CASE_SOURCE, run=CURRENT_CASE_RUN)
        report['independent_ios_admission_replay'] = verify_ios_admission(folder, CURRENT_CASE_SOURCE, result, require_program=False)


def published_root_files(directory):
    """Read-only two-pass replay of ALREADY published evidence, including result.

    The producer's seal_files precondition intentionally forbids result.json.
    Do not weaken it, delete that original, or mistake this reader for a sealer.
    """
    try:
        def snapshot():
            files, directories = lifecycle_reader._inventory(directory)
            require('result.json' in files and '.result-pending' not in files and
                    '.result-pending' not in directories and all(value[6] == 1 for value in files.values()),
                    'current original evidence changed')
            return files, directories
        before = snapshot()
        first = {name: lifecycle_reader._record(directory / name, value) for name, value in before[0].items()}
        require(snapshot() == before, 'current original evidence changed')
        second = {name: lifecycle_reader._record(directory / name, value) for name, value in before[0].items()}
        require(first == second and snapshot() == before, 'current original evidence changed')
        return second
    except Exception:
        # Do not expose path/OS operands; the caller retains prior finite data.
        raise RuntimeError('current original evidence changed') from None


def diagnose_current_platform(out, platform, identifier, size, digest):
    global CURRENT_MEMBER_INTEGRITY, CURRENT_PLATFORM, CURRENT_SAFE_REPORT
    CURRENT_PLATFORM, CURRENT_MEMBER_INTEGRITY, CURRENT_SAFE_REPORT = platform, None, None
    diagnostic_stage('artifact-metadata')
    endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(identifier)
    record = json.loads(subprocess.check_output(['gh', 'api', endpoint], timeout=30))
    require(record['id'] == identifier and record['name'] == 'password-continuation-native-' + platform + '-' + CURRENT_CASE_RUN + '-1' and
            str(record['workflow_run']['id']) == CURRENT_CASE_RUN and record['workflow_run']['head_sha'] == CURRENT_CASE_SOURCE and
            record['digest'] == 'sha256:' + digest and record['size_in_bytes'] == size and
            record['expired'] is False, 'prior continuation artifact identity differs')
    original = out / (platform + '-original.zip')
    diagnostic_stage('artifact-download')
    with original.open('wb') as file: subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=file, check=True, timeout=120)
    diagnostic_stage('archive-bytes')
    require(original.stat().st_size == size and sha(original) == digest, 'prior original ZIP differs')
    diagnostic_stage('archive-extract')
    folder = out / platform; safe_extract(original, folder)
    diagnostic_stage('result-identity')
    result = json.loads((folder / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
            (CURRENT_CASE_SOURCE, CURRENT_CASE_RUN, '1', platform), 'current diagnostic identity differs')
    diagnostic_stage('member-inventory')
    namespace = attachment_namespace(folder)
    files = {name for name, kind in namespace.items() if kind == 'file'}
    require(files == set(result['files']) | {'result.json'}, 'prior continuation inventory differs')
    diagnostic_stage('member-bytes')
    CURRENT_MEMBER_INTEGRITY = member_integrity(folder, result['files'])
    require(CURRENT_MEMBER_INTEGRITY['mismatch_count'] == 0, 'prior continuation member differs')
    original_files = dict(result['files'], **{'result.json': {'bytes': (folder / 'result.json').stat().st_size,
                                                           'sha256': sha(folder / 'result.json')}})
    diagnostic_stage('lifecycle-receipt')
    lifecycle = sealed_lifecycle(result, platform)
    diagnostic_stage('progress-and-native-log')
    report = current_progress(result, files, platform)
    CURRENT_SAFE_REPORT = report
    report.update(old_source_sha=CURRENT_CASE_SOURCE, old_run_id=CURRENT_CASE_RUN, old_attempt=1,
        platform=platform, artifact_id=identifier, original_bytes=size, original_sha256=digest,
        verified_member_count=len(files), arbitrary_log_text_printed=False,
        source_positions_not_authenticated_callsites=True, member_integrity=CURRENT_MEMBER_INTEGRITY,
        producer_lifecycle_receipt=lifecycle, producer_receipt_is_event_trace_proof=False,
        original_namespace_and_bytes_preserved=False)
    try:
        report['native_failure_locations'] = locations(folder / 'native.log') if 'native.log' in files else []
        report['activity_timing'] = activity_timing(folder / 'native.log')
        replay_current_ui(folder, result, report)
        inspect_native_result(folder, files, report)
        current_ancillary(folder, files, result, report, platform)
    finally:
        # Also recheck on refusal, without erasing the earlier finite outcome.
        earlier_stage = CURRENT_DIAGNOSTIC_STAGE
        diagnostic_stage('current-original-recheck')
        require(attachment_namespace(folder) == namespace and published_root_files(folder) == original_files and
                original.stat().st_size == size and sha(original) == digest, 'current original evidence changed')
        report['original_namespace_and_bytes_preserved'] = True
        diagnostic_stage(earlier_stage)
    diagnostic_stage('safe-report')
    return report


def run_current_platforms(out, diagnoser=diagnose_current_platform):
    global CURRENT_MEMBER_INTEGRITY, CURRENT_PLATFORM, CURRENT_SAFE_REPORT
    failed = False
    for platform, (identifier, size, digest) in CURRENT_CASE_ARTIFACTS.items():
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


def current_main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    diagnostic_stage('scope-and-source')
    guard()
    endpoint = 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/contents/' + SOURCE_FILE + '?ref=' + CURRENT_CASE_SOURCE
    source_record = json.loads(subprocess.check_output(['gh', 'api', endpoint], timeout=30))
    verify_frozen_ui_source(source_record)
    require(set(CURRENT_CASE_ARTIFACTS) == {'macos', 'iphone', 'ipad'}, 'exact three-platform diagnostic artifact pins required')
    out = ROOT / 'build/apple-password-continuation-diagnostic'; out.mkdir(parents=True, exist_ok=False)
    return run_current_platforms(out)


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
        if not current_main(): raise SystemExit(1)
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
