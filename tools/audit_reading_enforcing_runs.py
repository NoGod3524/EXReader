#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replay authenticated existing enforcing evidence; never run new measurements."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require
from export_reading_cpu_baseline import encoded, extract_raw
from join_reading_cpu_exports import member_bytes
from measure_reading_real import (CONTRACT, MANIFEST, PROTECTED, ROOT, SDK,
    audit, baseline_origin, git, native_metrics, percentile, read, sha256)
from reading_real_environments import REGISTRY, report_budget
from reading_required import workflow_identity

FROZEN = '220585e8248918096b9fc2c389ea5ad2389d388b'
MERGE = 'eb773e284c58aa8a474f09d780df8db610572e48'
RUNS = (40013452463, 40013457389, 40013462159, 40015227294, 40015233091, 40013585658)


def verify_upload(log, artifact):
    final = re.findall(r'Artifact ' + re.escape(artifact['name']) +
        r' has been successfully uploaded! Final size is (\d+) bytes\. Artifact ID is (\d+)', log)
    hashes = re.findall(r'SHA256 digest of uploaded artifact zip is ([0-9a-f]{64})', log)
    require(final == [(str(artifact['size_in_bytes']), str(artifact['id']))] and
            hashes == [artifact['digest'].removeprefix('sha256:')],
            'original job upload ID/size/digest differs from API')


def upload_selfcheck():
    artifact = {'name': 'reading-real-12-1', 'id': 34, 'size_in_bytes': 56,
                'digest': 'sha256:' + 'a' * 64}
    log = ('Artifact reading-real-12-1 has been successfully uploaded! Final size is 56 bytes. Artifact ID is 34\n'
           'SHA256 digest of uploaded artifact zip is ' + 'a' * 64)
    verify_upload(log, artifact)
    for altered in (log.replace('34', '35'), log.replace('56 bytes', '57 bytes'),
                    log.replace('a' * 64, 'b' * 64), log + '\n' + log,
                    log.replace('reading-real-12-1', 'reading-real-12-2')):
        try:
            verify_upload(altered, artifact)
        except ValueError:
            continue
        raise AssertionError('counterfeit original upload accepted')


def frozen_inputs():
    paths = {REGISTRY, 'tests/reading_real/contract.json'}
    registry = read(ROOT / REGISTRY)
    for entry in registry['environments']:
        paths.add(entry['budget_path'])
        paths.add(read(ROOT / entry['budget_path'])['pixel_review_path'])
    for relative in paths:
        require(subprocess.check_output(['git', 'show', FROZEN + ':' + relative], cwd=ROOT) ==
                (ROOT / relative).read_bytes(), 'audit checkout differs from frozen source: ' + relative)
    return registry, paths


def raw_identity(summary, raw, source):
    before = summary['before']
    require(before == summary['after'] and before['source_clean'] is True and
            before['source_sha'] == source and before['source_tree'] == git('rev-parse', source + '^{tree}') and
            summary['sdk_candidate'] == before['sdk_candidate'] == SDK and
            all(before['sdk_trees'][path] == git('rev-parse', FROZEN + ':' + path) ==
                git('rev-parse', source + ':' + path) == git('rev-parse', SDK + ':' + path)
                for path in PROTECTED), 'original protected source/SDK tree differs')
    identity = raw.parent / 'identity'
    for relative, expected in (('build/reading-real-consumer/reading-real-benchmark', before['binary']),
                               ('build/reading-real-font/Reader.otf', before['font'])):
        path = identity / relative
        require({'bytes': path.stat().st_size, 'sha256': sha256(path)} == expected,
                'original consumer/font bytes differ')
    require(sha256(identity / 'tests/reading_real/contract.json') == sha256(CONTRACT) ==
            summary['contract_sha256'] and sha256(identity / 'tools/reading_corpus/real-v1.json') ==
            sha256(MANIFEST) == summary['corpus_manifest_sha256'], 'original contract/corpus bytes differ')
    inventory = summary['installed_sdk']
    require(inventory['files'] and inventory['bytes'] == sum(row['bytes'] for row in inventory['files'].values()) and
            all(type(row['bytes']) is int and row['bytes'] >= 0 and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                for row in inventory['files'].values()), 'original SDK inventory accounting differs')
    for row in summary['references']:
        for key in ('stdout', 'stderr'):
            require(sha256(raw / row[key]) == row[key + '_sha256'], 'reference process log digest differs')


def inspect(run_id, output):
    run = fetch(f'actions/runs/{run_id}')
    required = run_id == RUNS[-1]
    source = MERGE if required else FROZEN
    require(run['id'] == run_id and run['head_sha'] == FROZEN and run['run_attempt'] == 1 and
            run['path'] == '.github/workflows/' + ('reading-required.yml' if required else 'reading-real.yml'),
            'fixed enforcing run/source/attempt differs')
    if required:
        parents = git('show', '-s', '--format=%P', source).split()
        workflow_identity(run, source, str(run_id), '1', parents)
    else:
        require(run['event'] == 'workflow_dispatch', 'independent enforcing invocation differs')
    jobs = pages(f'actions/runs/{run_id}/jobs', 'jobs')
    matching = [job for job in jobs if job['name'] ==
                ('performance / reading-performance' if required else 'reading-performance')]
    require(len(matching) == 1, 'missing/duplicate original performance job')
    job = matching[0]
    require(job['run_id'] == run_id and job['run_attempt'] == 1 and job['head_sha'] == FROZEN and
            job['status'] == 'completed', 'original performance job not complete or source differs')
    artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
    matching = [item for item in artifacts if item['name'] == f'reading-real-{run_id}-1']
    require(len(matching) == 1 and (required or len(artifacts) == 1), 'missing/duplicate enforcing artifact')
    artifact = matching[0]
    require(artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == FROZEN and
            artifact['expired'] is False and artifact['size_in_bytes'] > 0 and
            re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')), 'original artifact metadata differs')
    report = {'schema': 1, 'diagnostic_only': True, 'accepted': False, 'measurement_performed': False,
        'auditor_source_sha': git('rev-parse', 'HEAD'), 'auditor_run_id': os.environ['GITHUB_RUN_ID'],
        'auditor_run_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'run_id': run_id, 'run_attempt': 1,
        'source_sha': source, 'workflow_head_sha': FROZEN, 'workflow_status': run['status'],
        'workflow_conclusion': run['conclusion'], 'job_id': job['id'], 'job_conclusion': job['conclusion'],
        'artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest')},
        'raw_audit_passed': False, 'source_performance_accepted': False, 'audit_problems': []}
    log = subprocess.check_output(['gh', 'api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/jobs/{job["id"]}/logs',
                                   '--allow-escape-sequences'],
                                  text=True, timeout=120)
    (output / 'original-job.log').write_text(log, encoding='utf-8')
    verify_upload(log, artifact)
    report['original_upload_verified'] = True
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        archive_path = temporary / 'original.zip'
        with archive_path.open('wb') as stream:
            download_artifact_zip(artifact['id'], stream)
        require(archive_path.stat().st_size == artifact['size_in_bytes'] and
                'sha256:' + sha256(archive_path) == artifact['digest'], 'original ZIP size/digest differs')
        report['zip_verified'] = True
        with zipfile.ZipFile(archive_path) as archive:
            summary_bytes = member_bytes(archive, 'reading-real/summary.json')
            summary = json.loads(summary_bytes)
            (output / 'original-summary.json').write_bytes(summary_bytes)
            require(summary['source_sha'] == source and summary['run_id'] == str(run_id) and
                    summary['run_attempt'] == '1', 'original summary source/run/attempt differs')
            report.update(environment=summary.get('environment'), budget_path=summary.get('budget_path'),
                budget_sha256=summary.get('budget_sha256'), budget_selection=summary.get('budget_selection'),
                original_accepted=summary.get('accepted'), measurement_valid=summary.get('measurement_valid'),
                original_problems=summary.get('problems'), native_processes=len(summary['attempts']),
                reference_processes=len(summary['references']))
            selection = summary.get('budget_selection') or {}
            report.update(cpu_model=(summary.get('environment') or {}).get('cpu_model'),
                environment_id=selection.get('environment_id'), registry_sha256=selection.get('registry_sha256'),
                frozen_registry_sha256=sha256(ROOT / REGISTRY))
            if len(summary['attempts']) != 40 or len(summary['references']) != 12:
                require(job['conclusion'] != 'success' and summary['accepted'] is False,
                        'successful enforcing job omitted raw processes')
                report['raw_audit_status'] = 'original_run_rejected_before_complete_measurement'
                return report
            selected = report_budget(summary)
            budget = read(selected)
            registry, _ = frozen_inputs()
            for relative in (REGISTRY, *(entry['budget_path'] for entry in registry['environments'])):
                require(member_bytes(archive, 'identity/' + relative) == (ROOT / relative).read_bytes(),
                        'retained registry/budget bytes differ from frozen checkout')
            _, extracted_summary, raw = extract_raw(archive, temporary / 'raw')
            require(extracted_summary == summary_bytes, 'extractor summary bytes differ')
            (raw / 'baseline-summary.json').write_bytes(member_bytes(archive, 'reading-real/baseline-summary.json'))
            (output / 'original-baseline-summary.json').write_bytes((raw / 'baseline-summary.json').read_bytes())
        raw_identity(summary, raw, source)
        origin = baseline_origin(budget, source)
        for kind, keys in (('run', ('id', 'head_sha', 'run_attempt')), ('artifact', ('id', 'digest', 'size_in_bytes'))):
            require(all(summary['baseline_origin'][kind][key] == origin[kind][key] for key in keys),
                    'fresh baseline API identity differs from original retained origin')
        expected = {'GITHUB_SHA': source, 'GITHUB_RUN_ID': str(run_id), 'GITHUB_RUN_ATTEMPT': '1'}
        try:
            # Only replay authenticated bytes in their original CI identity; no consumer is executed.
            with patch.dict(os.environ, expected):
                require(audit(summary, raw, budget) == summary['results'], 'raw strict recomputation differs')
            require(summary['refusal_regression']['passed'] is True and
                    summary['signature_refusal_regression']['passed'] is True, 'original refusal regressions incomplete')
            report['raw_audit_passed'] = True
            report['raw_audit_status'] = 'passed'
        except (ValueError, KeyError, TypeError) as error:
            report['raw_audit_error'] = str(error)
            report['raw_audit_status'] = 'rejected'
            if str(error).startswith('Budget exceeded: '):
                case, metric = str(error).removeprefix('Budget exceeded: ').split('/', 1)
                entry = next(item for item in summary['files'] if item['id'] == case)
                samples = [native_metrics(read(raw / item['stdout']), entry, summary['contract'])[0][metric]
                           for item in summary['attempts'] if item['case'] == case]
                actual, maximum = percentile(samples, .95), budget['cases'][case][metric]
                report['rejected_metric'] = {'case': case, 'metric': metric, 'samples': samples,
                    'p95': actual, 'budget': maximum, 'excess': actual - maximum,
                    'excess_percent': (actual / maximum - 1) * 100 if maximum else None,
                    'budget_sha256': summary['budget_sha256']}
        report['source_performance_accepted'] = (job['conclusion'] == 'success' and
            summary['accepted'] is True and summary['measurement_valid'] is True and summary['problems'] == [] and
            report['raw_audit_passed'])
        require(job['conclusion'] != 'success' or report['source_performance_accepted'],
                'successful enforcing job did not survive strict original-byte audit')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', type=int, choices=RUNS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'original evidence audit runs only in cloud CI')
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'auditor checkout identity differs')
    require(not args.output.exists(), 'preserve previous diagnostic evidence')
    args.output.mkdir(parents=True)
    upload_selfcheck()
    frozen_inputs()
    report = inspect(args.run_id, args.output)
    (args.output / 'audit.json').write_bytes(encoded(report))
    print('CPU_ENFORCING_AUDIT_JSON_BEGIN\n' + json.dumps(report, allow_nan=False) + '\nCPU_ENFORCING_AUDIT_JSON_END')


if __name__ == '__main__':
    main()
