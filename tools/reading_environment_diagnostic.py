#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect two retained JSON reports in Actions; never execute a consumer."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require

HEAD = 'de9871aca6a54f70c6c1d147ba12f308cedf1004'
MERGE = '6cb92c16ac6b36922551a64b52f323afd6406539'
BASELINE_SUMMARY = 'f83c42b738127ce52ee2a4ddb8653fbda36b03e8cd56adf5971fd1f219e3135d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def positive(value):
    if re.fullmatch(r'[1-9][0-9]{0,18}', value) is None:
        raise argparse.ArgumentTypeError('Positive bounded decimal ID/size required')
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('run_id', 'job_id', 'artifact_id', 'artifact_bytes'):
        parser.add_argument('--' + field.replace('_', '-'), type=positive,
                            default=os.environ.get('DIAG_' + field.upper()))
    parser.add_argument('--artifact-digest', default=os.environ.get('DIAG_ARTIFACT_DIGEST'))
    args = parser.parse_args()
    require(all(type(getattr(args, field)) is int for field in ('run_id', 'job_id', 'artifact_id', 'artifact_bytes'))
            and args.artifact_bytes <= 256 * 1024 * 1024 and
            re.fullmatch(r'[0-9a-f]{64}', args.artifact_digest or '') is not None, 'Bounded artifact inputs required')
    run_id, job_id, artifact_id = args.run_id, args.job_id, args.artifact_id
    name = f'reading-real-{run_id}-1'
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Cloud repository required')
    output = Path('build/reading-environment-diagnostic')
    output.mkdir(parents=True, exist_ok=False)
    report = {'diagnostic_only': True, 'accepted': False, 'engine_executed': False,
              'diagnostic_source': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'inspected_run': run_id, 'inspected_attempt': 1, 'inspected_head': HEAD,
              'inspected_merge': MERGE, 'inspected_job': job_id, 'artifact_id': artifact_id, 'problems': []}
    try:
        run, job = fetch(f'actions/runs/{run_id}'), fetch(f'actions/jobs/{job_id}')
        require(run['id'] == run_id and run['head_sha'] == HEAD and run['run_attempt'] == 1 and
                run['path'] == '.github/workflows/reading-required.yml', 'Run identity refused')
        require(job['id'] == job_id and job['run_id'] == run_id and job['head_sha'] == HEAD and
                job['run_attempt'] == 1 and job['name'] == 'performance / reading-performance' and
                job['status'] == 'completed' and job['conclusion'] == 'failure', 'Failed job identity refused')
        selected = [row for row in pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
                    if row['id'] == artifact_id or row['name'] == name]
        require(len(selected) == 1, 'Artifact missing/duplicate')
        artifact = selected[0]
        require(artifact['id'] == artifact_id and artifact['name'] == name and artifact['size_in_bytes'] == args.artifact_bytes and
                artifact['digest'] == 'sha256:' + args.artifact_digest and artifact['expired'] is False and
                artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == HEAD,
                'Artifact metadata refused')
        raw = download_artifact_zip(artifact_id)
        require(len(raw) == args.artifact_bytes and sha(raw) == args.artifact_digest, 'Artifact ZIP bytes/digest refused')
        reports = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in ('reading-real/summary.json', 'reading-real/baseline-summary.json'):
                require(archive.namelist().count(name) == 1, 'Report path missing/duplicate')
                info = archive.getinfo(name)
                require(not info.is_dir() and (info.external_attr >> 16 & 0o170000) in (0, 0o100000) and
                        0 < info.file_size <= 16 * 1024 * 1024, 'Report type/extent refused')
                payload = archive.read(name)
                (output / Path(name).name).write_bytes(payload)
                reports.append(json.loads(payload))
                if name.endswith('baseline-summary.json'):
                    require(sha(payload) == BASELINE_SUMMARY, 'Pinned baseline summary digest refused')
        current, baseline = reports
        require(current['source_sha'] == MERGE and current['run_id'] == str(run_id) and
                current['run_attempt'] == '1' and current['accepted'] is False and
                current['measurement_valid'] is False and current['results'] is None and
                current['attempts'] == [] and current['references'] == [] and
                current['problems'] == ['Baseline environment refused'], 'Current refusal report identity refused')
        require(baseline['source_sha'] == '887e1bb59ef6f28c15824cb7593654f3610f3cef' and
                baseline['run_id'] == '39899829270' and baseline['run_attempt'] == '1' and
                baseline['measurement_valid'] is True, 'Frozen baseline identity refused')
        keys = ('cpu_model', 'compiler', 'reference')
        report['current_environment'] = {key: current['environment'][key] for key in keys}
        report['baseline_environment'] = {key: baseline['environment'][key] for key in keys}
        report['different_fields'] = [key for key in keys if current['environment'][key] != baseline['environment'][key]]
        report['diagnostic_completed'] = True
    except Exception as error:
        report['problems'].append(str(error))
        report['diagnostic_completed'] = False
    (output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
