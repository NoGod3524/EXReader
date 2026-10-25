# SPDX-License-Identifier: MIT
"""Actions-only real pointer DND, native clipboard ownership and file import."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import atspi_client as bus


def main():
    parser = argparse.ArgumentParser()
    for name in ('payload', 'fixtures', 'output', 'backend', 'native-source'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    os.environ.pop('NO_AT_BRIDGE', None)
    os.environ.pop('GTK_MODULES', None)
    args.output.mkdir(parents=True)
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), args.output.resolve())
    report = dict(accepted=False, drop_import_scope_passed=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=[],
                  program_sha256=hashlib.sha256(host.binary.read_bytes()).hexdigest(), complete_product=False)
    manifest = json.loads((args.fixtures / 'manifest.json').read_text())
    sources, source_logs = [], []
    app = None

    def observed(section='file_input'):
        value = configparser.ConfigParser(interpolation=None)
        value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}

    def wait(predicate, seconds=40):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert host.process.poll() is None, 'host exited'
            if predicate():
                return
            time.sleep(.02)
        raise TimeoutError('file input ' + repr(observed()) + ' folder ' + repr(observed('folder_import')) + ' host ' + repr(host.read()))

    def check(name, condition, details=None):
        row = dict(name=name, passed=bool(condition), observed=details)
        report['checks'].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        assert condition, row

    def element(name, roles=None):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            node = next((node for node in bus.walk(app) if bus.name(node) == name and
                         (roles is None or bus.role(node) in roles) and bus.states(node).get('showing')), None)
            if node:
                return node
            time.sleep(.02)
        raise TimeoutError('missing native control: ' + name)

    def click_node(node):
        if bus.role(node) == 'list item':
            assert node.get_component_iface().grab_focus()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rect = bus.extents(node)
            if rect and rect['x'] >= 0 and rect['y'] >= 0 and rect['width'] > 8 and rect['height'] > 8 and bus.states(node).get('sensitive'):
                command('xdotool', 'mousemove', '--sync', str(rect['x'] + rect['width'] // 2), str(rect['y'] + rect['height'] // 2))
                command('xdotool', 'click', '1')
                return
            time.sleep(.02)
        raise TimeoutError('native control not allocated: ' + bus.name(node))

    def paste_files():
        command('xdotool', 'windowactivate', '--sync', host.window)
        click_node(element('Import sources'))
        click_node(element('Paste book files', {'menu item'}))

    def source(mode, target, name, delay=0):
        path = args.output / ('native-source-%d.log' % len(sources))
        log = path.open('w')
        process = subprocess.Popen([str(args.native_source), mode, target, str(args.fixtures / name),
                                    'Native file source', str(delay)], stdout=log, stderr=subprocess.STDOUT)
        sources.append(process)
        source_logs.append(log)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, path.read_text()
            if 'NATIVE_FILE_SOURCE_READY' in path.read_text():
                return process, path
            time.sleep(.02)
        raise TimeoutError('native source did not become ready')

    def stop_source(process):
        process.terminate()
        process.wait(timeout=10)

    def close_import():
        click_node(element('Close', {'push button'}))
        wait(lambda: observed('folder_import').get('owner') == '0' and observed('folder_import').get('visible') == '0')
        host.wait(lambda state: not state['saving'] and not state['shelf_loading'])

    def inspect(name, expected):
        out = args.output / (name + '.tsv')
        result = subprocess.run([str(args.backend), str(args.output / 'profile/library.sqlite'), str(host.font), str(out), 'unused', 'inspect'],
                                capture_output=True, text=True, timeout=60)
        (args.output / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        rows = [line.split('\t') for line in out.read_text().splitlines()]
        actual = {(row[1], row[2], int(row[3])) for row in rows}
        wanted = {(row['format'], row['sha256'], row['bytes']) for row in expected}
        check(name, actual == wanted and len(rows) == len(wanted))
        return rows

    def frame():
        value = host.read()
        return {name: value[name] for name in ('book', 'part', 'page', 'start', 'end', 'font', 'position', 'frame_generation')}

    try:
        assert bus.init()[0]
        host.launch()
        app = bus.wait_application('^exreader-linux$')
        host.wait(lambda value: not value['saving'] and not value['shelf_loading'])
        check('file_paste_is_one_explicit_import_menu_action', host.read()['books'] == 0)
        process, log = source('drag', 'text/uri-list', 'mixed.uris')
        native = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^Native file source$').splitlines()[-1]
        command('wmctrl', '-ir', hex(int(native)), '-e', '0,20,20,240,90')
        command('xdotool', 'windowactivate', '--sync', native)
        sender = bus.wait_application('reader-gtk-drop-native-source')
        button = bus.find_one(sender, roles={'push button'}, text='Drag real book files')
        assert button
        start = bus.extents(button)
        dest = bus.extents(element('Bookshelf', {'scroll pane'}))
        assert start and dest and start['width'] > 50 and dest['height'] > 100
        sx, sy = start['x'] + start['width'] // 2, start['y'] + start['height'] // 2
        dx, dy = dest['x'] + dest['width'] // 2, dest['y'] + 70
        command('xdotool', 'mousemove', '--sync', str(sx), str(sy))
        command('xdotool', 'mousedown', '1')
        for fraction in (.15, .4, .7, 1):
            command('xdotool', 'mousemove', '--sync', str(round(sx + (dx - sx) * fraction)), str(round(sy + (dy - sy) * fraction)))
            time.sleep(.18)
        command('xdotool', 'mouseup', '1')
        wait(lambda: observed().get('accepted') == '1')
        check('real_pointer_drag_delivered_exact_native_uri_bytes', 'NATIVE_FILE_SELECTION' in log.read_text() and
              observed()['payload_sha256'] == hashlib.sha256((args.fixtures / 'mixed.uris').read_bytes()).hexdigest(), dict(source=start, destination=dest))
        stop_source(process)
        wait(lambda: observed('folder_import').get('done') == '1', seconds=90)
        value = observed('folder_import')
        check('native_drop_reports_actual_import_duplicate_and_refusal_counts',
              value['attempted'] == '20' and value['imported'] == '10' and value['duplicates'] == '1' and value['failed'] == '9' and value['pending'] == '0', value)
        check('request_path_duplicates_are_distinct_from_sdk_duplicate_books', observed()['source_items'] == '20' and observed()['source_duplicates'] == '1')
        check('drop_has_no_implicit_book_navigation', host.read()['book'] == 0)
        receipts = [bus.name(node) for node in bus.children(element('Latest file import results', {'list box'}))]
        check('rejected_directory_and_remote_entries_are_visible', any('directory' in name for name in receipts) and any('remote_' in name for name in receipts))
        close_import()
        host.key('F2')
        host.wait(lambda value: value['books'] == 10 and not value['shelf_loading'])
        before = observed()['accepted']
        host.key('ctrl+f', 'ctrl+a')
        host.paste('ordinary text Ctrl+V')
        wait(lambda: bus.accessible_text(element('Search bookshelf', {'text'})).get('text') == 'ordinary text Ctrl+V')
        check('ordinary_text_ctrl_v_is_not_a_file_import_action', observed()['accepted'] == before and observed()['pending'] == '0')
        host.key('ctrl+a', 'BackSpace')
        host.wait(lambda value: value['books'] == 10 and not value['shelf_loading'])
        host.key('F2')
        rows = [node for node in bus.children(element('Bookshelf', {'list box'})) if bus.role(node) == 'list item']
        assert rows
        click_node(rows[0])
        host.wait(lambda value: value['reader_visible'] and value['book'] > 0 and not value['saving'])
        accepted = frame()
        delayed, delayed_log = source('clipboard', 'text/uri-list', 'bulk.uris', delay=5000)
        paste_files()
        wait(lambda: observed().get('pending') == '1' and 'NATIVE_FILE_REQUEST_BEGIN' in delayed_log.read_text())
        host.key('F2')
        check('gtk_remains_responsive_during_real_delayed_clipboard_owner', not host.read()['reader_visible'] and observed()['pending'] == '1')
        host.key('Escape')
        check('escape_cancels_pending_clipboard_without_queuing_import', observed()['pending'] == '0' and observed()['accepted'] == before)
        wait(lambda: observed()['inflight'] == '0', seconds=12)
        check('late_native_clipboard_response_cannot_restart_cancelled_import', observed()['accepted'] == before and observed('folder_import')['owner'] == '0')
        stop_source(delayed)
        clipboard, clipboard_log = source('clipboard', 'x-special/gnome-copied-files', 'bulk.gnome')
        paste_files()
        wait(lambda: int(observed().get('accepted', 0)) == int(before) + 1)
        stop_source(clipboard)
        wait(lambda: observed('folder_import').get('done') == '1', seconds=90)
        value = observed('folder_import')
        check('gnome_cut_paste_owns_payload_after_clipboard_owner_dies', 'NATIVE_FILE_SELECTION' in clipboard_log.read_text() and
              value['attempted'] == '40' and value['imported'] == '40' and value['failed'] == '0' and value['pending'] == '0')
        check('explicit_multi_file_input_keeps_only_32_visible_receipts', value['max_rows'] == '32' and 1 <= int(value['rows']) <= 32)
        check('paste_keeps_accepted_reader_position_and_font', frame() == accepted)
        close_import()
        huge, huge_log = source('clipboard', 'text/uri-list', 'oversize.uris')
        rejected = int(observed()['rejected'])
        paste_files()
        wait(lambda: int(observed()['rejected']) == rejected + 1)
        check('native_payload_over_one_mib_is_refused_before_owner_job', observed('folder_import')['owner'] == '0' and observed()['pending'] == '0' and 'NATIVE_FILE_SELECTION' in huge_log.read_text())
        stop_source(huge)
        delayed, delayed_log = source('clipboard', 'text/uri-list', 'bulk.uris', delay=5000)
        paste_files()
        wait(lambda: observed()['pending'] == '1' and 'NATIVE_FILE_REQUEST_BEGIN' in delayed_log.read_text())
        host.close()
        check('parent_close_finishes_without_waiting_for_clipboard_owner', delayed.poll() is None and host.process.returncode == 0)
        first_rows = inspect('all_selected_originals_and_canonical_mappings_survive_close', manifest['mixed'] + manifest['bulk'])
        host.launch()
        app = bus.wait_application('^exreader-linux$')
        host.wait(lambda value: not value['saving'])
        check('process_reopen_does_not_resume_raw_file_requests', observed()['pending'] == '0' and observed()['accepted'] == '0' and observed('folder_import')['owner'] == '0')
        host.close()
        second_rows = inspect('reopen_keeps_every_original_identity_stable', manifest['mixed'] + manifest['bulk'])
        check('reopen_keeps_real_sdk_ids_and_canonical_keys_stable', sorted(row[:4] for row in first_rows) == sorted(row[:4] for row in second_rows))
        check('cut_drag_and_refused_items_never_mutate_original_files', all(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256'] for row in manifest['originals']))
        report['drop_import_scope_passed'] = True
    except BaseException as error:
        report['error'] = repr(error)
        try:
            command('import', '-window', 'root', str(args.output / 'failure.png'))
            if app:
                (args.output / 'failure-tree.json').write_text(json.dumps(bus.dump(app), ensure_ascii=False, indent=2))
        except BaseException as diagnostic:
            report['diagnostic_error'] = repr(diagnostic)
        raise
    finally:
        report['last_input'] = observed()
        report['last_folder'] = observed('folder_import')
        if host.process and host.process.poll() is None:
            host.process.kill()
            host.process.wait(timeout=10)
        if host.log and not host.log.closed:
            host.log.close()
        for process in sources:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for log in source_logs:
            log.close()
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        bus.exit_bus()


if __name__ == '__main__':
    main()
