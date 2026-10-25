# SPDX-License-Identifier: MIT
"""Run the installed annotation-view consumers and judge their real report.

Actions only. The original book is generated here; the C++ probe builds the
product history, SDK library and every expectation through public APIs.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED = [
    'dataset_history_size', 'book_has_more_than_1000_annotations', 'book_has_exactly_100_annotations',
    'direct_scan_has_safe_concurrent_pending_blocked', 'annotation_ids_are_distinct_across_books',
    'product_dump_covers_history_outbox_and_database',
    'forward_scan_matches_direct_public_pages_limit_100', 'forward_scan_matches_direct_public_pages_limit_1',
    'forward_scan_matches_direct_public_pages_limit_7', 'forward_scan_matches_direct_public_pages_limit_33',
    'reverse_scan_matches_direct_public_pages', 'limit_100_over_1203_is_13_pages', 'all_states_and_kinds_are_distinguished',
    'reverse_cursor_returns_previous_100_in_descending_order', 'reverse_of_first_page_is_empty_and_complete',
    'next_cursor_continues_without_overlap', 'host_resolution_is_recorded_only_in_the_snapshot', 'page_free_zeroes_the_page',
    'exact_100_items_yield_full_page_then_empty_complete_page', 'complete_cursor_stays_complete', 'second_book_scan_matches_direct_pages',
    'scan_epub_v1_v2_duplicate_spine', 'scan_fixed_pages_textless_v1_v2', 'scan_large_notes_default_budget',
    'duplicate_spine_path_is_told_apart_by_part_and_v1_has_no_part', 'book_without_annotations_is_one_empty_complete_page',
    'largest_legal_fields_roundtrip_within_default_budget', 'page_budget_stops_before_a_row_and_resumes_without_loss',
    'invalid_budget_and_option_size_are_refused', 'cursor_of_another_book_binding_version_direction_or_shape_is_refused',
    'a_foreign_after_id_never_leaks_another_books_rows', 'invalid_book_keys_are_refused_by_open_or_the_store',
    'limit_direction_and_null_arguments_are_refused', 'another_thread_is_refused_and_the_handle_survives',
    'poll_count_is_reported_and_exact', 'cancel_at_every_poll_point_discards_the_page_and_retry_is_identical',
    'cancel_after_the_last_poll_changes_nothing', 'descending_page_polls_the_same_way',
    'reentrant_page_and_close_from_the_cancel_callback_are_busy_and_change_nothing', 'view_is_usable_after_refused_reentry',
    'product_history_outbox_and_database_unchanged_after_all_reads', 'sdk_progress_notes_and_library_file_unchanged_after_all_reads',
    'concurrent_insert_and_tombstone_between_pages_has_no_duplicate_or_gap', 'tombstone_is_shown_as_safe_deletion_without_a_body',
    'rescan_after_mutation_equals_new_direct_scan', 'page_is_readable_after_view_store_and_sdk_are_closed',
]
UNCOVERED = [
    'macOS/iOS/Android hosts and any non-desktop build',
    'host navigation: this module never resolves or navigates; FOUND/MISSING/AMBIGUOUS/LEGACY are recorded by the host only',
    'UI, accessibility, real devices and WebDAV transport',
    'cross-device product synchronization of annotations',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    Path(log).write_text(f'$ {" ".join(map(str, command))}\nexit={result.returncode}\n--- stdout\n{result.stdout}\n--- stderr\n{result.stderr}', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ('probe', 'c-consumer', 'output', 'link-map'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    out = Path(args.output)
    work = out / 'work'
    work.mkdir(parents=True, exist_ok=False)
    problems = []

    def need(ok, message):
        if not ok:
            problems.append(message)

    text = ('Annotation view fixture. 书签与标注列表快照 🙂\n' * 40).encode('utf-8')
    book = out / 'book.txt'
    book.write_bytes(text)
    book_sha = hashlib.sha256(text).hexdigest()
    probe = run([args.probe, '--work', str(work), '--book', str(book), '--sha', book_sha], out / 'probe.log')
    need(probe.returncode == 0, f'probe exit {probe.returncode}')
    report_path = work / 'report.json'
    report = None
    c_line = ''
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        # The probe rewrites the whole report after every check, so a fault still
        # names its exact step. Only a finished run may be judged as accepted.
        need(report.get('complete') is True, f"probe report is not complete: stopped during {report.get('last_trace')}")
        names = {c['name']: c for c in report['checks']}
        for name in REQUIRED:
            need(name in names, f'required check missing: {name}')
        for check in report['checks']:
            need(check['pass'], f'failed: {check["name"]} {check["detail"]}')
        need(report['checks_failed'] == 0 and report['checks_total'] >= len(REQUIRED), 'check totals disagree')
        need(report['book_a_initial'] > 1000 and report['book_a_final'] == report['book_a_initial'] + 2, 'book A totals unexpected')
        # The probe closed its stores; the C consumer reads the final product catalog independently.
        c = run([args.c_consumer, str(work / 'product.sqlite'), report['book_a_key'], str(report['book_a_final'])], out / 'c-consumer.log')
        need(c.returncode == 0 and ' failed=0' in c.stdout, f'C consumer failed: {c.stdout.strip()} {c.stderr.strip()}')
        c_line = c.stdout.strip()
    else:
        problems.append('probe produced no report')
    link_map = Path(args.link_map)
    need(link_map.exists() and link_map.stat().st_size > 0, 'link map missing')
    summary = {
        'identity': {k: os.environ.get(k) for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'RUNNER_OS')},
        'problems': problems, 'module_version': report and report['module_version'], 'checks_total': report and report['checks_total'],
        'checks_failed': report and report['checks_failed'], 'book_a_initial': report and report['book_a_initial'],
        'book_a_final': report and report['book_a_final'], 'history_revisions': report and report['history_revisions'],
        'c_consumer': c_line, 'probe_complete': report and report.get('complete'),
        'probe_last_trace': report and report.get('last_trace'), 'probe_sha256': sha(args.probe), 'c_consumer_sha256': sha(args.c_consumer),
        'report_sha256': sha(report_path) if report_path.exists() else None, 'link_map_sha256': sha(link_map) if link_map.exists() else None,
        'annotation_view_accepted_on_this_platform': not problems, 'uncovered': UNCOVERED,
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
