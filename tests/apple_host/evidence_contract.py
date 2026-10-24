#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The shared, fail-closed WP13 Apple evidence contract (no SDK execution)."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import subprocess
import zipfile
import posixpath
import urllib.parse
import xml.etree.ElementTree as ET

PLATFORMS = ('macos', 'iphone', 'ipad')
SDK_TARGET = {'macos': 'macos', 'iphone': 'iphonesimulator', 'ipad': 'iphonesimulator'}
READING_SDK_BASELINE = '9854061be331fe603a1822d9b2b36ee357154927'
BASE_CASES = {
    'test01ImportDeduplicateAndErrors': '''step01_launch_fresh_state step02_import_epub_fixture step03_duplicate_import_reuses_row step04_import_pdf_fixture step05_broken_import_error_is_recoverable step06_reopen_epub_after_error step07_element_tree_import'''.split(),
    'test02PagingTypographyAndLayout': '''step08_launch_and_open_reader step09_first_page step10_next_page_progress step11_next_page_again step12_previous_page step13_font_increase_repaginates step14_font_decrease_restores_size step15_rotate_or_resize_viewport step16_layout_fits_new_size step17_restore_original_orientation step18_element_tree_reader'''.split(),
    'test03SelectionCopyAnnotation': '''step19_open_selection_sheet step20_keyboard_select_text step21_copy_selection step22_create_annotation step23_annotation_list_navigation step24_edit_annotation step25_jump_to_annotation step26_delete_annotation'''.split(),
    'test04LifecycleAndPersistence': '''step27_open_and_navigate step28_create_note_and_read_state step29_background_and_foreground step30_relaunch_restores_position_and_state step31_notes_survive_relaunch step32_view_rebuild_via_library'''.split(),
    'test05CancellationAndRecovery': '''step33_launch_with_deterministic_slow_import step34_cancel_in_flight_import step35_recover_with_valid_import step36_reader_remains_usable step37_state_tree_after_cancel'''.split(),
    'test06FixedPagePdfAndAnchor': '''step38_open_pdf_fixed_layout step39_fixed_page_navigation step40_fixed_annotation step41_fixed_annotation_jump step42_fixed_progress_survives_relaunch'''.split(),
    'test07AccessibilityAndDynamicType': '''step43_identifiers_and_labels step44_reading_order step45_element_tree step46_dynamic_type_launch'''.split(),
}
CASES = dict(BASE_CASES)
CASES.update({
    'test08BusyImportGuardsAndCancellationRecovery': '''regression01_busy_import_disables_competing_actions regression02_cancel_restores_real_shelf regression03_cancel_then_open_and_turn'''.split(),
    'test09BusyReadingBackAndBookOwnership': '''regression04_reading_busy_guards regression05_back_cancels_before_other_book regression06_other_book_remains_owner_after_prior_completion'''.split(),
    'test10UnicodeSelectionAndCrossBookIsolation': '''regression07_capture_original_book_notes regression08_select_and_copy_complete_unicode_scalars regression09_unicode_annotation_matches_selected_source regression10_unicode_selection_never_writes_other_book'''.split(),
    'test11SelectionInvalidatedByViewportChange': '''regression11_select_before_viewport_change regression12_changed_frame_rejects_old_selection regression13_new_frame_requires_fresh_selection'''.split(),
    'test12NondefaultFontAndExactProgressRelaunch': '''regression14_save_nondefault_font_and_progress regression15_real_process_relaunch_restores_font_and_page'''.split(),
})
ATTACHMENTS = {}
for case, names in zip(BASE_CASES, (
        '01-empty-library 02-imported-epub 03-library-two-books 04-broken-import-error 05-import-tree',
        '06-reader-open 07-layout-resized 08-layout-restored 09-reader-tree',
        '10-selection-sheet 11-selection-copied 12-annotation-list 13-annotation-jump 14-annotation-deleted',
        '15-after-background 16-after-relaunch 17-notes-after-relaunch',
        '18-library-slow-mode 19-import-cancelled 20-after-cancel-recovery 21-cancel-tree',
        '22-pdf-first-page 23-pdf-annotation 24-pdf-after-relaunch',
        '25-accessibility-reader 26-accessibility-tree 27-dynamic-type')):
    ATTACHMENTS.update({name: case for name in names.split()})
for case, names in zip(list(CASES)[7:], (
        '28-busy-import-guards 29-after-cancel-real-page', '30-other-book-after-back',
        '31-unicode-native-selection 32-cross-book-selection-cleared',
        '33-old-frame-selection-rejected', '34-nondefault-font-restored')):
    ATTACHMENTS.update({name: case for name in names.split()})
CASES['test13BoundedChapterNotesAndRelaunch'] = '''bounded01_import_source_and_open bounded02_cross_chapter_same_local_offset bounded03_note_current_chapter bounded04_repeat_path_rejects_old_frame bounded05_process_reopen_restores_route bounded06_backwards_cross_chapter'''.split()
ATTACHMENTS.update({name: 'test13BoundedChapterNotesAndRelaunch' for name in
                    ('35-bounded-first-chapter', '36-bounded-note-cross-chapter-jump', '37-bounded-reopen-route')})
LEGACY_CHECKS = '''epub_width epub_height epub_pixels epub_text library_insert library_deduplicate next_page previous_page_pixels previous_page_text font_increase font_decrease resume_position excerpt_saved pdf_dimensions pdf_channels pdf_pixels pdf_text image_bridge switch_book library_reopen resume_after_session_reopen'''.split()
MODEL_CHECKS = '''open_real_source cancelled_turn_keeps_frame_and_recovers precise_progress_is_atomic resize_keeps_exact_offset invalid_resize_keeps_viewport_and_frame cancelled_font_change_recovers failed_save_rolls_back_page_and_numeric_progress failed_save_rolls_back_font_and_viewport persistence_failure_is_reported failed_open_keeps_previous_session cancelled_candidate_keeps_previous_book reopen_uses_exact_saved_offset selection_context_rejects_wrong_book_page_and_text unicode_scalar_ranges_are_exact cross_book_notes_query_failure_clears_previous_book same_book_notes_query_failure_preserves_list_and_recovers pending_viewport_handoff_has_no_idle_frame cancel_pending_viewport_keeps_frame_and_recovers'''.split()
BOUNDED_CHECKS = '''source_import_marks_unknown_extent duplicate_preserves_storage_mode source_import_pre_cancel_is_atomic source_import_mid_cancel_and_late_rollback publication_rebinds_stable_source_control repeated_spine_path_keeps_part_identity cross_chapter_next_and_previous same_part_notes_crud_and_cross_part_jump font_resize_reopen_restores_part_and_point ambiguous_restore_preserves_selector invalid_part_path_rejected original_repeated_fixture_refuses_ambiguous_note legacy_memory_import_keeps_global_progress schema6_upgrade_preserves_legacy_original_progress_notes long_chapter_tail_text_without_snapshot'''.split()
SDK_CHECKS = set('''position-preserves-latest-metadata import-pre-cancel-preserves-library import-oversize-rejected-before-read import-cancel-during-bounded-read import-late-cancel-removes-new-row import-late-cancel-preserves-reused-row import-rollback-failure-reports-retained-row pager-rebinds-after-creator-cancel pager-current-token-controls-cache-hit pager-render-polls-current-token pager-seek-propagates-real-limit pager-seek-verifies-target-range-and-eof snapshot-pager-anchor-uses-document-api fixed-render-polls-current-token fixed-text-polls-current-token fixed-reuses-after-cancel fixed-comment-update-keeps-reflow-note-separate fixed-notes-propagates-cancellation fixed-notes-text-failure-is-propagated publication-cancel-ordering embedded-nul-note-is-rejected'''.split())
FIXTURES = {'Sample.epub', 'Sample.pdf', 'Large.epub', 'Broken.epub', 'Reader.otf', 'OFL.txt', 'Unicode.epub', 'Bounded.epub', 'BoundedLong.epub', 'Repeated.epub', 'reader-catalog-v1.sql'}


class Rejected(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def load(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(value, dict) and value, 'empty or invalid JSON object: ' + str(path))
    return value


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def inventory(root):
    root = Path(root).resolve(strict=True)
    require(root.is_dir(), 'missing evidence directory: ' + str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        require(path.resolve().is_relative_to(root), 'file escapes evidence directory')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    require(result, 'empty evidence directory: ' + str(root))
    return result


def tree_digest(root):
    return hashlib.sha256(json.dumps(inventory(root), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def cloud_identity(platform):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Apple evidence is collected only in cloud CI')
    return {'platform': platform, 'source_sha': os.environ['GITHUB_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
            'job': os.environ['GITHUB_JOB'],
            'run_url': '%s/%s/actions/runs/%s' % (os.environ['GITHUB_SERVER_URL'],
                os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_RUN_ID'])}


def validate_identity(value, source, run_id, attempt, platform=None, job=None):
    require(bool(re.fullmatch('[0-9a-f]{40}', source)), 'invalid expected source SHA')
    for key, expected in [('source_sha', source), ('run_id', str(run_id)), ('attempt', str(attempt))]:
        require(value.get(key) == expected, 'identity mismatch: ' + key)
    if platform:
        require(value.get('platform') == platform, 'identity mismatch: platform')
    if job:
        require(value.get('job') == job, 'identity mismatch: job')
    if 'run_url' in value:
        expected_url = '%s/%s/actions/runs/%s' % (os.environ['GITHUB_SERVER_URL'],
            os.environ['GITHUB_REPOSITORY'], run_id)
        require(value['run_url'] == expected_url, 'identity mismatch: run URL')


def case_key(name):
    require(isinstance(name, str), 'missing test identity')
    names = re.findall(r'\btest\d+[A-Za-z0-9_]+\b', name)
    require(len(names) == 1 and names[0] in CASES, 'unknown or ambiguous test identity')
    return names[0]


def validate_cases(cases):
    require(isinstance(cases, list) and len(cases) == len(CASES), 'incomplete test case set')
    seen = set()
    for case in cases:
        key = case_key(case.get('name'))
        require(key not in seen, 'duplicate test case')
        seen.add(key)
        require(case.get('result') == 'Passed', 'test case did not pass: ' + key)
        require(case.get('steps') == CASES[key] and case.get('step_count') == len(CASES[key]),
                'missing, reordered or duplicate steps: ' + key)
    require(seen == set(CASES), 'missing test identity')
    return {'cases': len(CASES), 'passed': len(CASES), 'failed': 0,
            'steps': sum(map(len, CASES.values()))}


def attachment_records(directory):
    directory = Path(directory)
    data = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    require(isinstance(data, list) and data, 'invalid attachment export manifest')
    records = []
    roles = set()
    filenames = set()
    step_payloads = {}
    for group in data:
        require(isinstance(group, dict) and isinstance(group.get('attachments'), list), 'invalid attachment group')
        owner = case_key(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item.get('exportedFileName', '')
            require(isinstance(filename, str) and Path(filename).name == filename and filename not in filenames,
                    'invalid or duplicate attachment filename')
            filenames.add(filename)
            path = directory/filename
            require(path.is_file() and path.stat().st_size > 0, 'missing attachment bytes')
            name = item.get('suggestedHumanReadableName', '')
            # xcresulttool appends the export occurrence and attachment UUID to
            # the XCTest name. Strip that exact envelope, never a name prefix.
            match = re.fullmatch(r'(.+)_(?:0|[1-9]\d*)_[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-'
                                 r'[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\.(png|txt|json)', name)
            require(match is not None,
                    'invalid attachment export name: owner=%s suggested=%r' % (owner, name))
            declared_name, extension = match.groups()
            if declared_name.startswith('steps-'):
                payload = load(path)
                key = case_key(payload.get('test'))
                require(extension == 'json' and case_key(declared_name) == owner and key == owner and
                        payload.get('steps') == CASES[key],
                        'attachment step identity mismatch: owner=%s suggested=%r' % (owner, name))
                require(key not in step_payloads, 'duplicate test step attachment')
                step_payloads[key] = payload['steps']
                role = 'steps-' + key
            else:
                role = declared_name
                require(ATTACHMENTS.get(role) == owner,
                        'unknown or misattributed attachment: role=%r owner=%s suggested=%r' % (role, owner, name))
                if 'tree' in role:
                    require(extension == 'txt', 'element tree attachment type mismatch: ' + role)
                    require('Application' in path.read_text(encoding='utf-8'), 'empty element tree attachment')
                else:
                    require(extension == 'png', 'screenshot attachment type mismatch: ' + role)
                    raw = path.read_bytes()
                    require(raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) > 24 and
                            int.from_bytes(raw[16:20], 'big') > 0 and int.from_bytes(raw[20:24], 'big') > 0,
                            'invalid screenshot attachment')
            require(role not in roles, 'duplicate attachment role')
            roles.add(role)
            records.append({'test': owner, 'role': role, 'file': filename,
                            'bytes': path.stat().st_size, 'sha256': digest(path)})
    expected = set(ATTACHMENTS) | {'steps-' + key for key in CASES}
    require(roles == expected, 'incomplete attachment set: missing=%s extra=%s' %
            (sorted(expected - roles), sorted(roles - expected)))
    require(set(inventory(directory)) == filenames | {'manifest.json'}, 'unmanifested attachment files')
    return sorted(records, key=lambda item: item['role']), step_payloads


def runtime_ids(path):
    proc = subprocess.run(['dwarfdump', '--uuid', str(path)], capture_output=True, text=True, check=True)
    ids = sorted(re.findall(r'UUID: ([0-9A-Fa-f-]+) \(([^)]+)\)', proc.stdout))
    require(ids, 'missing Mach-O UUID')
    return [list(value) for value in ids]


def sdk_record(root, target):
    root = Path(root)
    base = (root/'include/exr/base.h').read_text()
    return {**cloud_identity(target), 'sdk_version': re.search(r'#define EXR_VERSION "([^"]+)"', base)[1],
            'reading_sdk_baseline': READING_SDK_BASELINE,
            'abi': int(re.search(r'#define EXR_ABI_VERSION (\d+)u', base)[1]),
            'files_sha256': inventory(root),
            'runtime_ids': {path.name: runtime_ids(path) for path in sorted((root/'lib').glob('libexreader*.dylib'))}}


def validate_sdk(root, value, source, run_id, attempt, target):
    validate_identity(value, source, run_id, attempt, target, 'sdk')
    require(value.get('reading_sdk_baseline') == READING_SDK_BASELINE, 'SDK frozen reading baseline mismatch')
    require(value.get('files_sha256') == inventory(root), 'SDK file identity mismatch')
    require(value.get('abi') == 1 and value.get('sdk_version'), 'SDK version or ABI missing')
    header = (Path(__file__).resolve().parents[2]/'include/exr/base.h').read_text()
    require(value['sdk_version'] == re.search(r'#define EXR_VERSION "([^"]+)"', header)[1],
            'SDK version differs from tested source')
    actual = {path.name: runtime_ids(path) for path in sorted((Path(root)/'lib').glob('libexreader*.dylib'))}
    require(actual and value.get('runtime_ids') == actual, 'SDK runtime identity mismatch')


def validate_program(bundle, environment, source, sdk):
    bundle = Path(bundle)
    mac = (bundle/'Contents').is_dir()
    info_path = bundle/('Contents/Info.plist' if mac else 'Info.plist')
    info = plistlib.loads(info_path.read_bytes())
    executable = bundle/('Contents/MacOS/' if mac else '')/info['CFBundleExecutable']
    require(info.get('CFBundleIdentifier') == 'org.exreader.host' and info.get('EXRSourceSHA') == source,
            'program bundle source identity mismatch')
    require(environment['app'].get('executable_sha256') == digest(executable) and
            environment['app'].get('info_plist_sha256') == digest(info_path), 'program identity mismatch')
    resources = bundle/'Contents/Resources' if mac else bundle
    fixtures = environment.get('fixtures', {})
    require(isinstance(fixtures, dict) and FIXTURES <= set(fixtures), 'fixture identity missing')
    for name, expected in fixtures.items():
        require(Path(name).name == name and digest(resources/name) == expected, 'fixture bytes mismatch: ' + name)
    require(environment.get('font_sha256') == fixtures['Reader.otf'], 'font identity mismatch')
    frameworks = bundle/'Contents/Frameworks' if mac else bundle/'Frameworks'
    actual = {path.name: runtime_ids(path) for path in sorted(frameworks.glob('libexreader*.dylib'))}
    require(actual == sdk['runtime_ids'], 'embedded runtime differs from the installed SDK')


def database_state(root, environment):
    root = Path(root)
    db = root/'library.sqlite'
    require(db.is_file(), 'missing persisted database')
    with sqlite3.connect(db.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as con:
        require(con.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'database integrity check failed')
        require(con.execute('PRAGMA application_id').fetchone()[0] == 1163416131 and
                con.execute('PRAGMA user_version').fetchone()[0] == 7, 'database identity mismatch')
        require(not con.execute('PRAGMA foreign_key_check').fetchall(), 'database foreign key mismatch')
        for table, columns in {
                'epub_bounded_books': {'book_id'},
                'epub_progress': {'book_id', 'part', 'path', 'position', 'prefix', 'suffix', 'chapter'},
                'epub_notes': {'id', 'book_id', 'part', 'path', 'start', 'end', 'exact', 'prefix', 'suffix', 'chapter', 'text'}}.items():
            require({row[1] for row in con.execute('PRAGMA table_info(' + table + ')')} == columns,
                    'schema7 chapter columns missing or changed: ' + table)
        rows = {table: con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                for table in ('books', 'notes', 'fixed_notes', 'book_progress', 'epub_bounded_books', 'epub_progress', 'epub_notes')}
        require(rows['books'] >= 2 and all(rows[key] >= 1 for key in ('epub_notes', 'fixed_notes', 'epub_progress')),
                'persisted acceptance state incomplete')
        state = load(root/'host-state.json')
        require(state.get('schema') == 2 and state.get('abi_version') == environment['sdk']['abi'] and
                state.get('sdk_version') == environment['sdk']['sdk_version'] and
                state.get('font_sha256') == environment['font_sha256'], 'host state SDK/font identity mismatch')
        books = state.get('books')
        require(isinstance(books, list) and len(books) == rows['books'], 'host state book set mismatch')
        actual = {row[0]: row[1:] for row in con.execute('SELECT id,title,position FROM books')}
        seen = set()
        parts, notes = [], []
        current_frame = None
        bounded_ids = {r[0] for r in con.execute('SELECT book_id FROM epub_bounded_books')}
        routes = {}
        for key, format_id, original, title, extent, position in con.execute('SELECT id,format,source,title,text_size,position FROM books'):
            if title in environment['fixtures']:
                require(hashlib.sha256(original).hexdigest() == environment['fixtures'][title], 'stored original fixture mismatch')
            if format_id == 4:
                require(key in bounded_ids and extent == 0 and position == 0, 'new EPUB lacks bounded marker or uses global coordinates')
                require(not con.execute('SELECT 1 FROM book_progress WHERE book_id=? UNION ALL SELECT 1 FROM notes WHERE book_id=?', (key, key)).fetchall(), 'bounded EPUB contains legacy position or notes')
                with zipfile.ZipFile(io.BytesIO(original)) as archive:
                    container = ET.fromstring(archive.read('META-INF/container.xml'))
                    package = next(n.attrib['full-path'] for n in container.iter() if n.tag.endswith('rootfile'))
                    opf = ET.fromstring(archive.read(package))
                    items = {n.attrib['id']: n.attrib['href'] for n in opf.iter() if n.tag.endswith('}item')}
                    routes[key] = [posixpath.normpath(posixpath.join(posixpath.dirname(package), urllib.parse.unquote(items[n.attrib['idref']])))
                                   for n in opf.iter() if n.tag.endswith('}itemref')]
            else:
                require(key not in bounded_ids, 'bounded marker belongs to non EPUB')
        for book in books:
            key = book.get('id')
            require(key not in seen and actual.get(key) == (book.get('title'), book.get('position')),
                    'host state differs from persisted book')
            seen.add(key)
            parts.append('b%s:%s' % (key, book['position']))
            bounded = key in bounded_ids
            require(book.get('storage') == ('epub' if bounded else 'fixed' if book.get('format') in ('PDF', 'CBZ') else 'global'), 'host storage mode mismatch')
            if bounded:
                saved = con.execute('SELECT part,path,position,prefix,suffix FROM epub_progress WHERE book_id=?', (key,)).fetchone()
                if saved is not None:
                    p = book.get('epub_progress', {})
                    require(0 <= saved[0] < len(routes[key]) and routes[key][saved[0]] == saved[1] and saved[2] >= 0, 'stored EPUB route invalid')
                    require((p.get('part'), p.get('path'), p.get('start'), p.get('prefix'), p.get('suffix')) == saved and
                            p.get('end') == p.get('start') and p.get('exact') == '', 'host EPUB progress differs from database')
                    parts.append('p%s:%s:%s:%s' % (key, saved[0], saved[1], saved[2]))
                else:
                    require('epub_progress' not in book, 'host invented EPUB progress')
            if 'notes' in book:
                require(isinstance(book['notes'], list), 'invalid host note state')
                notes = book['notes']
                table = 'epub_notes' if bounded else 'fixed_notes' if book.get('format') in ('PDF', 'CBZ') else 'notes'
                stored = dict(con.execute('SELECT id,text FROM ' + table + ' WHERE book_id=?', (key,)))
                require(len(notes) == len(stored) and len({note.get('id') for note in notes}) == len(notes),
                        'host note set mismatch')
                for note in notes:
                    require(stored.get(note.get('id')) == note.get('comment'), 'host note text differs from database')
                    require(note.get('storage') == book['storage'], 'host note namespace mismatch')
                    if bounded:
                        record = con.execute('SELECT part,path,start,end,exact FROM epub_notes WHERE id=? AND book_id=?', (note['id'], key)).fetchone()
                        require(record == (note.get('part'), note.get('path'), note.get('selector_start'), note.get('selector_end'), note.get('quote')),
                                'host EPUB note selector differs from database')
                        require(0 <= record[0] < len(routes[key]) and routes[key][record[0]] == record[1], 'stored EPUB note route invalid')
                        if note.get('state') == '精确':
                            require((note.get('start'), note.get('end')) == record[2:4], 'resolved EPUB range mismatch')
                if bounded:
                    require(book.get('part') in range(len(routes[key])) and routes[key][book['part']] == book.get('path'), 'current frame route mismatch')
                    require(isinstance(book.get('reading_offset'), int) and book['reading_offset'] >= 0, 'current frame offset missing')
                    require(isinstance(book.get('unresolved_progress'), bool), 'current frame recovery state missing')
                    if not book['unresolved_progress']:
                        require(saved is not None and saved[:3] == (book['part'], book['path'], book['reading_offset']),
                                'accepted frame and persisted chapter point differ')
                    current_frame = 'f%s:%s:%s:%s' % (key, book['part'], book['path'], book['reading_offset'])
                    memory = book.get('bounded_memory', {})
                    require(memory.get('explicit_snapshot_bytes') == 0 and memory.get('peak_parse_workspace_bytes', 1 << 60) <= 16 * 1024 * 1024 and
                            memory.get('swift_page_text_bytes', 1 << 60) <= 2 * 1024 * 1024, 'bounded frame memory contract missing')
        if current_frame is not None:
            parts.append(current_frame)
        parts.extend('n%s:%s:%s:%s:%s:%s:%s:%s' % (n['storage'], n['id'], n['part'], n['path'], n['page'], n['start'], n['state'], n['comment']) for n in notes)
        require(state.get('state_hash') == hashlib.sha256('|'.join(parts).encode()).hexdigest()[:8],
                'host state hash mismatch')
    require((root/'host-log.txt').stat().st_size > 0, 'missing host operation log')
    return {'database': {'status': 'copied', 'sha256': digest(db), 'bytes': db.stat().st_size,
                         'rows': rows, 'source_name': 'library.sqlite'},
            'host_state': {'status': 'copied', 'sha256': digest(root/'host-state.json'),
                           'log_sha256': digest(root/'host-log.txt'), 'payload': state}}


def validate_platform(root, platform, source, run_id, attempt, sdk, result_root=None):
    root = Path(root)
    evidence = load(root/'evidence.json')
    require(evidence.get('schema') == 2, 'unsupported platform evidence schema')
    env = evidence.get('environment', {})
    validate_identity(env, source, run_id, attempt, platform, 'uitest')
    require(evidence.get('source_sha') == source and evidence.get('platform') == platform and
            evidence.get('physical_device_execution') is False and evidence.get('accepted') is True,
            'platform acceptance identity mismatch')
    require(all(isinstance(env.get(key), str) and env[key] for key in
                ('xcode', 'host', 'device', 'runtime', 'destination', 'input_driver')), 'environment identity incomplete')
    require((platform == 'macos' and env['destination'] == 'platform=macOS') or
            (platform != 'macos' and env['destination'].startswith('platform=iOS Simulator,id=') and
             env['device'].lower().startswith(platform)), 'environment destination mismatch')
    require(evidence.get('run') == {'id': str(run_id), 'attempt': str(attempt), 'job': 'uitest',
            'url': env.get('run_url')}, 'platform run identity mismatch')
    require(evidence.get('totals') == validate_cases(evidence.get('tests')), 'case totals mismatch')
    require(evidence.get('collector_status') == 0 and not evidence.get('errors'), 'collector failed')
    records, steps = attachment_records(root/'attachments')
    require(evidence.get('attachments') == {'status': 0, 'count': len(records), 'records': records},
            'attachment inventory mismatch')
    for case in evidence['tests']:
        require(case['steps'] == steps[case_key(case['name'])], 'case attachment steps mismatch')
    require(env.get('sdk') == sdk, 'platform SDK manifest mismatch')
    require(evidence.get('program_files_sha256') == inventory(root/'program/EXReaderHost.app'),
            'program file inventory mismatch')
    validate_program(root/'program/EXReaderHost.app', env, source, sdk)
    require(evidence.get('state') == database_state(root, env), 'persisted state evidence mismatch')
    if result_root is not None:
        result_root = Path(result_root)
        require(evidence.get('xcresult_sha256') == tree_digest(result_root/(platform + '.xcresult')),
                'raw xcresult identity mismatch')
        require(evidence.get('xcodebuild_log_sha256') == digest(result_root/(platform + '-xcodebuild.log')),
                'xcodebuild log identity mismatch')
    return evidence


def validate_package(root, source, run_id, attempt, sdks):
    root = Path(root)
    identity = load(root/'package-identity.json')
    validate_identity(identity, source, run_id, attempt, 'package', 'package')
    builds = {}
    legacy = {}
    for target, folder in [('macos', 'macos'), ('iphonesimulator', 'simulator'), ('iphoneos', 'device')]:
        base = root/folder
        build = load(base/'build.json')
        require(build.get('source_sha') == source and build.get('sdk_version') == sdks[target]['sdk_version'],
                'package build source/SDK mismatch')
        require(build.get('platform') == {'macos': 'macos', 'simulator': 'simulator', 'device': 'iphoneos'}[folder],
                'package target mismatch')
        require(build.get('files') == inventory(base/'EXReader.app'), 'package program bytes mismatch')
        mac = target == 'macos'
        bundle = base/'EXReader.app'
        info = plistlib.loads((bundle/('Contents/Info.plist' if mac else 'Info.plist')).read_bytes())
        require(info.get('EXRSourceSHA') == source and info.get('CFBundleIdentifier') == 'org.exreader.host',
                'package executable source mismatch')
        frameworks = bundle/('Contents/Frameworks' if mac else 'Frameworks')
        require({p.name: runtime_ids(p) for p in sorted(frameworks.glob('libexreader*.dylib'))} == sdks[target]['runtime_ids'],
                'package runtime mismatch')
        builds[folder] = {'sha256': digest(base/'build.json'), 'program_files': build['files']}
    for platform in PLATFORMS:
        report = root/('evidence-' + platform)/'report.json'
        data = load(report)
        require(data.get('schema') == 1 and data.get('passed') is True and data.get('source_sha') == source and
                data.get('check_count') == 21 and data.get('checks') == LEGACY_CHECKS and
                data.get('platform') == ('macOS' if platform == 'macos' else 'iOS') and
                data.get('engine_version') == sdks[SDK_TARGET[platform]]['sdk_version'], 'legacy self-check evidence incomplete')
        screenshot = report.parent/'screen.png'
        require(screenshot.is_file() and screenshot.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'legacy screenshot missing')
        legacy[platform] = {'checks': 21, 'passed': True, 'sha256': digest(report),
                            'path': report.relative_to(root).as_posix()}
    ipa = root/'device/EXReader-iOS-unsigned.ipa'
    with zipfile.ZipFile(ipa) as archive:
        files = [item.filename for item in archive.infolist() if not item.is_dir()]
        expected = {'Payload/EXReader.app/' + name: value for name, value in builds['device']['program_files'].items()}
        require(len(files) == len(expected) and set(files) == set(expected), 'device archive content mismatch')
        require(all(hashlib.sha256(archive.read(name)).hexdigest() == expected[name] for name in files),
                'device archive bytes differ from built program')
    require(not list((root/'device/EXReader.app').rglob('embedded.mobileprovision')), 'device package unexpectedly provisioned')
    require(load(root/'device/build.json').get('signing') ==
            'ad-hoc; device installation requires the owner signing identity', 'device signing policy mismatch')
    device_info = plistlib.loads((root/'device/EXReader.app/Info.plist').read_bytes())
    require(device_info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'] and
            device_info.get('UIDeviceFamily') == [1, 2], 'device archive is not an iPhone/iPad device build')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(root/'device/EXReader.app')],
                   capture_output=True, text=True, check=True)
    signing = subprocess.run(['codesign', '-d', '--verbose=4', str(root/'device/EXReader.app')],
                             capture_output=True, text=True, check=True)
    require('Signature=adhoc' in signing.stderr and 'TeamIdentifier=not set' in signing.stderr,
            'device archive is not the declared ad-hoc package')
    return legacy, {'installation_status': 'owner_signing_required', 'ipa_sha256': digest(ipa), 'builds': builds}


def validate_review_reports(root, source, run_id, attempt, sdk, fixtures):
    root = Path(root)
    source_root = Path(__file__).resolve().parents[2]
    require(fixtures.get('reader-catalog-v1.sql') == digest(source_root/'apps/reader/store/001_catalog.sql'),
            'product catalog resource differs from original migration')
    model_root = root/'model-review'
    model = load(model_root/'model-review.json')
    validate_identity(model, source, run_id, attempt, job='package')
    require(model.get('schema') == 1 and model.get('accepted') is True, 'model review did not pass')
    checks = model.get('checks', [])
    require([item.get('name') for item in checks] == MODEL_CHECKS and
            all(item.get('passed') is True for item in checks), 'model review checks incomplete')
    require(model.get('program') == {'path': 'model-review', 'sha256': digest(model_root/'model-review')},
            'model program identity mismatch')
    require(model.get('sdk_files_sha256') == sdk['files_sha256'], 'model review SDK identity mismatch')
    require(model.get('fixtures') == {name: fixtures[name] for name in
            ('Sample.epub', 'Sample.pdf', 'Unicode.epub', 'Reader.otf', 'reader-catalog-v1.sql')}, 'model fixture identity mismatch')
    model_sources = ('examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift',
                     'examples/apple/HostCatalog.swift', 'examples/apple/HostAccount.swift', 'examples/apple/SelectableText.swift',
                     'tests/apple_host/review/ModelReview.swift', 'tools/check_apple_model_review.py',
                     'apps/reader/store/001_catalog.sql')
    require(model.get('source_files_sha256') == {name: digest(source_root/name) for name in model_sources},
            'model consumer source identity mismatch')
    sdk_root = root/'sdk-review'
    identity = load(sdk_root/'sdk-review-identity.json')
    validate_identity(identity, source, run_id, attempt, job='package')
    require(identity.get('schema') == 1 and identity.get('passed') is True and identity.get('checks') == 21 and
            identity.get('exit_code') == 0 and identity.get('local_execution') is False,
            'SDK review did not pass')
    require(identity.get('program') == {'path': 'sdk-review', 'sha256': digest(sdk_root/'sdk-review')},
            'SDK review program identity mismatch')
    require(identity.get('report_sha256') == digest(sdk_root/'consumer/sdk-review.json'),
            'SDK review report identity mismatch')
    report = load(sdk_root/'consumer/sdk-review.json')
    cases = report.get('cases', [])
    names = [item.get('id') for item in cases]
    require(report.get('schema') == 1 and report.get('passed') is True and report.get('checks') == 21 and
            len(names) == 21 and set(names) == SDK_CHECKS and len(set(names)) == len(names) and
            all(item.get('passed') is True for item in cases), 'SDK review check identities incomplete')
    require(identity.get('sdk_version') == sdk['sdk_version'] and identity.get('abi') == sdk['abi'],
            'SDK consumer version identity mismatch')
    subset = {name: value for name, value in sdk['files_sha256'].items() if
              name in ('include/exreader.h', 'include/module.modulemap') or
              (name.startswith('include/exr/') and name.endswith('.h')) or
              (name.startswith('lib/libexreader') and name.endswith('.dylib'))}
    require(identity.get('sdk_files_sha256') == subset, 'SDK consumer headers/runtime mismatch')
    require(identity.get('fixtures') == {name: fixtures[name] for name in ('Reader.otf', 'Sample.epub', 'Sample.pdf')},
            'SDK consumer fixture identity mismatch')
    source_root = Path(__file__).resolve().parents[2]
    sources = ('examples/apple/HostSDK.swift', 'tests/apple_host/sdk_review/SDKReview.swift',
               'tests/apple_host/run_sdk_review.py', 'tests/fixtures/pdf-public-text.pdf')
    require(identity.get('source_files_sha256') == {name: digest(source_root/name) for name in sources},
            'SDK consumer source identity mismatch')
    files = ('sdk-review', 'build.log', 'consumer.log', 'consumer/TextFailure.pdf', 'consumer/sdk-review.json')
    require(identity.get('evidence_files_sha256') == {name: digest(sdk_root/name) for name in files},
            'SDK consumer evidence bytes mismatch')
    require(digest(sdk_root/'consumer/TextFailure.pdf') == digest(source_root/'tests/fixtures/pdf-public-text.pdf'),
            'SDK consumer fixed input mismatch')
    bounded_root = root/'bounded-review'
    bounded = load(bounded_root/'bounded-review.json')
    validate_identity(bounded, source, run_id, attempt, 'bounded-macos', 'package')
    require(bounded.get('schema') == 1 and bounded.get('accepted') is True and bounded.get('physical_device_execution') is False and
            bounded.get('runtime_budget_seconds') == 900 and bounded.get('diagnostic_only') is False and
            [c.get('name') for c in bounded.get('checks', [])] == BOUNDED_CHECKS and
            all(c.get('passed') is True for c in bounded['checks']), 'bounded consumer checks incomplete')
    require(bounded.get('program_sha256') == digest(bounded_root/'bounded-review') and
            bounded.get('sdk_files_sha256') == sdk['files_sha256'], 'bounded consumer SDK/program identity mismatch')
    require(bounded.get('fixtures') == {n: fixtures[n] for n in ('Bounded.epub', 'BoundedLong.epub', 'Unicode.epub', 'Reader.otf', 'Repeated.epub', 'reader-catalog-v1.sql')},
            'bounded consumer fixture identity mismatch')
    sources = ('examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift', 'examples/apple/SelectableText.swift',
               'examples/apple/HostCatalog.swift', 'examples/apple/HostAccount.swift', 'tests/apple_host/bounded_review/BoundedReview.swift',
               'tests/apple_host/run_bounded_review.py', 'apps/reader/store/001_catalog.sql')
    require(bounded.get('source_files_sha256') == {p: digest(source_root/p) for p in sources}, 'bounded consumer source mismatch')
    require(load(bounded_root/'consumer/bounded-review.json').get('checks') == bounded['checks'] and
            load(bounded_root/'consumer/bounded-review.json').get('measurements') == bounded.get('measurements'), 'bounded consumer raw result mismatch')
    metrics = bounded.get('measurements', {})
    require(metrics.get('repeated_window_bytes') == 16384 and
            metrics.get('projection_bytes', 0) >= 49 * 1024 * 1024 and metrics.get('tail_text_bytes') == 512 and
            metrics.get('explicit_snapshot_bytes') == 0 and metrics.get('peak_parse_workspace_bytes', 1 << 60) <= 16 * 1024 * 1024 and
            bounded.get('process_peak_rss_bytes', 0) > 0, 'bounded long chapter evidence incomplete')
    return {'model': {'checks': len(MODEL_CHECKS), 'accepted': True, 'sha256': digest(model_root/'model-review.json')},
            'sdk': {'checks': len(SDK_CHECKS), 'accepted': True, 'sha256': digest(sdk_root/'sdk-review-identity.json')},
            'bounded': {'checks': len(BOUNDED_CHECKS), 'accepted': True, 'sha256': digest(bounded_root/'bounded-review.json')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['sdk', 'identity'])
    parser.add_argument('--root', type=Path)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = sdk_record(args.root, args.platform) if args.kind == 'sdk' else cloud_identity(args.platform)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
