#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect two retained JSON reports in Actions; never execute a consumer."""
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require

RUN = 39991113462
JOB = 120542797965
HEAD = 'de9871aca6a54f70c6c1d147ba12f308cedf1004'
MERGE = '6cb92c16ac6b36922551a64b52f323afd6406539'
ARTIFACT = 12517309623
NAME = 'reading-real-39991113462-1'
BYTES = 17484694
DIGEST = '85aabaf7ca19f8b7f6b95e31c027bb5479f2f09e58b8d901363e90110c396d9a'
BASELINE_SUMMARY = 'f83c42b738127ce52ee2a4ddb8653fbda36b03e8cd56adf5971fd1f219e3135d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Cloud repository required')
    output = Path('build/reading-environment-diagnostic')
    output.mkdir(parents=True, exist_ok=False)
    report = {'diagnostic_only': True, 'accepted': False, 'engine_executed': False,
              'diagnostic_source': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'inspected_run': RUN, 'inspected_attempt': 1, 'inspected_head': HEAD,
              'inspected_merge': MERGE, 'inspected_job': JOB, 'artifact_id': ARTIFACT, 'problems': []}
    try:
        run, job = fetch(f'actions/runs/{RUN}'), fetch(f'actions/jobs/{JOB}')
        require(run['id'] == RUN and run['head_sha'] == HEAD and run['run_attempt'] == 1 and
                run['path'] == '.github/workflows/reading-required.yml', 'Run identity refused')
        require(job['id'] == JOB and job['run_id'] == RUN and job['head_sha'] == HEAD and
                job['run_attempt'] == 1 and job['name'] == 'performance / reading-performance' and
                job['status'] == 'completed' and job['conclusion'] == 'failure', 'Failed job identity refused')
        selected = [row for row in pages(f'actions/runs/{RUN}/artifacts', 'artifacts')
                    if row['id'] == ARTIFACT or row['name'] == NAME]
        require(len(selected) == 1, 'Artifact missing/duplicate')
        artifact = selected[0]
        require(artifact['id'] == ARTIFACT and artifact['name'] == NAME and artifact['size_in_bytes'] == BYTES and
                artifact['digest'] == 'sha256:' + DIGEST and artifact['expired'] is False and
                artifact['workflow_run']['id'] == RUN and artifact['workflow_run']['head_sha'] == HEAD,
                'Artifact metadata refused')
        raw = download_artifact_zip(ARTIFACT)
        require(len(raw) == BYTES and sha(raw) == DIGEST, 'Artifact ZIP bytes/digest refused')
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
        require(current['source_sha'] == MERGE and current['run_id'] == str(RUN) and
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
