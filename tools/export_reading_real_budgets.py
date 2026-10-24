#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Export the pinned baseline's review template or reviewed numeric budgets in CI."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import tempfile

from check_parallel_integration import fetch, pages, require


def verify_review(review, baseline, artifact):
    require(review.get('schema') == 1 and review.get('render_parity_granted') is False and
            review.get('baseline_source_sha') == baseline['source_sha'] and
            str(review.get('baseline_run_id')) == baseline['run_id'] and
            str(review.get('baseline_run_attempt')) == baseline['run_attempt'] and
            review.get('baseline_artifact_id') == artifact['id'] and
            review.get('baseline_artifact_digest') == artifact['digest'], 'pixel review belongs to another baseline/artifact')
    expected = [(item['case'], item['page'], item['native_identity']['sha256'], item['reference_identity']['sha256'])
                for item in baseline['references']]
    rows = review.get('pages', [])
    require(len(expected) == len(rows) == 12 and
            [(item['case'], item['page'], item['native_sha256'], item['reference_sha256']) for item in rows] == expected,
            'pixel review must cover all twelve exact baseline image pairs in order')
    require(all(item.get('reviewed') is True and isinstance(item.get('finding'), str) and item['finding'].strip()
                for item in rows), 'each baseline page requires an actual recorded review')


def derive_budget(baseline, provenance, origin, review_path, review_sha256):
    """Apply the original contract formula to one complete, independent run."""
    policy = baseline['contract']['budget_derivation']
    cases = {}
    for name, metrics in baseline['results']['cases'].items():
        limits = {}
        for key, result in metrics.items():
            measured = result['p95']
            limits[key] = (measured * policy['latency_multiplier_max'] if key.endswith('_ms') else
                           measured if key == 'oversize_fallbacks' else 0 if key == 'explicit_snapshot_bytes' else
                           math.floor(measured * policy['byte_multiplier_max'] + policy['memory_slack_bytes_max']))
        cases[name] = limits
    return dict(provenance, schema=1, frozen=True, render_parity_granted=False,
                baseline_summary_sha256=origin['summary_sha256'],
                contract_sha256=baseline['contract_sha256'], corpus_manifest_sha256=baseline['corpus_manifest_sha256'],
                cpu_model=baseline['environment']['cpu_model'], compiler=baseline['environment']['compiler'],
                cases=cases,
                consumer_bytes=math.floor(baseline['before']['binary']['bytes'] * policy['byte_multiplier_max'] +
                                          policy['consumer_slack_bytes_max']),
                installed_sdk_bytes=math.floor(baseline['installed_sdk']['bytes'] * policy['byte_multiplier_max']),
                pixel_tolerances={f'{item["case"]}/{item["page"]}':
                                  min(1, item['normalized_mean_absolute_error'] + policy['external_difference_slack_max'])
                                  for item in baseline['results']['pixel_comparisons']},
                page_signatures=baseline['results']['page_signatures'],
                signature_policy='exact-baseline-route-rgba-utf8-position',
                pixel_review_path=review_path, pixel_review_sha256=review_sha256,
                signature_review_record=review_path, pixel_review_record=review_path)


def main():
    from measure_reading_real import (CONTRACT, MANIFEST, PROTECTED, SDK, baseline_origin, git, read,
                                     retain_baseline_report, sha256, verify_baseline_report)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source-sha', required=True)
    parser.add_argument('--baseline-run-id', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-record', type=Path)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'budget export runs only in cloud CI')
    require(re.fullmatch('[0-9a-f]{40}', args.baseline_source_sha) and args.baseline_run_id > 0,
            'immutable baseline source and positive run ID required')
    require(not args.output.exists(), 'export output already exists')
    args.output.mkdir(parents=True)
    run = fetch(f'actions/runs/{args.baseline_run_id}')
    artifacts = pages(f'actions/runs/{args.baseline_run_id}/artifacts', 'artifacts')
    matches = [item for item in artifacts if item['name'] == f'reading-real-{run["id"]}-{run["run_attempt"]}']
    require(len(matches) == 1, 'unique baseline artifact required')
    artifact = matches[0]
    provenance = {'baseline_source_sha': args.baseline_source_sha, 'baseline_run_id': args.baseline_run_id,
                  'baseline_run_attempt': run['run_attempt'], 'baseline_artifact_id': artifact['id'],
                  'baseline_artifact_digest': artifact['digest']}
    origin = baseline_origin(provenance, git('rev-parse', 'HEAD'))
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        retain_baseline_report(origin, directory)
        baseline = read(directory / 'baseline-summary.json')
        require(baseline.get('measurement_valid') is True and baseline.get('render_parity_granted') is False and
                baseline['sdk_candidate'] == SDK and baseline['source_sha'] == args.baseline_source_sha and
                len(baseline['attempts']) == 40 and all(item['exit_code'] == 0 and not item.get('failure')
                                                     for item in baseline['attempts']), 'complete 40-process baseline required')
        require(baseline['before'] == baseline['after'] and baseline['before']['source_clean'] and
                all(baseline['before']['sdk_trees'][path] == git('rev-parse', 'HEAD:' + path) ==
                    git('rev-parse', SDK + ':' + path) for path in PROTECTED), 'export SDK differs from accepted baseline')
        require(baseline['contract'] == read(CONTRACT) and baseline['contract_sha256'] == sha256(CONTRACT) and
                baseline['corpus_manifest_sha256'] == sha256(MANIFEST), 'baseline contract or corpus changed')
        review_template = dict(provenance, schema=1, render_parity_granted=False,
                               pages=[{'case': item['case'], 'page': item['page'],
                                       'native_sha256': item['native_identity']['sha256'],
                                       'reference_sha256': item['reference_identity']['sha256'],
                                       'reviewed': False, 'finding': ''} for item in baseline['references']])
        (args.output / 'review-template.json').write_text(json.dumps(review_template, indent=2) + '\n', encoding='utf-8')
        print('REVIEW_TEMPLATE_JSON_BEGIN\n' + json.dumps(review_template, allow_nan=False) + '\nREVIEW_TEMPLATE_JSON_END')
        if args.review_record is None:
            return
        review = read(args.review_record)
        verify_review(review, baseline, artifact)
        review_path = args.review_record.resolve().relative_to(Path.cwd().resolve()).as_posix()
        require(git('show', 'HEAD:' + review_path).strip() == args.review_record.read_text(encoding='utf-8').strip(),
                'review record must be committed at the exporter source')
        budget = derive_budget(baseline, provenance, origin, review_path, sha256(args.review_record))
        context = copy.deepcopy(baseline)
        context['baseline_origin'] = origin
        verify_baseline_report(budget, context, directory)
        (args.output / 'budgets.json').write_text(json.dumps(budget, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print('FROZEN_BUDGET_JSON_BEGIN\n' + json.dumps(budget, allow_nan=False) + '\nFROZEN_BUDGET_JSON_END')


if __name__ == '__main__':
    main()
