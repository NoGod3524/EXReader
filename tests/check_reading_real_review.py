#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bind actual twelve-page reviews to the pinned baseline, not earlier images."""
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_reading_real_budgets import verify_review


def main():
    artifact = {'id': 456, 'digest': 'sha256:' + 'd' * 64}
    baseline = {'source_sha': 'a' * 40, 'run_id': '123', 'run_attempt': '1',
                'references': [{'case': 'pdf-' + str(index // 3), 'page': index % 3,
                                'native_identity': {'sha256': f'{index:064x}'},
                                'reference_identity': {'sha256': f'{index + 100:064x}'}}
                               for index in range(12)]}
    review = {'schema': 1, 'render_parity_granted': False, 'baseline_source_sha': baseline['source_sha'],
              'baseline_run_id': 123, 'baseline_run_attempt': 1,
              'baseline_artifact_id': artifact['id'], 'baseline_artifact_digest': artifact['digest'],
              'pages': [{'case': row['case'], 'page': row['page'], 'native_sha256': row['native_identity']['sha256'],
                         'reference_sha256': row['reference_identity']['sha256'], 'reviewed': True,
                         'finding': 'synthetic protocol fixture; no actual image review credit'} for row in baseline['references']]}
    verify_review(review, baseline, artifact)
    changes = {
        'old_source': lambda value: value.update(baseline_source_sha='b' * 40),
        'wrong_run': lambda value: value.update(baseline_run_id=124),
        'wrong_attempt': lambda value: value.update(baseline_run_attempt=2),
        'wrong_artifact': lambda value: value.update(baseline_artifact_id=457),
        'wrong_zip_digest': lambda value: value.update(baseline_artifact_digest='sha256:' + 'e' * 64),
        'parity_claim': lambda value: value.update(render_parity_granted=True),
        'old_three_pages': lambda value: value.update(pages=value['pages'][:3]),
        'wrong_native': lambda value: value['pages'][0].update(native_sha256='f' * 64),
        'wrong_reference': lambda value: value['pages'][0].update(reference_sha256='f' * 64),
        'not_reviewed': lambda value: value['pages'][0].update(reviewed=False),
        'empty_finding': lambda value: value['pages'][0].update(finding=' '),
        'duplicate_page': lambda value: value['pages'].__setitem__(0, copy.deepcopy(value['pages'][1])),
        'reordered_pages': lambda value: value['pages'].reverse(),
    }
    for name, change in changes.items():
        altered = copy.deepcopy(review)
        change(altered)
        try:
            verify_review(altered, baseline, artifact)
        except (ValueError, KeyError, TypeError):
            continue
        raise AssertionError('invalid review accepted: ' + name)
    print(json.dumps({'protocol_only': True, 'positive': 1, 'refusals': len(changes), 'passed': True}))


if __name__ == '__main__':
    main()
