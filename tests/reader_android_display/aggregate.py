#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
import subprocess
import sys
from strict import decoded, need, selected, verify


def api(path):
    done = subprocess.run(['gh', 'api', path], capture_output=True, timeout=180)
    need(done.returncode == 0, 'GitHub API failure: ' + done.stderr.decode('utf-8', 'replace')[-400:])
    return decoded(done.stdout)


def pages(path, field):
    result = []
    for page in range(1, 21):
        body = api(path + f'?per_page=100&page={page}')
        rows = body.get(field); need(type(rows) is list, 'API list type'); result += rows
        if len(result) >= body['total_count']:
            need(len(result) == body['total_count'], 'API page count'); return result
        need(len(rows) > 0, 'API missing page')
    raise RuntimeError('API page bound')


def download(path):
    done = subprocess.run(['gh', 'api', '--allow-escape-sequences', path], capture_output=True, timeout=180)
    need(done.returncode == 0, 'GitHub evidence download failure')
    return done.stdout


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    output = Path('build/aggregate'); output.mkdir(parents=True, exist_ok=True)
    inputs = Path('build/display-downloads'); inputs.mkdir(parents=True, exist_ok=True)
    result = {'accepted': False, 'complete_product': False}
    try:
        repo = os.environ['GITHUB_REPOSITORY']; sha = os.environ['GITHUB_SHA']
        run_id = int(os.environ['GITHUB_RUN_ID']); attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
        base = f'/repos/{repo}/actions/runs/{run_id}'
        run = api(base + f'/attempts/{attempt}')
        jobs = pages(base + f'/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(base + '/artifacts', 'artifacts')
        artifact = selected(artifacts, f'reader-android-display-native-{run_id}-{attempt}')
        job = selected(jobs, 'Android API34 native display')
        data = download(f'/repos/{repo}/actions/artifacts/{artifact["id"]}/zip')
        log = download(f'/repos/{repo}/actions/jobs/{job["id"]}/logs')
        module_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD:extras/android-reader-display'], text=True).strip()
        bundle = dict(run=run, jobs=jobs, artifacts=artifacts, repo=repo, sha=sha,
                      run_id=run_id, attempt=attempt, module_tree=module_tree)
        (inputs / 'metadata.json').write_text(json.dumps(bundle))
        (inputs / 'native.zip').write_bytes(data); (inputs / 'producer.log').write_bytes(log)
        result = verify(data=data, log=log, **bundle)
    except Exception as error:
        result = {'accepted': False, 'complete_product': False, 'error': type(error).__name__ + ': ' + str(error)}
    (output / 'aggregate.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['accepted'] else 1


if __name__ == '__main__': sys.exit(main())
