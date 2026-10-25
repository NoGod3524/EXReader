"""Actions-only: authenticate this run's original ZIPs and independently rejudge all API stages."""
import argparse
from datetime import datetime, timezone
import pathlib
import subprocess
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common
import validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/reader-next-c08.yml'
BRANCH = 'codex/reader-next-c08-root-review'
JOBS = {
    'static': 'C08 guards, validator self-test, authenticated inputs and consumer build',
    'emulator': 'C08 real UI import and independent public-API readback on a fresh emulator',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def authenticate_zip(role, artifact, identity, output):
    require(artifact['name'] == f"reader-next-c08-{role}-{identity['run_id']}-{identity['attempt']}", 'unexpected current artifact name')
    require(not artifact['expired'] and artifact['workflow_run']['head_sha'] == identity['source_sha'] and
            str(artifact['workflow_run']['id']) == identity['run_id'] and
            datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'current artifact source/run/expiry differs')
    body = common.gh_api_bytes('actions/artifacts/' + str(artifact['id']) + '/zip')
    require(len(body) == artifact['size_in_bytes'] and 'sha256:' + common.sha256_bytes(body) == artifact['digest'],
            'current original ZIP bytes/digest differ')
    return common.safe_extract(body, output / role) / role


def check_build(build, identity, contract):
    require(build['identity'] == identity and build['producer_source'] == contract['producer']['source_sha'],
            'consumer source/run/producer identity differs')
    require(build['source_sha256'] == common.sha256_file(ROOT / 'tests/reader_next_c08/consumer/c08_consumer.c'),
            'consumer built from different API source')
    require('exr/library.h' in build['headers'], 'public library header missing')
    for name, digest in build['headers'].items():
        path = pathlib.PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name,
                'unsafe public header path')
        data = subprocess.check_output(['git', 'show', contract['producer']['source_sha'] + ':include/' + name], cwd=ROOT)
        require(common.sha256_bytes(data) == digest, 'compiled public header differs from frozen producer: ' + name)


def check_original_inputs(attestation, identity, contract):
    require(attestation['identity'] == identity and attestation['producer']['source_sha'] == contract['producer']['source_sha'] and
            attestation['producer']['run_id'] == contract['producer']['run_id'] and attestation['producer']['attempt'] == 1,
            'frozen producer or current identity differs')
    actual = attestation['artifacts']
    require(len(actual) == len(contract['producer']['artifacts']), 'frozen input artifact set differs')
    for row, pin in zip(actual, contract['producer']['artifacts']):
        require(all(row[key] == pin[key] for key in ('role', 'id', 'name', 'bytes', 'digest', 'expires_at')) and
                all(row['checks'].values()) and row['downloaded']['bytes'] == pin['bytes'] and
                'sha256:' + row['downloaded']['sha256'] == pin['digest'], 'frozen original ZIP authentication differs')
    require(attestation['s04_protocol_run']['matches'], 'S04 fixed identity not found')


def check_stages(emulator, identity, contract):
    require(emulator['identity'] == identity and emulator['accepted'] and not emulator['mandatory_failed'],
            'emulator current identity or mandatory result differs')
    names = [row['name'] for row in emulator['checks']]
    require(len(names) == len(set(names)) == emulator['checks_total'] and
            emulator['checks_passed'] == sum(row['pass'] is True for row in emulator['checks']),
            'emulator check inventory differs')
    checks = {row['name']: row for row in emulator['checks']}
    required = {'emulator_is_virtual_api34_x86_64', 'installed_bytes_equal_original_apk',
                'device_consumer_bytes_equal_built_program', 'consumer_build_identity_matches_this_run',
                'book_imported_through_real_ui', 'turned_to_page_3', 'annotation_created_through_ui',
                'fresh_reopen_restores_page_3', 'offline_reopen_restores_page_3', 'device_offline',
                'values_stable_across_close_fresh_reopen_and_offline_reopen',
                'consumer_library_is_installed_apk_member', 'consumer_loaded_only_the_installed_sdk_library',
                'no_preference_injection_or_apk_modification'}
    require(required <= set(checks) and all(checks[name]['mandatory'] and checks[name]['pass'] for name in required),
            'required original APK/UI/API cases omitted or not passing')
    observed = emulator['observed']
    require(observed['annotation']['created'] and observed['expected_notes'] == [contract['expected_note']],
            'required UI-created note was not confirmed')
    require(observed['pages'] == [1, 2, 3] and observed['fresh_reopen_page']['page'] == observed['offline_reopen_page']['page'] == 3,
            'actual initial/fresh/offline UI page observations differ')
    book_id = observed['ui_book_id']
    require(observed['fresh_reopen_page']['book'] == observed['offline_reopen_page']['book'] == book_id,
            'reopen UI book IDs differ')
    offline = observed['offline']
    require(offline['airplane_mode_on'] == '1' and offline['wifi_on'] == offline['mobile_data'] == '0' and offline['ping_exit'] != 0,
            'offline environment was not independently recorded')
    expect = dict(format=contract['fixture']['format'], title_stem=contract['fixture']['title_stem'],
                  sha256=contract['fixture']['sha256'], bytes=contract['fixture']['bytes'],
                  notes=[contract['expected_note']], book_id=book_id,
                  sdk_version=contract['expected_sdk_version'], abi_version=contract['expected_abi_version'])
    stages = emulator['stages']
    require([stage['stage'] for stage in stages] == ['1-after-first-close', '2-after-fresh-reopen', '3-after-offline-reopen'],
            'three distinct real readback stages are required')
    values, retained, pending = [], [], []
    installed_apk = observed['installed']['path']
    allowed = {installed_apk + '!/lib/x86_64/libexreader.so', '/data/local/tmp/c08/lib/libexreader.so'}
    for stage in stages:
        require(stage['snapshot_unchanged'] and stage['target_before'] == stage['target_after'] and
                stage['copy_unchanged'] and stage['copy_before'] == stage['copy_after'] and stage['snapshot_files'] > 0,
                'target or full read-only copy inventory changed')
        expected_files = {path[len('files/'):] for path in stage['target_before'] if path in (
            'files/library.db', 'files/library.db-wal', 'files/library.db-shm', 'files/library.db-journal')}
        require(set(stage['copy']) == expected_files == set(stage['copy_before']) and 'library.db' in expected_files,
                'copied database/sidecar inventory differs')
        for name, file in stage['copy'].items():
            original = stage['target_before']['files/' + name]
            require(file['bytes'] == original['size'] and file['sha256'] == original['sha256'] and
                    stage['copy_before'][name]['bytes'] == file['bytes'] and stage['copy_before'][name]['sha256'] == file['sha256'],
                    'read-only database copy is not byte-identical to target')
        successes = []
        for attempt in stage['modes']['shell_readonly_copy']:
            report = attempt['report']
            reasons = validate.validate(report, expect) if report else ['no API report']
            if attempt['exit'] == 0 and not reasons:
                require(report['loaded_from'] in allowed and report['process']['uid'] == 2000 and
                        report['database_path'] == '/data/local/tmp/c08/copy/' + stage['stage'] + '/library.db',
                        'consumer loaded unknown SDK object or did not read its separate copy as shell UID')
                successes.append(report)
        require(successes, 'certified read-only copy route did not return public API values in ' + stage['stage'])
        report = successes[0]
        actual = validate.normalize(report)
        values.append(actual)
        retained.append({'stage': stage['stage'], 'values': actual, 'calls': report['calls'],
                         'symbols': report['symbols'], 'process': report['process'],
                         'sdk_version': report['sdk_version'], 'abi_version': report['abi_version'],
                         'loaded_from': report['loaded_from'], 'database_path': report['database_path']})
        same_uid = stage['modes']['same_uid_run_as']
        pending.append({'stage': stage['stage'], 'attempts': [
            {'variant': row['variant'], 'exit': row['exit'], 'stderr': row['stderr'], 'refusals': row['refusals']}
            for row in same_uid if row['exit'] != 0]})
    require(values[0] == values[1] == values[2], 'actual public API values changed across separate cold/offline reopens')
    relationship = observed['progress_relationship']
    require(relationship['public_api_page_number'] is None and relationship['independent_exact_page3_resolution_accepted'] is False,
            'persisted public offset was inflated into independent exact UI page resolution')
    return retained, pending, relationship


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-summary'))
    args = parser.parse_args()
    common.require_actions()
    identity = common.identity()
    result = {'identity': identity, 'accepted': False, 'problems': [], 'artifacts': [],
              'scope': 'original APK public SDK readback through certified read-only copies on API34 default x86_64 only',
              'same_uid_execution_accepted': False, 'independent_exact_page3_resolution_accepted': False,
              'physical_device_execution': False, 'complete_product': False}
    try:
        contract = common.read_json(ROOT / 'tests/reader_next_c08/contract.json')
        run = common.gh_api('actions/runs/' + identity['run_id'] + '/attempts/' + identity['attempt'])
        require(run['head_sha'] == identity['source_sha'] and run['head_branch'] == BRANCH and run['path'] == WORKFLOW,
                'actual source/branch/workflow identity differs')
        jobs = common.gh_api('actions/runs/' + identity['run_id'] + '/attempts/' + identity['attempt'] + '/jobs?per_page=100')
        require(jobs['total_count'] == 3, 'complete original three-job workflow required')
        artifacts = common.gh_api('actions/runs/' + identity['run_id'] + '/artifacts?per_page=100')['artifacts']
        roots = {}
        for role, name in JOBS.items():
            selected = [row for row in jobs['jobs'] if row['name'] == name]
            require(len(selected) == 1 and selected[0]['conclusion'] == 'success' and selected[0]['head_sha'] == identity['source_sha'] and
                    str(selected[0]['run_attempt']) == identity['attempt'], 'producer job identity or success differs: ' + role)
            selected = [row for row in artifacts if row['name'] == f"reader-next-c08-{role}-{identity['run_id']}-{identity['attempt']}"]
            require(len(selected) == 1, 'missing/repeated original current ZIP: ' + role)
            roots[role] = authenticate_zip(role, selected[0], identity, args.output.parent / 'c08-summary-inputs')
            result['artifacts'].append({key: selected[0][key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        static, device = roots['static'], roots['emulator']
        selftest = common.read_json(static / 'validate-selftest.json')
        required_negatives = {'positive_control', 'refuses_sql_scan_only', 'refuses_file_hash_only',
                              'refuses_no_calls_recorded', 'refuses_symbol_from_other_object',
                              'refuses_missing_required_note', 'refuses_notes_value_status_failure',
                              'refuses_partial_read_at_transcript', 'refuses_root_process'}
        require(required_negatives <= set(selftest) and all(selftest.values()), 'validator negative controls failed or missing')
        for role in JOBS:
            check_original_inputs(common.read_json(roots[role] / 'authenticate/attestation.json'), identity, contract)
        builds = [common.read_json(root / 'consumer-build.json') for root in (static, device)]
        for build in builds:
            check_build(build, identity, contract)
        require(builds[0]['headers'] == builds[1]['headers'], 'static/emulator compiled different public headers')
        require(common.sha256_file(device / 'c08_consumer') == builds[1]['binary_sha256'], 'retained consumer program differs from build')
        emulator = common.read_json(device / 'emulator-report.json')
        observed = emulator['observed']
        require(observed['consumer']['binary_sha256'] == builds[1]['binary_sha256'] and observed['consumer']['build'] == builds[1],
                'device-executed consumer origin differs')
        require(common.sha256_file(device / 'installed-base.apk') == contract['producer']['apk_sha256'] and
                (device / 'installed-base.apk').stat().st_size == contract['producer']['apk_bytes'], 'actual installed APK bytes changed')
        with zipfile.ZipFile(device / 'installed-base.apk') as apk:
            member = apk.read('lib/x86_64/libexreader.so')
        require(common.sha256_bytes(member) == common.sha256_file(device / 'libexreader.so') ==
                observed['consumer']['extracted_library_sha256'], 'actual loaded library copy differs from installed APK member')
        stages, pending, relationship = check_stages(emulator, identity, contract)
        result.update(accepted=True, actual_api_stages=stages, pending_same_uid_attempts=pending,
                      progress_relationship=relationship, emulator_checks=emulator['checks_total'],
                      emulator_passed=emulator['checks_passed'], original_apk_sha256=contract['producer']['apk_sha256'],
                      consumer_builds=builds, all_target_and_copy_snapshots_unchanged=True,
                      api_source_headers_and_sdk_object_authenticated=True,
                      current_original_zips_authenticated=True)
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    common.write_json(args.output / 'summary.json', result)
    print(__import__('json').dumps(result), flush=True)
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
