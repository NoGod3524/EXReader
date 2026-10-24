# SPDX-License-Identifier: MIT
"""Supplement the unchanged account checks with explicit native receive actions."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time


def run_receive_checks(context):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    args, folder, host, report = (context[name] for name in ('args', 'folder', 'host', 'report'))
    account, ready, window = (context[name] for name in ('account', 'ready', 'window'))
    open_account, close_account, disconnect, scan = (context[name] for name in ('open_account', 'close_account', 'disconnect', 'scan'))
    sql, protocol, record = (context[name] for name in ('sql', 'protocol', 'record'))
    entries, directories, requests = (context[name] for name in ('entries', 'directories', 'requests'))
    command, raw = context['command'], context['raw']
    fixtures = args.receive_fixtures.resolve()
    manifest = json.loads((fixtures / 'manifest.json').read_text(encoding='utf-8'))
    work = folder / 'public-capture-seed';work.mkdir()
    seed_report = folder / 'public-capture-seed.json'
    invocation = [str(args.reading_probe.resolve()), '--fixtures', str(fixtures), '--font', str(args.payload.resolve() / 'Reader.otf'),
                  '--work', str(work), '--report', str(seed_report)]
    for role, item in manifest.items():
        assert hashlib.sha256((fixtures / item['file']).read_bytes()).hexdigest() == item['sha256']
        invocation += ['--sha', role + '=' + item['sha256']]
    seeded = subprocess.run(invocation, capture_output=True, text=True, encoding='utf-8', timeout=180)
    (folder / 'public-capture-seed.log').write_text(seeded.stdout + '\n' + seeded.stderr, encoding='utf-8')
    assert seeded.returncode == 0, 'installed real-capture seed refused'
    capture = json.loads(seed_report.read_text(encoding='utf-8'))
    assert capture['failures'] == 0 and len(capture['cases']) == 18 and capture['receiver_mislocated'] == 0
    names, observed = [], {}

    def checked(name):
        record(name);names.append(name)

    titles = {role: 'Cloud ' + role.upper() + ' 书籍' for role in ('txt', 'epub', 'pdf', 'cbz')}
    book_keys = {role: role + ':' + manifest[role]['sha256'] for role in titles}
    with sqlite3.connect(work / 'A-product.sqlite') as database:
        history = database.execute('SELECT body_json FROM reader_revisions ORDER BY revision_id').fetchall()
    assert len(history) == 22
    exact = {}
    for (body,) in history:
        value = json.loads(body)
        if value['entity_kind'] == 'book':
            role = value['payload']['format']
            value['payload'].update(title=titles[role], author='远端作者 café', favorite=True)
            body = raw(value)
        else:
            body = body.encode('utf-8') if isinstance(body, str) else bytes(body)
        exact[value['id']] = body
        prefix = '/dav/exreader-sync-v1/revisions/' + value['id'][:2] + '/'
        directories.add(prefix)
        entries[prefix + value['id'] + '-' + hashlib.sha256(body).hexdigest() + '.json'] = body
    for role, key in book_keys.items():
        item = manifest[role];body = (fixtures / item['file']).read_bytes()
        prefix = '/dav/exreader-sync-v1/objects/' + item['sha256'][:2] + '/'
        directories.add(prefix);entries[prefix + item['sha256'] + '.' + role] = body
    checked('received_seed_uses_four_exact_originals_and_eighteen_public_sdk_captures')

    old_metadata = sql('SELECT book_key,title,author,sort_title,favorite FROM reader_books ORDER BY book_key')
    old_local = sql('SELECT book_key,sdk_book_id FROM reader_local_books ORDER BY book_key')
    previous = int(account()['session_generation']);scan()
    synced = ready(lambda state: int(state['session_generation']) > previous and state['session_state'] == '4', seconds=180)
    assert sql('SELECT book_key,title,author,sort_title,favorite FROM reader_books ORDER BY book_key') == old_metadata
    assert sql('SELECT book_key,sdk_book_id FROM reader_local_books ORDER BY book_key') == old_local
    for revision_id, body in exact.items():
        received = sql('SELECT body_json FROM reader_revisions WHERE revision_id=?', (revision_id,))
        assert len(received) == 1 and received[0][0].encode('utf-8') == body
    checked('received_scan_retains_exact_history_without_projecting_or_importing_books')
    active = host.read();assert active['book'] > 0
    window();host.key('alt+r')
    projected = ready(lambda state: int(state['receive_seen']) >= 56 and state['phase'] == '0' and state['projection_status'] == '0')
    assert int(projected['max_receive_page_rows']) == 50
    for role, key in book_keys.items():
        assert sql('SELECT title,author,favorite FROM reader_books WHERE book_key=?', (key,)) == [(titles[role], '远端作者 café', 1)]
        assert not sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (key,))
    assert host.read()['book'] == active['book'] and host.read()['start'] == active['start']
    checked('received_explicit_native_action_projects_safe_metadata_in_bounded_owner_pages_without_sdk_import')
    first = context['first'];head_rows = context['before_heads']['heads']
    assert protocol('heads', 'book', first)['heads'] == head_rows
    assert int(projected['conflict_rows']) >= 1 and first in projected['conflict_keys']
    assert all(head['id'] in projected['conflict_heads'] for head in head_rows)
    checked('received_unresolved_book_versions_remain_retained_and_visible_without_choosing_a_head')
    close_account()

    def search(title):
        command('xdotool', 'windowactivate', '--sync', host.window)
        previous_queries = host.read()['shelf_queries']
        host.key('ctrl+f', 'ctrl+a');host.paste(title)
        host.wait(lambda state: state['shelf_queries'] > previous_queries and not state['shelf_loading'] and
                  not state['shelf_restoring'] and state['books'] == 1, timeout=60)

    def activate(role):
        search(titles[role]);host.key('Tab', 'Home', 'Return')

    def mapped(role):
        values = sql('SELECT sdk_book_id FROM reader_local_books WHERE book_key=?', (book_keys[role],))
        return values[0][0] if values else 0

    def opened(role):
        value = ready(lambda state: state['visible'] == '0' and mapped(role) > 0 and
                      int(state['imported_book']) == mapped(role), seconds=180)
        host.wait(lambda state: state['book'] == mapped(role) and state['reader_visible'] == 1 and not state['saving'], timeout=90)
        return value

    cache = host.folder / 'profile/sync-work'
    txt_cache = cache / (manifest['txt']['sha256'] + '.txt')
    original_txt = txt_cache.read_bytes();txt_cache.write_bytes(b'corrupt original retained for diagnosis')
    activate('txt');refused = ready(lambda state: state['visible'] == '1' and state['retry_enabled'] == '1')
    assert not mapped('txt') and txt_cache.read_bytes() == b'corrupt original retained for diagnosis'
    assert host.read()['book'] == active['book'] and host.read()['start'] == active['start']
    checked('received_hash_mismatch_refuses_import_without_replacing_the_existing_reader_or_cache')
    txt_cache.unlink();outside = folder / 'outside.txt';outside.write_bytes(original_txt);outside.chmod(0o600)
    txt_cache.symlink_to(outside)
    window();host.key('alt+t');ready(lambda state: state['retry_enabled'] == '1')
    assert not mapped('txt') and txt_cache.is_symlink() and outside.read_bytes() == original_txt
    checked('received_symlink_cache_is_refused_without_following_or_modifying_its_target')
    txt_cache.unlink();txt_cache.write_bytes(original_txt);txt_cache.chmod(0o600)
    window();host.key('alt+t');observed['txt'] = opened('txt')
    checked('received_txt_explicit_retry_imports_and_opens_the_verified_original')
    assert int(observed['txt']['restored_book']) == active['book'] and int(observed['txt']['restored_position']) == active['position']
    assert observed['txt']['restore_failed'] == '0'
    checked('received_import_restores_the_preexisting_reader_before_the_explicit_book_switch')

    activate('epub');observed['epub'] = opened('epub')
    checked('received_epub_original_opens_through_the_actual_bounded_native_host')
    pdf_cache = cache / (manifest['pdf']['sha256'] + '.pdf');pdf_cache.unlink()
    prefix = '/dav/exreader-sync-v1/objects/' + manifest['pdf']['sha256'][:2] + '/' + pdf_cache.name
    gets = sum(row['method'] == 'GET' and row['path'] == prefix for row in requests)
    activate('pdf');observed['pdf'] = opened('pdf')
    assert sum(row['method'] == 'GET' and row['path'] == prefix for row in requests) > gets
    assert observed['pdf']['session_present'] == '0' and observed['pdf']['closed_generation'] == observed['pdf']['session_generation']
    checked('received_missing_pdf_cache_drives_real_download_and_closed_before_owner_import')
    activate('cbz');observed['cbz'] = opened('cbz')
    checked('received_cbz_original_opens_through_the_actual_fixed_page_host')

    # Only selected heads authorize current positions. Superseded progress stays
    # in retained history; the full eighteen captures were checked in the seed.
    selected = {}
    for case in capture['cases']:
        selected[(case['kind'], case['entity_key'])] = case
    expected = {case['revision_id']: case for case in selected.values()}
    resolutions = {}
    for role, value in observed.items():
        rows = []
        for entry in value['resolutions'].split(';'):
            if not entry: continue
            rid, status, state, part, page, start, end = entry.split('|')
            case = expected[rid]
            rows.append(rid);resolutions[rid] = dict(status=int(status), state=int(state), part=int(part), page=int(page), start=int(start), end=int(end))
            if case['state'] == 'FOUND':
                assert int(status) == 0 and int(start) == case['start'] and int(end) == case['end'], case['id']
                if case['mode'] == 'epub_chapter': assert int(part) == case['part'], case['id']
            else:
                assert case['state'] == 'AMBIGUOUS' and int(status) == 6, case['id']
        assert len(rows) == int(value['reading_rows']) and value['reading_more'] == '0'
        checked('received_' + role + '_selected_progress_and_annotations_resolve_through_public_v2_without_mislocation')
    assert set(resolutions) == set(expected) and len(expected) == 15
    checked('received_selected_heads_keep_the_other_progress_revisions_in_history_without_implicit_navigation')
    for role, key in book_keys.items():
        assert sql('SELECT title,author,favorite FROM reader_books WHERE book_key=?', (key,)) == [(titles[role], '远端作者 café', 1)]
    checked('received_sdk_mapping_keeps_remote_title_author_and_favorite_instead_of_local_defaults')

    # An already imported book remains readable with neither a cached download
    # nor a working server. This is an actual new process, not an import retry.
    ids = {role: mapped(role) for role in titles};host.close()
    for role, sdk_id in ids.items():
        output = folder / ('sdk-retained-' + role + '.original')
        inspected = subprocess.run([str(args.inspect_consumer.resolve()), str(host.folder / 'profile/library.sqlite'), str(sdk_id), str(output)],
                                   capture_output=True, text=True, encoding='utf-8', timeout=60)
        assert inspected.returncode == 0, 'public installed SDK readback failed'
        value = json.loads(inspected.stdout)
        assert value['notes'] == 0 and output.read_bytes() == (fixtures / manifest[role]['file']).read_bytes()
    checked('received_public_sdk_readback_confirms_four_originals_and_zero_copied_product_annotations')
    pdf_cache.unlink();context['flags']['http'] = 503
    before_requests = len(requests);host.launch();search(titles['pdf']);host.key('Tab', 'Home', 'Return')
    host.wait(lambda state: state['book'] == ids['pdf'] and state['reader_visible'] == 1 and not state['error'], timeout=60)
    assert len(requests) == before_requests and not pdf_cache.exists()
    checked('received_downloaded_book_reopens_offline_from_the_sdk_when_cache_and_server_are_unavailable')
    context['flags']['http'] = 0
    open_account()
    return {'checks': names, 'selected_captures': len(expected), 'resolutions': resolutions,
            'found': sum(value['status'] == 0 for value in resolutions.values()), 'mislocated': 0,
            'originals_read_back': 4, 'public_capture_seed_sha256': hashlib.sha256(seed_report.read_bytes()).hexdigest()}
