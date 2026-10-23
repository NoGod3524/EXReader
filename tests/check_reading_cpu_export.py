#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud protocol checks for exact-byte review inheritance and original formulas."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_reading_cpu_baseline import CPU_IDS, ENVIRONMENT_KEYS, extract_raw, inherited_review
from export_reading_real_budgets import derive_budget
from join_reading_cpu_exports import combine_entries


def refused(operation):
    try:
        operation()
    except (ValueError, KeyError, TypeError):
        return
    raise AssertionError('invalid CPU baseline export accepted')


def main():
    old_artifact = {'id': 7, 'digest': 'sha256:' + 'a' * 64}
    references = [{'case': f'pdf-{i // 3}', 'page': i % 3,
                   'native_identity': {'sha256': f'{i:064x}'},
                   'reference_identity': {'sha256': f'{i + 50:064x}'}} for i in range(12)]
    old = {'source_sha': 'a' * 40, 'run_id': '100', 'run_attempt': '1', 'references': references,
           'results': {'page_signatures': {'route': {'pixel_hash': '1' * 16}}}}
    review = {'schema': 1, 'render_parity_granted': False, 'baseline_source_sha': 'a' * 40,
              'baseline_run_id': 100, 'baseline_run_attempt': 1, 'baseline_artifact_id': old_artifact['id'],
              'baseline_artifact_digest': old_artifact['digest'],
              'pages': [{'case': item['case'], 'page': item['page'],
                         'native_sha256': item['native_identity']['sha256'],
                         'reference_sha256': item['reference_identity']['sha256'],
                         'reviewed': True, 'finding': 'synthetic protocol fixture; no visual review credit'}
                        for item in references]}
    new = copy.deepcopy(old)
    new.update(source_sha='b' * 40, run_id='200')
    artifact = {'id': 8, 'digest': 'sha256:' + 'b' * 64}
    args = (review, old, old_artifact, new, artifact, 'docs/old-review.json', 'c' * 64)
    result = inherited_review(*args)
    assert result['baseline_source_sha'] == 'b' * 40 and result['baseline_artifact_id'] == 8
    assert result['pages'] == review['pages']
    assert result['equivalence_source']['review_sha256'] == 'c' * 64
    assert result['equivalence_source']['new_visual_review_claimed'] is False
    changes = {
        'native_byte': lambda value: value['references'][0]['native_identity'].update(sha256='f' * 64),
        'reference_byte': lambda value: value['references'][0]['reference_identity'].update(sha256='f' * 64),
        'missing_pair': lambda value: value['references'].pop(),
        'duplicate_pair': lambda value: value['references'].__setitem__(0, copy.deepcopy(value['references'][1])),
        'reordered_pair': lambda value: value['references'].reverse(),
        'route_signature': lambda value: value['results']['page_signatures']['route'].update(pixel_hash='f' * 16),
    }
    for change in changes.values():
        altered = copy.deepcopy(new); change(altered)
        refused(lambda: inherited_review(review, old, old_artifact, altered, artifact, 'docs/old-review.json', 'c' * 64))
    for field, value in (('reviewed', False), ('finding', ' ')):
        altered = copy.deepcopy(review); altered['pages'][0][field] = value
        refused(lambda: inherited_review(altered, old, old_artifact, new, artifact, 'docs/old-review.json', 'c' * 64))
    baseline = {'contract': {'budget_derivation': {'latency_multiplier_max': 1.25,
                'byte_multiplier_max': 1.05, 'memory_slack_bytes_max': 1048576,
                'consumer_slack_bytes_max': 4096, 'external_difference_slack_max': 1 / 255}},
                'results': {'cases': {'book': {'open_ms': {'p95': 8}, 'peak_rss_bytes': {'p95': 10},
                    'oversize_fallbacks': {'p95': 1}, 'explicit_snapshot_bytes': {'p95': 0}}},
                    'pixel_comparisons': [{'case': 'book', 'page': 0, 'normalized_mean_absolute_error': .1}],
                    'page_signatures': {}}, 'contract_sha256': 'a' * 64, 'corpus_manifest_sha256': 'b' * 64,
                'environment': {'cpu_model': 'CPU', 'compiler': 'compiler'},
                'before': {'binary': {'bytes': 100}}, 'installed_sdk': {'bytes': 200}}
    budget = derive_budget(baseline, {}, {'summary_sha256': 'd' * 64}, 'docs/new-review.json', 'e' * 64)
    assert budget['cases']['book'] == {'open_ms': 10, 'peak_rss_bytes': 1048586,
                                      'oversize_fallbacks': 1, 'explicit_snapshot_bytes': 0}
    assert budget['consumer_bytes'] == 4201 and budget['installed_sdk_bytes'] == 210
    assert set(ENVIRONMENT_KEYS) == {'runner_os', 'runner_arch', 'runner_image', 'cpu_model', 'compiler', 'reference'}
    assert len(CPU_IDS) == 2 and not any('9V74' in name or '8370' in name for name in CPU_IDS.values())
    old_environment = {key: 'fixed-' + key for key in ENVIRONMENT_KEYS}
    old_environment['cpu_model'] = 'AMD EPYC 7763 64-Core Processor'
    legacy = {'id': 'amd-epyc-7763', 'environment': old_environment,
              'budget_path': 'tests/reading_real/budgets.json', 'budget_sha256': 'c' * 64}
    drafts = {}
    for environment_id, cpu in CPU_IDS.items():
        environment = dict(old_environment, cpu_model=cpu)
        drafts[environment_id] = {'schema': 1, 'legacy_budget_sha256': 'c' * 64,
            'environments': [copy.deepcopy(legacy), {'id': environment_id, 'environment': environment,
                'budget_path': f'tests/reading_real/environments/{environment_id}/budgets.json',
                'budget_sha256': 'd' * 64}]}
    assert len(combine_entries(drafts, 'c' * 64)['environments']) == 3
    first = sorted(CPU_IDS)[0]
    registry_changes = {
        'missing_cpu': lambda value: value.pop(first),
        'wrong_legacy_hash': lambda value: value[first].update(legacy_budget_sha256='e' * 64),
        'legacy_environment_changed': lambda value: value[first]['environments'][0]['environment'].update(reference='other'),
        'extra_environment_field': lambda value: value[first]['environments'][1]['environment'].update(extra='unexpected'),
        'missing_environment_field': lambda value: value[first]['environments'][1]['environment'].pop('reference'),
        'wrong_cpu': lambda value: value[first]['environments'][1]['environment'].update(cpu_model='unmeasured 9V74'),
        'unsafe_budget_path': lambda value: value[first]['environments'][1].update(budget_path='../budgets.json'),
        'changed_legacy_path': lambda value: value[first]['environments'][0].update(budget_path='new-legacy.json'),
    }
    for change in registry_changes.values():
        altered = copy.deepcopy(drafts); change(altered)
        refused(lambda: combine_entries(altered, 'c' * 64))
    for unsafe in ('../outside', '/outside', 'reading-real/../../outside', 'C:/outside', 'a\\outside'):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(unsafe, b'unsafe')
        stream.seek(0)
        with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(stream) as archive:
            refused(lambda: extract_raw(archive, Path(directory)))
    print(json.dumps({'protocol_only': True, 'positive': 3, 'refused': len(changes) + 2 + 5 + len(registry_changes),
                      'budget_formula_unchanged': True, 'passed': True}))


if __name__ == '__main__':
    main()
