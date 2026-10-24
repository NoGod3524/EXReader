# SPDX-License-Identifier: MIT
"""Actions-only real chooser, finite native receipt list and durable SDK readback."""
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
    for name in ('payload', 'fixtures', 'output', 'backend'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    os.environ.pop('NO_AT_BRIDGE', None)
    os.environ.pop('GTK_MODULES', None)
    os.environ['GTK_A11Y'] = 'atspi'
    output = args.output.resolve()
    output.mkdir()
    source = args.fixtures.resolve()
    backend = args.backend.resolve()
    host = Session((args.payload / 'bin/exreader-linux').resolve(), (args.payload / 'Reader.otf').resolve(), output)
    report = dict(accepted=False, batch_import_scope_passed=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], checks=[],
                  program_sha256=hashlib.sha256(host.binary.read_bytes()).hexdigest(), complete_product=False,
                  settings_whole_page_palette_accepted=False)
    app = None
    manifest = json.loads((source / 'manifest.json').read_text())
    expected = {row['sha256']: row['bytes'] for row in manifest['files'] if row['relative'].startswith('folder 书籍/') and row['relative'].endswith('.txt') and '/nested/' not in row['relative']}

    def observed():
        value = configparser.ConfigParser(interpolation=None)
        value.read(host.observe)
        return dict(value['folder_import']) if value.has_section('folder_import') else {}

    def wait(predicate, seconds=35):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert host.process.poll() is None, 'host exited'
            value = observed()
            if value and predicate(value):
                return value
            time.sleep(.02)
        raise TimeoutError('folder import: ' + repr(observed()) + ' host: ' + repr(host.read()))

    def element(name, roles=None):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            value = next((node for node in bus.walk(app) if bus.name(node) == name and (roles is None or bus.role(node) in roles) and bus.states(node).get('showing')), None)
            if value:
                return value
            time.sleep(.02)
        raise TimeoutError('missing native control: ' + name)

    def click_node(node):
        rect = bus.extents(node)
        assert rect and rect['width'] > 3 and rect['height'] > 3 and bus.states(node).get('sensitive'), bus.name(node)
        command('xdotool', 'mousemove', '--sync', str(rect['x'] + rect['width'] // 2), str(rect['y'] + rect['height'] // 2))
        command('xdotool', 'click', '1')

    def click(name, roles=None):
        click_node(element(name, roles))

    def record(name, condition, actual=None):
        value = dict(name=name, passed=bool(condition), observed=actual)
        report['checks'].append(value)
        print(json.dumps(value, ensure_ascii=False), flush=True)
        assert condition, value

    def launch():
        nonlocal app
        host.launch()
        app = bus.wait_application('exreader-linux')
        host.wait(lambda value: not value['saving'])

    def choose(root, recursive=False):
        command('xdotool', 'windowactivate', '--sync', host.window)
        click('Import sources')
        click('Import folder…', {'menu item'})
        wait(lambda value: value['chooser'] == '1')
        chooser = element('Import folder', {'file chooser'})
        checkbox = element('Include subfolders', {'check box'})
        record('recursive_choice_starts_false_%d' % len(report['checks']), not bus.states(checkbox).get('checked'))
        if recursive:
            click_node(checkbox)
        native = command('xdotool', 'search', '--onlyvisible', '--name', '^Import folder$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', native)
        host.key('ctrl+l')
        entries = [node for node in bus.walk(chooser) if bus.role(node) == 'text' and bus.states(node).get('showing') and bus.states(node).get('sensitive')]
        assert entries, 'native folder location entry missing'
        click_node(entries[0])
        host.key('ctrl+a')
        host.paste(str(root))
        host.key('Return')
        # GTK may accept the selected folder immediately, or navigate into it.
        end = time.monotonic() + 10
        while time.monotonic() < end:
            if observed().get('visible') == '1':
                return
            try:
                node = element('Choose folder', {'push button'})
                if bus.states(node).get('sensitive'):
                    click_node(node)
                    break
            except TimeoutError:
                if observed().get('visible') == '1':
                    return
                raise
            time.sleep(.02)
        wait(lambda value: value['visible'] == '1')

    def close_dialog():
        click('Close', {'push button'})
        wait(lambda value: value['visible'] == '0' and value['owner'] == '0')
        host.wait(lambda value: not value['busy'] and not value['saving'])

    def inspect(name):
        target = output / (name + '.tsv')
        result = subprocess.run([str(backend), str(output / 'profile/library.sqlite'), str(host.font), str(target), 'unused', 'inspect'], capture_output=True, text=True, timeout=30)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        values = []
        for row in target.read_text().splitlines():
            if not row.startswith('#'):
                book, sha, size, position = row.split('\t')
                values.append(dict(book=int(book), sha256=sha, bytes=int(size), position=int(position)))
        return values

    try:
        launch()
        record('empty_bookshelf_and_import_entry_accessible', host.read()['books'] == 0 and bus.states(element('Import F1')).get('sensitive'))
        choose(source / 'folder 书籍')
        value = wait(lambda value: value['done'] == '1', seconds=60)
        record('native_flat_scan_exact_results_and_real_file_failures', value['seen'] == '37' and value['attempted'] == '37' and value['imported'] == '35' and value['duplicates'] == '1' and value['failed'] == '1', value)
        record('normal_completion_does_not_mean_truncation_or_cancellation', value['complete'] == '1' and value['truncated'] == '0' and value['cancelled'] == '0')
        record('native_receipt_window_is_at_most_32_rows', 1 <= int(value['rows']) <= 32 and int(value['max_rows']) == 32)
        nodes = bus.children(element('Latest folder import results'))
        record('visible_receipts_match_bounded_worker_count', sum(bus.role(node) == 'list item' for node in nodes) == int(value['rows']))
        record('every_committed_current_receipt_reconciled_to_bookshelf', value['pending'] == '0')
        close_dialog()
        host.key('F2')
        host.wait(lambda state: not state['reader_visible'] and state['books'] == 35)
        record('real_bookshelf_has_unique_books_and_is_usable', host.read()['books'] == 35)
        host.close()
        first = inspect('flat-originals')
        record('all_public_original_bytes_and_sha_match_sources_no_link_imports', {row['sha256']: row['bytes'] for row in first} == expected and len(first) == 35)
        record('private_staging_directories_removed_on_dialog_close', not list((output / 'profile').glob('*.batch-*')))
        launch()
        choose(source / 'folder 书籍')
        value = wait(lambda value: value['done'] == '1', seconds=60)
        record('close_reopen_reimport_reports_exact_duplicates', value['imported'] == '0' and value['duplicates'] == '36' and value['failed'] == '1')
        close_dialog()
        host.close()
        second = inspect('duplicate-originals')
        record('sdk_ids_product_keys_bytes_and_progress_stable_after_reopen', first == second)
        launch()
        choose(source / 'depth', recursive=True)
        value = wait(lambda value: value['done'] == '1')
        record('native_recursive_depth_budget_truthfully_truncates', value['complete'] == '0' and value['truncated'] == '1' and value['imported'] == '0')
        close_dialog()
        choose(source / 'cancel')
        wait(lambda value: 1 <= int(value['imported']) < 90)
        command('xdotool', 'windowactivate', '--sync', host.window)
        host.key('F2')
        record('main_bookshelf_remains_responsive_during_import', not host.read()['reader_visible'])
        native = command('xdotool', 'search', '--onlyvisible', '--name', '^Folder import$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', native)
        click('Cancel import', {'push button'})
        requested = wait(lambda value: value['cancel_requested'] == '1')
        value = wait(lambda value: value['done'] == '1')
        record('native_cancel_stops_later_items_and_keeps_committed', value['cancelled'] == '1' and 1 <= int(value['imported']) < 96 and int(value['attempted']) <= int(requested['attempted']) + 1 and value['pending'] == '0', value)
        imported = int(value['imported'])
        close_dialog()
        host.close()
        cancelled = inspect('cancelled-originals')
        record('cancelled_committed_originals_survive_close', len(cancelled) == 35 + imported and set(row['sha256'] for row in first).issubset(row['sha256'] for row in cancelled))
        launch()
        time.sleep(.4)
        record('restart_does_not_silently_resume_folder_enumeration', observed()['owner'] == '0' and observed()['visible'] == '0')
        choose(source / 'closing')
        wait(lambda value: 1 <= int(value['imported']) < 90)
        command('xdotool', 'windowactivate', '--sync', host.window)
        host.close()
        closed = inspect('closed-originals')
        record('application_close_reconciles_committed_book_without_resuming_later_files', len(cancelled) < len(closed) < len(cancelled) + 96)
        record('shutdown_removes_private_staging_directory', not list((output / 'profile').glob('*.batch-*')))
        launch()
        host.key('F2')
        host.wait(lambda state: not state['reader_visible'] and not state['busy'])
        record('reopened_bookshelf_keeps_canonical_product_mappings', min(len(closed), 50) <= host.read()['books'] <= min(len(closed), 150))
        host.close()
        record('reopen_keeps_all_original_identities_stable', inspect('final-originals') == closed)
        unchanged = all((source / row['relative']).is_file() and hashlib.sha256((source / row['relative']).read_bytes()).hexdigest() == row['sha256'] for row in manifest['files'])
        record('enumeration_staging_and_import_never_mutate_any_source_file', unchanged)
        allowed = {row['sha256']: row['bytes'] for row in manifest['files'] if row['relative'].startswith(('folder 书籍/', 'cancel/', 'closing/')) and row['relative'].endswith('.txt') and '/nested/' not in row['relative']}
        record('every_cancel_and_shutdown_original_is_a_byte_exact_selected_regular_file', all(allowed.get(row['sha256']) == row['bytes'] for row in closed))
        report['batch_import_scope_passed'] = True
    except BaseException as error:
        report['error'] = repr(error)
        try:
            command('import', '-window', 'root', str(output / 'failure.png'))
            if app:
                (output / 'failure-tree.json').write_text(json.dumps(bus.dump(app), ensure_ascii=False, indent=2))
        except BaseException as diagnostic:
            report['diagnostic_error'] = repr(diagnostic)
        raise
    finally:
        report['checks_total'] = len(report['checks'])
        report['checks_failed'] = sum(not row['passed'] for row in report['checks'])
        report['last_observation'] = observed()
        if host.process and host.process.poll() is None:
            host.process.kill()
            host.process.wait(timeout=10)
        if host.log and not host.log.closed:
            host.log.close()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({key: report[key] for key in ('batch_import_scope_passed', 'source_sha', 'run_id', 'attempt', 'checks_total', 'checks_failed', 'program_sha256')}), flush=True)
        bus.exit_bus()


if __name__ == '__main__':
    main()
