#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Join two same-run CPU exports without pooling measurements or altering budgets."""
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
from export_reading_cpu_baseline import CPU_IDS, ENVIRONMENT_KEYS, encoded, print_file
from measure_reading_real import BUDGETS, git, sha256


def combine_entries(drafts, legacy_hash):
    require(len(drafts) == len(CPU_IDS) == 2, 'both independent exports required')
    legacy = None
    entries = []
    for environment_id in sorted(CPU_IDS):
        draft = drafts[environment_id]
        require(draft['schema'] == 1 and draft['legacy_budget_sha256'] == legacy_hash and
                len(draft['environments']) == 2, 'export registry draft identity differs')
        old, new = draft['environments']
        require(old['id'] == 'amd-epyc-7763' and old['budget_path'] == 'tests/reading_real/budgets.json' and
                old['budget_sha256'] == legacy_hash and new['id'] == environment_id and
                new['budget_path'] == f'tests/reading_real/environments/{environment_id}/budgets.json' and
                re.fullmatch('[0-9a-f]{64}', new['budget_sha256']), 'registry path/hash identity differs')
        require(legacy is None or old == legacy, 'legacy environment entries differ between independent exports')
        legacy = old
        entries.append(new)
    entries.insert(0, legacy)
    for entry in entries:
        environment = entry['environment']
        require(set(environment) == set(ENVIRONMENT_KEYS) and
                all(isinstance(environment[key], str) and environment[key] for key in ENVIRONMENT_KEYS),
                'exact six-string environment identity required')
    require(len({tuple(entry['environment'][key] for key in ENVIRONMENT_KEYS) for entry in entries}) == len(entries),
            'duplicate environment identity')
    require(all(entry['environment']['cpu_model'] == CPU_IDS[entry['id']] for entry in entries[1:]),
            'new CPU identity differs from its registered export')
    return {'schema': 1, 'legacy_budget_sha256': legacy_hash, 'environments': entries}


def member_bytes(archive, name):
    names = archive.namelist()
    require(len(names) == len(set(names)) and len(names) <= 1000, 'duplicate/excessive export artifact members')
    for candidate in names:
        path = PurePosixPath(candidate)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in candidate and
                not re.match(r'^[A-Za-z]:', candidate), 'unsafe export artifact path')
    require(names.count(name) == 1, 'export evidence file missing/duplicate: ' + name)
    info = archive.getinfo(name)
    require(0 < info.file_size <= 4 * 1024 * 1024 and not info.is_dir() and
            stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG), 'invalid export evidence file')
    return archive.read(info)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'join only in GitHub Actions')
    source, run_id, attempt = git('rev-parse', 'HEAD'), int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    require(source == os.environ['GITHUB_SHA'] and not args.output.exists(), 'join source/output identity differs')
    run = fetch(f'actions/runs/{run_id}')
    require(run['head_sha'] == source and run['run_attempt'] == attempt and
            run['path'] == '.github/workflows/reading-cpu-baseline-export.yml', 'join workflow identity differs')
    jobs = pages(f'actions/runs/{run_id}/jobs', 'jobs')
    artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
    legacy_bytes = BUDGETS.read_bytes()
    legacy_hash = hashlib.sha256(legacy_bytes).hexdigest()
    args.output.mkdir(parents=True)
    drafts = {}
    verified = []
    for environment_id in sorted(CPU_IDS):
        matched_jobs = [job for job in jobs if job['name'] == 'export-' + environment_id]
        require(len(matched_jobs) == 1 and matched_jobs[0]['status'] == 'completed' and
                matched_jobs[0]['conclusion'] == 'success' and matched_jobs[0]['head_sha'] == source and
                matched_jobs[0]['run_attempt'] == attempt, 'independent export job did not succeed at this source')
        artifact_name = f'cpu-baseline-export-{environment_id}-{run_id}-{attempt}'
        matching = [artifact for artifact in artifacts if artifact['name'] == artifact_name]
        require(len(matching) == 1, 'independent export artifact missing/duplicate')
        artifact = matching[0]
        require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == source and
                re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')), 'export artifact metadata differs')
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / 'export.zip'
            with archive_path.open('wb') as stream:
                download_artifact_zip(artifact['id'], stream)
            require(archive_path.stat().st_size == artifact['size_in_bytes'] and
                    'sha256:' + sha256(archive_path) == artifact['digest'], 'export ZIP size/digest differs')
            with zipfile.ZipFile(archive_path) as archive:
                report = json.loads(member_bytes(archive, 'result/export.json'))
                require(report['exported'] is True and report['accepted'] is False and
                        report['measurement_performed'] is False and report['problems'] == [] and
                        report['source_sha'] == source and str(report['run_id']) == str(run_id) and
                        str(report['attempt']) == str(attempt) and report['legacy_budget_sha256'] == legacy_hash and
                        report['raw_native_processes_verified'] == 40 and report['raw_reference_processes_verified'] == 12 and
                        report['exact_image_pairs'] == 12 and report['route_signatures_equal'] is True,
                        'export report identity/verification differs')
                draft = json.loads(member_bytes(archive, 'result/registry-entry-draft.json'))
                drafts[environment_id] = draft
                expected_budget = f'tests/reading_real/environments/{environment_id}/budgets.json'
                expected_review = f'docs/validation/reading-real-{environment_id}-pixel-review.json'
                require(report['budget_path'] == expected_budget and report['review_path'] == expected_review,
                        'export report destination differs')
                require(draft['environments'][1]['environment'] == report['environment'] and
                        draft['environments'][1]['budget_sha256'] == report['budget_sha256'],
                        'draft differs from independently verified export')
                for relative, hash_key in ((expected_budget, 'budget_sha256'), (expected_review, 'review_sha256')):
                    data = member_bytes(archive, 'result/tree/' + relative)
                    require(hashlib.sha256(data).hexdigest() == report[hash_key], 'exported source bytes differ')
                    destination = args.output / 'tree' / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
        verified.append({key: artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes')})
    registry = combine_entries(drafts, legacy_hash)
    registry_bytes = encoded(registry)
    registry_path = args.output / 'tree/tests/reading_real/environments.json'
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_bytes(registry_bytes)
    require(BUDGETS.read_bytes() == legacy_bytes, 'legacy budget bytes changed')
    report = {'schema': 1, 'exported': True, 'accepted': False, 'source_sha': source,
              'run_id': str(run_id), 'attempt': str(attempt), 'legacy_budget_sha256': legacy_hash,
              'independent_exports': verified, 'environments': 3,
              'registry_sha256': hashlib.sha256(registry_bytes).hexdigest(), 'problems': []}
    (args.output/'join.json').write_bytes(encoded(report))
    print_file('CPU_REGISTRY_FILE', registry_bytes)
    print('CPU_REGISTRY_JOIN_JSON_BEGIN\n' + json.dumps(report) + '\nCPU_REGISTRY_JOIN_JSON_END')


if __name__ == '__main__':
    main()
