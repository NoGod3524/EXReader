#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the pinned rejected environment in Actions without executing a benchmark."""
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require
from join_reading_cpu_exports import member_bytes
from reading_real_environments import FIELDS, REGISTRY, environment_key, read

RUN = 40035574150
JOB = 120694075328
HEAD = '4aa25cf7b1aef19b31a1a86830d59e8880c3b57a'
SOURCE = '6d582273241ac014622fadda5c20111f97056840'
ARTIFACT = 12536408174
SIZE = 17455734
DIGEST = '20a2f4013161c3b693c7fc4a6f657346a83880e99e94f47cc68daa953a4f6847'
ROOT = Path(__file__).resolve().parents[1]


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Actions repository required')
    output = ROOT / 'build/rejected-environment'
    output.mkdir(parents=True, exist_ok=False)
    report = {'diagnostic_only': True, 'accepted': False, 'measurement_performed': False,
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'inspected_run': RUN,
              'inspected_attempt': 1, 'inspected_head': HEAD, 'inspected_source': SOURCE,
              'inspected_job': JOB, 'artifact_id': ARTIFACT, 'artifact_bytes': SIZE,
              'artifact_sha256': DIGEST, 'problems': []}
    try:
        run, job = fetch(f'actions/runs/{RUN}'), fetch(f'actions/jobs/{JOB}')
        require(run['id'] == RUN and run['head_sha'] == HEAD and run['run_attempt'] == 1 and
                run['path'] == '.github/workflows/reading-required.yml', 'Run identity differs')
        require(job['id'] == JOB and job['run_id'] == RUN and job['head_sha'] == HEAD and
                job['run_attempt'] == 1 and job['name'] == 'performance / reading-performance' and
                job['status'] == 'completed' and job['conclusion'] == 'failure', 'Failed job identity differs')
        name = f'reading-real-{RUN}-1'
        found = [item for item in pages(f'actions/runs/{RUN}/artifacts', 'artifacts')
                 if item['id'] == ARTIFACT or item['name'] == name]
        require(len(found) == 1, 'Missing/duplicate original artifact')
        artifact = found[0]
        require(artifact['id'] == ARTIFACT and artifact['name'] == name and
                artifact['size_in_bytes'] == SIZE and artifact['digest'] == 'sha256:' + DIGEST and
                artifact['expired'] is False and artifact['workflow_run']['id'] == RUN and
                artifact['workflow_run']['head_sha'] == HEAD, 'Artifact identity differs')
        raw = download_artifact_zip(ARTIFACT)
        require(len(raw) == SIZE and hashlib.sha256(raw).hexdigest() == DIGEST, 'ZIP size/hash differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            payload = member_bytes(archive, 'reading-real/summary.json')
        current = json.loads(payload)
        require(current['source_sha'] == SOURCE and current['run_id'] == str(RUN) and
                current['run_attempt'] == '1' and current['accepted'] is False and
                current['measurement_valid'] is False and current['results'] is None and
                current['attempts'] == [] and current['references'] == [] and current['problems'] ==
                ['Baseline environment refused: no exact frozen environment'], 'Refusal identity differs')
        environment_key(current['environment'])
        registry = read(ROOT / REGISTRY)
        report['environment'] = {field: current['environment'][field] for field in FIELDS}
        report['registered_differences'] = [
            {'id': item['id'], 'different_fields': [field for field in FIELDS
             if item['environment'][field] != current['environment'][field]], 'environment': item['environment']}
            for item in registry['environments']]
        require(all(item['different_fields'] for item in report['registered_differences']),
                'Unexpected exact registered environment')
        report['summary_sha256'] = hashlib.sha256(payload).hexdigest()
        report['diagnostic_completed'] = True
    except Exception as error:
        report['diagnostic_completed'] = False
        report['problems'].append(str(error))
    (output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
