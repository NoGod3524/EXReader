#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import os
import unittest
from continuation_contract import CASE, STAGES, case_name, verdict


class ContinuationControls(unittest.TestCase):
    def test_even_clean_diagnostic_is_never_strict_acceptance(self):
        report = verdict(dict.fromkeys(STAGES, True))
        self.assertTrue(report['strict_privacy_checks_passed'])
        self.assertFalse(report['accepted']); self.assertFalse(report['full_f10_accepted'])
        self.assertTrue(report['diagnostic_only'])

    def test_each_failed_strict_observation_survives_continuation(self):
        for stage in STAGES:
            checks = dict.fromkeys(STAGES, True); checks[stage] = False
            report = verdict(checks)
            self.assertFalse(report['strict_privacy_checks_passed'])
            self.assertEqual(report['failed_strict_checkpoints'], [stage])
            self.assertFalse(report['accepted'])

    def test_incomplete_or_unknown_stages_refuse(self):
        for checks in ({}, dict.fromkeys(STAGES[:-1], True), dict.fromkeys(STAGES + ['foreign'], True)):
            with self.assertRaises(RuntimeError): verdict(checks)

    def test_nonboolean_verdicts_refuse(self):
        for value in (0, 1, 'false', None):
            checks = dict.fromkeys(STAGES, True); checks[STAGES[0]] = value
            with self.assertRaises(RuntimeError): verdict(checks)

    def test_strict_case_cannot_be_replayed_as_diagnostic(self):
        self.assertEqual(case_name(CASE), CASE)
        with self.assertRaises(RuntimeError): case_name('testRememberThenUncheckUpdateDoesNotPersistSessionCredential')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    unittest.main()
