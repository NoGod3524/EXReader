#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only same-source preintegration of desktop shelves and native sync modules."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require

WORKFLOW = '.github/workflows/reader-product-integration.yml'
JOBS = {
    'desktop / desktop SDK (ubuntu-22.04)': ('reader-desktop-sdk', 'Linux'),
    'desktop / desktop SDK (windows-2022)': ('reader-desktop-sdk', 'Windows'),
    'commands / installed typed product commands (ubuntu-22.04)': ('reader-commands', 'Linux'),
    'commands / installed typed product commands (windows-2022)': ('reader-commands', 'Windows'),
}


def identity(report, source, run, attempt, *, has_run=True, has_attempt=True):
    require(isinstance(report, dict) and report.get('source_sha') == source, 'report source differs')
    if has_run:
        require(str(report.get('run_id')) == str(run), 'report run differs')
    if has_attempt:
        require(str(report.get('attempt')) == str(attempt), 'report attempt differs')
    for key in ('problems', 'errors'):
        require(key not in report or report[key] == [], 'report contains ' + key)
    require(report.get('complete_product', False) is False, 'component cannot grant product completion')


def checks(rows, count, *, flag=None, key='id'):
    require(isinstance(rows, list) and len(rows) == count, 'check count differs')
    names = [row.get(key) if flag else row for row in rows]
    require(all(isinstance(name, str) and name for name in names) and len(set(names)) == count,
            'missing or repeated check identity')
    if flag:
        require(all(row.get(flag) is True for row in rows), 'failed or skipped check')


def verify_metadata(run, jobs, artifacts, source, run_id, attempt):
    require(run.get('id') == run_id and run.get('head_sha') == source and
            run.get('run_attempt') == attempt and run.get('path') == WORKFLOW and
            run.get('event') in ('push', 'workflow_dispatch'), 'caller identity differs')
    expected = set(JOBS) | {'strict preintegration summary'}
    require(len(jobs) == len(expected) and {job['name'] for job in jobs} == expected and
            len({job['id'] for job in jobs}) == len(jobs), 'upstream job set differs')
    for job in jobs:
        require(job.get('head_sha') == source and job.get('run_id') == run_id and
                job.get('run_attempt') == attempt, 'job source/run/attempt differs')
        if job['name'] in JOBS:
            require(job['status'] == 'completed' and job['conclusion'] == 'success',
                    'upstream failed skipped cancelled or incomplete')
    names = {f'{prefix}-{platform}-{run_id}-{attempt}' for prefix, platform in JOBS.values()}
    require(len({a['id'] for a in artifacts}) == len(artifacts) and
            len({a['name'] for a in artifacts}) == len(artifacts), 'duplicate artifact identity')
    prefixes = [f'{prefix}-{platform}' for prefix, platform in JOBS.values()] + ['reader-product-preintegration']
    current = []
    for artifact in artifacts:
        if artifact['name'] not in names:
            # Retain old attempts without taking any evidence from them. A partial
            # rerun still fails the exact current-attempt job and artifact sets.
            previous = re.fullmatch('(?:' + '|'.join(map(re.escape, prefixes)) +
                                    f')-{run_id}-([1-9][0-9]*)', artifact['name'])
            require(previous is not None and int(previous.group(1)) < attempt,
                    'unexpected or current-attempt artifact')
            continue
        current.append(artifact)
        require(artifact.get('expired') is False and type(artifact.get('size_in_bytes')) is int and
                0 < artifact['size_in_bytes'] <= 1024 * 1024 * 1024 and
                artifact.get('workflow_run', {}).get('id') == run_id and
                artifact['workflow_run'].get('head_sha') == source and
                re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest', '')) is not None,
                'artifact expired empty or identity/digest differs')
    require(len(current) == 4 and {a['name'] for a in current} == names, 'required artifact set differs')
    return current


def validate_archive(archive):
    names = archive.namelist()
    require(0 < len(names) <= 10000 and len(names) == len(set(names)), 'ZIP member count/uniqueness differs')
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and
                ':' not in info.filename and '\x00' not in info.filename and
                stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR),
                'unsafe ZIP member')


def report_bytes(archive, name):
    info = archive.getinfo(name)
    require(not info.is_dir() and 0 < info.file_size <= 4 * 1024 * 1024, 'JSON member size differs')
    return archive.read(info)


def verify_reports(kind, platform, read, source, run_id, attempt):
    verified = {}

    def load(name, count=None, *, field='checks', flag=None, key='id', success='accepted',
             has_run=True, has_attempt=True):
        data = read(name)
        report = json.loads(data)
        identity(report, source, run_id, attempt, has_run=has_run, has_attempt=has_attempt)
        require(report.get(success) is True, name + ': report refused')
        if count is not None:
            checks(report.get(field), count, flag=flag, key=key)
        verified[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'checks': count}
        return report

    if kind == 'reader-commands':
        for folder, count in (('sync-source-evidence', 77 if platform == 'Linux' else 76),
                              ('sync-protocol-evidence', 59), ('sync-evidence', 33),
                              ('projection-evidence', 32), ('commands-evidence', 33), ('metadata-evidence', 29)):
            value = load(folder + '/result.json', count, flag=None if folder=='metadata-evidence' else 'pass')
            require(value.get('count') == count, 'module recorded count differs')
            require(value.get('platform') == ('linux' if platform == 'Linux' else 'win32'),
                    'module platform differs')
            if folder == 'sync-evidence':
                require(value.get('shards') == 256 and value.get('entries_per_shard_ceiling') == 2000 and
                        value.get('full_library_complete') is False, 'discovery contract differs')
            if folder == 'projection-evidence':
                require(value.get('metadata_history_outbox_same_product_transaction') is True and
                        value.get('sdk_database_writes') is False, 'projection contract differs')
            if folder == 'commands-evidence':
                require(value.get('native_only_wire_producer') is True and value.get('schema1_changed') is False and
                        value.get('sdk_database_writes') is False and value.get('mobile_accepted') is False,
                        'typed commands contract differs')
            if folder == 'metadata-evidence':
                require(value.get('native_adapter_only') is True and value.get('sdk_database_writes') is False and
                        value.get('schema1_changed') is False and value.get('wire_changed') is False and
                        value.get('desktop_ui_accepted') is False and value.get('sdk_source_verification_accepted') is False and
                        re.fullmatch('[0-9a-f]{64}', value.get('consumer_sha256', '')) is not None,
                        'metadata adapter contract differs')
        return verified

    sdk = load('desktop-sdk/verified.json', 9, field='sdk_checks', flag='passed')
    checks(sdk.get('native_checks'), 12, flag='passed')
    kills = sdk.get('process_kills', [])
    require(len(kills) == 2 and {k['stage'] for k in kills} == {'sdk', 'transaction'} and
            all(k.get('recovered') is True and k.get('killed_returncode') not in (None, 0) for k in kills),
            'real kill/recovery evidence differs')
    load('desktop-sdk/shelf-check/shelf-result.json', 10, flag='passed')
    organization = load('desktop-sdk/organization-check/organization-result.json', 15, flag='passed')
    require(organization.get('sdk_changed') is False and organization.get('schema_changed') is False and
            organization.get('ui_accepted') is False, 'native organization reader contract differs')
    if platform == 'Linux':
        original_path = 'desktop-gtk-ui/report.json'
        original = load(original_path, 20, flag='pass', key='name', success='passed', has_attempt=False)
        product = load('desktop-gtk-product/product-result.json', 5)
        load('desktop-gtk-fixed/fixed-ui.json', 24, flag='passed', key='name')
        shelf = load('desktop-gtk-shelf/shelf-result.json', 14)
        metadata = load('desktop-gtk-metadata/metadata-ui.json', 15)
        require(metadata.get('count') == 15 and metadata.get('groups_ui_accepted') is False and
                metadata.get('performance_accepted') is False and len(metadata.get('screenshots', [])) == 4 and
                re.fullmatch('[0-9a-f]{64}', metadata.get('program_sha256', '')) is not None,
                'actual GTK metadata UI contract differs')
        manifest_path = 'desktop-linux-package/build.json'
        manifest_bytes = read(manifest_path)
        manifest = json.loads(manifest_bytes)
        require(manifest.get('source_sha') == source and manifest.get('sdk_version') == '3.40.0' and
                manifest.get('abi') == 1 and manifest.get('files', {}).get('bin/exreader-linux') == metadata['program_sha256'],
                'GTK metadata tested program differs from actual package')
        verified[manifest_path] = {'sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'checks': None}
        regression = load('desktop-gtk-regressions/regressions.json', success='passed', has_run=False, has_attempt=False)
        require(regression.get('checks') and all(row.get('pass') is True for row in regression['checks']),
                'retained GTK regressions failed or missing')
        require(product.get('original_ui_cases') == 20, 'retained GTK case count differs')
    else:
        original_path = 'desktop-windows-ui/wp13-windows-evidence.json'
        original = load(original_path, 9, flag='passed', key='name', success='passed', has_run=False, has_attempt=False)
        require(original.get('counts') == {'steps': 158, 'passed': 158, 'failed': 0} and
                len(original.get('steps', [])) == 158 and all(s.get('result') == 'PASS' for s in original['steps']) and
                sum(len(v) for v in original.get('screenshots', {}).values()) == 8, 'retained Windows UI differs')
        product = load('desktop-windows-product/product-result.json', 10)
        load('desktop-windows-shelf-worker/worker-result.json', 5)
        shelf = load('desktop-windows-shelf-ui/shelf-result.json', 13)
        metadata = load('desktop-windows-metadata/metadata-ui.json', 18)
        require(metadata.get('count') == 18 and metadata.get('groups_ui_accepted') is False and
                metadata.get('performance_accepted') is False and len(metadata.get('screenshots', [])) == 6 and
                metadata.get('program_sha256') == shelf.get('binary_sha256'),
                'actual Windows metadata UI contract differs')
        require(product.get('original_ui_steps') == 158 and
                product.get('program_sha256') == original.get('program_sha256') == shelf.get('binary_sha256') and
                re.fullmatch('[0-9a-f]{64}', shelf.get('binary_sha256', '')) is not None,
                'Windows actual product binary differs')
    require(product.get('original_report_sha256') == verified[original_path]['sha256'], 'original report binding differs')
    require(shelf.get('originals') == 2202 and shelf.get('page_size') == 50 and shelf.get('cache_limit') == 150,
            'bounded shelf contract differs')
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'verify only in GitHub Actions')
    source = os.environ['GITHUB_SHA']
    run_id, attempt = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
              'scope': 'same-source desktop shelves book metadata UI and native sync modules only',
              'complete_product': False, 'performance_accepted': False, 'six_platform_accepted': False,
              'artifacts': [], 'problems': []}
    try:
        run = fetch(f'actions/runs/{run_id}')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        artifacts = verify_metadata(run, jobs, artifacts, source, run_id, attempt)
        result['jobs'] = [{k: job[k] for k in ('id', 'name', 'head_sha', 'run_attempt', 'conclusion')}
                          for job in jobs if job['name'] in JOBS]
        for artifact in sorted(artifacts, key=lambda a: a['name']):
            kind, platform = next((prefix, platform) for prefix, platform in JOBS.values()
                                  if artifact['name'] == f'{prefix}-{platform}-{run_id}-{attempt}')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                size = stream.tell()
                stream.seek(0)
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
                require(size == artifact['size_in_bytes'] and 'sha256:' + digest.hexdigest() == artifact['digest'],
                        'downloaded ZIP size/digest differs')
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    validate_archive(archive)
                    reports = verify_reports(kind, platform, lambda name: report_bytes(archive, name), source, run_id, attempt)
            result['artifacts'].append({**{key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest')},
                                        'reports': reports})
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(str(error))
        raise
    finally:
        (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
