# SPDX-License-Identifier: MIT
"""Actions-only real GTK Wave 3 tool checks on the explicit raw0.2 family.

Source identity: this file is tests/reader_wave3_c10/check_ui.py at
blob 43bab342c97cde24ae30556e46cebe269312d66e (DSF-G01, tested source
0be6a226540a8d54e6aa25ac2bf74cbc44d9971e, run 40350391595) with exactly one
added raw-family precondition: the installed raw0.2 importer only commits into a
store that already retains the original identity, so one real record is saved
through the same native Reading records route the retained compact suite uses
before the ten tool checks run. All ten records, the reveal-based chooser, every
timeout and every assertion are unchanged.

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
    browsed = []
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

    def state_section(name):
        value = configparser.ConfigParser(interpolation=None)
        value.read(host.observe, encoding='utf-8')
        return dict(value[name]) if value.has_section(name) else {}

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
        assert box and box['x'] >= 0 and box['y'] >= 0 and box['width'] > 0 and box['height'] > 0, \
            (bus.name(node), box)
        command('xdotool', 'mousemove', '--sync',
                str(box['x'] + box['width'] // 2), str(box['y'] + box['height'] // 2))
        command('xdotool', 'click', '1')
        time.sleep(.15)

    def ancestor(node, roles, stop):
        current = bus._safe(lambda: node.get_parent())
        for _ in range(24):
            if current is None or bus.same(current, stop):
                return None
            if bus.role(current) in roles:
                return current
            current = bus._safe(lambda: current.get_parent())
        return None

    def centre(node):
        box = bus.extents(node)
        if not box:
            return None, None
        return box, (box['x'] + box['width'] // 2, box['y'] + box['height'] // 2)

    def points_into(box, point, outer):
        return (box['width'] > 3 and box['height'] > 3 and box['x'] >= 0 and box['y'] >= 0
                and outer is not None
                and outer['x'] <= point[0] < outer['x'] + outer['width']
                and outer['y'] <= point[1] < outer['y'] + outer['height'])

    def visible_cell(cell, dialog, seconds=25):
        """Wait for GTK itself to report a real screen box for one native cell.

        A tree cell that lies outside the tree view's visible rect is reported
        with x = y = G_MININT (-2147483648) while its real width, height and the
        ATK_STATE_SHOWING state stay set, so an off-screen directory row looks
        actionable even though the click coordinate is -2147483313. The cell's
        own AT-SPI Component focus action is GTK's native scroll-to-cell path
        (gtk_tree_view_grab_cell_focus -> gtk_tree_view_set_cursor_on_cell), the
        same reveal the retained folder-import driver uses. Real input only
        happens once that rectangle is real and its centre lies inside the
        native table, never on a sentinel coordinate.
        """
        component = bus._safe(lambda: cell.get_component_iface())
        assert component is not None, 'native directory cell has no component: ' + bus.name(cell)
        table = ancestor(cell, {'table'}, dialog)
        outer = bus.extents(table) if table is not None else bus.extents(dialog)
        before = bus.extents(cell)
        revealed = bool(bus._safe(lambda: component.grab_focus(), False))
        retry = time.monotonic() + 1
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert host.process.poll() is None, 'host exited'
            box, point = centre(cell)
            if box and points_into(box, point, outer):
                print(json.dumps({'native_row_visible': bus.name(cell), 'reveal': revealed,
                                  'before': before, 'after': box, 'table': outer,
                                  'selected': bool(bus.states(cell).get('selected'))},
                                 ensure_ascii=False), flush=True)
                return box
            if revealed is not True and time.monotonic() >= retry:
                revealed = bool(bus._safe(lambda: component.grab_focus(), False))
                retry = time.monotonic() + 1
            time.sleep(.05)
        raise TimeoutError('native directory row never entered the table viewport: '
                           + bus.name(cell) + ' before ' + repr(before) + ' now '
                           + repr(bus.extents(cell)) + ' table ' + repr(outer)
                           + ' focus ' + repr(revealed))

    def cell_click(cell, dialog, repeat=1):
        box = visible_cell(cell, dialog)
        x, y = box['x'] + box['width'] // 2, box['y'] + box['height'] // 2
        command('xdotool', 'mousemove', '--sync', str(x), str(y))
        if repeat > 1:
            command('xdotool', 'click', '--repeat', str(repeat), '--delay', '150', '1')
        else:
            command('xdotool', 'click', '1')
        time.sleep(.15)
        return box

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
            # SELECT_FOLDER has different location-entry acceptance semantics
            # from OPEN. Reuse the retained folder-import driver's real native
            # table traversal: enter each parent, then select the final folder.
            click('Home', {'label'})
            parts = path.relative_to(Path.home()).parts
            for index, part in enumerate(parts):
                row = element(part, {'table cell'})
                box = cell_click(row, dialog)
                wait_nodes(lambda: [row] if bus.states(row).get('selected') else [])
                browsed.append({'name': part, 'x': box['x'], 'y': box['y']})
                if index + 1 < len(parts):
                    cell_click(row, dialog, repeat=2)
            click(accept, {'push button'})
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
        raise TimeoutError('native file chooser did not close')

    def import_book():
        click('Import book')
        chooser('Import book', book)
        host.wait(lambda value: value['reader_visible'] == 1 and not value['saving'] and not value['error'])

    def save_identity_record():
        """raw0.2 precondition, not one of the ten checks.

        The installed raw importer only commits into a store that already
        retains this original identity, and one real saved record is what
        creates it. The native route below is the one the retained compact
        records suite already drives: Reading -> Reading records... ->
        Add bookmark -> record text -> alt+s.
        """
        menu('Reading', 'Reading records…')
        dialog = element('Reading records', {'dialog'})
        wait_nodes(lambda: [dialog] and state_section('reading_records').get('running') == '0')
        for _ in range(40):
            if any(bus.name(node) == 'Add bookmark' for node in bus.focused_all(app)):
                break
            host.key('Tab')
        else:
            raise AssertionError('native Add bookmark control cannot be reached')
        host.key('Return')
        entry = element('Reading record text', {'text'})
        click_node(entry)
        host.paste('raw identity record')
        host.key('alt+s')
        wait_nodes(lambda: state_section('reading_records').get('count') == '1'
                   and state_section('reading_records').get('running') == '0')
        host.key('Escape')
        wait_nodes(lambda: not nodes('Reading records'))
        idle()

    try:
        assert bus.init()[0]
        host.launch()
        app = bus.wait_application('exreader-linux')
        idle()
        import_book()
        # raw0.2 only: one real record so the raw store retains the identity the
        # installed importer requires; the ten checks below are unchanged.
        save_identity_record()

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
                'created': exported_state['export_created'], 'durable': exported_state['export_durable'],
                'folder_selection': browsed})

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
