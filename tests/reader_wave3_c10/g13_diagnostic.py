# SPDX-License-Identifier: MIT
"""Run the unchanged G13 checker and retain independent empty-name diagnostics.

The original name result is always returned to G13. Diagnostic reads never
replace it, clear an AT-SPI cache, retry an assertion, or change a passing rule.
"""
import json
import os
from pathlib import Path
import runpy
import sys

import atspi_client as bus
from gi.repository import Gio, GLib


def raw_focused():
    """Read focused controls directly over D-Bus, outside libatspi's cache."""
    session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    address = session.call_sync('org.a11y.Bus', '/org/a11y/bus', 'org.a11y.Bus',
                                'GetAddress', None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
    connection = Gio.DBusConnection.new_for_address_sync(
        address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)

    def call(owner, path, interface, method, parameters=None):
        return connection.call_sync(owner, path, interface, method, parameters,
                                    None, Gio.DBusCallFlags.NONE, 1500, None).unpack()

    def name(owner, path):
        value = call(owner, path, 'org.freedesktop.DBus.Properties', 'Get',
                     GLib.Variant('(ss)', ('org.a11y.atspi.Accessible', 'Name')))[0]
        return value.unpack() if isinstance(value, GLib.Variant) else value

    roots = call('org.a11y.atspi.Registry', '/org/a11y/atspi/accessible/root',
                 'org.a11y.atspi.Accessible', 'GetChildren')[0]
    todo = [(owner, path) for owner, path in roots if name(owner, path) == 'exreader-linux']
    seen = set()
    focused = []
    while todo and len(seen) < 600:
        owner, path = todo.pop()
        if (owner, path) in seen:
            continue
        seen.add((owner, path))
        states = call(owner, path, 'org.a11y.atspi.Accessible', 'GetState')[0]
        bit = int(bus.Atspi.StateType.FOCUSED)
        if states[bit // 32] & (1 << (bit % 32)):
            focused.append({'bus': owner, 'path': path, 'name': name(owner, path),
                            'role': call(owner, path, 'org.a11y.atspi.Accessible', 'GetRoleName')[0]})
        todo.extend(call(owner, path, 'org.a11y.atspi.Accessible', 'GetChildren')[0])
    return {'focused': focused, 'visited': len(seen), 'bounded': bool(todo)}


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    output = Path(sys.argv[sys.argv.index('--output') + 1])
    original = bus.name
    diagnostics = []

    def observed_name(acc):
        original_error = None
        try:
            value = str(acc.get_name() or '') if acc is not None else ''
        except Exception as error:
            original_error = repr(error)
            value = ''
        if acc is not None and not value and len(diagnostics) < 4:
            if bus.role(acc) == 'toggle button' and bus.states(acc).get('focused'):
                row = {'original_name': value, 'proxy': str(acc), 'states': bus.states(acc)}
                if original_error is not None:
                    row['direct_exception'] = original_error
                else:
                    row['direct_name'] = value
                try:
                    row['raw_dbus'] = raw_focused()
                except Exception as error:
                    row['raw_dbus_exception'] = repr(error)
                diagnostics.append(row)
                print('G13_EMPTY_NAME_DIAGNOSTIC=' + json.dumps(row), flush=True)
        return value

    bus.name = observed_name
    try:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'reader_gtk_receive' / 'check_atspi_fixes.py'),
                       run_name='__main__')
    finally:
        bus.name = original
        if output.exists():
            (output / 'empty-name-diagnostics.json').write_text(json.dumps(diagnostics, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
