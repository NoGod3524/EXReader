#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic regressions for the same-attempt artefact aggregation gate.

The aggregation job must reject a summary that drops, duplicates, renames or
fails any of the fixed named results, and it must reject a mismatched negative
case list. These fixtures prove that on the real validator, without any network
or artefact download.
"""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reader_distribution_windows'))
import aggregate_artifacts
import verify_distribution

CASES = []


def case(label):
    CASES.append(label)
    print('case:', label, flush=True)


def summary(source='a' * 40, run='40135232301', attempt='1'):
    results = [{'name': name, 'status': 'pass'} for name in verify_distribution.REQUIRED_RESULTS]
    results += [{'name': name, 'status': 'pass'} for name in verify_distribution.REQUIRED_NEGATIVES]
    return {'schema': 'reader-distribution-windows-summary-v1', 'accepted': True,
            'source_sha': source, 'ci': {'GITHUB_RUN_ID': run, 'GITHUB_RUN_ATTEMPT': attempt},
            'negative_cases': list(verify_distribution.REQUIRED_NEGATIVES), 'results': results}


def expect_refusal(label, document, source='a' * 40, run='40135232301', attempt='1'):
    try:
        aggregate_artifacts.validate_summary(document, source, run, attempt)
    except ValueError as error:
        case(label + ':' + str(error).split(':')[0][:48])
        return str(error)
    raise AssertionError('aggregation accepted ' + label)


def main():
    document = summary()
    results = aggregate_artifacts.validate_summary(document, 'a' * 40, '40135232301', '1')
    statuses = {item['name']: item['status'] for item in results}
    assert statuses['summary-named-results-complete'] == 'pass', statuses
    assert statuses['summary-source-bound'] == 'pass'
    assert statuses['summary-same-run-and-attempt'] == 'pass'
    assert len(verify_distribution.REQUIRED_RESULTS) == 20, len(verify_distribution.REQUIRED_RESULTS)
    assert len(verify_distribution.REQUIRED_NEGATIVES) == 4
    case('summary-complete-contract-accepted')

    missing = summary()
    missing['results'] = [item for item in missing['results']
                          if item['name'] != 'nine-format-smoke-complete']
    message = expect_refusal('missing-required-result', missing)
    assert 'nine-format-smoke-complete' in message, message

    duplicated = summary()
    duplicated['results'].append({'name': 'stage-scanned-clean', 'status': 'pass'})
    message = expect_refusal('duplicate-result', duplicated)
    assert 'duplicate' in message, message

    renamed = summary()
    for item in renamed['results']:
        if item['name'] == 'deterministic-seal':
            item['name'] = 'deterministic-seal-relaxed'
    message = expect_refusal('substituted-result-name', renamed)
    assert 'missing' in message or 'unexpected' in message, message

    failed = summary()
    for item in failed['results']:
        if item['name'] == 'archive-tamper-evident':
            item['status'] = 'fail'
    message = expect_refusal('failed-result-status', failed)
    assert 'failing' in message, message

    dropped_negative = summary()
    dropped_negative['results'] = [item for item in dropped_negative['results']
                                   if item['name'] != 'negative-scan-blocks-leaking-control']
    message = expect_refusal('missing-negative-result', dropped_negative)
    assert 'negative-scan-blocks-leaking-control' in message, message

    short_negative_list = summary()
    short_negative_list['negative_cases'] = list(verify_distribution.REQUIRED_NEGATIVES)[:3]
    message = expect_refusal('negative-case-list-shortened', short_negative_list)
    assert 'negative case list' in message, message

    extra_negative = summary()
    extra_negative['results'].append({'name': 'negative-not-in-contract', 'status': 'pass'})
    message = expect_refusal('unexpected-negative-result', extra_negative)
    assert 'unexpected' in message, message

    empty = summary()
    empty['results'] = []
    message = expect_refusal('empty-results', empty)
    assert 'no named results' in message, message

    wrong_source = summary(source='b' * 40)
    results = aggregate_artifacts.validate_summary(wrong_source, 'a' * 40, '40135232301', '1')
    statuses = {item['name']: item['status'] for item in results}
    assert statuses['summary-source-bound'] == 'fail', statuses
    case('cross-source-summary-rejected')

    wrong_attempt = summary(attempt='2')
    results = aggregate_artifacts.validate_summary(wrong_attempt, 'a' * 40, '40135232301', '1')
    statuses = {item['name']: item['status'] for item in results}
    assert statuses['summary-same-run-and-attempt'] == 'fail', statuses
    case('cross-attempt-summary-rejected')

    drifted = summary()
    drifted['results'] = copy.deepcopy(drifted['results'])
    for item in drifted['results']:
        if item['name'] == 'pkgconfig-metadata-relocatable':
            item['name'] = 'pkgconfig-metadata-usable'
    expect_refusal('pkgconfig-result-cannot-be-renamed', drifted)

    print(json.dumps({'accepted': True, 'checks': len(CASES), 'cases': CASES}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except AssertionError as error:
        print('fixture failure: ' + str(error), file=sys.stderr)
        sys.exit(1)
