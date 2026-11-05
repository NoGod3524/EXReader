#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One Actions-only, read-only extraction of an authenticated old xcresult.

No build, simulator, UI, fixture generation or downloaded executable is invoked.
The failed producer remains failed; missing installed identity stays missing.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/ios-activation-original-artifact-extraction'
REPO = 'NoGod3524/EXReader'
SOURCE = '6a6615373474d993ba02f651325fb7c5d3ccbed0'
RUN, ATTEMPT, JOB = 40823753931, 1, 123281953805
ARTIFACT = 12876715734
ARTIFACT_NAME = 'ios-organization-activation-probe-40823753931-1'
ZIP_BYTES = 160592575
ZIP_SHA = '3547088a598c9a15be1b4923cc16d676770fcdeafe75d271654fb5919da33e64'
BRANCH = 'codex/apple-ios-organization-activation-artifact-audit-20261029'
PATHS = ['.github/workflows/apple-ios-organization-activation-artifact-audit-20261029.yml',
         'tests/apple_ios_organization_activation_artifact_audit_20261029.py']
PACKAGE = 'tests/apple_ios_organization_activation_probe_20261029/'
PACKAGE_HASHES = {
    '.github/workflows/apple-ios-organization-activation-probe-20261029.yml': 'c92caab802f946a6f4ddb8f5350b461aa997b142aeeee2e9c71260fedfcbca26',
    PACKAGE + 'prepare.py': 'f86ac81d320927424f6c458bb158f1f98b91489801f4b8d05e62c9410ccbaa48',
    PACKAGE + 'ActivationProbeTests.swift': 'e68e978af2be547dde9fbe321738e486f5576d7fdff02aa5d9476dab62723fd8',
    PACKAGE + 'collect.py': 'f0a8fd7bc9ef4b4ca561a7ec806d3d485275adea84a4d7371e3f45671b4a0edd',
    PACKAGE + 'README.md': '872ac06bfaab0f096608bd3c207ed46dbd85d8aca1adaed322e73e43fbf4a93d'}
RAW_LIMIT, ATTACH_LIMIT = 64 * 1024 ** 2, 512 * 1024 ** 2
DEADLINE = time.monotonic() + 720
COMMANDS = []


def require(value, message):
    if not value:
        raise ValueError(message)


def check_time():
    require(time.monotonic() < DEADLINE, '12-minute reader deadline exhausted')


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n')


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 ** 2), b''):
            check_time()
            checksum.update(chunk)
    return checksum.hexdigest()


def directory_size(path):
    total = 0
    count = 0
    if path.exists():
        for item in path.rglob('*'):
            check_time()
            require(not item.is_symlink(), 'derived output symlink refused')
            count += 1
            require(count <= 20000, 'derived output entry limit exceeded')
            if item.is_file():
                total += item.stat().st_size
    return total


def command(argv, name, limit=RAW_LIMIT, output=None, attachment_dir=None):
    """Fixed source-built argv only; bounded files survive error/timeout."""
    check_time()
    argv = list(map(str, argv))
    stdout = output or OUT / (name + '.stdout')
    stderr = OUT / (name + '.stderr')
    started = time.monotonic()
    record = {'argv': argv, 'stdout': str(stdout), 'stderr': str(stderr), 'started': started}
    COMMANDS.append(record)
    save('commands.json', COMMANDS)
    try:
        with stdout.open('wb') as out, stderr.open('wb') as err:
            def file_ceiling():
                resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
            child = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err,
                                     start_new_session=True, preexec_fn=file_ceiling)
            try:
                while True:
                    check_time()
                    require(time.monotonic() - started < 180, 'fixed parser/command exceeded 180 seconds')
                    require(stdout.stat().st_size <= limit and stderr.stat().st_size <= RAW_LIMIT, 'command output ceiling exceeded')
                    if attachment_dir is not None:
                        require(directory_size(attachment_dir) <= ATTACH_LIMIT, '512MiB derived attachment ceiling exceeded')
                    status = child.poll()
                    if status is not None:
                        record['exit_code'] = status
                        require(stdout.stat().st_size <= limit and stderr.stat().st_size <= RAW_LIMIT,
                                'completed command output ceiling exceeded')
                        if attachment_dir is not None:
                            require(directory_size(attachment_dir) <= ATTACH_LIMIT, 'completed attachment ceiling exceeded')
                        require(status == 0, 'fixed command failed: ' + name + ' exit=' + str(status))
                        break
                    time.sleep(0.2)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        return stdout
    except Exception as error:
        record['refusal'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        record['finished'] = time.monotonic()
        record['stdout_bytes'] = stdout.stat().st_size if stdout.exists() else 0
        record['stderr_bytes'] = stderr.stat().st_size if stderr.exists() else 0
        save('commands.json', COMMANDS)


def text_command(argv, name):
    return command(argv, name).read_text().strip()


def api(endpoint, name):
    return json.loads(text_command(['gh', 'api', 'repos/' + REPO + '/' + endpoint], name))


def canonical(value):
    return unicodedata.normalize('NFC', value).casefold()


def safe_zip(archive):
    """Admit all names before writing; include implicit-directory aliases."""
    entries = archive.infolist()
    require(len(entries) <= 20000 and sum(i.file_size for i in entries) <= 2 * 1024 ** 3,
            'ZIP exceeds 20000-entry/2GiB bound')
    seen, explicit = {}, set()
    for item in entries:
        check_time()
        name = item.filename
        require(name == item.orig_filename and name and '\\' not in name and '\x00' not in name,
                'invalid ZIP name')
        directory = item.is_dir()
        parts = (name[:-1] if directory else name).split('/')
        require(all(p not in ('', '.', '..') and ':' not in p for p in parts), 'unsafe ZIP path')
        mode = stat.S_IFMT(item.external_attr >> 16)
        require(mode in (0, stat.S_IFDIR if directory else stat.S_IFREG), 'ZIP link/special file/type mismatch')
        key = canonical('/'.join(parts))
        require(key not in explicit, 'duplicate/aliased ZIP member')
        explicit.add(key)
        for index in range(1, len(parts) + 1):
            spelling = '/'.join(parts[:index])
            kind = 'directory' if index < len(parts) or directory else 'file'
            normalized = canonical(spelling)
            if normalized in seen:
                require(seen[normalized] == (spelling, kind), 'case/Unicode/file-directory ZIP alias')
            else:
                seen[normalized] = (spelling, kind)
    return entries


def extract(archive, folder):
    entries = safe_zip(archive)
    folder.mkdir(mode=0o700)
    for item in entries:
        check_time()
        target = folder / item.filename
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with archive.open(item) as source, target.open('xb') as dest:
            for chunk in iter(lambda: source.read(1024 ** 2), b''):
                check_time()
                size += len(chunk)
                require(size <= item.file_size, 'ZIP stream exceeds declared size')
                dest.write(chunk)
        require(size == item.file_size, 'ZIP stream size differs')


def inventory(folder):
    require(folder.is_dir(), 'required directory missing: ' + folder.name)
    result = {}
    for path in sorted(folder.rglob('*')):
        check_time()
        require(not path.is_symlink(), 'inventory symlink refused')
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = digest(path)
    require(result, 'empty inventory')
    return result


def admit_source(summary):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'macOS Actions only')
    require(os.environ['GITHUB_REPOSITORY'] == REPO and os.environ['GITHUB_RUN_ATTEMPT'] == '1'
            and os.environ['GITHUB_REF_NAME'] == BRANCH, 'wrong reader repository/attempt/branch')
    head = text_command(['git', 'rev-parse', 'HEAD'], 'reader-head')
    require(head == os.environ['GITHUB_SHA'], 'reader HEAD differs')
    delta = text_command(['git', 'diff', '--name-status', SOURCE, head], 'reader-delta').splitlines()
    require(sorted(delta) == sorted('A\t' + p for p in PATHS), 'reader must be exactly two additions')
    for path, expected in PACKAGE_HASHES.items():
        require(digest(ROOT / path) == expected, 'frozen diagnostic source differs: ' + path)
    # Imports define validators only. Their collect/audit/build entry points are never called.
    sys.path.insert(0, str(ROOT / PACKAGE))
    import collect as probe
    original_delta = text_command(['git', 'diff', '--name-status', probe.BASE, SOURCE], 'producer-delta').splitlines()
    require(sorted(original_delta) == sorted('A\t' + p for p in probe.PATHS), 'producer five-path admission differs')
    summary['reader_paths'] = {p: digest(ROOT / p) for p in PATHS}
    summary['source_admitted'] = True
    return probe


def authenticate(summary, target):
    run = api(f'actions/runs/{RUN}', 'producer-run')
    job = api(f'actions/jobs/{JOB}', 'producer-job')
    artifact = api(f'actions/artifacts/{ARTIFACT}', 'producer-artifact')
    require(run['id'] == RUN and run['run_attempt'] == ATTEMPT and run['head_sha'] == SOURCE
            and run['status'] == 'completed' and run['conclusion'] == 'failure'
            and run['path'] == '.github/workflows/apple-ios-organization-activation-probe-20261029.yml', 'producer run differs')
    require(job['id'] == JOB and job['run_id'] == RUN and job['run_attempt'] == ATTEMPT
            and job['head_sha'] == SOURCE and job['conclusion'] == 'failure'
            and job['name'] == 'iPhone organization activation diagnostic', 'producer job differs')
    require(artifact['id'] == ARTIFACT and artifact['name'] == ARTIFACT_NAME and not artifact['expired']
            and artifact['size_in_bytes'] == ZIP_BYTES and artifact['digest'] == 'sha256:' + ZIP_SHA
            and artifact['workflow_run']['id'] == RUN and artifact['workflow_run']['head_sha'] == SOURCE, 'artifact metadata differs')
    command(['gh', 'api', f'repos/{REPO}/actions/artifacts/{ARTIFACT}/zip'], 'original-zip-download', ZIP_BYTES, target)
    require(target.stat().st_size == ZIP_BYTES and digest(target) == ZIP_SHA, 'original ZIP size/SHA differs')
    summary['original_zip_authenticated'] = True
    summary['input'] = {'source_sha': SOURCE, 'run_id': RUN, 'attempt': ATTEMPT, 'job_id': JOB,
                        'artifact_id': ARTIFACT, 'name': ARTIFACT_NAME, 'bytes': ZIP_BYTES, 'sha256': ZIP_SHA}


def original_identity(evidence, probe, summary):
    old = json.loads((evidence / 'diagnostic.json').read_text())
    guard = json.loads((evidence / 'source-guard.json').read_text())
    for report in (old, guard):
        require(report['source_sha'] == SOURCE and str(report['run_id']) == str(RUN)
                and str(report['attempt']) == str(ATTEMPT) and report['frozen_product_source'] == probe.BASE
                and report['sdk_version'] == '3.42.0' and report['product_accepted'] is False
                and report['formal_credit'] == 0, 'original source/scope identity differs')
    require(old['collection_complete'] is False and old['problems'], 'original failure must remain visible')
    require(guard['package_files'] == PACKAGE_HASHES and guard['changed_paths'] == sorted(probe.PATHS)
            and guard['selected_cases'] == list(probe.CASES) and guard['all_existing_blobs_unchanged'] is True
            and guard['formal_reconstruction_equal'] is True and guard['formal_ui_sha256'] == probe.FORMAL_HASH, 'original source guard differs')
    sdk = guard['sdk_package_identity']
    require((sdk['source_sha'], str(sdk['run_id']), str(sdk['attempt']), sdk['product']['sdk_version']) ==
            (SOURCE, str(RUN), str(ATTEMPT), '3.42.0'), 'original SDK package identity differs')
    dest = (evidence / 'destination.txt').read_text().splitlines()
    require(dest == ['platform=iOS Simulator,id=48B2DA2E-AF18-4E36-BB25-B25969A4EBCF',
            '48B2DA2E-AF18-4E36-BB25-B25969A4EBCF', 'iPhone SE (3rd generation)',
            'com.apple.CoreSimulator.SimRuntime.iOS-26-2'], 'recorded destination differs')
    summary['selected_destination'] = dest
    summary['original_collection_problems'] = old['problems']
    installed_names = ['EXReaderHost-installed.zip', 'installed-app-identity.json']
    summary['installed_evidence_presence'] = {n: (evidence / n).exists() for n in installed_names}
    require(not any(summary['installed_evidence_presence'].values()) and not old.get('installed_app_verified', False),
            'unexpected installed evidence requires a separate review, not substitution')
    return old, guard


def verify_built(evidence, old, guard, summary):
    path = evidence / 'EXReaderHost.zip'
    require(digest(path) == old['retained']['EXReaderHost.zip'], 'retained built ZIP differs')
    with zipfile.ZipFile(path) as archive:
        safe_zip(archive)
        prefix = 'EXReaderHost.app/'
        info = plistlib.loads(archive.read(prefix + 'Info.plist'))
        require(info['EXRSourceSHA'] == SOURCE and info['EXRSDKVersion'] == '3.42.0'
                and info['EXRPageThemeEnabled'] is True, 'built-only app identity differs')
        components = dict(guard['fixtures'], **{'EXReaderHost': old['executable_sha256'],
                           'Frameworks/libexreader.3.42.0.dylib': old['runtime_sha256']})
        for name, expected in components.items():
            check_time()
            require(hashlib.sha256(archive.read(prefix + name)).hexdigest() == expected, 'built-only component differs: ' + name)
    summary['built_only_components_verified'] = components
    summary['built_bytes_are_not_installed_identity'] = True


def observations(folder, probe, cases, summary):
    manifest = json.loads((folder / 'manifest.json').read_text())
    receipts, seen, filenames, retained = {}, set(), set(), {}
    for group in manifest:
        case = probe.owner(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            check_time()
            role = probe.attachment_role(item['suggestedHumanReadableName'])
            if role is None:
                continue
            filename = item['exportedFileName']
            require(filename and '/' not in filename and '\\' not in filename and filename not in ('.', '..')
                    and (case, role) not in seen and canonical(filename) not in filenames, 'unsafe/duplicate attachment')
            path = folder / filename
            require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 16 * 1024 ** 2, 'attachment size/type differs')
            raw = path.read_bytes()
            if role == 'receipt':
                receipts[case] = json.loads(raw)
            elif role.endswith('screen'):
                require(raw[:8] == b'\x89PNG\r\n\x1a\n', 'phase screenshot is not PNG')
            elif role.endswith('tree'):
                require('Application' in raw.decode(), 'native tree missing')
            elif role == 'frozen_steps':
                require(probe.owner(json.loads(raw)['test']) == case, 'frozen teardown identity differs')
            seen.add((case, role))
            filenames.add(canonical(filename))
            retained[filename] = {'case': case, 'role': role, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            save('original-receipts.json', receipts)
            save('attachment-identity.json', retained)
    save('original-receipts.json', receipts)
    save('attachment-identity.json', retained)
    probe.validate_roles(seen, receipts)
    report = {'product_accepted': False, 'formal_credit': 0, 'physical_device_execution': False,
              'frozen_product_source': probe.BASE, 'sdk_version': '3.42.0', 'cases': cases, 'receipts': receipts}
    probe.validate_report(report)
    trials = []
    for case, arm in probe.CASES.items():
        receipt = receipts[case]
        native = next(c['result'] for c in cases if c['name'] == case)
        require(receipt['freshness_proved'] is True, 'fresh trial proof incomplete')
        if arm == 'return':
            require(native == 'Failed' and receipt['outcome'] == 'inapplicable_keyboard'
                    and receipt['keyboard_applicable'] is False and receipt['native_tap_calls'] == receipt['return_tap_calls'] == 0
                    and [s['phase'] for s in receipt['trace']] == ['pre-intervention', 'post-intervention']
                    and receipt['trace'][0]['keyboard_count'] != 1, 'original inapplicable Return evidence differs')
        else:
            require(native == 'Passed' and receipt['outcome'] == 'verification_completed', 'original control result differs')
        trials.append({'case': case, 'arm': arm, 'native': native, 'outcome': receipt['outcome'],
                       'native_tap_calls': receipt['native_tap_calls'], 'return_tap_calls': receipt['return_tap_calls'],
                       'freshness_proved': receipt['freshness_proved'], 'observed_order': receipt['observed_order'],
                       'trace': receipt['trace']})
    summary['trials'] = trials
    summary['native_observation_extraction_complete'] = True


def device_metadata(value, path='$'):
    """Retain recorded fields, not an inference about selected vs XCTest clone."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = path + '.' + key
            if 'device' in key.lower() or key == 'runDestinations':
                found.append({'json_path': child, 'recorded_value': item})
            else:
                found.extend(device_metadata(item, child))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(device_metadata(item, path + '[' + str(i) + ']'))
    return found


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    summary = {'reader_source_sha': os.environ.get('GITHUB_SHA'), 'reader_run_id': os.environ.get('GITHUB_RUN_ID'),
        'reader_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'original_workflow_conclusion': 'failure',
        'original_diagnostic_chain_complete': False, 'installed_app_identity_verified': False,
        'actual_execution_device_verified': False, 'product_accepted': False, 'formal_credit': 0,
        'root_cause_proved': False, 'native_observation_extraction_complete': False, 'reader_complete': False, 'problems': []}
    def stage(name, operation):
        try:
            value = operation()
            summary[name] = 'passed'
            return value
        except Exception as error:
            summary[name] = 'failed'
            summary['problems'].append(name + ': ' + type(error).__name__ + ': ' + str(error))
            return None
        finally:
            save('summary.json', summary)
    try:
        probe = admit_source(summary)
        with tempfile.TemporaryDirectory(prefix='exr-original-artifact-') as temporary:
            temporary = Path(temporary)
            archive_path = temporary / 'original.zip'
            authenticate(summary, archive_path)
            evidence = temporary / 'original'
            with zipfile.ZipFile(archive_path) as archive:
                extract(archive, evidence)
            original_inventory = inventory(evidence)
            save('original-archive-inventory.json', original_inventory)
            for name in ('diagnostic.json', 'source-guard.json', 'destination.txt'):
                shutil.copy2(evidence / name, OUT / ('original-' + name))
            old, guard = original_identity(evidence, probe, summary)
            bundle = evidence / 'activation.xcresult'
            before = inventory(bundle)
            save('pre-parse-xcresult-inventory.json', before)
            summary['pre_parse_xcresult_sha256'] = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            stage('reader_xcode_identity', lambda: text_command(['xcodebuild', '-version'], 'reader-xcode-version'))
            raw_tests = stage('native_tests_export', lambda: command(['xcrun', 'xcresulttool', 'get', 'test-results',
                'tests', '--path', bundle, '--format', 'json'], 'native-tests'))
            cases = stage('native_tests_parse', lambda: probe.native_results(raw_tests.read_bytes())) if raw_tests else None
            if cases is not None:
                summary['cases'] = cases
            attachments = OUT / 'attachments'
            exported = stage('attachments_export', lambda: command(['xcrun', 'xcresulttool', 'export', 'attachments',
                '--path', bundle, '--output-path', attachments], 'attachments-export', attachment_dir=attachments))
            if exported is not None and cases is not None:
                stage('original_observations', lambda: observations(attachments, probe, cases, summary))
            raw_summary = stage('native_summary_export', lambda: command(['xcrun', 'xcresulttool', 'get', 'test-results',
                'summary', '--path', bundle, '--format', 'json'], 'native-summary'))
            if raw_summary is not None:
                metadata = stage('device_metadata_parse', lambda: device_metadata(json.loads(raw_summary.read_bytes())))
                summary['recorded_device_metadata'] = metadata
                summary['device_binding_note'] = 'Raw recorded fields only; selected destination is not presumed to be the executed XCTest clone.'
            def generated():
                def bounded_plutil(*argv):
                    require(list(map(str, argv[:5])) == ['plutil', '-convert', 'xml1', '-o', '-']
                            and Path(argv[5]) == evidence / 'generated/project/EXReaderHost.xcodeproj/project.pbxproj'
                            and len(argv) == 6, 'unexpected generated-source parser command')
                    return text_command(argv, 'generated-pbx-plutil')
                probe.command = bounded_plutil
                summary['generated_wiring'] = probe.verify_generated(evidence, guard)
            stage('generated_source_verification', generated)
            stage('built_only_verification', lambda: verify_built(evidence, old, guard, summary))
            def unchanged_bundle():
                require(inventory(bundle) == before, 'native parser mutated original extracted xcresult')
            stage('post_parse_xcresult_identity', unchanged_bundle)
            summary['reader_complete'] = summary['native_observation_extraction_complete'] and not summary['problems']
    except Exception as error:
        summary['problems'].append(type(error).__name__ + ': ' + str(error))
    finally:
        save('summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary['reader_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
