#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export one independently measured CPU baseline in Actions; never publish it."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require
from export_reading_real_budgets import derive_budget, verify_review
from measure_reading_real import (BUDGETS, CONTRACT, MANIFEST, PROTECTED, ROOT, SDK,
    audit, baseline_origin, git, read, sha256, verify_baseline_report)

ENVIRONMENT_KEYS = ('runner_os', 'runner_arch', 'runner_image', 'cpu_model', 'compiler', 'reference')
CPU_IDS = {
    'amd-epyc-9v45': 'AMD EPYC 9V45 96-Core Processor',
    'intel-xeon-8573c': 'INTEL(R) XEON(R) PLATINUM 8573C',
}
MAX_MEMBER = 128 * 1024 * 1024
MAX_SELECTED = 512 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')


def print_file(marker, data):
    print(marker + '_BEGIN')
    sys.stdout.write(data.decode('utf-8'))
    print(marker + '_END')


def committed(path):
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    require(subprocess.check_output(['git', 'show', 'HEAD:' + relative], cwd=ROOT) == path.read_bytes(),
            'export input must be committed byte-for-byte: ' + relative)
    return relative


def provenance_for(source, run_id):
    run = fetch(f'actions/runs/{run_id}')
    artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
    require(len(artifacts) == 1 and artifacts[0]['name'] == f'reading-real-{run_id}-{run["run_attempt"]}',
            'one independent baseline artifact required')
    artifact = artifacts[0]
    return {'baseline_source_sha': source, 'baseline_run_id': run_id,
            'baseline_run_attempt': run['run_attempt'], 'baseline_artifact_id': artifact['id'],
            'baseline_artifact_digest': artifact['digest']}


def extract_raw(archive, output):
    """Extract only authenticated report dependencies, rejecting unsafe ZIP paths."""
    infos = archive.infolist()
    names = [item.filename for item in infos]
    require(len(infos) <= 10000 and len(set(names)) == len(names), 'duplicate or excessive baseline ZIP members')
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and
                not re.match(r'^[A-Za-z]:', name), 'unsafe baseline ZIP member')
    summary_name = 'reading-real/summary.json'
    require(summary_name in names and archive.getinfo(summary_name).file_size <= 16 * 1024 * 1024,
            'missing or oversized baseline summary')
    summary_bytes = archive.read(summary_name)
    summary = json.loads(summary_bytes.decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    dependencies = set()
    for row in summary['attempts']:
        dependencies.update(row[key] for key in ('stdout', 'stderr'))
    for row in summary['references']:
        dependencies.update(row[key] for key in ('stdout', 'stderr', 'native', 'reference'))
    selected = {summary_name, *('reading-real/' + name for name in dependencies),
                'identity/build/reading-real-consumer/reading-real-benchmark',
                'identity/build/reading-real-font/Reader.otf',
                'identity/tests/reading_real/contract.json', 'identity/tools/reading_corpus/real-v1.json'}
    require(sum(archive.getinfo(name).file_size for name in selected) <= MAX_SELECTED,
            'baseline selected evidence exceeds its byte limit')
    for name in selected:
        info = archive.getinfo(name)
        member = PurePosixPath(name)
        require(name in names and not member.is_absolute() and '..' not in member.parts and
                '\\' not in name and info.file_size <= MAX_MEMBER and not info.is_dir() and
                stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG), 'invalid baseline raw member')
        destination = output.joinpath(*member.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(info))
    return summary, summary_bytes, output / 'reading-real'


def retain_raw(origin, directory):
    archive_path = directory / 'baseline.zip'
    with archive_path.open('wb') as stream:
        download_artifact_zip(origin['artifact']['id'], stream)
    require(archive_path.stat().st_size == origin['artifact']['size_in_bytes'] and
            'sha256:' + sha256(archive_path) == origin['artifact']['digest'], 'baseline ZIP size/digest refused')
    with zipfile.ZipFile(archive_path) as archive:
        summary, summary_bytes, raw = extract_raw(archive, directory / 'raw')
    archive_path.unlink()
    (directory / 'baseline-summary.json').write_bytes(summary_bytes)
    origin.update(summary_file='baseline-summary.json', summary_sha256=sha256(directory / 'baseline-summary.json'))
    return summary, raw


def verify_raw(summary, raw, origin):
    run = origin['run']
    require(summary['source_sha'] == run['head_sha'] and summary['run_id'] == str(run['id']) and
            summary['run_attempt'] == str(run['run_attempt']) and summary['measurement_valid'] is True and
            summary['accepted'] is False and summary['budget_sha256'] is None and
            len(summary['attempts']) == 40 and len(summary['references']) == 12,
            'complete independent unbudgeted 40+12 baseline required')
    require(summary['sdk_candidate'] == SDK and summary['before'] == summary['after'] and
            summary['before']['source_clean'] and summary['before']['source_tree'] ==
            git('rev-parse', summary['source_sha'] + '^{tree}') and
            all(summary['before']['sdk_trees'][path] == git('rev-parse', 'HEAD:' + path) ==
                git('rev-parse', SDK + ':' + path) == git('rev-parse', summary['source_sha'] + ':' + path)
                for path in PROTECTED), 'baseline protected source differs from frozen SDK')
    require(summary['contract_sha256'] == sha256(CONTRACT) and summary['contract'] == read(CONTRACT) and
            summary['corpus_manifest_sha256'] == sha256(MANIFEST), 'baseline contract/corpus changed')
    identity = raw.parent / 'identity'
    for path, expected in ((identity/'build/reading-real-consumer/reading-real-benchmark', summary['before']['binary']),
                           (identity/'build/reading-real-font/Reader.otf', summary['before']['font'])):
        require({'bytes': path.stat().st_size, 'sha256': sha256(path)} == expected,
                'retained native consumer or font identity differs')
    require(sha256(identity/'tests/reading_real/contract.json') == summary['contract_sha256'] and
            sha256(identity/'tools/reading_corpus/real-v1.json') == summary['corpus_manifest_sha256'],
            'retained contract/manifest bytes differ')
    installed = summary['installed_sdk']
    require(isinstance(installed['files'], dict) and installed['files'] and
            installed['bytes'] == sum(item['bytes'] for item in installed['files'].values()) and
            all(type(item['bytes']) is int and item['bytes'] >= 0 and
                re.fullmatch('[0-9a-f]{64}', item['sha256']) for item in installed['files'].values()),
            'installed SDK inventory/size accounting differs')
    expected_identity = {'GITHUB_SHA': run['head_sha'], 'GITHUB_RUN_ID': str(run['id']),
                         'GITHUB_RUN_ATTEMPT': str(run['run_attempt'])}
    # audit() checks ambient identity. Bind that check only to the separately
    # authenticated earlier run while replaying its retained bytes; no process
    # measurement occurs here and exporter provenance stays separate.
    with patch.dict(os.environ, expected_identity):
        require(audit(summary, raw, None) == summary['results'], 'raw baseline metrics/signatures differ from summary')
    for item in summary['references']:
        for key in ('stdout', 'stderr'):
            require(sha256(raw / item[key]) == item[key + '_sha256'], 'reference process log digest refused')
    require(summary['refusal_regression']['passed'] is True and
            summary['signature_refusal_regression']['passed'] is True, 'baseline refusal regressions incomplete')
    return {key: summary['environment'][key] for key in ENVIRONMENT_KEYS}


def inherited_review(old_review, old_baseline, old_artifact, baseline, artifact, review_path, review_hash):
    verify_review(old_review, old_baseline, old_artifact)
    pairs = [(row['case'], row['page'], row['native_identity']['sha256'], row['reference_identity']['sha256'])
             for row in baseline['references']]
    reviewed = [(row['case'], row['page'], row['native_sha256'], row['reference_sha256']) for row in old_review['pages']]
    require(len(pairs) == 12 and pairs == reviewed, 'new image bytes differ; a new explicit page review is required')
    require(baseline['results']['page_signatures'] == old_baseline['results']['page_signatures'],
            'new route signatures differ; a new explicit signature review is required')
    result = copy.deepcopy(old_review)
    result.update(baseline_source_sha=baseline['source_sha'], baseline_run_id=int(baseline['run_id']),
                  baseline_run_attempt=int(baseline['run_attempt']), baseline_artifact_id=artifact['id'],
                  baseline_artifact_digest=artifact['digest'])
    result['equivalence_source'] = {
        'policy': 'exact-twelve-native-and-reference-image-sha256-and-all-route-signatures',
        'review_path': review_path, 'review_sha256': review_hash,
        'baseline_source_sha': old_baseline['source_sha'], 'baseline_run_id': int(old_baseline['run_id']),
        'baseline_run_attempt': int(old_baseline['run_attempt']),
        'baseline_artifact_id': old_artifact['id'], 'baseline_artifact_digest': old_artifact['digest'],
        'new_visual_review_claimed': False,
    }
    verify_review(result, baseline, artifact)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source-sha', required=True)
    parser.add_argument('--baseline-run-id', type=int, required=True)
    parser.add_argument('--environment-id', choices=sorted(CPU_IDS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'CPU baseline export runs only in cloud CI')
    require(re.fullmatch('[0-9a-f]{40}', args.baseline_source_sha) and args.baseline_run_id > 0,
            'immutable source and run ID required')
    require(not args.output.exists(), 'preserve previous export evidence; choose a new output')
    args.output.mkdir(parents=True)
    exporter_source = git('rev-parse', 'HEAD')
    require(exporter_source == os.environ['GITHUB_SHA'], 'exporter checkout identity mismatch')
    committed(BUDGETS)
    legacy_bytes = BUDGETS.read_bytes()
    legacy_hash = hashlib.sha256(legacy_bytes).hexdigest()
    legacy = read(BUDGETS)
    review_file = ROOT / legacy['pixel_review_path']
    review_path = committed(review_file)
    require(sha256(review_file) == legacy['pixel_review_sha256'], 'legacy pixel review digest changed')
    provenance = provenance_for(args.baseline_source_sha, args.baseline_run_id)
    origin = baseline_origin(provenance, exporter_source)  # Original guards remain unchanged.
    legacy_origin = baseline_origin(legacy, exporter_source)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        candidate = temporary / 'candidate'; candidate.mkdir()
        old = temporary / 'legacy'; old.mkdir()
        baseline, raw = retain_raw(origin, candidate)
        environment = verify_raw(baseline, raw, origin)
        require(all(isinstance(environment[key], str) and environment[key] for key in ENVIRONMENT_KEYS) and
                environment['runner_os'] == 'Linux' and environment['runner_arch'] == 'X64' and
                environment['runner_image'] == 'ubuntu22' and
                environment['cpu_model'] == CPU_IDS[args.environment_id], 'requested exact CPU environment differs from seed')
        old_baseline, old_raw = retain_raw(legacy_origin, old)
        verify_raw(old_baseline, old_raw, legacy_origin)
        require(legacy_origin['summary_sha256'] == legacy['baseline_summary_sha256'], 'legacy baseline summary changed')
        review = inherited_review(read(review_file), old_baseline, legacy_origin['artifact'], baseline,
                                  origin['artifact'], review_path, sha256(review_file))
        new_review_path = f'docs/validation/reading-real-{args.environment_id}-pixel-review.json'
        review_bytes = encoded(review)
        budget = derive_budget(baseline, provenance, origin, new_review_path,
                               hashlib.sha256(review_bytes).hexdigest())
        context = copy.deepcopy(baseline); context['baseline_origin'] = origin
        verify_baseline_report(budget, context, candidate)
        budget_bytes = encoded(budget)
        budget_path = f'tests/reading_real/environments/{args.environment_id}/budgets.json'
        for relative, data in ((new_review_path, review_bytes), (budget_path, budget_bytes)):
            destination = args.output / 'tree' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        legacy_environment = {key: old_baseline['environment'][key] for key in ENVIRONMENT_KEYS}
        registry = {'schema': 1, 'legacy_budget_sha256': legacy_hash, 'environments': [
            {'id': 'amd-epyc-7763', 'environment': legacy_environment,
             'budget_path': 'tests/reading_real/budgets.json', 'budget_sha256': legacy_hash},
            {'id': args.environment_id, 'environment': environment, 'budget_path': budget_path,
             'budget_sha256': hashlib.sha256(budget_bytes).hexdigest()}]}
        (args.output / 'registry-entry-draft.json').write_bytes(encoded(registry))
        require(BUDGETS.read_bytes() == legacy_bytes, 'legacy budget bytes changed during export')
        report = {'schema': 1, 'exported': True, 'accepted': False, 'measurement_performed': False,
            'source_sha': exporter_source, 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'seed': provenance, 'environment': environment,
            'legacy_budget_sha256': legacy_hash, 'raw_native_processes_verified': 40,
            'raw_reference_processes_verified': 12, 'exact_image_pairs': 12,
            'route_signatures_equal': True, 'review_path': new_review_path,
            'review_sha256': hashlib.sha256(review_bytes).hexdigest(),
            'budget_path': budget_path, 'budget_sha256': hashlib.sha256(budget_bytes).hexdigest(),
            'problems': []}
        (args.output / 'export.json').write_bytes(encoded(report))
        print('CPU_BASELINE_EXPORT_JSON_BEGIN\n' + json.dumps(report, allow_nan=False) + '\nCPU_BASELINE_EXPORT_JSON_END')
        print('CPU_BUDGET_JSON_BEGIN\n' + json.dumps(budget, allow_nan=False) + '\nCPU_BUDGET_JSON_END')
        print('CPU_REVIEW_JSON_BEGIN\n' + json.dumps(review, allow_nan=False) + '\nCPU_REVIEW_JSON_END')
        print('CPU_REGISTRY_DRAFT_JSON_BEGIN\n' + json.dumps(registry, allow_nan=False) + '\nCPU_REGISTRY_DRAFT_JSON_END')
        print_file('CPU_BUDGET_FILE', budget_bytes)
        print_file('CPU_REVIEW_FILE', review_bytes)


if __name__ == '__main__':
    main()
