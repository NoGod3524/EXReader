# SPDX-License-Identifier: MIT
"""Actions-only same-source scope check; known palette failures stay failures."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re


def check_names(names, legacy_originals=False):
    assert all(isinstance(name, str) and name for name in names)
    duplicates = {name: count for name, count in Counter(names).items() if count > 1}
    if not legacy_originals:
        assert not duplicates
        return
    # The fixed F4 probe exports both committed receipts of one duplicate book.
    # Its unchanged checker labels those two exports by the same SDK ID and by
    # the final receipt's path. Only these three exact paired checks may repeat.
    known = [name for name in duplicates if re.fullmatch(r'import\.original\.known\.[1-9][0-9]*', name)]
    assert len(known) == 1
    tails = [tail for tail in ('sample.epub', '重复/副本.epub')
             if 'import.original.sha.' + tail in duplicates]
    assert len(tails) == 1
    assert duplicates == {known[0]: 2, 'import.original.sha.' + tails[0]: 2,
                          'import.original.bytes.' + tails[0]: 2}


def check_name_protocol():
    legacy = ['import.original.known.7'] * 2 + ['import.original.sha.sample.epub'] * 2 + ['import.original.bytes.sample.epub'] * 2
    cases = [(['one', 'two'], False, True), (['one', 'one'], False, False),
             (legacy, True, True), (legacy + ['one', 'one'], True, False),
             (legacy + ['import.original.known.7'], True, False),
             (legacy[:-1], True, False),
             ([name.replace('sample.epub', 'unrelated.txt') for name in legacy], True, False),
             ([name.replace('known.7', 'known.0') for name in legacy], True, False)]
    for names, legacy_originals, expected in cases:
        try:
            check_names(names, legacy_originals)
            passed = True
        except AssertionError:
            passed = False
        assert passed is expected, (names, expected)
    print('EVIDENCE_NAME_PROTOCOL checks=8 all passed', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true')
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    check_name_protocol()
    build = args.build
    source = os.environ['GITHUB_SHA']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    binary = build / 'account-package/EXReader-Linux/bin/exreader-linux'
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    report = dict(accepted=False, batch_import_scope_passed=False, complete_product=False,
                  settings_whole_page_palette_accepted=False, diagnostic_only=args.diagnostic,
                  source_sha=source, run_id=run_id, attempt=attempt, program_sha256=digest, verified={})

    def load(path, *, count=None, grant=None):
        value = json.loads((build / path).read_text())
        assert value.get('source_sha', value.get('source')) == source, path
        if 'run_id' in value:
            assert str(value['run_id']) == run_id and str(value['attempt']) == attempt, path
        if 'program_sha256' in value:
            assert value['program_sha256'] == digest, path
        if grant:
            assert value[grant] is True, path
        if count is not None:
            checks = value['checks']
            assert len(checks) == count and all(row.get('passed', row.get('pass', row.get('ok'))) is True for row in checks), path
            names = [row.get('name') for row in checks]
            check_names(names, legacy_originals=path == 'gtk-batch-original/report.json')
        report['verified'][path] = dict(sha256=hashlib.sha256((build / path).read_bytes()).hexdigest(), count=count)
        return value

    try:
        own = load('gtk-batch-ui/report.json', count=27, grant='batch_import_scope_passed')
        assert own['checks_failed'] == 0 and own['accepted'] is False and own['complete_product'] is False
        assert own['diagnostic_only'] is False and own['program_source_sha'] == source
        required = {
            'native_flat_scan_exact_results_and_real_file_failures',
            'normal_completion_does_not_mean_truncation_or_cancellation',
            'native_receipt_window_is_at_most_32_rows',
            'all_public_original_bytes_and_sha_match_sources_no_link_imports',
            'sdk_ids_product_keys_bytes_and_progress_stable_after_reopen',
            'native_recursive_depth_budget_truthfully_truncates',
            'native_cancel_stops_later_items_and_keeps_committed',
            'application_close_reconciles_committed_book_without_resuming_later_files',
            'enumeration_staging_and_import_never_mutate_any_source_file',
            'every_cancel_and_shutdown_original_is_a_byte_exact_selected_regular_file',
        }
        assert required.issubset({row['name'] for row in own['checks']})
        load('gtk-batch-original/report.json', count=668, grant='ok')
        load('gtk-batch-review/review.json', count=4, grant='ok')
        log = (build / 'gtk-batch-backend/checks.log').read_text()
        match = re.search(r'GTK_BATCH_BACKEND checks=(\d+) all passed', log)
        assert match and int(match[1]) > 600, log[-2000:]
        report['backend_checks'] = int(match[1])
        faults = load('gtk-batch-owner-faults/report.json', count=3, grant='ok')
        assert faults['allocation_failures'] == 2
        assert {row['name'] for row in faults['checks']} == {'allocation-failure-map-close', 'allocation-failure-direct-close', 'empty-directory-map-close'}
        report['owner_fault_scenarios'] = 3
        report['batch_import_scope_passed'] = True
        if not args.diagnostic:
            load('records-ui/report.json', count=30, grant='reading_records_scope_passed')
            load('gtk-navigation-ui/result.json', count=29, grant='navigation_scope_passed')
            load('gtk-search-ui/result.json', count=30, grant='search_scope_passed')
            settings = load('preferences-ui/result.json')
            assert settings['accepted'] is False and settings['diagnostic_only'] is False
            assert settings['count'] == 35 and settings['passed'] == 33 and settings['failed'] == 2
            failed = [row['name'] for row in settings['checks'] if row['pass'] is False]
            assert set(failed) == {'light_foreground_and_background_change_page_pixels', 'dark_theme_and_palette_change_page_pixels'}
            report['retained_sdk_failures'] = failed
            report['all_reading_navigation_search_and_non_palette_settings_retained'] = True
        report['ok'] = True
    except BaseException as error:
        report['ok'] = False
        report['error'] = repr(error)
        raise
    finally:
        (build / 'gtk-batch-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
