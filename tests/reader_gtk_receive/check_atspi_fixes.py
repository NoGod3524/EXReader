# SPDX-License-Identifier: MIT
"""Actions-only targeted regressions for eight G13 GTK production findings.

Uses G13's fixed read-only AT-SPI transport helper, not its audit or acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import atspi_client as bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    os.environ.pop('NO_AT_BRIDGE', None)
    os.environ['GTK_MODULES'] = 'gail:atk-bridge'
    output = args.output.resolve();output.mkdir()
    host = Session((args.payload / 'bin/exreader-linux').resolve(),
                   (args.payload / 'Reader.otf').resolve(), output)
    source = output / 'Named book.txt'
    source.write_text('Accessible native reading. Select this sentence.\n' * 100, encoding='utf-8')
    invalid = output / 'invalid.epub';invalid.write_bytes(b'invalid EPUB')
    checks, keys = [], []
    recorder = bus.Recorder()
    report = {'accepted': False, 'scope': 'targeted GTK fixes, not G13 full audit or Orca',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'checks': checks,
              'helper_source': '67e2f8c4941205c5581e82fd5a1469d18f696019',
              'program_sha256': hashlib.sha256(host.binary.read_bytes()).hexdigest(),
              'g13_audit_accepted': False, 'orca_accepted': False, 'complete_product': False}

    def wait(predicate, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            found = predicate()
            if found: return found
            assert host.process.poll() is None
            time.sleep(.15)
        raise TimeoutError('AT-SPI predicate did not settle')

    def key(*values):
        host.key(*values)
        keys.extend({'key': value, 'focused': [bus.path_of(node) for node in bus.focused_all(app)]}
                    for value in values)

    def check(name, condition, observed=None):
        checks.append({'name': name, 'pass': bool(condition), 'observed': observed})
        assert condition, checks[-1]
        print(json.dumps(checks[-1]), flush=True)

    def snap(name):
        (output / (name + '.json')).write_text(json.dumps(bus.dump(app), indent=2), encoding='utf-8')
        command('import', '-window', host.window, str(output / (name + '.png')))

    def focused_inside(surface):
        return any(bus.same(surface, node) or bus.is_ancestor(surface, node)
                   for node in bus.focused_all(app))

    try:
        assert bus.init()[0] and recorder.start()
        host.launch();app = bus.wait_application('exreader-linux')
        host.dialog(source);host.wait(lambda state: state['book'] > 0 and not state['error'])
        key('F2');host.wait(lambda state: not state.get('shelf_loading') and not state.get('shelf_restoring'))
        shelf = wait(lambda: bus.find_one(app, roles={'list box'}, text='Bookshelf'))
        rows = wait(lambda: [node for node in bus.children(shelf) if bus.role(node) == 'list item'])
        check('shelf_rows_named', all(bus.name(row) for row in rows), [bus.name(row) for row in rows])
        stops = []
        for _ in range(26):
            key('Tab');stops.extend({'name': bus.name(node), 'role': bus.role(node)} for node in bus.focused_all(app))
        check('shelf_tab_stops_named', bool(stops) and all(stop['name'] for stop in stops), stops)
        snap('shelf')
        key('ctrl+shift+c')
        dialog = wait(lambda: bus.find_one(app, roles={'dialog'}, text='Library collections'))
        host.wait(lambda state: True)
        wait(lambda: focused_inside(dialog))
        check('collections_initial_focus', focused_inside(dialog), [bus.name(node) for node in bus.focused_all(app)])
        selector = bus.find_one(dialog, roles={'combo box'}, text='Collection type')
        reachable = False
        for _ in range(26):
            key('Tab')
            reachable |= bool(selector and focused_inside(selector))
        check('collections_type_in_tab_cycle', reachable)
        scrolls = bus.find_all(dialog, roles={'scroll pane'})
        check('collections_scroll_containers_named', len(scrolls) >= 2 and all(bus.name(node) for node in scrolls),
              [bus.name(node) for node in scrolls])
        snap('collections');key('Escape')
        wait(lambda: not bus.find_one(app, roles={'dialog'}, text='Library collections'))
        key('ctrl+shift+a')
        dialog = wait(lambda: bus.find_one(app, roles={'dialog'}, text='Account and Sync'))
        host.wait(lambda state: True)
        wait(lambda: focused_inside(dialog))
        check('account_declares_modal', bus.states(dialog).get('modal'), bus.states(dialog))
        snap('account');key('Escape')
        wait(lambda: not bus.find_one(app, roles={'dialog'}, text='Account and Sync'))
        frame = bus.find_one(app, roles={'frame'}, text='EXReader Linux')
        wait(lambda: focused_inside(frame))
        check('account_escape_restores_internal_focus', focused_inside(frame), [bus.name(node) for node in bus.focused_all(app)])
        key('F2', 'Return');host.wait(lambda state: state['reader_visible'] == 1)
        key('F7', 'ctrl+a');host.wait(lambda state: state['selected'] > 0)
        key('F11');host.paste('Named note');key('F8');host.wait(lambda state: state['notes'] == 1)
        notes = wait(lambda: bus.find_one(app, roles={'list box'}, text='Saved notes; activate to return to selected text'))
        rows = wait(lambda: [node for node in bus.children(notes) if bus.role(node) == 'list item'])
        check('annotation_rows_named', all(bus.name(row) for row in rows), [bus.name(row) for row in rows])
        mark = recorder.mark();host.dialog(invalid);host.wait(lambda state: state['error'] != 0)
        events = wait(lambda: [event for event in recorder.since(mark)
                              if event['type'].startswith('object:property-change')
                              and event['detail1'] == 'accessible-name' and event.get('source_role') == 'label'
                              and event.get('source_name') == 'Reading operation failed; accepted page retained'])
        check('status_delivers_accessible_name_event', bool(events), events)
        snap('status');assert len(checks) == 9
        report.update(accepted=True, count=len(checks))
    finally:
        recorder.stop()
        (output / 'events.json').write_text(json.dumps(recorder.items, indent=2), encoding='utf-8')
        (output / 'keys.json').write_text(json.dumps(keys, indent=2), encoding='utf-8')
        (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if host.process and host.process.poll() is None:
            host.process.kill();host.process.wait(timeout=15)
        if host.log: host.log.close()
        bus.exit_bus()
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
