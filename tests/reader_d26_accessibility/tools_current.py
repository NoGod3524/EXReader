# D26 current five-tool driver; original frozen driver remains in reader_wave3_c10.
# SPDX-License-Identifier: MIT
"""Actions-only real GTK Wave 3 tool checks.

Drives the installed compact host with real X11 input: the More menu, the real
annotation importer with its checked preview and explicit confirmation, the
local font library with a real on-disk anomaly and a leased face, the original
export against an existing folder, jump history after a real search landing, and
the read-only sync status inside the account window. Observations come from the
host's own [wave3] state section, AT-SPI names/states and the files on disk.
"""
import argparse
import configparser
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import atspi_client as bus

TOOLS = ('Import annotations…', 'Reading font…', 'Export original…',
         'Back to previous position', 'Forward to next position', 'Sync status…')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'book', 'annotations', 'font', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    for name in ('NO_AT_BRIDGE', 'GTK_MODULES', 'AT_SPI_BUS_ADDRESS'):
        os.environ.pop(name, None)
    os.environ['GTK_A11Y'] = 'atspi'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    book = args.book.resolve()
    font_file = args.font.resolve()
    host = Session((args.payload / 'bin/exreader-linux').resolve(),
                   (args.payload / 'Reader.otf').resolve(), output)
    profile = output / 'profile'
    exported = output / 'exported'
    exported.mkdir()
    checks = []
    app = None
    report = {'accepted': False, 'scope': 'five Wave 3 GTK tools only; not a full product acceptance',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks,
              'program_sha256': hashlib.sha256(host.binary.read_bytes()).hexdigest(),
              'original_file': str(book), 'original_sha256': hashlib.sha256(book.read_bytes()).hexdigest(),
              'complete_product': False, 'screen_reader_accepted': False}

    def wave():
        value = configparser.ConfigParser(interpolation=None)
        value.read(host.observe, encoding='utf-8')
        return {key: item for key, item in (value['wave3'].items() if value.has_section('wave3') else [])}

    def wait_wave(predicate, seconds=45, label='wave3'):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert host.process.poll() is None, 'host exited'
            state = wave()
            try:
                if state and predicate(state):
                    return state
            except (KeyError, ValueError):
                pass
            time.sleep(.05)
        raise TimeoutError(label + ': ' + repr(wave()) + ' host: ' + repr(host.read()))

    def nodes(name=None, roles=None, showing=True):
        return [node for node in bus.walk(app)
                if (name is None or bus.name(node) == name)
                and (roles is None or bus.role(node) in roles)
                and (not showing or bus.states(node).get('showing'))]

    def wait_nodes(predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = predicate()
            if found:
                return found
            assert host.process.poll() is None, 'host exited'
            time.sleep(.05)
        raise TimeoutError('native control did not appear')

    def element(name, roles=None):
        return wait_nodes(lambda: nodes(name, roles))[0]

    def click_node(node):
        box = bus.extents(node)
        assert box and box['width'] > 0 and box['height'] > 0, bus.name(node)
        assert box['x'] > -10000 and box['y'] > -10000, ('offscreen native control', bus.name(node), box)
        command('xdotool', 'mousemove', '--sync',
                str(box['x'] + box['width'] // 2), str(box['y'] + box['height'] // 2))
        command('xdotool', 'click', '1')
        time.sleep(.15)

    def click(name, roles=None):
        click_node(element(name, roles))

    def record(name, condition=True, observed=None):
        row = {'name': name, 'pass': bool(condition), 'observed': observed}
        checks.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        assert condition, row

    def snapshot(name):
        command('import', '-window', 'root', str(output / (name + '.png')))

    def frame():
        value = host.read()
        return {key: value[key] for key in ('book', 'part', 'page', 'start', 'end', 'frame_generation')}

    def idle():
        host.wait(lambda value: not value['busy'] and not value['saving'])

    def status_text():
        frame = bus.find_one(app, roles={'frame'}, text='EXReader Linux')
        if frame is None:
            return ''
        root = bus.children(frame)[0]
        labels = [node for node in bus.children(root) if bus.role(node) == 'label']
        return bus.name(labels[0]) if len(labels) == 1 else ''

    def open_menu():
        command('xdotool', 'windowactivate', '--sync', host.window)
        click('More reader actions')

    def menu(section, title):
        open_menu()
        if section:
            click(section, {'menu'})
            host.key('Right')
        click(title, {'menu item'})

    def chooser(name, path, accept=None):
        window = command('xdotool', 'search', '--sync', '--onlyvisible', '--name', '^' + name + '$').splitlines()[-1]
        command('xdotool', 'windowactivate', '--sync', window)
        dialog = element(name, {'file chooser'})
        if accept:
            # The previous run's GTK table cell refused AT-SPI scroll_to. Use the chooser's real keyboard location entry instead,
            # never offscreen cell coordinates or programmatic file selection.
            host.key('ctrl+l')
            entry = wait_nodes(lambda: [node for node in bus.walk(dialog)
                                        if bus.role(node) == 'text' and bus.states(node).get('showing')
                                        and bus.states(node).get('sensitive')
                                        and bus.states(node).get('focused')])
            host.key('ctrl+a')
            host.paste(str(path))
            def location_text():
                return (bus.accessible_text(entry[0]) or {}).get('text', '')
            try:
                # GtkFileChooser may complete an existing directory with a slash.
                # Normalize only path separators/dot segments, not a fuzzy name.
                wait_nodes(lambda: [entry[0]] if os.path.normpath(location_text()) == str(path) else [])
            except TimeoutError:
                raise AssertionError({'expected_location': str(path), 'actual_location': location_text(),
                                      'focused': [dict(name=bus.name(n), role=bus.role(n)) for n in bus.focused_all(app)]})
            # Enter resolves the typed folder through the chooser itself. If
            # SELECT_FOLDER navigates rather than closes, reach its real response
            # button with Tab and press Space; no stale pointer coordinates.
            host.key('Return')
            for response in range(2):
                for _ in range(64):
                    if not nodes(name, {'file chooser'}):
                        return
                    buttons = [node for node in nodes(accept, {'push button'})
                               if bus.is_ancestor(dialog, node)]
                    if len(buttons) == 1 and any(node == buttons[0] for node in bus.focused_all(app)):
                        break
                    host.key('Tab')
                else:
                    raise AssertionError('native Export here button is not keyboard reachable')
                host.key('space')
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if not nodes(name, {'file chooser'}):
                        return
                    time.sleep(.1)
        else:
            host.key('ctrl+l')
            entry = wait_nodes(lambda: [node for node in bus.walk(dialog)
                                        if bus.role(node) == 'text' and bus.states(node).get('showing')
                                        and bus.states(node).get('sensitive')])
            click_node(entry[0])
            host.key('ctrl+a')
            host.paste(str(path))
            time.sleep(.4)
            host.key('Return')
            time.sleep(.6)
            if nodes(name, {'file chooser'}):
                host.key('Return')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^' + name + '$'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 1:
                return
            time.sleep(.1)
        print(json.dumps({'chooser_failure': name, 'requested_path': str(path),
              'controls': [dict(role=bus.role(n), name=bus.name(n), states=bus.states(n),
                                text=bus.accessible_text(n), box=bus.extents(n))
                           for n in bus.walk(dialog) if bus.states(n).get('showing')
                           and bus.role(n) in ('text', 'label', 'push button')]}), flush=True)
        raise TimeoutError('native file chooser did not close')

    def import_book():
        click('Import book')
        chooser('Import book', book)
        host.wait(lambda value: value['reader_visible'] == 1 and not value['saving'] and not value['error'])

    try:
        assert bus.init()[0]
        host.launch()
        app = bus.wait_application('exreader-linux')
        idle()
        import_book()

        # 1. Every tool is reachable from the low-frequency More menu.
        open_menu()
        click('Reading tools', {'menu'})
        host.key('Right')
        found = [name for name in TOOLS if nodes(name, {'menu item'})]
        record('reading_tools_menu_complete', found == list(TOOLS), found)
        host.key('Escape', 'Escape')

        # 2. The default reading screen is unchanged: no tool surface is open and
        #    the primary controls stay the compact reading set.
        anchor = bus.extents(element('Back to library'))
        primary = sorted(bus.name(node) for node in bus.walk(app)
                         if bus.states(node).get('showing') and bus.role(node) in ('push button', 'toggle button')
                         and bus.extents(node) and abs(bus.extents(node)['y'] - anchor['y']) < anchor['height'] // 2)
        record('compact_default_has_no_tool_surfaces',
               not nodes('Annotation import preview') and not nodes('Reading font')
               and not nodes('Sync status details') and not nodes('Annotation import preview details')
               and primary == sorted(['Back to library', 'Previous page', 'Next page', 'Contents / pages',
                                      'More reader actions']), primary)

        # 3. A checked preview validates the whole file and imports nothing.
        menu('Reading tools', 'Import annotations…')
        chooser('Import annotations', args.annotations.resolve())
        preview = element('Annotation import preview', {'dialog'})
        checked = wait_wave(lambda state: state['ann_phase'] == '2', label='preview')
        snapshot('annotation-preview')
        record('annotation_preview_validates_without_writing',
               checked['ann_validated'] == '1' and int(checked['ann_annotations']) >= 1
               and checked['ann_committed'] == '0' and bus.states(preview).get('modal')
               and any(bus.is_ancestor(preview, node) for node in bus.focused_all(app)),
               {key: checked[key] for key in ('ann_phase', 'ann_validated', 'ann_annotations', 'ann_heads',
                                              'ann_committed', 'ann_bytes')})

        # 4. Only the explicit confirmation commits the records.
        click('Import annotations', {'push button'})
        done = wait_wave(lambda state: state['ann_phase'] == '4', label='confirmed import')
        record('annotation_confirm_commits_records',
               int(done['ann_committed']) >= 1 and int(done['ann_created']) >= 1 and int(done['ann_duplicates']) == 0,
               {key: done[key] for key in ('ann_phase', 'ann_created', 'ann_duplicates', 'ann_committed')})

        # 5. A truncated file is refused by the same preview and writes nothing.
        broken = output / 'broken.jsonl'
        payload = args.annotations.read_bytes()
        broken.write_bytes(payload[:-12])
        menu('Reading tools', 'Import annotations…')
        chooser('Import annotations', broken)
        refused = wait_wave(lambda state: state['ann_phase'] == '5', label='refused import')
        message = status_text()
        record('annotation_broken_file_refused_without_writing',
               refused['ann_validated'] == '0' and 'refused' in message.lower()
               and not nodes('Annotation import preview', {'dialog'}),
               {'ann_phase': refused['ann_phase'], 'ann_validated': refused['ann_validated'], 'status': message})

        # 6. Two real fonts are imported; the selected one is leased only after the
        #    frame is accepted and reading continues with it.
        menu('Reading tools', 'Reading font…')
        element('Reading font', {'dialog'})
        click('Add font file…', {'push button'})
        chooser('Add font file', font_file)
        listed = wait_wave(lambda state: state['font_count'] == '1', label='first font import')
        second = Path(font_file).parent / 'fallback.ttf'
        assert second.exists(), 'the fallback fixture font is required'
        click('Add font file…', {'push button'})
        chooser('Add font file', second)
        wait_wave(lambda state: state['font_count'] == '2', label='second font import')
        click(Path(font_file).name, {'list item'})
        click('Use selected', {'push button'})
        applied = wait_wave(lambda state: state['font_busy'] == '0' and int(state['font_applied']) >= 1
                            and len(state['font_active']) == 64, label='font lease')
        primary_hash = applied['font_active']
        snapshot('reading-font')
        click('Close', {'push button'})
        wait_nodes(lambda: not nodes('Reading font'))
        before = host.read()
        host.key('F4')
        after = host.wait(lambda value: value['generation'] > before['generation'] and not value['saving'])
        record('font_import_lease_and_reading_agree',
               after['error'] == 0 and after['book'] == before['book'] and len(primary_hash) == 64,
               {'font_active': primary_hash, 'font_count': applied['font_count'],
                'font_applied': applied['font_applied'], 'book': after['book'], 'error': after['error']})

        # 7. A stored font changed on disk is refused; the previous face and page stay.
        stored = sorted((profile / 'fonts').glob('*.font'))
        assert len(stored) == 2, [str(path) for path in stored]
        anomaly = next(path for path in stored if path.name[:-5] != primary_hash)
        original_bytes = anomaly.read_bytes()
        damaged = bytearray(original_bytes)
        damaged[len(damaged) // 2] ^= 0x55
        anomaly.write_bytes(bytes(damaged))
        retained = frame()
        menu('Reading tools', 'Reading font…')
        element('Reading font', {'dialog'})
        click(second.name, {'list item'})
        click('Use selected', {'push button'})
        failed = wait_wave(lambda state: int(state['font_failed']) >= 1, label='refused font')
        notice = failed['font_notice']
        after_failure = frame()
        snapshot('font-failure-retains-page')
        click('Close', {'push button'})
        wait_nodes(lambda: not nodes('Reading font'))
        before = host.read()
        click('Next page')
        after = host.wait(lambda value: value['start'] != before['start'] and not value['saving'])
        click('Previous page')
        returned_page = host.wait(lambda value: value['start'] == before['start'] and not value['saving'])
        anomaly.write_bytes(original_bytes)
        record('font_anomaly_keeps_previous_font_and_page',
               'previous' in notice.lower() and failed['font_active'] == primary_hash
               and retained == after_failure and after['error'] == 0 and after['book'] == before['book']
               and returned_page['error'] == 0 and returned_page['book'] == before['book'],
               {'font_notice': notice, 'font_active': failed['font_active'],
                'font_failed': failed['font_failed'], 'retained': retained, 'after_failure': after_failure,
                'next_start': after['start'], 'returned_start': returned_page['start'], 'error': after['error']})

        # 8. The original export reproduces the source bytes in an existing folder.
        menu('Reading tools', 'Export original…')
        chooser('Export original', exported, accept='Export here')
        exported_state = wait_wave(lambda state: state['export_phase'] == '4', label='original export')
        written = Path(exported_state['export_path'])
        record('original_export_matches_source_bytes',
               written.exists() and written.read_bytes() == book.read_bytes()
               and int(exported_state['export_bytes']) == book.stat().st_size
               and written.parent == exported,
               {'path': str(written), 'bytes': exported_state['export_bytes'],
                'created': exported_state['export_created'], 'durable': exported_state['export_durable']})

        # 9. A real search landing makes history back and forward available, and only
        #    an accepted frame moves the cursor.
        command('xdotool', 'windowactivate', '--sync', host.window)
        host.key('ctrl+shift+f')
        element('Search within book', {'dialog'})
        click('In-book query', {'text'})
        host.key('ctrl+a')
        host.paste('NEEDLEONE')
        host.key('alt+s')

        def search_rows():
            listing = next((node for node in bus.walk(app) if bus.name(node) == 'In-book results'), None)
            if listing is None:
                return []
            return [row for row in bus.children(listing)
                    if bus.role(row) == 'list item' and bus.name(row).startswith('Search result 1:')]
        result_row = wait_nodes(search_rows)
        click_node(result_row[0])
        landed = wait_wave(lambda state: int(state['history_count']) >= 2 and state['history_can_back'] == '1',
                           label='history landing')
        first_start = host.read()['start']
        menu('Reading tools', 'Back to previous position')
        back = wait_wave(lambda state: int(state['history_cursor']) < int(landed['history_cursor']),
                         label='history back')
        moved = host.wait(lambda value: value['start'] != first_start and not value['saving'])
        menu('Reading tools', 'Forward to next position')
        forward = wait_wave(lambda state: int(state['history_cursor']) > int(back['history_cursor']),
                            label='history forward')
        returned = host.wait(lambda value: value['start'] == first_start and not value['saving'])
        record('history_back_forward_after_real_landing',
               returned['book'] == moved['book'] and int(forward['history_moves']) >= 2
               and landed['back_enabled'] == '1' and landed['forward_enabled'] == '0'
               and back['back_enabled'] == '0' and back['forward_enabled'] == '1'
               and forward['back_enabled'] == '1' and forward['forward_enabled'] == '0',
               {'count': forward['history_count'], 'cursor': forward['history_cursor'],
                'moves': forward['history_moves'], 'landing_start': first_start,
                'back_start': moved['start'], 'forward_start': returned['start']})

        # 10. Sync status is a read-only capture; it never starts a session.
        menu('Reading tools', 'Sync status…')
        element('Account and Sync', {'dialog'})
        wait_nodes(lambda: nodes('Sync status', {'push button'}))
        click('Sync status', {'push button'})
        synced = wait_wave(lambda state: int(state['sync_refreshes']) >= 1 and state['sync_busy'] == '0',
                           label='sync status')
        view = element('Sync status details', {'text'})
        read_only = not bus.states(view).get('editable')
        snapshot('sync-status-read-only')
        host.key('Escape')
        wait_nodes(lambda: not nodes('Account and Sync', {'dialog'}))
        menu('Reading tools', 'Sync status…')
        element('Account and Sync', {'dialog'})
        reopened_view = element('Sync status details', {'text'})
        reopened = wave()
        reopened_text = bus.accessible_text(reopened_view)
        host.key('Escape')
        wait_nodes(lambda: not nodes('Account and Sync', {'dialog'}))
        account = configparser.ConfigParser(interpolation=None)
        account.read(host.observe, encoding='utf-8')
        section = dict(account['account']) if account.has_section('account') else {}
        record('sync_status_read_only',
               synced['sync_text'].startswith('No sync session') and read_only
               and reopened['sync_text'] == synced['sync_text']
               and reopened_text and reopened_text['text'] == synced['sync_text']
               and section.get('session_present', '0') == '0' and section.get('session_state', '0') == '0',
               {'sync_refreshes': synced['sync_refreshes'], 'sync_phase': synced['sync_phase'],
                'sync_text': synced['sync_text'][:120], 'reopened_text': reopened_text, 'editable': not read_only,
                'session_present': section.get('session_present'), 'session_state': section.get('session_state')})

        report['accepted'] = True
    except Exception as error:
        report['failure'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if app is not None:
            try:
                (output / 'atspi-tree.json').write_text(json.dumps(bus.dump(app), indent=2) + '\n', encoding='utf-8')
            except Exception:
                pass
        report['checks'] = checks
        (output / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if host.process is not None and host.process.poll() is None:
            try:
                host.process.kill()
                host.process.wait(timeout=15)
            except Exception:
                pass
        if host.log:
            host.log.close()
        bus.exit_bus()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
