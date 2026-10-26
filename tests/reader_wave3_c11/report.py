#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run acceptance for the C11 Android wave3 delivery.

Reads only evidence produced by this attempt: the ownership guard, the existing
uitest suites on the installed APK and the wave3 instrumentation phases. Every
identity (source commit, run, attempt, installed bytes, fixture hashes) is bound
to the environment. A missing or failing requirement is recorded, never skipped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
APP_REQUIRED_CASES = ('import_epub', 'open_epub', 'page_next', 'page_prev', 'font_increase', 'font_decrease')
WAVE3_REQUIRED = (
    'stage_cancel_before_and_after_rename_removes_private_files',
    'original_export_cancel_receipt_and_ordinary_exception_under_checkjni',
    'closed_panel_drops_real_pending_jump_peek_on_owner',
    'annotation_batch_cancel_retains_committed_receipt_and_stops_remaining_items',
    'wave3_surfaces_present_and_no_leases',
    'local_font_saf_import_select_lease_and_release',
    'invalid_font_rejected_and_library_unchanged',
    'quick_size_cancel_keeps_accepted_frame_and_stored_appearance',
    'quick_size_settings_failure_keeps_frame_and_stored_appearance',
    'original_export_private_original_receipt_and_saf_save',
    'annotation_export_private_files_and_saf_save',
    'annotation_import_wrong_book_rejected_without_write',
    'jump_history_back_forward_over_real_search_landing',
    'sync_status_view_without_session_and_real_failed_session',
    'rotation_keeps_selected_font_and_releases_leases',
    'toc_directory_entry_reaches_real_chapter',
    'annotation_preview_confirm_import_creates_records',
    'annotation_reimport_all_duplicates_no_new_rows',
    'tampered_file_rejected_before_any_write',
    'imported_bookmark_navigable_by_public_found',
)
OPERATIONS = {
    'import': 'android-walkthrough: import_epub',
    'open': 'android-walkthrough: open_epub',
    'page': 'android-walkthrough: page_next, page_prev',
    'settings': 'android-walkthrough: font_increase, font_decrease',
    'search': 'wave3-ui: jump_history_back_forward_over_real_search_landing',
    'toc': 'wave3-ui: toc_directory_entry_reaches_real_chapter',
    'annotations': 'wave3-ui: annotation export, preview, confirmed import and duplicate replay',
    'fonts': 'wave3-ui: SAF local font import, real layout lease and release',
    'original': 'wave3-ui: private original, per-item receipt and SAF save',
    'sync_view': 'wave3-ui: read-only sync status view over a real failed session',
    'jump_history': 'wave3-ui: back/forward over two real landings',
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guard', type=Path, required=True)
    parser.add_argument('--walkthrough', type=Path, required=True)
    parser.add_argument('--wave3', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    identity = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    problems, operations = [], {}
    app_sha = ''
    capture_count = 0
    if args.app.is_file():
        app_sha = sha256(args.app)
    else:
        problems.append('the packaged application artifact is missing')
    try:
        manifest = load(args.fixtures / 'manifest.json')
        epub = next(row for row in manifest['books'] if row['role'] == 'epub')
        epub_file = args.fixtures / epub['file']
        if sha256(epub_file) != epub['sha256']:
            problems.append('fixture manifest does not describe the epub bytes')
    except (OSError, ValueError, StopIteration, KeyError) as error:
        problems.append('fixtures: ' + type(error).__name__ + ': ' + str(error))
        epub = {}
    try:
        guard = load(args.guard)
        if guard.get('seed') != SEED:
            problems.append('guard: different seed')
        if guard.get('source_sha') != identity['source_sha']:
            problems.append('guard: different source')
        if guard.get('run_id') != identity['run_id'] or guard.get('attempt') != identity['attempt']:
            problems.append('guard: different run/attempt')
        if not guard.get('changed_paths'):
            problems.append('guard: no recorded change set')
    except (OSError, ValueError) as error:
        problems.append('guard: ' + type(error).__name__ + ': ' + str(error))
    try:
        execution = load(args.walkthrough / 'execution.json')
        if not execution.get('completed'):
            problems.append('walkthrough: device execution did not complete: ' + ', '.join(execution.get('errors') or []))
        for key in ('source_sha', 'run_id', 'attempt'):
            if execution.get(key) != identity[key]:
                problems.append('walkthrough: different ' + key)
        if execution.get('installed_sha256') != app_sha or execution.get('app_sha256') != app_sha:
            problems.append('walkthrough: the device did not run the packaged application bytes')
        expected_titles = {name: {'title': Path(name).stem, 'format': Path(name).suffix[1:].upper()}
                           for name in ('Sample.epub', 'Sample.txt', 'Sample.pdf',
                                        'BigChapter.epub', 'Ambiguous.epub', 'Second.epub')}
        if execution.get('expected_titles') != expected_titles:
            problems.append('walkthrough: explicit stem title and format contract is missing or changed')
        provenance = load(args.walkthrough / 'candidate-provenance.json')
        if any(provenance['expected_titles'].get(name) != value for name, value in expected_titles.items()):
            problems.append('walkthrough: candidate title expectations differ')
        drivers = provenance.get('drivers') or []
        if len(drivers) != 2 or any(not item.get('original_sha256') or not item.get('candidate_sha256') for item in drivers):
            problems.append('walkthrough: original and candidate driver hashes are missing')
        validation = load(args.walkthrough / 'walkthrough-evidence' / 'validation.json')
        summary = validation.get('summary') or {}
        if int(summary.get('failed') or 0) != 0 or int(summary.get('skipped') or 0) != 0:
            problems.append('walkthrough: failed or skipped case')
        if int(summary.get('passed') or 0) != int(summary.get('total') or -1) or int(summary.get('total') or 0) < 45:
            problems.append('walkthrough: inconsistent or incomplete case summary')
        if validation.get('apk_sha256') != app_sha:
            problems.append('walkthrough: validation filename describes another APK')
        cases = {item.get('id'): item.get('status') for item in validation.get('cases') or []}
        missing = [name for name in APP_REQUIRED_CASES if cases.get(name) != 'pass']
        if missing:
            problems.append('walkthrough: not passing: ' + ', '.join(missing))
        for operation in ('import', 'open', 'page', 'settings'):
            operations[operation] = OPERATIONS[operation]
        for suite, total in (('review', 10), ('bounded', 11)):
            regression = load(args.walkthrough / (suite + '-evidence') / 'validation.json')
            if regression.get('summary') != {'total': total, 'passed': total, 'failed': 0, 'skipped': 0}:
                problems.append(suite + ': frozen regression summary failed or changed')
            if len(regression.get('cases') or []) != total or any(item.get('status') != 'pass' for item in regression.get('cases') or []):
                problems.append(suite + ': missing or failing frozen regression case')
            for key in ('source_sha', 'run_id', 'attempt'):
                if regression.get(key) != identity[key]:
                    problems.append(suite + ': different ' + key)
            if regression.get('apk_sha256') != app_sha:
                problems.append(suite + ': different installed application bytes')
    except (OSError, ValueError, KeyError) as error:
        problems.append('walkthrough: ' + type(error).__name__ + ': ' + str(error))
    try:
        wave3 = load(args.wave3 / 'result.json')
        if wave3.get('accepted') is not True or wave3.get('wave3_ui_accepted') is not True:
            problems.append('wave3: the real UI phases did not accept')
        for key in ('source_sha', 'run_id', 'attempt'):
            if wave3.get(key) != identity[key]:
                problems.append('wave3: different ' + key)
        if wave3.get('apk_sha256') != app_sha or wave3.get('installed_apk_sha256') != app_sha:
            problems.append('wave3: the device did not run the packaged application bytes')
        if wave3.get('checkjni') != '1':
            problems.append('wave3: CheckJNI was not enabled')
        phases = {report.get('phase'): report for report in wave3.get('phases') or []}
        checks = {}
        for name in ('first', 'cancel', 'restore'):
            report = phases.get(name)
            if report is None:
                problems.append('wave3: missing phase ' + name)
                continue
            if report.get('passed') is not True or int(report.get('failed_checks') or 0) != 0:
                problems.append('wave3: phase ' + name + ' recorded failures')
            if int(report.get('font_leases') or 0) != 0:
                problems.append('wave3: phase ' + name + ' left font leases')
            for check in report.get('checks') or []:
                checks[check.get('name')] = check.get('pass')
        missing = [name for name in WAVE3_REQUIRED if checks.get(name) is not True]
        if missing:
            problems.append('wave3: not passing: ' + ', '.join(missing))
        stops = wave3.get('process_stops') or []
        if len(stops) != 3 or any(stop.get('pid_after_stop') for stop in stops):
            problems.append('wave3: the instrumented process was not actually stopped')
        sources = {item.get('what'): item for item in wave3.get('sources') or []}
        original = sources.get('saf-saved-original') or {}
        if epub and (original.get('sha256') != epub['sha256'] or original.get('bytes') != epub['bytes']):
            problems.append('wave3: the SAF original is not the complete fixture original')
        portable = sources.get('portable-annotations') or {}
        exported = args.wave3 / 'exported-annotations.jsonl'
        if not exported.is_file():
            problems.append('wave3: portable annotation export is missing')
        elif portable.get('sha256') != sha256(exported):
            problems.append('wave3: recorded annotation export identity differs')
        observed = wave3.get('captures') or []
        if len(observed) < 6:
            problems.append('wave3: too few real UI screenshots')
        for capture in observed:
            path = args.wave3 / 'captures' / (capture.get('phase') + '-' + capture.get('name') + '.png')
            if not path.is_file() or sha256(path) != capture.get('sha256'):
                problems.append('wave3: capture evidence is missing or changed: ' + path.name)
        capture_count = len(observed)
        for operation in ('search', 'toc', 'annotations', 'fonts', 'original', 'sync_view', 'jump_history'):
            operations[operation] = OPERATIONS[operation]
    except (OSError, ValueError, KeyError) as error:
        problems.append('wave3: ' + type(error).__name__ + ': ' + str(error))
    try:
        navigation = load(args.wave3.parent / 'navigation' / 'result.json')
        if navigation.get('accepted') is not True or navigation.get('navigation_ui_accepted') is not True:
            problems.append('navigation: original 18-case suite did not accept')
        for key in ('source_sha', 'run_id', 'attempt'):
            if navigation.get(key) != identity[key]:
                problems.append('navigation: different ' + key)
        phases = navigation.get('phases') or []
        if navigation.get('checks') != 18 or [(item.get('phase'), item.get('count')) for item in phases] != [('first', 16), ('reopen', 2)]:
            problems.append('navigation: original 16+2 case counts changed')
        for phase in phases:
            if phase.get('passed') is not True or phase.get('native_live') != 0 or not all(item.get('pass') is True for item in phase.get('checks') or []):
                problems.append('navigation: failed case or native snapshot leak')
        stops = navigation.get('process_stops') or []
        if len(stops) != 2 or any(item.get('pid_after_stop') for item in stops):
            problems.append('navigation: process-stop regression failed')
    except (OSError, ValueError, KeyError) as error:
        problems.append('navigation: ' + type(error).__name__ + ': ' + str(error))
    try:
        reading_folder = args.wave3.parent / 'reading'
        reading = load(reading_folder / 'result.json')
        if reading.get('accepted') is not True or reading.get('reading_ui_accepted') is not True:
            problems.append('reading: original 16-case suite did not accept')
        if sha256(args.wave3.parent / 'reading-installed.apk') != app_sha:
            problems.append('reading: installed host differs from the delivered APK')
        for key in ('source_sha', 'run_id', 'attempt'):
            if reading.get(key) != identity[key]:
                problems.append('reading: different ' + key)
        phases = reading.get('phases') or []
        if reading.get('checks') != 16 or [(item.get('phase'), item.get('count')) for item in phases] != [('first', 14), ('retry', 1), ('reopen', 1)]:
            problems.append('reading: original 14+1+1 case counts changed')
        for phase in phases:
            if phase.get('passed') is not True or len(phase.get('checks') or []) != phase.get('count') or not all(item.get('pass') is True for item in phase.get('checks') or []):
                problems.append('reading: missing or failed original case')
            if any(phase.get(key) != identity[key] for key in identity):
                problems.append('reading: phase has different source/run/attempt')
        if len({phase.get('pid') for phase in phases}) != 3:
            problems.append('reading: first/retry/reopen did not execute in three distinct processes')
        stops = reading.get('process_stops') or []
        if len(stops) != 3 or [item.get('phase') for item in stops] != ['first', 'retry', 'reopen'] or any(item.get('pid_after_stop') or item.get('requested') is not True for item in stops):
            problems.append('reading: actual process-stop regression failed')
        kill = reading.get('real_postcommit_kill') or {}
        pending = reading_folder / 'killed-pending-request.json'
        if kill.get('actual_postcommit_gate') is not True or not kill.get('pid_before_stop') or kill.get('pid_after_stop'):
            problems.append('reading: real postcommit kill was not observed')
        if sha256(pending) != kill.get('request_sha256') or pending.stat().st_size != kill.get('request_bytes'):
            problems.append('reading: killed durable request evidence changed or is missing')
        request = load(pending)
        if request.get('revision') != kill.get('revision_id') or request.get('annotation') != kill.get('annotation_id') or request.get('body') != 'lost response exact request' or request.get('operation') != 0:
            problems.append('reading: killed request identity differs from the exact retry')
    except (OSError, ValueError, KeyError) as error:
        problems.append('reading: ' + type(error).__name__ + ': ' + str(error))
    accepted = not problems and all(name in operations for name in OPERATIONS)
    result = {**identity, 'schema': 1, 'kind': 'reader-wave3-c11-android-acceptance', 'seed': SEED,
              'accepted': accepted, 'problems': problems,
              'missing_operations': [name for name in OPERATIONS if name not in operations],
              'operations': operations, 'app_sha256': app_sha, 'capture_count': capture_count,
              'source_tree': '', 'requires': 'android-x86_64 API34 emulator, real APK and real UI'}
    try:
        result['source_tree'] = json.loads(Path(args.guard).read_text(encoding='utf-8')).get('tree', '')
    except (OSError, ValueError):
        pass
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': accepted, 'problems': problems,
                      'missing_operations': result['missing_operations']}, ensure_ascii=False))
    return 0 if accepted else 1


if __name__ == '__main__':
    sys.exit(main())
