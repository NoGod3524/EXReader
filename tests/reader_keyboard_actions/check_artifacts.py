#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-run evidence for the three keyboard-actions jobs.

The verifier reads the run, its jobs and its artifacts through the API, then
downloads each platform ZIP and re-computes its size and SHA-256, opens the
report inside it, and refuses anything that is expired, cross-source,
cross-attempt, empty, renamed or inconsistent between platforms."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_keyboard import (CASE_C, CASE_CPP, CASE_PROBE, DOCUMENTED_SKIPS,  # noqa: E402
                            COMMON_START, PACKAGE)

WORKFLOW = '.github/workflows/reader-keyboard-actions.yml'
PLATFORMS = (('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022'), ('macOS', 'macos-14'))
EXPECTED_CASES = len(CASE_C) + len(CASE_CPP) + len(CASE_PROBE)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    source = os.environ['GITHUB_SHA']
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        'accepted': False,
        'package': PACKAGE,
        'common_start': COMMON_START,
        'source_sha': source,
        'run_id': run_id,
        'attempt': attempt,
        'artifacts': [],
        'jobs': [],
        'platforms': {},
        'skipped': {},
        'uncovered': [],
        'problems': [],
        'checks_per_platform': 0,
        'granted_platforms': [],
        'macos_accepted': False,
        'host_ui_accepted': False,
        'performance_claimed': False,
        'six_platform_accepted': False,
        'complete_product': False,
        'sdk_changed': False,
        'schema_changed': False,
    }
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source and run['run_attempt'] == attempt,
                'caller identity differs')
        require(run['path'].split('@')[0] == WORKFLOW, 'wrong workflow')
        require(run['conclusion'] == 'success', 'the run did not succeed')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        outcomes = []
        for platform, runner in PLATFORMS:
            artifact_name = 'reader-keyboard-actions-%s-%d-%d' % (platform, run_id, attempt)
            job_name = 'keyboard actions (%s)' % runner
            matches = [a for a in artifacts if a['name'] == artifact_name]
            require(len(matches) == 1, 'missing or duplicate artifact ' + artifact_name)
            artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing or duplicate job ' + job_name)
            job = matches[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and
                    job['conclusion'] == 'success', 'upstream failed or had another source')
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                    artifact['workflow_run']['head_sha'] == source, 'artifact identity differs')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'], 'ZIP bytes differ')
            require('sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'],
                    'ZIP digest differs')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                report = json.loads(archive.read('keyboard-evidence/result.json'))
            require(report.get('accepted') is True, 'report refused: %s' % report.get('problems'))
            require(report.get('package') == PACKAGE, 'package identity differs')
            require(report.get('common_start') == COMMON_START, 'common start differs')
            require(report.get('source_sha') == source, 'report source differs')
            require(int(report.get('run_id', 0)) == run_id and
                    int(report.get('attempt', 0)) == attempt, 'report identity differs')
            require(report.get('granted_platform') == platform.lower(), 'platform grant differs')
            require(int(report.get('checks', 0)) == EXPECTED_CASES and
                    len(report.get('cases', [])) == EXPECTED_CASES, 'case count differs')
            cases = sorted((case['suite'], case['name'], case['status'])
                           for case in report['cases'])
            for suite, expected in (('consumer-c', CASE_C), ('consumer-cpp', CASE_CPP),
                                    ('probe', CASE_PROBE)):
                names = {name for suite_name, name, _ in cases if suite_name == suite}
                require(names == set(expected), '%s case identity differs on %s' % (suite, platform))
            statuses = {(suite, name): status for suite, name, status in cases}
            for key, status in statuses.items():
                require(status != 'FAIL', 'a named case failed on %s: %s' % (platform, key))
                if status == 'SKIP':
                    require(key[1] in DOCUMENTED_SKIPS, 'undocumented skip ' + key[1])
            skipped = sorted(name for (suite, name), status in statuses.items() if status == 'SKIP')
            outcomes.append(sorted(statuses.items()))
            summary['platforms'][platform.lower()] = {
                'case_names': len(statuses),
                'skipped': skipped,
                'binaries': report.get('binaries', {}),
            }
            summary['skipped'][platform.lower()] = skipped
            summary['artifacts'].append({key: artifact[key] for key in
                                         ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({key: job[key] for key in ('id', 'name', 'conclusion')})
            summary['granted_platforms'].append(platform.lower())
        require(len(outcomes) == 3 and outcomes[0] == outcomes[1] == outcomes[2],
                'the three platforms reported different case sets or statuses')
        summary['checks_per_platform'] = EXPECTED_CASES
        summary['uncovered'] = [{'case': name, 'reason': reason}
                                for name, reason in sorted(DOCUMENTED_SKIPS.items())
                                if any(name in skipped for skipped in summary['skipped'].values())]
        summary['accepted'] = True
        summary['macos_accepted'] = True
    except Exception as error:  # noqa: BLE001 - refusal is evidence
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (out / 'report.md').write_text(
        '# keyboard-actions artifact authentication\n\n'
        '- source: %s\n- run: %s attempt %s\n- accepted: %s\n- checks per platform: %d\n'
        '- problems: %s\n' % (source, run_id, attempt, summary['accepted'],
                              summary['checks_per_platform'],
                              '; '.join(summary['problems']) if summary['problems'] else 'none'),
        encoding='utf-8')
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__':
    main()
