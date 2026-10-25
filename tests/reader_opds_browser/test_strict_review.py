#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only negative regression tests for strict evidence authentication."""
import copy
import os
import unittest
from check_artifacts import validate_cases, validate_job, validate_members

class StrictReview(unittest.TestCase):
    def test_job_identity(self):
        good = dict(head_sha='source', run_id=12, run_attempt=2,
                    status='completed', conclusion='success')
        validate_job(good, 'source', 12, 2)
        for field, value in [('head_sha', 'other'), ('run_id', 13), ('run_attempt', 1),
                             ('status', 'in_progress'), ('conclusion', 'failure')]:
            with self.subTest(field=field):
                bad = dict(good, **{field: value})
                with self.assertRaises(ValueError):
                    validate_job(bad, 'source', 12, 2)

    def test_members(self):
        good = ['opds-evidence/result.json', 'opds-consumer/opds-consumer']
        validate_members(good)
        for extra in ['opds-evidence/result.json', 'other/result.json', '../escape',
                      '/absolute', 'foo\\bar', 'foo/../bar', 'foo//bar', 'C:/absolute']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_members(good + [extra])
        with self.assertRaises(ValueError):
            validate_members(['opds-consumer/opds-consumer'])

    def test_cases(self):
        good = {'checks': 60, 'cases': [{'id': 'case_%d' % i, 'ok': True} for i in range(60)]}
        self.assertEqual(len(validate_cases(good)), 60)
        for value in [False, 'true', 1, None]:
            bad = copy.deepcopy(good)
            bad['cases'][0]['ok'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_cases(bad)
        bad = copy.deepcopy(good)
        bad['cases'][0]['id'] = bad['cases'][1]['id']
        with self.assertRaises(ValueError):
            validate_cases(bad)
        bad = copy.deepcopy(good)
        bad['checks'] = 59
        with self.assertRaises(ValueError):
            validate_cases(bad)
        with self.assertRaises(ValueError):
            validate_cases({'checks': 59, 'cases': good['cases'][:59]})

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Actions only: no local tests')
    unittest.main()
