#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small protocol checks; execute only in GitHub Actions."""
import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'reader_wave3_package'))
from diagnostics import android_cases, candidate_identity, matrix_markdown, xctest_log


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('run diagnostics checks in GitHub Actions only')
    log = "\n".join((
        "Test Case '-[HostTests test01ImportDeduplicateAndErrors]' started.",
        '/tmp/HostTests.swift:42: error: -[HostTests test01ImportDeduplicateAndErrors] : XCTAssertTrue failed - missing import row',
        "Test Case '-[HostTests test01ImportDeduplicateAndErrors]' failed (4 seconds).",
        "Test Case '-[HostTests test13Other]' passed (1 seconds).",
        "Test Case '-[HostTests test01ImportDeduplicateAndErrors]' passed (1 seconds)."))
    result = xctest_log(log)
    assert result['failed'] == 1 and result['passed'] == 2
    assert result['failed_cases'][0]['name'] == 'test01ImportDeduplicateAndErrors'
    assert result['failed_cases'][0]['first_assertion']['line'] == 2
    assert result['first_assertion']['assertion'].endswith('missing import row')
    assert xctest_log('** TEST FAILED **')['tests'] == []
    validation = {'cases': [{'id': 'import_epub', 'status': 'fail', 'detail': 'import status missing'}],
                  'summary': {'passed': 0, 'failed': 1, 'skipped': 0, 'total': 1}}
    result = android_cases(validation)
    assert not result['accepted'] and result['first_failure']['detail'] == 'import status missing'
    validation['cases'][0]['status'] = 'pass'
    validation['summary'].update(passed=1, failed=0)
    assert android_cases(validation, expected_total=1)['accepted']
    validation['cases'].append(dict(validation['cases'][0]))
    assert not android_cases(validation, expected_total=2)['accepted']
    identity = {'source_sha': 'a' * 40, 'sdk_version': '3.41.0', 'target': 'ipad'}
    archive = {'name': 'EXReader-ipad.zip', 'sha256': 'b' * 64, 'bytes': 42}
    manifest = dict(identity, archive=archive, entry='EXReader.app/EXReader',
                    files={'EXReader.app/EXReader': {'sha256': 'c' * 64}},
                    provenance={'run_id': '12', 'attempt': '1'})
    unpack = dict(identity, archive=archive, entry=manifest['entry'], entry_sha256='c' * 64,
                  provenance=manifest['provenance'])
    report = dict(identity, package={'archive': archive}, entry=manifest['entry'],
                  entry_sha256='c' * 64, run_id='12', attempt='1')
    args = dict(source_sha='a' * 40, run_id='12', attempt='1', sdk_version='3.41.0')
    assert candidate_identity(manifest, unpack, report, **args) == []
    stale = copy.deepcopy(manifest)
    stale['provenance']['attempt'] = '2'
    assert any('manifest attempt' in p for p in candidate_identity(stale, unpack, report, **args))
    stale = copy.deepcopy(unpack)
    stale.pop('provenance')
    assert any('unpack run_id' in p for p in candidate_identity(manifest, stale, report, **args))
    stale = copy.deepcopy(report)
    stale['package']['archive']['sha256'] = 'd' * 64
    assert any('ZIP sha256' in p for p in candidate_identity(manifest, unpack, stale, **args))
    table = matrix_markdown({'targets': {'ipad': {'accepted': False, 'problems': ['failed | row']}}})
    assert table.count('未通过') == 6 and 'failed \\| row' in table
    print('diagnostics protocol checks passed; no platform GUI claim')


if __name__ == '__main__':
    main()
