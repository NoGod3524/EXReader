# SPDX-License-Identifier: MIT
"""Small strict verifier shared by live collector and rejection regressions."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile
from contract import CASES, PROCESS_CASES, UNAVAILABLE

LIMIT = 64 * 1024 * 1024


class EvidenceError(Exception):
    pass


def need(value, reason):
    if not value:
        raise EvidenceError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decoded(data):
    def pairs(rows):
        value = {}
        for key, item in rows:
            need(key not in value, 'duplicate_json_key'); value[key] = item
        return value
    def constant(_):
        raise EvidenceError('nonfinite_json')
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise EvidenceError('invalid_json') from None
    need(type(value) is dict, 'json_root'); return value


def unique(rows, field):
    values = [row.get(field) for row in rows]
    need(len(values) == len(set(values)) and None not in values, 'duplicate_' + field)


def selected(rows, name):
    found = [row for row in rows if row.get('name') == name]
    need(len(found) == 1, 'missing_or_duplicate_named_evidence'); return found[0]


def unpack(data):
    need(type(data) is bytes and 0 < len(data) <= LIMIT, 'archive_size')
    files = {}; total = 0; names = set()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            need(0 < len(archive.infolist()) <= 512, 'archive_count')
            for info in archive.infolist():
                name = info.filename.rstrip('/') if info.is_dir() else info.filename
                path = PurePosixPath(name)
                need(name and not path.is_absolute() and '..' not in path.parts and str(path) == name
                     and '\\' not in name and ':' not in name and '\0' not in name, 'archive_path')
                need(name.casefold() not in names, 'duplicate_archive_member'); names.add(name.casefold())
                need(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR)
                     and not info.flag_bits & 1, 'archive_special')
                total += info.file_size; need(total <= LIMIT * 2, 'archive_expanded')
                if not info.is_dir(): files[name] = archive.read(info)
    except zipfile.BadZipFile:
        raise EvidenceError('archive_format') from None
    return files


def runtime_identity(raw, report, files):
    for key in ('source_sha', 'run_id', 'run_attempt', 'module_version', 'api'):
        need(raw.get(key) == report.get(key), 'runtime_' + key)
    apk = files['consumer/probe-debug.apk']; aar = files['stage/exreader-android-display-0.1.0.aar']
    need(raw.get('installed_apk_sha256') == digest(apk) and raw.get('apk_bytes') == len(apk), 'runtime_apk')
    need(raw.get('aar_sha256') == digest(aar), 'runtime_aar')


def verify_files(files, sha, run_id, attempt, module_tree):
    required = {'evidence/report.json', 'evidence/suite.json', 'evidence/process-seed.json',
                'evidence/process-reopen.json', 'consumer/probe-debug.apk', 'consumer/installed.apk',
                'stage/exreader-android-display-0.1.0.aar', 'stage/classes.jar', 'stage/README.md',
                'logs/instrumentation.stdout', 'logs/apk-manifest.stdout', 'logs/apk-dex.stdout',
                'logs/pid-before.stdout', 'logs/pid-after-stop.stdout', 'logs/pid-reopen.stdout'}
    need(required <= set(files), 'required_files')
    report = decoded(files['evidence/report.json'])
    need(report.get('schema') == 1 and report.get('module') == 'EXReaderAndroidDisplay'
         and report.get('module_version') == '0.1.0' and report.get('accepted') is True, 'report_contract')
    need(report.get('source_sha') == sha and report.get('run_id') == str(run_id)
         and report.get('run_attempt') == str(attempt) and report.get('job') == 'android', 'report_origin')
    need(report.get('source_module_tree') == module_tree, 'original_module_tree')
    need(report.get('api') == 34 and report.get('abi') == 'x86_64', 'actual_platform')
    need(report.get('physical_effect') == 'UNAVAILABLE' and report.get('unavailable') == UNAVAILABLE, 'scope_grant')
    need(report.get('ui_cases') == CASES and report.get('process_cases') == PROCESS_CASES
         and report.get('checks') == len(CASES) + len(PROCESS_CASES), 'case_contract')
    manifest = report.get('files'); need(type(manifest) is list, 'binary_manifest')
    unique(manifest, 'path')
    expected = {name for name in files if name.startswith(('stage/', 'consumer/'))}
    need({row['path'] for row in manifest} == expected, 'binary_coverage')
    for row in manifest:
        data = files[row['path']]
        need(type(row.get('bytes')) is int and row['bytes'] == len(data) and len(data) > 0
             and row.get('sha256') == digest(data), 'binary_hash')
    need(files['consumer/probe-debug.apk'] == files['consumer/installed.apk'], 'installed_apk_bytes')
    aar = unpack(files['stage/exreader-android-display-0.1.0.aar'])
    need(aar.get('classes.jar') == files['stage/classes.jar'], 'aar_original_classes')
    classes = unpack(files['stage/classes.jar'])
    need('org/exreader/display/ReaderDisplay.class' in classes
         and classes['org/exreader/display/ReaderDisplay.class'].startswith(b'\xca\xfe\xba\xbe'), 'real_library_class')
    apk = unpack(files['consumer/probe-debug.apk'])
    need('AndroidManifest.xml' in apk and 'classes.dex' in apk and apk['classes.dex'].startswith(b'dex\n'), 'real_apk')
    need(b'org.exreader.display.ReaderDisplay' in files['logs/apk-dex.stdout'], 'apk_library_dex')
    suite = decoded(files['evidence/suite.json']); runtime_identity(suite, report, files)
    need(suite.get('accepted') is True and suite.get('module') == report['module']
         and suite.get('job') == 'android' and suite.get('physical_effect') == 'UNAVAILABLE', 'suite_contract')
    rows = suite.get('cases'); need(type(rows) is list and [row.get('name') for row in rows] == CASES, 'named_ui_cases')
    for row in rows:
        need(row.get('passed') is True and type(row.get('assertions')) is int and row['assertions'] >= 3, 'ui_assertions')
        obs = row.get('observations'); need(type(obs) is list and len(obs) >= 1, 'ui_observations')
        for item in obs:
            need(item.get('main_thread') is True and item.get('brightness') == item.get('expected_brightness')
                 and type(item.get('keep')) is bool and item.get('keep') == item.get('expected_keep'), 'raw_window_property')
    instrument = files['logs/instrumentation.stdout'].decode('utf-8')
    found = re.findall(r'DISPLAY_CASE ([a-z_]+) (PASS|FAIL)', instrument)
    need(found == [(name, 'PASS') for name in CASES] and 'INSTRUMENTATION_CODE: -1' in instrument, 'raw_instrumentation')
    seed = decoded(files['evidence/process-seed.json']); reopened = decoded(files['evidence/process-reopen.json'])
    for raw in (seed, reopened): runtime_identity(raw, report, files)
    need(seed.get('phase') == 'seed' and abs(seed.get('brightness', 0) - 0.73) < 0.00001 and seed.get('keep') is True, 'process_seed')
    need(reopened.get('phase') == 'reopen' and reopened.get('brightness') == -1 and reopened.get('keep') is False, 'process_reopen')
    need(type(seed.get('pid')) is int and type(reopened.get('pid')) is int and seed['pid'] > 0
         and reopened['pid'] > 0 and seed['pid'] != reopened['pid'] and report.get('terminated_pid') == seed['pid']
         and report.get('reopened_pid') == reopened['pid'], 'process_identity')
    need(files['logs/pid-before.stdout'].strip() == str(seed['pid']).encode()
         and files['logs/pid-after-stop.stdout'].strip() == b''
         and files['logs/pid-reopen.stdout'].strip() == str(reopened['pid']).encode(), 'process_raw_pid')
    import xml.etree.ElementTree as ET
    xml = ET.fromstring(files['logs/apk-manifest.stdout'])
    need(not xml.findall('uses-permission') and not xml.findall('.//service'), 'permissions_services')
    need(set(report.get('global_before', {})) == {'screen_brightness', 'screen_brightness_mode'}
         and report['global_before'] == report.get('global_after'), 'global_settings')
    for key in report['global_before']:
        need(files['logs/global-before-' + key + '.stdout'].decode().strip() == report['global_before'][key]
             and files['logs/global-after-' + key + '.stdout'].decode().strip() == report['global_after'][key], 'global_raw_settings')
    return report


def verify(run, jobs, artifacts, data, log, repo, sha, run_id, attempt, module_tree):
    need(run.get('id') == run_id and run.get('head_sha') == sha and run.get('run_attempt') == attempt
         and run.get('path') == '.github/workflows/reader-android-display.yml', 'run_identity')
    need(run.get('repository', {}).get('full_name') == repo
         and run.get('head_repository', {}).get('id') == run['repository'].get('id'), 'run_repository')
    unique(jobs, 'id'); unique(jobs, 'name'); unique(artifacts, 'id'); unique(artifacts, 'name')
    job = selected(jobs, 'Android API34 native display')
    need(job.get('head_sha') == sha and job.get('run_id') == run_id and job.get('run_attempt') == attempt
         and job.get('status') == 'completed' and job.get('conclusion') == 'success', 'producer_job')
    artifact = selected(artifacts, f'reader-android-display-native-{run_id}-{attempt}')
    need(type(artifact.get('id')) is int and artifact['id'] > 0 and artifact.get('expired') is False
         and type(artifact.get('size_in_bytes')) is int and artifact['size_in_bytes'] > 0, 'artifact_identity')
    need(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'artifact_expiry')
    origin = artifact.get('workflow_run', {})
    need(origin.get('id') == run_id and origin.get('head_sha') == sha
         and origin.get('repository_id') == run['repository']['id']
         and origin.get('head_repository_id') == run['repository']['id'], 'artifact_origin')
    need(artifact['size_in_bytes'] == len(data), 'zip_size')
    need(artifact.get('digest') == 'sha256:' + digest(data), 'zip_digest')
    text = log.decode('utf-8', 'replace')
    match = re.findall(r'Artifact ' + re.escape(artifact['name'])
                      + r' has been successfully uploaded! Final size is (\d+) bytes\. Artifact ID is (\d+)', text)
    need(match == [(str(len(data)), str(artifact['id']))], 'producer_upload_binding')
    need(re.findall(r'SHA256 digest of uploaded artifact zip is ([a-f0-9]{64})', text) == [digest(data)], 'producer_digest_binding')
    files = unpack(data); report = verify_files(files, sha, run_id, attempt, module_tree)
    return {'schema': 1, 'accepted': True, 'complete_product': False, 'source_sha': sha,
            'run_id': run_id, 'run_attempt': attempt, 'producer_job': job['id'],
            'artifact': artifact, 'recomputed_zip_sha256': digest(data), 'recomputed_zip_bytes': len(data),
            'producer_log_sha256': digest(log), 'report_sha256': digest(files['evidence/report.json']),
            'checks': report['checks'], 'ui_cases': CASES, 'process_cases': PROCESS_CASES,
            'binaries': report['files'], 'unavailable': UNAVAILABLE}
