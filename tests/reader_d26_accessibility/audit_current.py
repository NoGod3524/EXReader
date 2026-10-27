# D26 corrected current driver; original historical audit is retained separately.
#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""AT-SPI and real-keyboard audit of the GTK product host, Actions only.

Every observation is taken over the accessibility bus (name, role, state,
actions, relations, attributes, screen extents, delivered events) while every
transition is produced by xdotool keystrokes on the mapped window.  Each named
check records the native element path, the reproduction steps, the actual and
the expected value.  The audit never repairs product source: the GTK receiver
owns those files.

audit_completed and accessibility_accepted are reported separately.  A blocking
finding keeps accessibility_accepted false, and no report claims Orca or human
screen-reader acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reader_a11y_gtk"))

import atspi_client as a11y
import driver
import current_expectations as contract


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SourceRecorder(a11y.Recorder):
    """Retain event source proxies for identity checks, never synthesize events."""
    def __init__(self):
        super().__init__()
        self.name_sources = []

    def _callback(self, event):
        if str(getattr(event, 'type', '')) == 'object:property-change:accessible-name':
            source = getattr(event, 'source', None)
            with self.lock:
                self.name_sources.append((source, a11y.name(source)))
        super()._callback(event)


class Audit:
    """Named checks with actual/expected evidence, findings and gaps."""

    def __init__(self, folder, meta):
        self.folder = folder
        self.meta = meta
        self.checks = []
        self.phases = []
        self.observations = {}
        self.dynamic_gaps = []

    def check(self, name, ok, expected, actual, element='', severity='blocking',
              reproduction=(), fix='', evaluated=True):
        entry = {'name': name, 'pass': bool(ok), 'evaluated': bool(evaluated),
                 'severity': severity,
                 'expected': expected, 'actual': actual, 'element': element,
                 'reproduction': list(reproduction), 'minimal_fix': fix}
        self.checks.append(entry)
        print('CHECK %-56s %s' % (name, 'PASS' if ok else 'FAIL'), flush=True)
        return entry

    def gap(self, text):
        if text not in self.dynamic_gaps:
            self.dynamic_gaps.append(text)

    def fill_missing(self):
        recorded = {entry['name'] for entry in self.checks}
        for name, phase in contract.CHECKS:
            if name in recorded:
                continue
            self.checks.append({
                'name': name, 'pass': False, 'evaluated': False, 'severity': 'blocking',
                'expected': 'check recorded by audit phase %r' % phase,
                'actual': 'not recorded: the phase did not reach this check',
                'element': '', 'minimal_fix': 'repair the audit harness or the host defect that '
                'aborted phase %r' % phase,
                'reproduction': ['run the audit workflow and read tree/%s-failed.json and '
                                 'shots/%s-failed.png' % (phase, phase)]})

    def findings(self):
        out = []
        for entry in self.checks:
            if entry['pass']:
                continue
            out.append({'check': entry['name'], 'severity': entry['severity'],
                        'evaluated': entry['evaluated'], 'element': entry['element'],
                        'expected': entry['expected'], 'actual': entry['actual'],
                        'reproduction': entry['reproduction'],
                        'minimal_fix': entry['minimal_fix']})
        out.sort(key=lambda item: (item['severity'] != 'blocking', item['check']))
        return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'This audit runs on the Actions runner only'
    folder = args.output.resolve()
    if folder.exists():
        parser.error('choose a new evidence directory')
    folder.mkdir(parents=True)
    for name in ('tree', 'shots', 'corpus', 'logs'):
        (folder / name).mkdir()

    binary = (args.payload / 'bin/exreader-linux').resolve(strict=True)
    font = (args.payload / 'Reader.otf').resolve(strict=True)
    meta = {'source_sha': os.environ.get('GITHUB_SHA', ''),
            'run_id': os.environ.get('GITHUB_RUN_ID', ''),
            'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
            'start_sha': contract.START_SHA,
            'sdk': {'commit': contract.SDK_SHA, 'version': contract.SDK_VERSION,
                    'abi': contract.SDK_ABI},
            'program_sha256': sha256_file(binary), 'font_sha256': sha256_file(font),
            'display': os.environ.get('DISPLAY', ''), 'payload': str(args.payload)}
    audit = Audit(folder, meta)
    host = driver.Host(binary, font, folder, title=contract.WINDOW_TITLE)
    recorder = SourceRecorder()
    secret = 'A11y-' + secrets.token_hex(12)

    # -- corpus ------------------------------------------------------------
    books = []
    for title, body in (('Alpha shelf book', 'Alpha page text for the audit. '),
                        ('Beta shelf book', 'Beta page text for the audit. '),
                        ('Gamma shelf book', 'Gamma page text for the audit. ')):
        path = folder / 'corpus' / (title.replace(' ', '-') + '.txt')
        path.write_text((body * 40) + ('\u4e2d\u6587 caf\u00e9 \u0928\u092e\u0938\u094d\u0924\u0947.\n' * 12),
                        encoding='utf-8')
        books.append(path)
    invalid = folder / 'corpus' / 'invalid.epub'
    invalid.write_bytes(b'not an epub document')

    # -- accessibility helpers --------------------------------------------
    def current_app():
        return a11y.wait_application('exreader', timeout=15)

    def frame():
        found = a11y.find_one(current_app(), roles=('frame',), text=contract.WINDOW_TITLE)
        return found or a11y.find_one(current_app(), roles=('frame',))

    def wait_element(text, roles=None, timeout=25):
        # A named scroll region is not its independently named content control.
        named_roles = {
            contract.NAMES['shelf_list']: contract.LIST_ROLES,
            contract.NAMES['notes_list']: contract.LIST_ROLES,
            contract.NAMES['page_text']: contract.ENTRY_ROLES,
            contract.NAMES['comment']: contract.ENTRY_ROLES,
            contract.NAMES['search']: contract.ENTRY_ROLES,
            contract.NAMES['page_image']: ('icon', 'image'),
            contract.COLLECTIONS_DIALOG: contract.DIALOG_ROLES,
            contract.ACCOUNT_DIALOG: contract.DIALOG_ROLES,
            contract.METADATA_DIALOG: contract.DIALOG_ROLES,
            contract.IMPORT_DIALOG: contract.DIALOG_ROLES + ('file chooser',),
            contract.COLLECTIONS_NAMES['type']: ('combo box',),
            contract.COLLECTIONS_NAMES['removed']: ('check box',),
            contract.COLLECTIONS_NAMES['groups']: contract.LIST_ROLES,
            contract.COLLECTIONS_NAMES['members']: contract.LIST_ROLES,
        }
        if roles is None:
            roles = named_roles.get(text)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = a11y.find_all(current_app(), roles=roles, text=text)
            candidates = [node for node in candidates if a11y.states(node).get('showing')]
            if len(candidates) == 1:
                return candidates[0]
            time.sleep(0.1)
        return None

    def snapshot(node):
        if node is None:
            return {'path': '', 'role': '', 'name': '', 'states': {}, 'extents': None}
        return {'path': a11y.path_of(node), 'role': a11y.role(node), 'name': a11y.name(node),
                'states': a11y.states(node), 'extents': a11y.extents(node)}

    def focus_node():
        try:
            nodes = a11y.focused_all(current_app())
        except Exception:
            nodes = []
        return nodes[0] if nodes else None

    def focus_snapshot():
        return snapshot(focus_node())

    def focus_restored():
        """Observe asynchronous WM/AT-SPI focus restoration, without setting it."""
        deadline = time.monotonic() + 6
        node = main = None
        while time.monotonic() < deadline:
            node, main = focus_node(), frame()
            if node is not None and main is not None and (
                    a11y.same(node, main) or a11y.is_ancestor(main, node)):
                return True, node, main
            time.sleep(.08)
        return False, node, main

    def focus_name():
        return focus_snapshot()['name']

    host.focus_hook = focus_name

    def wait_focus_change(previous, timeout=6):
        deadline = time.monotonic() + timeout
        current = focus_snapshot()
        while time.monotonic() < deadline:
            if current['path'] != previous:
                return current
            time.sleep(0.08)
            current = focus_snapshot()
        return current

    def traverse(count):
        sequence = []
        previous = ''
        for _ in range(count):
            host.key('Tab')
            current = wait_focus_change(previous)
            sequence.append(current)
            previous = current['path']
        return sequence

    def tab_to(target, limit=30):
        for _ in range(limit):
            if focus_name() == target:
                return True
            host.key('Tab')
        return focus_name() == target

    def wait_rows(listing, minimum, timeout=25):
        """Rows are created by the shelf/notes result handler after the stack switches."""
        deadline = time.monotonic() + timeout
        rows = a11y.children(listing) if listing is not None else []
        while time.monotonic() < deadline and len(rows) < minimum:
            time.sleep(0.15)
            rows = a11y.children(listing) if listing is not None else []
        return rows

    def dump_tree(tag):
        tree = a11y.dump(current_app())
        path = folder / 'tree' / (tag + '.json')
        path.write_text(json.dumps(tree, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        (folder / 'tree' / (tag + '.txt')).write_text('\n'.join(a11y.render(tree)) + '\n',
                                                      encoding='utf-8')
        return path

    def shot(tag, window=None):
        path = folder / 'shots' / (tag + '.png')
        host.screenshot(path, window)
        return path

    def idle(timeout=120):
        # reader.c leaves shelf_restoring set while the reader is the visible child, so the
        # shelf bookkeeping only has to settle when the shelf is the one on screen.
        return host.wait_state(
            lambda state: not state.get('busy') and not state.get('saving')
            and (state.get('reader_visible') == 1
                 or (not state.get('shelf_loading') and not state.get('shelf_restoring'))),
            timeout=timeout)

    def dialog_window(title, present=True, timeout=30):
        return host.window_named(title, present, timeout=timeout)

    def chooser_visible():
        return driver.command('xdotool', 'search', '--onlyvisible', '--name',
                              '^' + contract.IMPORT_DIALOG + '$').returncode == 0

    def run_chooser(path, timeout=40):
        host.activate(host.window)
        idle()
        host.key('F1')
        chooser = dialog_window(contract.IMPORT_DIALOG, True)
        host.activate(chooser)
        host.key('ctrl+l')
        host.key('ctrl+a')  # drop any location the chooser prefilled
        host.type_text(str(path))
        host.key('Return')
        time.sleep(0.4)
        if chooser_visible():
            host.key('Return')
        driver.wait_until(lambda: not chooser_visible(), timeout,
                          description='import chooser to close')

    def import_file(path, expect_books):
        run_chooser(path)
        return host.wait_state(lambda state: not state.get('busy') and not state.get('saving')
                               and state.get('books', 0) >= expect_books, timeout=120,
                               description='library row count to grow')

    def failed_import(path):
        run_chooser(path)
        return idle(120)

    def status_node():
        """The first label in pre-order inside the main frame is the status label."""
        root = frame()
        if root is None:
            return None
        for node in a11y.walk(root):
            if a11y.role(node) == 'label' and a11y.name(node):
                return node
        return None

    def close_with_escape(title, timeout=40):
        for _ in range(2):
            idle()
            host.key('Escape')
            try:
                dialog_window(title, False, timeout=timeout)
                return
            except TimeoutError:
                continue
        raise TimeoutError('dialog %r stayed open after two real Escape presses' % title)

    def selected_menu_item():
        for node in a11y.find_all(current_app(), roles=('menu item',)):
            current = a11y.states(node)
            if current.get('showing') and (current.get('selected') or current.get('focused')):
                return a11y.name(node)
        return ''

    def choose_menu_item(target):
        host.key('Home')
        time.sleep(0.25)
        current = selected_menu_item()
        if current == target:
            return True
        if not current:
            # No item reports SELECTED or FOCUSED; Home still targets the first entry.
            shown = [a11y.name(node) for node in a11y.find_all(current_app(), roles=('menu item',))
                     if a11y.states(node).get('showing')]
            return bool(shown) and shown[0] == target
        for _ in range(4):
            host.key('Down')
            time.sleep(0.12)
            if selected_menu_item() == target:
                return True
        return False

    # -- phases ------------------------------------------------------------
    def phase_bridge():
        app = a11y.wait_application('exreader', timeout=180)
        applications = [a11y.name(entry) for entry in a11y.applications()]
        # The application registers with the registry before it creates its window,
        # so wait for the frame the same way a user waits for the window to appear.
        found = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and found is None:
            found = a11y.find_one(app, roles=('frame',), text=contract.WINDOW_TITLE)
            if found is None:
                time.sleep(0.2)
        frames = [a11y.name(entry) for entry in a11y.find_all(app, roles=('frame',))]
        audit.check(
            'atspi_bridge_exposes_main_window', found is not None,
            expected='the accessibility bus lists this process as an application exposing a '
                     'frame named %r' % contract.WINDOW_TITLE,
            actual={'applications': applications, 'frames': frames,
                    'application_role': a11y.role(app), 'application_name': a11y.name(app),
                    'registered_events': recorder.registered,
                    'rejected_events': recorder.rejected},
            element=snapshot(found)['path'] if found is not None else 'desktop/%r' % (applications,),
            severity='blocking',
            reproduction=['launch bin/exreader-linux with the AT-SPI bridge enabled',
                          'read the desktop children and the frame role through AT-SPI'],
            fix='none for the host: this check proves the audit sees the real tree')
        dump_tree('00-bridge')
        shot('00-bridge')
        audit.observations['bridge'] = {
            'application': a11y.name(app), 'applications': applications,
            'atspi_version': a11y.atspi_version(), 'registered_events': recorder.registered,
            'rejected_events': recorder.rejected}

    def phase_shelf():
        host.activate(host.window)
        idle()
        host.key('F2')
        idle()
        listing = wait_element(contract.NAMES['shelf_list'])
        listing_role = a11y.role(listing) if listing is not None else None
        audit.check('shelf_list_named',
                    listing is not None and listing_role in contract.LIST_ROLES,
                    expected='the shelf list exposes the accessible name %r with a list role'
                             % contract.NAMES['shelf_list'],
                    actual={'found': listing is not None, 'role': listing_role,
                            'rows': len(a11y.children(listing)) if listing is not None else None},
                    element=snapshot(listing)['path'],
                    reproduction=['press F2 to show the shelf',
                                  'read the list element through AT-SPI'],
                    fix='if the role is not a list role: the name is already set in reader.c, so '
                        'the container role would need an explicit accessible type')

        buttons = a11y.find_all(current_app(), roles=contract.BUTTON_ROLES)
        by_name = {}
        for node in buttons:
            by_name.setdefault(a11y.name(node), node)
        missing = [entry for entry in contract.TOOLBAR if entry not in by_name]
        without_action = [entry for entry in contract.TOOLBAR
                          if entry in by_name and not any(action['name'] == 'click'
                                                          for action in a11y.actions(by_name[entry]))]
        audit.check('shelf_toolbar_names_and_actions', not missing and not without_action,
                    expected='all ten toolbar buttons are exposed with their label text as the '
                             'accessible name and a clickable action',
                    actual={'missing': missing, 'without_click_action': without_action,
                            'roles': {entry: a11y.role(by_name[entry]) for entry in contract.TOOLBAR
                                      if entry in by_name}},
                    element=snapshot(by_name.get(contract.TOOLBAR[0]))['path'],
                    reproduction=['show the shelf with F2',
                                  'list every button on the bus and compare names'],
                    fix='none: the labels already carry the shortcut text')

        details = by_name.get(contract.NAMES['details'])
        more = by_name.get(contract.NAMES['more'])
        audit.check('shelf_action_row_names', details is not None and more is not None,
                    expected='the shelf action row exposes %r and %r'
                             % (contract.NAMES['details'], contract.NAMES['more']),
                    actual={'details': snapshot(details), 'more': snapshot(more)},
                    element=snapshot(more)['path'],
                    reproduction=['show the shelf with F2', 'read the action row elements'],
                    fix='none: both names are set through atk_object_set_name in reader.c')

        entry = wait_element(contract.NAMES['search'])
        audit.check('shelf_search_entry',
                    entry is not None and a11y.states(entry).get('editable', False),
                    expected='the search field is exposed as an editable entry named %r'
                             % contract.NAMES['search'],
                    actual=snapshot(entry),
                    element=snapshot(entry)['path'],
                    reproduction=['show the shelf with F2', 'read the entry element'],
                    fix='none: the name and EDITABLE state come from GTK')

        dump_tree('01-shelf')
        shot('01-shelf')
        audit.observations['shelf'] = {'buttons': sorted(by_name), 'list_role': listing_role}

    def phase_shelf_tab_order():
        host.activate(host.window)
        host.key('Escape')
        idle()
        sequence = traverse(26)
        names = [entry['name'] for entry in sequence]
        expected_controls = list(contract.TOOLBAR) + [contract.NAMES['search'],
                                                      contract.NAMES['details'],
                                                      contract.NAMES['more']]
        missing = [entry for entry in expected_controls if entry not in names]
        focused_steps = [entry for entry in sequence if entry['path']]
        if not focused_steps:
            audit.gap('No element carried the FOCUSED state during Tab traversal, so the focus '
                      'order could not be evaluated')
        audit.check('shelf_tab_order_reaches_controls', not missing and bool(focused_steps),
                    expected='Tab reaches every toolbar button, the search field, the details '
                             'button and the more menu button',
                    actual={'missing': missing, 'sequence': names},
                    element='window/%s' % contract.WINDOW_TITLE,
                    reproduction=['show the shelf with F2',
                                  'press Tab 26 times and read the FOCUSED element after each'],
                    evaluated=bool(focused_steps),
                    fix='none when the sequence is complete')

        def first_cycle(observations, available):
            cycle = []
            for entry in observations:
                if entry in available and entry not in cycle:
                    cycle.append(entry)
            return cycle

        def cyclic_equal(observed, expected):
            if len(observed) != len(expected) or not expected:
                return False
            return any(observed == expected[index:] + expected[:index]
                       for index in range(len(expected)))

        toolbar_cycle = first_cycle(names, set(contract.TOOLBAR))
        toolbar_order_ok = cyclic_equal(toolbar_cycle, list(contract.TOOLBAR))
        row_names = [contract.NAMES['search'], contract.NAMES['details'], contract.NAMES['more']]
        boxes = []
        for text in row_names:
            deadline = time.monotonic() + 6
            box = None
            while time.monotonic() < deadline:
                node = a11y.find_one(frame(), roles=contract.BUTTON_ROLES + contract.ENTRY_ROLES,
                                     text=text)
                box = a11y.extents(node) if node is not None else None
                if (box and a11y.states(node).get('showing') and box['width'] > 0
                        and box['height'] > 0 and box['x'] > -10000 and box['y'] > -10000):
                    break
                box = None
                time.sleep(.08)
            if box is not None:
                boxes.append((text, box))
        visual_order = [text for text, _ in sorted(boxes, key=lambda pair: (pair[1]['y'],
                                                                          pair[1]['x']))]
        row_cycle = first_cycle(names, set(row_names))
        row_order_ok = cyclic_equal(row_cycle, visual_order)
        audit.check('shelf_tab_order_follows_visual_order',
                    toolbar_order_ok and row_order_ok and len(boxes) == len(row_names),
                    expected='focus order matches the visual left-to-right order of the toolbar '
                             'and of the shelf action row',
                    actual={'toolbar_focus_cycle': toolbar_cycle,
                            'toolbar_expected_cycle': list(contract.TOOLBAR),
                            'toolbar_matches': toolbar_order_ok,
                            'action_row_focus_cycle': row_cycle,
                            'action_row_visual_order': visual_order,
                            'action_row_matches': row_order_ok,
                            'action_row_extents': dict(boxes)},
                    element='window/%s' % contract.WINDOW_TITLE, severity='blocking',
                    evaluated=bool(focused_steps),
                    reproduction=['show the shelf with F2',
                                  'press Tab and compare the focus order with the element '
                                  'extents reported by AT-SPI'],
                    fix='create the row in visual order: call gtk_box_pack_end for the more '
                        'button before the details button in reader.c, so the focus chain '
                        'agrees with the drawn order')

        unnamed = [{'role': entry['role'], 'name': entry['name'], 'path': entry['path']}
                   for entry in focused_steps if not entry['name']]
        audit.check('tab_cycle_elements_named', bool(focused_steps) and not unnamed,
                    expected='every element that takes keyboard focus exposes a non-empty '
                             'accessible name',
                    actual={'unnamed_focus_stops': unnamed,
                            'cycle': [{'role': entry['role'], 'name': entry['name']}
                                      for entry in sequence]},
                    element=unnamed[0]['path'] if unnamed else '',
                    severity='blocking',
                    evaluated=bool(focused_steps),
                    reproduction=['show the shelf with F2',
                                  'press Tab through one complete cycle and read the name of the '
                                  'FOCUSED element after each press'],
                    fix='the focusable element is the GtkScrolledWindow the host wraps each list '
                        'in; GTK leaves its accessible unnamed while it still takes focus, so name '
                        'it in reader.c: atk_object_set_name(gtk_widget_get_accessible('
                        'gtk_widget_get_ancestor(image, GTK_TYPE_SCROLLED_WINDOW)), "Page") and '
                        'the same for the shelf, notes, organizer group and member lists')

        cycles = len(names) - len({entry['path'] for entry in sequence}) > 0
        audit.check('shelf_tab_order_cycles_without_trap', cycles,
                    expected='26 real Tab presses return to an already focused element, so focus '
                             'is not trapped',
                    actual={'distinct_focus_paths': len({entry['path'] for entry in sequence}),
                            'presses': len(sequence)},
                    element='window/%s' % contract.WINDOW_TITLE, severity='advisory',
                    reproduction=['press Tab 26 times from the shelf'],
                    fix='none when focus cycles')
        audit.observations['shelf_tab_order'] = [
            {'name': entry['name'], 'role': entry['role'], 'path': entry['path']}
            for entry in sequence]

    def phase_menu():
        host.activate(host.window)
        host.key('F2')
        idle()
        reached = tab_to(contract.NAMES['more'])
        host.key('space')
        items = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            items = [node for node in a11y.find_all(current_app(), roles=('menu item',))
                     if a11y.states(node).get('showing')]
            if items:
                break
            time.sleep(0.1)
        shown = [node for node in items if a11y.states(node).get('showing')]
        names = [a11y.name(node) for node in shown]
        missing = [entry for entry in contract.MORE_MENU_ITEMS if entry not in names]
        audit.check('more_menu_items_named', reached and bool(shown) and not missing,
                    expected='the more menu button opens a menu whose items are named %r'
                             % (contract.MORE_MENU_ITEMS,),
                    actual={'reached_more_button': reached, 'menu_items': names,
                            'missing': missing, 'roles': [a11y.role(node) for node in items]},
                    element=snapshot(items[0])['path'] if items else snapshot(frame())['path'],
                    severity='advisory',
                    reproduction=['press F2, Tab to the more menu button, press space',
                                  'read the menu item roles and names'],
                    fix='none: the items are created with gtk_menu_item_new_with_label')
        dump_tree('02-more-menu')
        shot('02-more-menu')

        chosen = choose_menu_item(contract.MORE_MENU_ITEMS[0])
        host.key('Return')
        activated = None
        try:
            activated = dialog_window(contract.COLLECTIONS_DIALOG, True, timeout=30)
        except TimeoutError:
            activated = None
        audit.check('more_menu_keyboard_activation', chosen and activated is not None,
                    expected='keyboard selection of %r in the more menu opens the Library '
                             'collections dialog' % contract.MORE_MENU_ITEMS[0],
                    actual={'menu_item_selected': chosen, 'menu_items': names,
                            'dialog_window': activated,
                            'focused_after_activation': focus_snapshot()},
                    element='window/%s' % contract.WINDOW_TITLE,
                    reproduction=['press F2, Tab to the more menu button, press space, select '
                                  '%r with the arrow keys and press Return'
                                  % contract.MORE_MENU_ITEMS[0]],
                    fix='none when the menu item activates from the keyboard')

    def phase_collections_dialog():
        window = dialog_window(contract.COLLECTIONS_DIALOG, True)
        host.activate(window)
        dialog = wait_element(contract.COLLECTIONS_DIALOG)
        focused = focus_snapshot()
        node = focus_node()
        inside = (dialog is not None and node is not None
                  and (a11y.same(node, dialog) or a11y.is_ancestor(dialog, node)))
        audit.check('collections_dialog_identity',
                    dialog is not None and a11y.role(dialog) in contract.DIALOG_ROLES
                    and a11y.states(dialog).get('modal', False) and inside,
                    expected='the organizer is a modal dialog named %r with keyboard focus inside '
                             'it' % contract.COLLECTIONS_DIALOG,
                    actual={'role': a11y.role(dialog) if dialog is not None else None,
                            'states': a11y.states(dialog) if dialog is not None else None,
                            'focused': focused, 'focus_inside_dialog': inside},
                    element=snapshot(dialog)['path'],
                    reproduction=['open the organizer from the shelf more menu with the keyboard',
                                  'read the dialog element and the focused element'],
                    fix='GTK_DIALOG_MODAL is already requested, but GTK never moves focus into '
                        'the dialog: add gtk_widget_grab_focus(collections.types) (or '
                        'collections.groups) after gtk_widget_show_all in collections_open(), as '
                        'metadata_present() and accounts_open() already do')

        controls = {key: snapshot(wait_element(text, timeout=15))
                    for key, text in contract.COLLECTIONS_NAMES.items()}
        missing = [key for key, entry in controls.items() if not entry['path']]
        buttons = a11y.find_all(current_app(), roles=contract.BUTTON_ROLES)
        present = {a11y.name(node) for node in buttons}
        missing_buttons = [entry for entry in contract.COLLECTIONS_BUTTONS if entry not in present]
        audit.check('collections_dialog_controls_named', not missing and not missing_buttons,
                    expected='the organizer exposes %r and its %d buttons by accessible name'
                             % (sorted(contract.COLLECTIONS_NAMES.values()),
                                len(contract.COLLECTIONS_BUTTONS)),
                    actual={'missing_named_controls': missing, 'missing_buttons': missing_buttons,
                            'controls': controls,
                            'buttons_present': sorted(name for name in present if name)},
                    element=snapshot(dialog)['path'],
                    reproduction=['open the organizer and read every control name on the bus'],
                    fix='none: collections_access() already sets these names')
        dump_tree('03-collections')
        shot('03-collections', window)

        sequence = traverse(16)
        focused_steps_dialog = [entry for entry in sequence if entry['path']]
        type_element = a11y.find_one(current_app(), roles=('combo box',),
                                     text=contract.COLLECTIONS_NAMES['type'])
        in_cycle = any(entry['name'] == contract.COLLECTIONS_NAMES['type']
                       for entry in sequence)
        host.key('alt+t')
        time.sleep(0.4)
        mnemonic_focus = focus_snapshot()
        mnemonic_ok = (mnemonic_focus['name'] == contract.COLLECTIONS_NAMES['type']
                       or mnemonic_focus['role'] == 'combo box')
        if mnemonic_ok:
            host.key('Escape')  # close the popped list so the next Escape closes the dialog
            time.sleep(0.2)
        audit.check('collections_type_selector_reachable',
                    type_element is not None and (in_cycle or mnemonic_ok),
                    expected='the collection type selector can be reached from the keyboard, '
                             'either in the Tab cycle or through its mnemonic',
                    actual={'in_tab_cycle': in_cycle, 'reachable_by_mnemonic': mnemonic_ok,
                            'focusable_state': a11y.states(type_element).get('focusable')
                            if type_element is not None else None,
                            'focus_after_mnemonic': mnemonic_focus,
                            'tab_cycle': [entry['name'] for entry in sequence]},
                    element=snapshot(type_element)['path'] or snapshot(dialog)['path'],
                    severity='advisory',
                    evaluated=bool(focused_steps_dialog),
                    reproduction=['open the organizer',
                                  'Tab through one complete cycle, then press Alt+T',
                                  'read the focused element after each step'],
                    fix='the selector sits outside the Tab chain and is reachable only through '
                        'its _Type mnemonic; add gtk_widget_set_can_focus(collections.types, TRUE) '
                        'while keeping the mnemonic widget so both paths work')

        mark = recorder.mark()
        close_with_escape(contract.COLLECTIONS_DIALOG)
        events = recorder.since(mark)
        reactivated = [event for event in events
                       if event['type'].startswith('window:')
                       and contract.WINDOW_TITLE in event.get('source_name', '')]
        restored, after_node, main = focus_restored()
        audit.check('collections_dialog_escape_restores_focus', restored,
                    expected='Escape closes the organizer and returns focus to a control inside '
                             'the main window',
                    actual={'focused_after_escape': snapshot(after_node),
                            'window_activate_events_for_main': reactivated,
                            'tab_steps_inside_dialog': [entry['name'] for entry in sequence],
                            'focus_is_inside_main_window': restored},
                    element=snapshot(after_node)['path'] or snapshot(main)['path'],
                    reproduction=['open the organizer', 'press Escape',
                                  'read the focused element'],
                    fix='focused stays empty only when GTK could not restore the previous widget')
        audit.observations['collections_tab_order'] = [entry['name'] for entry in sequence]

    def phase_import_dialog():
        host.activate(host.window)
        idle()
        host.key('F1')
        window = dialog_window(contract.IMPORT_DIALOG, True)
        host.activate(window)
        dialog = wait_element(contract.IMPORT_DIALOG)
        # Focus may arrive asynchronously as the native chooser maps. Observe
        # one node per sample so the reported node is the one being checked.
        deadline = time.monotonic() + 6
        node = None
        inside = False
        while time.monotonic() < deadline:
            node = focus_node()
            inside = (dialog is not None and node is not None
                      and (a11y.same(node, dialog) or a11y.is_ancestor(dialog, node)))
            if inside:
                break
            time.sleep(.08)
        focused = snapshot(node)
        audit.check('import_dialog_identity_and_focus',
                    dialog is not None
                    and a11y.role(dialog) in contract.DIALOG_ROLES + ('file chooser',)
                    and inside,
                    expected='F1 opens a file chooser dialog named %r that takes keyboard focus '
                             'inside its own subtree' % contract.IMPORT_DIALOG,
                    actual={'role': a11y.role(dialog) if dialog is not None else None,
                            'focused': focused, 'focus_inside_dialog': inside, 'window': window},
                    element=snapshot(dialog)['path'],
                    reproduction=['press F1 on the main window',
                                  'read the dialog and the focused element'],
                    fix='none: GtkFileChooserDialog owns this dialog')
        dump_tree('04-import-dialog')
        shot('04-import-dialog', window)
        sequence = traverse(8)
        close_with_escape(contract.IMPORT_DIALOG)
        restored, after_node, main = focus_restored()
        audit.check('import_dialog_escape_restores_focus', restored,
                    expected='Escape closes the import dialog and focus returns to a control inside '
                             'the main window',
                    actual={'focused_after_escape': snapshot(after_node),
                            'tab_steps': [entry['name'] for entry in sequence],
                            'focus_is_inside_main_window': restored},
                    element=snapshot(after_node)['path'] or snapshot(main)['path'],
                    reproduction=['press F1', 'press Escape', 'read the focused element'],
                    fix='focused stays empty only when GTK could not restore the previous widget')

    def phase_import_books():
        for index, path in enumerate(books):
            import_file(path, index + 1)
        host.activate(host.window)
        host.key('F2')
        state = idle()
        listing = wait_element(contract.NAMES['shelf_list'])
        row_nodes = wait_rows(listing, len(books))
        row_text = [' '.join(a11y.name(node) for node in a11y.find_all(row, roles=('label',)))
                    for row in row_nodes]
        missing = [path.stem for path in books
                   if not any(path.stem in text for text in row_text)]
        audit.check('import_books_visible_on_shelf',
                    len(row_nodes) >= len(books) and not missing,
                    expected='each imported original appears as its own shelf row, so %r are all '
                             'listed' % ([path.stem for path in books],),
                    actual={'rows': len(row_nodes), 'row_text': row_text,
                            'missing_originals': missing,
                            'library_rows': state.get('books')},
                    element=snapshot(listing)['path'],
                    reproduction=['import three real UTF-8 text originals with F1',
                                  'show the shelf with F2 and read every row caption'],
                    fix='none when each original has its own row')
        dump_tree('05-shelf-imported')
        shot('05-shelf-imported')

    def phase_shelf_rows():
        host.activate(host.window)
        host.key('F2')
        idle()
        listing = wait_element(contract.NAMES['shelf_list'])
        rows = wait_rows(listing, max(1, host.host_state().get('books', 1)))
        detail = []
        for row in rows:
            detail.append({'role': a11y.role(row), 'name': a11y.name(row),
                           'path': a11y.path_of(row), 'states': a11y.states(row),
                           'text_children': [a11y.name(node)
                                             for node in a11y.find_all(row, roles=('label',))]})
        unnamed = [entry for entry in detail if not entry['name']]
        fallback = [entry for entry in unnamed if any(entry['text_children'])]
        audit.check('shelf_row_names', bool(detail) and not unnamed,
                    expected='every shelf row exposes a non-empty accessible name so list '
                             'navigation can announce the book',
                    actual={'rows': detail, 'unnamed_rows': len(unnamed),
                            'unnamed_with_text_child': len(fallback)},
                    element=detail[0]['path'] if detail else snapshot(listing)['path'],
                    reproduction=['import originals, show the shelf with F2',
                                  'read the Name property of each list row on the bus'],
                    fix='in reader.c shelf_present(), after building the caption: '
                        'atk_object_set_name(gtk_widget_get_accessible(row), caption) before the '
                        'row is inserted; one call per row and no layout change. The caption is '
                        'only reachable today as a child label, which a reader may fall back to '
                        'but which leaves the row Name empty for AT-SPI clients that use it')

        not_focusable = [entry['path'] for entry in detail if not entry['states'].get('focusable')]
        audit.check('shelf_rows_focusable', bool(detail) and not not_focusable,
                    expected='every shelf row is focusable so it can be reached and activated from '
                             'the keyboard',
                    actual={'rows': len(detail), 'not_focusable': not_focusable,
                            'insensitive': [entry['path'] for entry in detail
                                            if not entry['states'].get('enabled')]},
                    element=detail[0]['path'] if detail else snapshot(listing)['path'],
                    reproduction=['show the shelf with F2 and read the FOCUSABLE state of each row'],
                    fix='none when the rows report FOCUSABLE')

    def phase_reader():
        host.activate(host.window)
        host.key('F2')
        idle()
        host.key('Return')
        state = host.wait_state(lambda current: current.get('reader_visible') == 1
                                and current.get('book', 0) > 0, timeout=120)
        panels = {}
        for key in ('page_image', 'page_text', 'comment', 'notes_list'):
            panels[key] = snapshot(wait_element(contract.NAMES[key], timeout=25))
        missing = [key for key in panels if not panels[key]['path']]
        roles_ok = (panels['page_text']['role'] in contract.ENTRY_ROLES
                    and panels['comment']['role'] in contract.ENTRY_ROLES
                    and panels['notes_list']['role'] in contract.LIST_ROLES)
        audit.check('reader_panel_names', not missing and roles_ok,
                    expected='the reader exposes the page image, selectable text, comment entry and '
                             'saved-notes list by accessible name and usable role',
                    actual={'panels': panels, 'missing': missing, 'book': state.get('book')},
                    element=panels['page_text']['path'] or snapshot(frame())['path'],
                    reproduction=['open a book with F2 then Return',
                                  'read the reader panel elements on the bus'],
                    fix='none: all four names are set through atk_object_set_name in reader.c')
        dump_tree('06-reader')
        shot('06-reader')

        # Observe a complete focus cycle, not a fixed prefix that predates new controls.
        sequence, cycle_complete = [], False
        host.key('Tab')
        anchor = driver.wait_until(focus_node, 6, description='reader focus-cycle anchor')
        node = anchor
        main = frame()
        within_reader = True
        for _ in range(128):
            sequence.append(snapshot(node))
            within_reader &= bool(a11y.is_ancestor(main, node) and a11y.name(node))
            host.key('Tab')
            previous = node
            def next_focus():
                candidate = focus_node()
                return candidate if candidate is not None and candidate != previous else None
            node = driver.wait_until(next_focus, 6, description='next real reader focus stop')
            if node == anchor:
                cycle_complete = True
                break
        reached = [entry['name'] for entry in sequence
                   if entry['role'] in contract.ENTRY_ROLES]
        audit.check('reader_tab_order_reaches_panels',
                    cycle_complete and within_reader and contract.NAMES['page_text'] in reached
                    and contract.NAMES['comment'] in reached,
                    expected='Tab reaches the selectable page text and the comment entry',
                    actual={'sequence': sequence, 'cycle_complete': cycle_complete, 'all_stops_named_inside_reader': within_reader}, element='window/%s' % contract.WINDOW_TITLE,
                    severity='advisory',
                    reproduction=['open a book', 'press Tab through one complete cycle (128-step safety bound) and read role and focus'],
                    fix='none when the panels are reachable')

    def phase_annotations():
        host.activate(host.window)
        host.key('F7')
        host.key('ctrl+a')
        idle()
        host.key('F11')
        host.key('ctrl+a')
        host.type_text('Audit note for the GTK accessibility audit')
        host.key('F8')
        state = host.wait_state(lambda current: current.get('notes', 0) >= 1, timeout=90)
        listing = wait_element(contract.NAMES['notes_list'])
        rows = wait_rows(listing, max(1, state.get('notes', 1) or 1))
        detail = [{'role': a11y.role(row), 'name': a11y.name(row), 'path': a11y.path_of(row),
                   'text_children': [a11y.name(node)
                                     for node in a11y.find_all(row, roles=('label',))]}
                  for row in rows]
        unnamed = [entry for entry in detail if not entry['name']]
        audit.check('annotation_note_rows_named', bool(detail) and not unnamed,
                    expected='the saved-note list exposes each annotation with a non-empty '
                             'accessible name',
                    actual={'notes': state.get('notes'), 'rows': detail,
                            'unnamed_rows': len(unnamed)},
                    element=detail[0]['path'] if detail else snapshot(listing)['path'],
                    reproduction=['select page text with F7 then ctrl+a',
                                  'type a comment after F11', 'press F8 to add the note',
                                  'read the saved-note rows'],
                    fix='in reader.c notes_present(), after gtk_label_new(result->notes[i].text): '
                        'atk_object_set_name(gtk_widget_get_accessible(row), '
                        'result->notes[i].text) for the created row')
        dump_tree('07-annotations')
        shot('07-annotations')

    def phase_status_messages():
        host.activate(host.window)
        idle()
        before = status_node()
        before_text = a11y.name(before) if before is not None else ''
        mark = recorder.mark()
        with recorder.lock:
            source_mark = len(recorder.name_sources)
        failed_import(invalid)
        after = None
        after_text = before_text
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            candidate = status_node()
            text = a11y.name(candidate) if candidate is not None else ''
            if text and text != before_text:
                after, after_text = candidate, text
                break
            time.sleep(0.2)
        # Label updates and AT-SPI delivery are asynchronous; wait for the actual
        # matching source event without fabricating focus or changing the name.
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            with recorder.lock:
                sources = list(recorder.name_sources[source_mark:])
            if any(source == before and name == after_text for source, name in sources):
                break
            time.sleep(.08)
        events = recorder.since(mark)
        name_events = [event for event in events
                       if event['type'] == 'object:property-change:accessible-name'
                       and event.get('source_name') == after_text]
        with recorder.lock:
            sources = list(recorder.name_sources[source_mark:])
        source_matches = any(source == before and name == after_text
                             for source, name in sources)
        same_element = (before is not None and after is not None
                        and after == before)
        evaluated = before is not None and bool(recorder.items)
        if not evaluated:
            audit.gap('The status element or the accessibility event stream was unavailable, so '
                      'the status notification check could not be evaluated (events=%d, before=%r)'
                      % (len(recorder.items), before_text))
        audit.check('status_message_exposed_as_name_change',
                    before is not None and after is not None and same_element
                    and before_text != after_text and bool(name_events) and source_matches,
                    expected='a refused import changes the status element name in place and the '
                             'registry delivers an accessible-name property change for it',
                    actual={'before_text': before_text, 'after_text': after_text,
                            'same_element': same_element,
                            'property_change_events': name_events[:6], 'event_source_matches': source_matches,
                            'event_total': len(events),
                            'status_role': a11y.role(after) if after is not None else None,
                            'status_attributes': a11y.attributes(after)
                            if after is not None else {}},
                    element=snapshot(after)['path'] or snapshot(before)['path'],
                    reproduction=['read the status label name', 'import invalid.epub with F1',
                                  'read the label again and the delivered accessibility events'],
                    evaluated=evaluated,
                    fix='the message is a plain label: use a GtkStatusbar (ATK_ROLE_STATUSBAR '
                        'plus Statusbar::text-pushed) so assistive clients that announce status '
                        'bars receive the change; GTK3 has no per-widget live region')
        audit.observations['status_messages'] = {'before': before_text, 'after': after_text,
                                                 'events': len(events),
                                                 'name_events': len(name_events)}
        dump_tree('08-status')
        shot('08-status')

    def phase_metadata_dialog():
        host.activate(host.window)
        host.key('F2')
        idle()
        host.key('ctrl+e')
        window = dialog_window(contract.METADATA_DIALOG, True)
        host.activate(window)
        dialog = wait_element(contract.METADATA_DIALOG)
        focused = focus_snapshot()
        title = wait_element(contract.METADATA_NAMES['title'])
        audit.check('metadata_dialog_identity_and_focus',
                    dialog is not None and title is not None
                    and a11y.states(dialog).get('modal', False)
                    and focused['name'] == contract.METADATA_NAMES['title'],
                    expected='Ctrl+E opens the modal %r dialog with focus on the %r entry'
                             % (contract.METADATA_DIALOG, contract.METADATA_NAMES['title']),
                    actual={'role': a11y.role(dialog) if dialog is not None else None,
                            'states': a11y.states(dialog) if dialog is not None else None,
                            'focused': focused, 'title_entry': snapshot(title)},
                    element=snapshot(dialog)['path'],
                    reproduction=['show the shelf with F2', 'press Ctrl+E',
                                  'read the dialog and the focused element'],
                    fix='none: metadata_present() already focuses the title entry')
        named = {key: snapshot(wait_element(text, timeout=15))
                 for key, text in contract.METADATA_NAMES.items()}
        missing = [key for key, entry in named.items() if not entry['path']]
        texts = {key: a11y.accessible_text(wait_element(text, timeout=5))
                 for key, text in (('title', contract.METADATA_NAMES['title']),
                                   ('author', contract.METADATA_NAMES['author']))}
        audit.check('metadata_dialog_controls_named', not missing,
                    expected='the details dialog exposes %r, %r and %r'
                             % (contract.METADATA_NAMES['title'],
                                contract.METADATA_NAMES['author'],
                                contract.METADATA_NAMES['favorite']),
                    actual={'controls': named, 'missing': missing, 'texts': texts},
                    element=named['title']['path'],
                    reproduction=['open the details dialog with Ctrl+E',
                                  'read the entry and check-box names'],
                    fix='none: metadata_ui.inc already sets all three names')
        dump_tree('09-metadata')
        shot('09-metadata', window)
        traverse(6)
        close_with_escape(contract.METADATA_DIALOG)
        restored, after_node, main = focus_restored()
        audit.check('metadata_dialog_escape_restores_focus', restored,
                    expected='Escape closes the details dialog and focus returns to a control '
                             'inside the main window',
                    actual={'focused_after_escape': snapshot(after_node),
                            'focus_is_inside_main_window': restored},
                    element=snapshot(after_node)['path'] or snapshot(main)['path'],
                    reproduction=['open the details dialog', 'press Escape',
                                  'read the focused element'],
                    fix='focused stays empty only when GTK could not restore the previous widget')

    def phase_account_dialog():
        host.activate(host.window)
        host.key('ctrl+shift+a')
        window = dialog_window(contract.ACCOUNT_DIALOG, True, timeout=40)
        host.activate(window)
        dialog = wait_element(contract.ACCOUNT_DIALOG)
        focused = focus_snapshot()
        root = wait_element(contract.ACCOUNT_ENTRIES['root'])
        audit.check('account_dialog_identity_and_focus',
                    dialog is not None and root is not None
                    and focused['name'] == contract.ACCOUNT_ENTRIES['root'],
                    expected='Ctrl+Shift+A opens the %r dialog with focus on the %r entry'
                             % (contract.ACCOUNT_DIALOG, contract.ACCOUNT_ENTRIES['root']),
                    actual={'role': a11y.role(dialog) if dialog is not None else None,
                            'states': a11y.states(dialog) if dialog is not None else None,
                            'focused': focused, 'root_entry': snapshot(root)},
                    element=snapshot(dialog)['path'],
                    reproduction=['press Ctrl+Shift+A',
                                  'read the dialog and the focused element'],
                    fix='none for the name: accounts_open() already focuses the root entry')

        audit.check('account_dialog_declares_modality',
                    a11y.states(dialog).get('modal', False),
                    expected='the account dialog declares the MODAL state, as the organizer and '
                             'details dialogs do, so assistive clients can announce that the '
                             'library is unavailable while it is open',
                    actual={'states': a11y.states(dialog) if dialog is not None else None,
                            'role': a11y.role(dialog) if dialog is not None else None,
                            'main_window_sensitive_note': 'accounts_open() sets the main content '
                            'insensitive instead of asking GTK for a modal dialog'},
                    element=snapshot(dialog)['path'],
                    severity='advisory',
                    reproduction=['press Ctrl+Shift+A',
                                  'read the dialog state set on the accessibility bus'],
                    fix='pass GTK_DIALOG_MODAL to gtk_dialog_new_with_buttons in accounts_open() '
                        '(accounts_ui.inc); the insensitive main content can then stay or go')

        entries = {key: snapshot(wait_element(text, timeout=10))
                   for key, text in contract.ACCOUNT_ENTRIES.items()}
        radios = {text: snapshot(wait_element(text, timeout=10))
                  for text in contract.ACCOUNT_RADIOS}
        present = {a11y.name(node) for node in
                   a11y.find_all(current_app(), roles=contract.BUTTON_ROLES)}
        missing = ([key for key, entry in entries.items() if not entry['path']]
                   + [text for text, entry in radios.items() if not entry['path']]
                   + [entry for entry in contract.ACCOUNT_BUTTONS if entry not in present])
        audit.check('account_entries_and_buttons_named', not missing,
                    expected='the account surface exposes three named entries, both storage '
                             'choices and every current named operation button',
                    actual={'entries': entries, 'radios': radios, 'missing': missing,
                            'buttons_present': sorted(name for name in present if name)},
                    element=snapshot(dialog)['path'],
                    reproduction=['open Account and Sync',
                                  'read every entry, radio button and button'],
                    fix='none: accounts_entry() and gtk_button_new_with_mnemonic() already name '
                        'the controls')
        dump_tree('10-account')
        shot('10-account', window)

        reached = tab_to(contract.ACCOUNT_ENTRIES['password'], limit=14)
        host.type_text(secret)
        driver.wait_until(lambda: host.number('account', 'has_password') == 1, 30,
                          description='the password entry to hold the typed secret')
        password = wait_element(contract.ACCOUNT_ENTRIES['password'],
                                roles=contract.BUTTON_ROLES + contract.ENTRY_ROLES, timeout=6)
        exported = a11y.accessible_text(password) if password is not None else None
        attributes = a11y.attributes(password) if password is not None else {}
        leaked = bool(exported and secret in (exported.get('text') or ''))
        marked = (a11y.role(password) == 'password text'
                  or bool(attributes.get('text-input-type')) or bool(attributes.get('password')))
        audit.check('account_password_secret_not_reachable_through_atspi',
                    reached and password is not None and not leaked,
                    expected='the password entry takes keyboard focus and its AT-SPI text does '
                             'not contain the typed secret',
                    actual={'reached_by_tab': reached, 'entry': snapshot(password),
                            'exported_text_length': (exported or {}).get('length'),
                            'exported_text_is_secret': leaked,
                            'exported_text_sample': '<secret was exported>' if leaked
                            else ((exported or {}).get('text') or '')[:8],
                            'attributes': attributes, 'attributes_mark_secret': marked},
                    element=snapshot(password)['path'] or snapshot(dialog)['path'],
                    severity='blocking',
                    reproduction=['open Account and Sync', 'Tab to the password entry',
                                  'paste a known secret', 'read the AT-SPI text and attributes of '
                                  'that entry'],
                    fix='if the secret is exported: keep the value out of AtkText by returning the '
                        'invisible character while the entry is not visible; the entry name and '
                        'attributes stay unchanged')
        if not marked:
            audit.gap('The password entry exposes neither the password-text role nor a secret '
                      'attribute (GTK3 host with at-spi2-core %s), so an assistive client cannot '
                      'know the field is masked before it reads it' % a11y.atspi_version())
        audit.observations['account_password'] = {
            'attributes': attributes, 'exported_text_length': (exported or {}).get('length'),
            'secret_exported': leaked, 'reached_by_tab': reached,
            'attributes_mark_secret': marked}

        mark = recorder.mark()
        close_with_escape(contract.ACCOUNT_DIALOG, timeout=45)
        events = recorder.since(mark)
        reactivated = [event for event in events
                       if event['type'].startswith('window:')
                       and contract.WINDOW_TITLE in event.get('source_name', '')]
        restored, after_node, main = focus_restored()
        audit.check('account_dialog_escape_restores_focus', restored,
                    expected='Escape closes the account dialog and focus returns to a control '
                             'inside the main window',
                    actual={'focused_after_escape': snapshot(after_node),
                            'window_activate_events_for_main': reactivated,
                            'focus_is_inside_main_window': restored,
                            'main_content_insensitive_while_open': True},
                    element=snapshot(after_node)['path'] or snapshot(main)['path'],
                    reproduction=['open Account and Sync', 'press Escape',
                                  'read the focused element'],
                    fix='accounts_open() makes the whole main content insensitive, which drops the '
                        'main window focus widget, and accounts_destroyed() only re-enables it: '
                        'remember the focused widget before opening and grab it again in '
                        'accounts_destroyed(), or use GTK_DIALOG_MODAL instead of insensitivity')

    # -- run ---------------------------------------------------------------
    started = time.monotonic()
    failure = None
    ok, message = a11y.init()
    if not ok:
        raise RuntimeError('AT-SPI did not initialise: ' + message)
    registered = recorder.start()
    audit.observations['recorder'] = {'registered': recorder.registered,
                                      'rejected': recorder.rejected,
                                      'started': registered, 'error': recorder.error}
    if not registered:
        audit.gap('No accessibility events could be subscribed: '
                  + (recorder.error or repr(recorder.rejected)))

    def run_phase(name, function):
        started_phase = time.monotonic()
        try:
            function()
            audit.phases.append({'name': name, 'executed': True,
                                 'seconds': round(time.monotonic() - started_phase, 2)})
            print('PHASE %s ok' % name, flush=True)
        except Exception as exc:
            audit.phases.append({'name': name, 'executed': False, 'error': repr(exc),
                                 'traceback': traceback.format_exc()[-4000:],
                                 'seconds': round(time.monotonic() - started_phase, 2)})
            print('PHASE %s FAILED %r' % (name, exc), flush=True)
            try:  # leave menus and dialogs so the next phase starts from the main window
                host.key('Escape')
                host.key('Escape')
            except Exception:
                pass
            for capture in (lambda: dump_tree(name + '-failed'),
                            lambda: shot(name + '-failed')):
                try:
                    capture()
                except Exception as capture_error:
                    print('capture failed: %r' % (capture_error,), flush=True)

    try:
        host.launch()
        run_phase('bridge', phase_bridge)
        run_phase('shelf', phase_shelf)
        run_phase('shelf-tab-order', phase_shelf_tab_order)
        run_phase('menu', phase_menu)
        run_phase('collections-dialog', phase_collections_dialog)
        run_phase('import-dialog', phase_import_dialog)
        run_phase('import-books', phase_import_books)
        run_phase('shelf-rows', phase_shelf_rows)
        run_phase('reader', phase_reader)
        run_phase('annotations', phase_annotations)
        run_phase('status-messages', phase_status_messages)
        run_phase('metadata-dialog', phase_metadata_dialog)
        run_phase('account-dialog', phase_account_dialog)
        dump_tree('99-final')
        shot('99-final')
    except BaseException as exc:  # keep the evidence even when the host dies
        failure = exc
        audit.observations['fatal'] = repr(exc)
        audit.observations['fatal_traceback'] = traceback.format_exc()[-4000:]
        print('AUDIT FATAL %r' % (exc,), flush=True)
    finally:
        host.focus_hook = None
        try:
            host.window_tree(folder / 'logs' / 'window-tree.txt')
        except Exception as exc:
            print('window tree capture failed: %r' % (exc,), flush=True)
        try:
            recorder.stop()
        finally:
            a11y.exit_bus()
        if host.process is not None and host.process.poll() is None:
            try:
                host.close()
            except Exception as exc:
                print('close failed: %r' % (exc,), flush=True)
                host.process.kill()

        audit.fill_missing()
        executed = {phase['name'] for phase in audit.phases if phase['executed']}
        missing_phases = [name for name in contract.PHASES if name not in executed]
        audit.observations['phases_executed'] = sorted(executed)
        audit.observations['phases_missing'] = missing_phases
        audit_completed = not missing_phases and failure is None
        blocking = [entry for entry in audit.checks
                    if not entry['pass'] and entry['severity'] == 'blocking']
        accepted = audit_completed and not blocking
        findings = audit.findings()
        leaks = 0
        leak_files = []
        for path in sorted(folder.rglob('*')):
            if path.is_file() and path.name != 'result.json':
                try:
                    if secret.encode() in path.read_bytes():
                        leaks += 1
                        leak_files.append(str(path.relative_to(folder)))
                except OSError:
                    pass
        report = {
            'schema': 1,
            'kind': 'gtk-atspi-keyboard-audit',
            'source_sha': meta['source_sha'], 'run_id': meta['run_id'],
            'attempt': meta['attempt'], 'start_sha': meta['start_sha'], 'sdk': meta['sdk'],
            'program_sha256': meta['program_sha256'], 'font_sha256': meta['font_sha256'],
            'environment': {'display': meta['display'], 'window_manager': 'openbox',
                            'payload': meta['payload'],
                            'atspi_version': a11y.atspi_version(),
                            'recorder': audit.observations.get('recorder')},
            'scope': 'GTK product host: shelf, import, organize, reading, annotation and account '
                     'surfaces observed through AT-SPI with real X11 keystrokes',
            'audit_completed': audit_completed,
            'accessibility_accepted': accepted,
            'orca_screen_reader_accepted': False,
            'human_reader_review_accepted': False,
            'complete_product': False,
            'seconds': round(time.monotonic() - started, 1),
            'phases': audit.phases,
            'checks': audit.checks,
            'counts': {'checks': len(audit.checks),
                       'passed': sum(1 for entry in audit.checks if entry['pass']),
                       'failed_blocking': len(blocking),
                       'failed_advisory': sum(1 for entry in audit.checks
                                              if not entry['pass']
                                              and entry['severity'] != 'blocking'),
                       'phases': len(audit.phases)},
            'findings': findings,
            'gaps': list(contract.GAPS) + audit.dynamic_gaps,
            'observations': audit.observations,
            'secret_typed_into_password_field': True,
            'secret_leak_hits': leaks,
            'secret_leak_files': leak_files,
            'evidence': {},
        }
        for path in sorted(folder.rglob('*')):
            if path.is_file() and path.name != 'result.json':
                report['evidence'][str(path.relative_to(folder))] = {
                    'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        (folder / 'result.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps({'audit_completed': audit_completed, 'accessibility_accepted': accepted,
                          'counts': report['counts'], 'findings': len(findings),
                          'source_sha': meta['source_sha'], 'run_id': meta['run_id'],
                          'attempt': meta['attempt']}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise
