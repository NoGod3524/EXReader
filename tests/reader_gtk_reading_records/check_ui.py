# SPDX-License-Identifier: MIT
"""Actions-only actual GTK reading records and durable process recovery."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import atspi_client as bus


def main():
    parser = argparse.ArgumentParser()
    for name in ('payload', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    os.environ.pop('NO_AT_BRIDGE', None)
    os.environ.pop('GTK_MODULES', None)
    os.environ['GTK_A11Y'] = 'atspi'
    output = args.output.resolve()
    output.mkdir()
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), output)
    profile = output / 'profile'
    checks = []
    report = dict(accepted=False, reading_records_scope_passed=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=checks,
                  sdk_changed=False, settings_whole_page_palette_accepted=False, complete_product=False,
                  program_sha256=hashlib.sha256(host.binary.read_bytes()).hexdigest())
    source = (args.fixtures / 'book.txt').resolve()
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    app = None

    def observed(section='reading_records'):
        value = configparser.ConfigParser(interpolation=None)
        value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}

    def wait(predicate=lambda value: True, idle=True, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert host.process.poll() is None, 'host exited'
            value = observed()
            if value and (not idle or (value['running'] == '0' and not host.read()['busy'] and not host.read()['saving'])) and predicate(value):
                return value
            time.sleep(.02)
        raise TimeoutError('reading records: ' + repr(observed()) + ' host: ' + repr(host.read()))

    def element(name, roles=None):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            node = next((node for node in bus.walk(app) if bus.name(node) == name and (roles is None or bus.role(node) in roles)), None)
            if node:
                return node
            time.sleep(.02)
        raise TimeoutError('missing native control: ' + name)

    def click_node(node):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            rect = bus.extents(node)
            if rect and rect['width'] > 4 and rect['height'] > 4 and bus.states(node).get('showing') and bus.states(node).get('sensitive'):
                command('xdotool', 'mousemove', '--sync', str(rect['x'] + rect['width'] // 2), str(rect['y'] + rect['height'] // 2))
                command('xdotool', 'click', '1')
                return
            time.sleep(.02)
        raise TimeoutError('native control is not actionable: ' + bus.name(node))

    def click(name, roles=None):
        click_node(element(name, roles))

    def record(name, condition=True, actual=None):
        value = dict(name=name, passed=bool(condition), observed=actual)
        checks.append(value)
        print(json.dumps(value, ensure_ascii=False), flush=True)
        assert condition, value

    def launch():
        nonlocal app
        end = time.monotonic() + 15
        while time.monotonic() < end:
            manager = subprocess.run(['wmctrl', '-m'], text=True, capture_output=True, timeout=2)
            if manager.returncode == 0 and 'Name: Openbox' in manager.stdout:
                break
            time.sleep(.05)
        else:
            raise TimeoutError('Openbox fixture is not ready')
        host.launch()
        app = bus.wait_application('exreader-linux')
        host.wait(lambda value: not value['saving'])

    def import_book(path):
        command('xdotool', 'windowactivate', '--sync', host.window)
        prior = host.read()['generation']
        end = time.monotonic() + 30
        host.key('F1')
        native_window = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Import book$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', native_window)

        def native(predicate):
            while time.monotonic() < end:
                assert host.process.poll() is None
                if predicate(observed('native_import')):
                    return
                time.sleep(.02)
            raise TimeoutError('native import: ' + repr(observed('native_import')))

        native(lambda value: value.get('active') == '1')
        host.key('ctrl+l')
        chooser = element('Import book', {'file chooser'})
        entry = next(node for node in bus.walk(chooser) if bus.role(node) == 'text' and bus.states(node).get('showing') and bus.states(node).get('sensitive'))
        click_node(entry)
        native(lambda value: value.get('entry_focused') == '1')
        host.key('ctrl+a')
        host.paste(str(path))
        digest = hashlib.sha256(str(path).encode()).hexdigest()
        native(lambda value: value.get('entry_sha256') == digest and value.get('selected_sha256') == digest and value.get('accept_sensitive') == '1')
        host.key('Return')
        host.wait(lambda value: value['generation'] > prior and not value['saving'] and observed('native_import').get('visible') == '0')
        assert host.read()['error'] == 0

    def open_records():
        command('xdotool', 'windowactivate', '--sync', host.window)
        host.key('ctrl+shift+r')
        wait(lambda value: value['visible'] == '1')
        native_window = command('xdotool', 'search', '--onlyvisible', '--name', '^Reading records$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', native_window)

    def action(name):
        before = int(observed()['actions'])
        click(name, {'push button'})
        return wait(lambda value: int(value['actions']) > before)

    def rows():
        return [node for node in bus.children(element('Bookmarks and annotations')) if bus.role(node) == 'list item']

    def select(index):
        click_node(rows()[index])
        wait(lambda value: value['selected'] == str(index))

    def editor(name, body):
        before = int(observed()['actions'])
        click(name, {'push button'})
        entry = element('Reading record text', {'text'})
        click_node(entry)
        host.key('ctrl+a')
        host.paste(body)
        host.key('alt+s')
        return wait(lambda value: int(value['actions']) >= before + 2)

    def sdk_dump(notes_only=False):
        with sqlite3.connect((profile / 'library.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            if notes_only:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%note%'")]
                data = [(name, sorted(db.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr)) for name in tables]
            else:
                data = sorted(db.iterdump())
        return hashlib.sha256(repr(data).encode()).hexdigest()

    def product_wires():
        with sqlite3.connect((profile / 'library.sqlite.product.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            found = []
            for table in tables:
                columns = [row[1] for row in db.execute('PRAGMA table_info("' + table + '")')]
                if 'body_json' in columns:
                    found.extend(json.loads(row[0]) for row in db.execute('SELECT body_json FROM "' + table + '"') if row[0])
            return found

    try:
        assert bus.init()[0]
        launch()
        import_book(source)
        baseline = sdk_dump()
        notes = sdk_dump(True)
        frame = {key: host.read()[key] for key in ('book', 'part', 'page', 'start', 'end', 'frame_generation')}
        open_records()
        dialog = element('Reading records', {'dialog'})
        record('actual_native_modal_starts_empty_with_explicit_missing_progress', bus.states(dialog).get('modal') and observed()['count'] == '0' and observed()['progress_state'] == '0')
        action('Save progress')
        record('save_progress_uses_product_history_without_sdk_or_frame_change', observed()['progress_state'] == '4' and sdk_dump() == baseline and all(host.read()[key] == value for key, value in frame.items()))
        editor('Add bookmark', '书签 café 🙂')
        record('genuine_point_bookmark_appears_without_implicit_navigation', observed()['count'] == '1' and any('书签 café 🙂' in bus.name(row) for row in rows()) and sdk_dump() == baseline)
        bookmark_before = next(wire for wire in product_wires() if wire['entity_kind'] == 'annotation' and wire['payload'] and wire['payload']['text'] == '书签 café 🙂')
        select(0)
        editor('Edit text', 'edited 书签 🙂')
        bookmark_after = next(wire for wire in product_wires() if wire['entity_kind'] == 'annotation' and wire['payload'] and wire['payload']['text'] == 'edited 书签 🙂')
        record('note_text_edit_keeps_product_selector_and_sdk_unchanged', any('edited 书签 🙂' in bus.name(row) for row in rows()) and sdk_dump() == baseline and bookmark_after['payload']['location'] == bookmark_before['payload']['location'])
        select(0)
        before = int(observed()['actions'])
        click('Delete record', {'push button'})
        click('Delete', {'push button'})
        wait(lambda value: int(value['actions']) >= before + 2)
        record('explicit_delete_is_a_bodyless_tombstone', any('deleted' in bus.name(row) and 'edited' not in bus.name(row) for row in rows()) and sdk_dump() == baseline)
        select(0)
        click('Choose restore version', {'push button'})
        retained = element('Retained reading versions')
        versions = [row for row in bus.children(retained) if bus.role(row) == 'list item']
        record('restore_requires_a_real_explicit_unselected_historical_version', len(versions) >= 2 and not any(bus.states(row).get('selected') for row in versions))
        click_node(versions[0])
        click('Restore selected version', {'push button'})
        click('Restore', {'push button'})
        wait(lambda value: value['count'] == '1' and value['running'] == '0' and 'deleted' not in bus.name(rows()[0]))
        record('restore_recaptures_only_after_independent_found_without_navigation', sdk_dump() == baseline and all(host.read()[key] == value for key, value in frame.items()))
        select(0)
        action('Open location')
        wait(lambda value: value['visible'] == '0')
        record('only_explicit_location_action_accepts_independent_found_frame', host.read()['frame_generation'] > frame['frame_generation'] and sdk_dump(True) == notes)
        command('xdotool', 'windowactivate', '--sync', host.window)
        click('Selectable page text', {'text'})
        host.key('ctrl+Home', 'ctrl+shift+Right')
        host.wait(lambda value: value['selected'] > 0)
        open_records()
        editor('Highlight selection', 'range 笔记 🙂')
        record('real_utf8_selection_creates_product_highlight_without_sdk_note_copy', observed()['count'] == '2' and any('range 笔记 🙂' in bus.name(row) for row in rows()) and sdk_dump(True) == notes)
        host.key('Escape')
        wait(lambda value: value['visible'] == '0')
        host.close()
        launch()
        open_records()
        record('real_process_reopen_retains_progress_bookmark_and_highlight', observed()['count'] == '2' and observed()['progress_state'] == '4')
        # A second real connection holds the product writer before a genuine
        # native save. Kill only after its private request is on disk.
        lock = sqlite3.connect(profile / 'library.sqlite.product.sqlite')
        lock.execute('BEGIN IMMEDIATE')
        click('Add bookmark', {'push button'})
        click_node(element('Reading record text', {'text'}))
        host.paste('exact retry across process death')
        host.key('alt+s')
        pending = profile / 'library.sqlite.product.sqlite.reading.pending'
        end = time.monotonic() + 10
        while time.monotonic() < end and not pending.exists():
            time.sleep(.01)
        assert pending.exists(), 'real save did not reach its durable request boundary'
        original_request = pending.read_bytes()
        record('pending_request_is_private_and_retains_capture_before_product_commit', pending.stat().st_mode & 0o077 == 0 and b'capture=' in original_request and b'revision=' in original_request)
        host.process.kill()
        host.process.wait(timeout=10)
        host.log.close()
        lock.rollback()
        lock.close()
        launch()
        open_records()
        record('true_process_death_keeps_original_request_pending_without_auto_replay', observed()['pending'] == '1' and observed()['count'] == '2' and pending.read_bytes() == original_request)
        action('Confirm original save')
        record('explicit_retry_commits_exact_original_once_then_clears_own_request', observed()['pending'] == '0' and observed()['count'] == '3' and not pending.exists() and sdk_dump(True) == notes)
        lock = sqlite3.connect(profile / 'library.sqlite.product.sqlite')
        lock.execute('BEGIN IMMEDIATE')
        click('Add bookmark', {'push button'})
        click_node(element('Reading record text', {'text'}))
        host.paste('finish the already-started save while closing')
        host.key('alt+s')
        end = time.monotonic() + 10
        while time.monotonic() < end and not pending.exists():
            time.sleep(.01)
        assert pending.exists(), 'graceful close did not reach its durable save boundary'
        command('wmctrl', '-ic', hex(int(host.window)))
        lock.rollback()
        lock.close()
        returncode = host.process.wait(timeout=20)
        host.log.close()
        record('parent_close_after_durable_save_finishes_owner_transaction_before_exit', returncode == 0 and not pending.exists())
        launch()
        open_records()
        record('graceful_close_save_is_retained_once_on_real_process_reopen', observed()['count'] == '4' and observed()['pending'] == '0' and sdk_dump(True) == notes)
        host.key('Escape')
        wait(lambda value: value['visible'] == '0')
        before = host.read()['frame_generation']
        open_records()
        record('cancel_or_close_read_only_panel_preserves_current_reading', host.read()['frame_generation'] == before and sdk_dump(True) == notes)
        host.key('Escape')
        wait(lambda value: value['visible'] == '0')
        import_book((args.fixtures / 'pages.cbz').resolve())
        record('actual_cbz_opens_with_genuine_empty_sdk_text_snapshot', host.read()['fixed'] == 1 and host.read()['end'] == 0)
        open_records()
        record('cbz_empty_snapshot_has_no_highlight_range_without_fabricating_text', observed()['has_range'] == '0' and not bus.states(element('Highlight selection', {'push button'})).get('sensitive'))
        action('Save progress')
        editor('Add bookmark', 'CBZ page point 书签')
        record('cbz_genuine_public_point_capture_saves_progress_and_bookmark', observed()['progress_state'] == '4' and observed()['count'] == '1' and sdk_dump(True) == notes)
        select(0)
        action('Open location')
        wait(lambda value: value['visible'] == '0')
        record('cbz_page_id_point_requires_independent_and_current_found_before_navigation', observed()['match'] == '1' and host.read()['fixed'] == 1 and host.read()['page'] == 0)
        record('all_original_source_bytes_remain_unchanged', hashlib.sha256(source.read_bytes()).hexdigest() == original_sha)
        record('product_wire_records_remain_explicit_versions', bool(product_wires()))
        host.close()
        # A separate real owner process seeds hostile graph states through the
        # installed public revision API; the GTK host only reads these records.
        graph_folder = output / 'graphs'
        profile = graph_folder / 'profile'
        profile.mkdir(parents=True, mode=0o700)
        seeded = subprocess.run([str(args.backend.resolve()), str(profile / 'library.sqlite'), str(host.font), str(source), 'graphs'], text=True, capture_output=True, timeout=60)
        (graph_folder / 'seed.log').write_text(seeded.stdout + seeded.stderr)
        assert seeded.returncode == 0, seeded.stdout + seeded.stderr
        host = Session(host.binary, host.font, graph_folder)
        launch()
        host.key('F2', 'Home', 'Return')
        host.wait(lambda value: value['book'] > 0 and not value['saving'])
        graph_sdk = sdk_dump()
        open_records()
        record('actual_native_page_reports_2mib_budget_stop_without_claiming_complete', observed()['count'] == '31' and observed()['complete'] == '0' and observed()['budget_stopped'] == '1' and int(observed()['output_bytes']) <= 2097152)
        action('Next batch')
        names = [bus.name(row) for row in rows()]
        record('next_keyset_batch_contains_all_three_unsafe_graph_states', observed()['count'] == '4' and observed()['complete'] == '1' and any('Versions need review' in name for name in names) and any('Waiting for earlier versions' in name for name in names) and any('Restore needs review' in name for name in names))
        record('unsafe_native_rows_show_counts_and_hide_all_retained_body_and_location', not any('PRIVATE' in bus.name(node) for node in bus.walk(app)) and all('versions /' in name and 'current /' in name for name in names[1:]))
        for index in (1, 2, 3):
            select(index)
            record('unsafe_row_%d_cannot_jump_edit_delete_or_restore' % index, all(not bus.states(element(name, {'push button'})).get('sensitive') for name in ('Open location', 'Edit text', 'Delete record', 'Choose restore version')))
        action('Previous batch')
        record('reverse_page_and_forward_return_keep_keyset_direction_and_budget_honest', observed()['count'] == '31' and observed()['complete'] == '1' and int(observed()['output_bytes']) <= 2097152)
        action('Next batch')
        record('forward_after_reverse_returns_same_four_rows_without_duplicates', [bus.name(row) for row in rows()] == names and sdk_dump() == graph_sdk)
        host.key('Escape')
        wait(lambda value: value['visible'] == '0')
        host.close()
        report['reading_records_scope_passed'] = True
    except BaseException as error:
        report['error'] = repr(error)
        try:
            command('import', '-window', 'root', str(output / 'failure.png'))
            if app:
                (output / 'failure-tree.json').write_text(json.dumps(bus.dump(app), ensure_ascii=False, indent=2))
        except BaseException as diagnostics:
            report['diagnostic_error'] = repr(diagnostics)
        raise
    finally:
        report['checks_total'] = len(checks)
        report['checks_failed'] = sum(not value['passed'] for value in checks)
        report['last_observation'] = observed()
        if not report['reading_records_scope_passed']:
            report['host_state'] = host.read() if host.observe.exists() else {}
            if (host.folder / 'application.log').exists():
                print((host.folder / 'application.log').read_text(errors='replace')[-6000:], flush=True)
        if host.process and host.process.poll() is None:
            host.process.kill()
            host.process.wait(timeout=10)
        if host.log and not host.log.closed:
            host.log.close()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        bus.exit_bus()


if __name__ == '__main__':
    main()
