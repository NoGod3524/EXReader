#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject tampered copies of the actual authenticated Actions artifact, not mocks."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import zipfile
from strict import EvidenceError, decoded, digest, selected, unpack, verify, need


def encoded(value): return json.dumps(value, sort_keys=True).encode()


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    folder = Path('build/display-downloads')
    original = decoded((folder / 'metadata.json').read_bytes())
    original['data'] = (folder / 'native.zip').read_bytes()
    original['log'] = (folder / 'producer.log').read_bytes()
    need(verify(**original)['accepted'], 'real baseline must pass')
    checks = ['actual_authenticated_baseline']
    def artifact(s): return selected(s['artifacts'], f"reader-android-display-native-{s['run_id']}-{s['attempt']}")
    def job(s): return selected(s['jobs'], 'Android API34 native display')
    def repack(s, mutate, extra=None):
        files = unpack(s['data']); mutate(files)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in files.items(): archive.writestr(name, value)
            if extra: archive.writestr(*extra)
        old = artifact(s); previous_size = old['size_in_bytes']; previous_hash = old['digest'][7:]
        s['data'] = buf.getvalue(); old['size_in_bytes'] = len(s['data']); old['digest'] = 'sha256:' + digest(s['data'])
        text = s['log'].decode('utf-8', 'replace').replace(previous_hash, digest(s['data']))
        text = text.replace(f'Final size is {previous_size} bytes.', f'Final size is {len(s["data"])} bytes.')
        s['log'] = text.encode()
    def change_json(s, name, mutate):
        def apply(files):
            value = decoded(files[name]); mutate(value); files[name] = encoded(value)
        repack(s, apply)
    def reject(name, mutate, reason):
        value = deepcopy(original); mutate(value)
        try: verify(**value)
        except EvidenceError as error:
            need(str(error) == reason, name + ': expected ' + reason + ', got ' + str(error)); checks.append(name)
        else: raise AssertionError('accepted tampering: ' + name)
    reject('wrong_run_source', lambda s: s['run'].__setitem__('head_sha', '0' * 40), 'run_identity')
    reject('wrong_run_attempt', lambda s: s['run'].__setitem__('run_attempt', 99), 'run_identity')
    reject('wrong_workflow', lambda s: s['run'].__setitem__('path', 'other.yml'), 'run_identity')
    reject('wrong_repository', lambda s: s['run']['repository'].__setitem__('full_name', 'wrong/repo'), 'run_repository')
    reject('producer_not_completed', lambda s: job(s).__setitem__('status', 'in_progress'), 'producer_job')
    reject('producer_failure', lambda s: job(s).__setitem__('conclusion', 'failure'), 'producer_job')
    reject('producer_wrong_attempt', lambda s: job(s).__setitem__('run_attempt', 99), 'producer_job')
    reject('producer_wrong_source', lambda s: job(s).__setitem__('head_sha', '0' * 40), 'producer_job')
    reject('duplicate_job', lambda s: s['jobs'].append(deepcopy(job(s))), 'duplicate_id')
    reject('duplicate_artifact_id', lambda s: s['artifacts'].append(deepcopy(artifact(s))), 'duplicate_id')
    reject('wrong_artifact_name', lambda s: artifact(s).__setitem__('name', 'wrong'), 'missing_or_duplicate_named_evidence')
    reject('expired_artifact', lambda s: artifact(s).__setitem__('expired', True), 'artifact_identity')
    reject('past_expiry', lambda s: artifact(s).__setitem__('expires_at', '2000-01-01T00:00:00Z'), 'artifact_expiry')
    reject('empty_artifact', lambda s: artifact(s).__setitem__('size_in_bytes', 0), 'artifact_identity')
    reject('artifact_wrong_source', lambda s: artifact(s)['workflow_run'].__setitem__('head_sha', '0' * 40), 'artifact_origin')
    reject('wrong_zip_size', lambda s: artifact(s).__setitem__('size_in_bytes', 1), 'zip_size')
    reject('wrong_api_digest', lambda s: artifact(s).__setitem__('digest', 'sha256:' + '0' * 64), 'zip_digest')
    reject('wrong_actual_zip', lambda s: s.__setitem__('data', s['data'][:-1] + bytes([s['data'][-1] ^ 1])), 'zip_digest')
    reject('missing_upload_log_binding', lambda s: s.__setitem__('log', b'no upload'), 'producer_upload_binding')
    reject('wrong_upload_digest', lambda s: s.__setitem__('log', s['log'].replace(digest(s['data']).encode(), b'0' * 64)), 'producer_digest_binding')
    reject('duplicate_zip_report', lambda s: repack(s, lambda f: None, ('evidence/report.json', b'{}')), 'duplicate_archive_member')
    reject('zip_path_traversal', lambda s: repack(s, lambda f: f.__setitem__('../outside', b'x')), 'archive_path')
    reject('zip_case_alias', lambda s: repack(s, lambda f: f.__setitem__('EVIDENCE/REPORT.JSON', b'{}')), 'duplicate_archive_member')
    reject('missing_raw_suite', lambda s: repack(s, lambda f: f.pop('evidence/suite.json')), 'required_files')
    reject('duplicate_json_key', lambda s: repack(s, lambda f: f.__setitem__('evidence/report.json', b'{"x":1,"x":2}')), 'duplicate_json_key')
    reject('nonfinite_json', lambda s: repack(s, lambda f: f.__setitem__('evidence/report.json', b'{"x":NaN}')), 'nonfinite_json')
    reject('wrong_report_source', lambda s: change_json(s, 'evidence/report.json', lambda r: r.__setitem__('source_sha', '0' * 40)), 'report_origin')
    reject('wrong_report_attempt', lambda s: change_json(s, 'evidence/report.json', lambda r: r.__setitem__('run_attempt', '99')), 'report_origin')
    reject('wrong_original_module', lambda s: change_json(s, 'evidence/report.json', lambda r: r.__setitem__('source_module_tree', '0' * 40)), 'original_module_tree')
    reject('physical_overclaim', lambda s: change_json(s, 'evidence/report.json', lambda r: r.__setitem__('physical_effect', 'PASS')), 'scope_grant')
    reject('missing_required_case', lambda s: change_json(s, 'evidence/report.json', lambda r: r['ui_cases'].pop()), 'case_contract')
    reject('wrong_apk_bytes', lambda s: repack(s, lambda f: f.__setitem__('consumer/probe-debug.apk', b'not an apk')), 'binary_hash')
    reject('wrong_aar_bytes', lambda s: repack(s, lambda f: f.__setitem__('stage/exreader-android-display-0.1.0.aar', b'wrong module')), 'binary_hash')
    reject('wrong_runtime_apk_identity', lambda s: change_json(s, 'evidence/suite.json', lambda r: r.__setitem__('installed_apk_sha256', '0' * 64)), 'runtime_apk')
    reject('wrong_runtime_aar_identity', lambda s: change_json(s, 'evidence/suite.json', lambda r: r.__setitem__('aar_sha256', '0' * 64)), 'runtime_aar')
    reject('duplicate_named_ui_case', lambda s: change_json(s, 'evidence/suite.json', lambda r: r['cases'].append(r['cases'][0])), 'named_ui_cases')
    reject('failed_ui_case', lambda s: change_json(s, 'evidence/suite.json', lambda r: r['cases'][0].__setitem__('passed', False)), 'ui_assertions')
    reject('raw_property_mismatch', lambda s: change_json(s, 'evidence/suite.json', lambda r: r['cases'][0]['observations'][0].__setitem__('brightness', 0.99)), 'raw_window_property')
    reject('worker_property_read', lambda s: change_json(s, 'evidence/suite.json', lambda r: r['cases'][0]['observations'][0].__setitem__('main_thread', False)), 'raw_window_property')
    reject('missing_instrumentation_case', lambda s: repack(s, lambda f: f.__setitem__('logs/instrumentation.stdout', b'INSTRUMENTATION_CODE: -1')), 'raw_instrumentation')
    reject('process_still_alive', lambda s: repack(s, lambda f: f.__setitem__('logs/pid-after-stop.stdout', b'123')), 'process_raw_pid')
    reject('process_not_fresh', lambda s: change_json(s, 'evidence/process-reopen.json', lambda r: r.__setitem__('brightness', 0.73)), 'process_reopen')
    reject('injected_permission', lambda s: repack(s, lambda f: f.__setitem__('logs/apk-manifest.stdout', b'<manifest><uses-permission name="WRITE_SETTINGS"/></manifest>')), 'permissions_services')
    reject('injected_service', lambda s: repack(s, lambda f: f.__setitem__('logs/apk-manifest.stdout', b'<manifest><application><service/></application></manifest>')), 'permissions_services')
    reject('global_change', lambda s: change_json(s, 'evidence/report.json', lambda r: r['global_after'].__setitem__('screen_brightness', 'changed')), 'global_settings')
    result = {'accepted': True, 'diagnostic_only': True, 'native_credit': 0, 'count': len(checks), 'checks': checks,
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    Path('build/aggregate/rejections.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
