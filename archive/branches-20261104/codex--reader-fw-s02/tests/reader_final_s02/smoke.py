#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Runtime verification of the relocated GTK compact candidate.

Three launches of the same relocated program, all with a fresh HOME, fresh XDG
directories, an empty working directory and no LD_LIBRARY_PATH:

1. the default no-argument launch (package-relative Reader.otf, XDG user data),
   traced so the opened font path is evidence rather than an assumption;
2. the same program started through the candidate desktop entry with gtk-launch;
3. an explicit-font launch that imports a CI-generated original book through the
   real GTK/AT-SPI file chooser and reads the rendered page back.

Every phase runs even when an earlier one fails: a failure is recorded against
that phase and the remaining evidence is still produced.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

import common

WINDOW_NAME = 'EXReader Linux'
APPLICATION = 'exreader-linux'


def xdotool(*arguments):
    return subprocess.run(['xdotool', *[str(item) for item in arguments]], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)


def search_windows(pattern):
    result = xdotool('search', '--onlyvisible', '--name', pattern)
    return [item for item in result.stdout.split() if item.strip()]


def window_name(identifier):
    return xdotool('getwindowname', identifier).stdout.strip()


def window_geometry(identifier):
    values = {}
    for line in xdotool('getwindowgeometry', '--shell', identifier).stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            if key in ('WIDTH', 'HEIGHT'):
                values[key] = int(value)
    return values


def pids_for(binary):
    target = os.path.realpath(str(binary))
    found = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            executable = os.readlink('/proc/%s/exe' % entry)
        except OSError:
            continue
        if executable in (target, target + ' (deleted)'):
            found.append(int(entry))
    return sorted(found)


def wait_pids_gone(binary, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pids_for(binary):
            return True
        time.sleep(0.2)
    return False


def trace_opens(text, needle):
    rows = []
    for line in text.splitlines():
        if needle not in line:
            continue
        match = re.search(r'open(?:at)?\([^"]*"([^"]+)"', line)
        if not match:
            continue
        result = line.rsplit('=', 1)[-1].strip()
        rows.append({'path': match.group(1), 'ok': not result.startswith('-1'),
                     'line': line.strip()[:400]})
    return rows


def read_observation(path):
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    return common.parse_observation(candidate.read_text(encoding='utf-8', errors='replace'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relocated', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--atspi-dir', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--xdg-data', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True,
                        help='XDG_CONFIG_HOME shared with the accessibility settings')
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = args.runtime.resolve()
    relocated = args.relocated.resolve(strict=True)
    program = relocated / 'bin/exreader-linux'
    workspace = os.path.realpath(str(args.workspace.resolve()))
    producer = common.read_json(args.producer)
    manifest = common.read_json(args.fixtures / 'manifest.json')
    fixture = args.fixtures / manifest['path']
    checks = common.Checks()
    evidence = {'launches': {}, 'screenshots': {}, 'atspi': {}}
    active = {'window': None}

    sys.path.insert(0, str(args.atspi_dir.resolve()))
    import atspi_client as bus  # noqa: E402  (the pinned audited AT-SPI client)

    initialised, diagnostic = bus.init()
    checks.add('atspi_available', initialised,
               'accessibility bus initialised' if initialised
               else 'AT-SPI is unavailable: %s' % diagnostic)

    def node(app, name, roles=None):
        for candidate in bus.walk(app):
            if bus.name(candidate) != name:
                continue
            if roles is not None and bus.role(candidate) not in roles:
                continue
            if not bus.states(candidate).get('showing'):
                continue
            return candidate
        return None

    def wait_node(app, name, roles=None, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = node(app, name, roles)
            if found is not None:
                return found
            time.sleep(0.1)
        raise common.S02Error('missing native element %r roles %s' % (name, roles))

    def activate(identifier=None):
        target = identifier or active['window']
        if target:
            xdotool('windowactivate', '--sync', target)
            time.sleep(0.1)

    def click_node(target):
        box = bus.extents(target)
        common.need(box and box['width'] > 0 and box['height'] > 0,
                    'element has no accessible extents')
        activate()
        xdotool('mousemove', '--sync', box['x'] + box['width'] // 2,
                box['y'] + box['height'] // 2)
        xdotool('click', '1')
        time.sleep(0.25)

    def click(app, name, roles=None, timeout=40):
        return click_node(wait_node(app, name, roles, timeout))

    def key(*keys):
        for value in keys:
            xdotool('key', '--clearmodifiers', value)
            time.sleep(0.15)

    def paste(text):
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'),
                       check=True, timeout=60)
        key('ctrl+v')

    def screenshot(identifier, path):
        activate(identifier)
        subprocess.run(['import', '-window', str(identifier), str(path)],
                       check=True, timeout=120)
        size = subprocess.run(['identify', '-format', '%w %h', str(path)], text=True,
                              stdout=subprocess.PIPE, timeout=60).stdout.split()
        return {'path': Path(path).name, 'sha256': common.sha256_file(path),
                'width': int(size[0]), 'height': int(size[1])}

    def wait_window(binary, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for pid in pids_for(binary):
                for identifier in xdotool('search', '--onlyvisible', '--pid', pid).stdout.split():
                    if window_name(identifier) == WINDOW_NAME:
                        return identifier
            time.sleep(0.1)
        raise common.S02Error('no %r window for %s' % (WINDOW_NAME, binary))

    def wait_no_application(timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = [item for item in bus.applications() if bus.name(item) == APPLICATION]
            if not found:
                return True
            time.sleep(0.2)
        return False

    def close_window(identifier, proc=None, timeout=120):
        activate(identifier)
        key('alt+F4')
        if proc is not None:
            return proc.wait(timeout=timeout)
        return 0 if wait_pids_gone(program, timeout) else 1

    config = args.config.resolve()
    config.mkdir(parents=True, exist_ok=True)

    def prepare(name):
        root = runtime / name
        paths = {key: root / key for key in ('home', 'data', 'cache', 'cwd', 'profile')}
        for value in paths.values():
            value.mkdir(parents=True, exist_ok=True)
        return root, paths

    def application_env(paths, extra=None):
        overrides = {'HOME': paths['home'], 'XDG_DATA_HOME': paths['data'],
                     'XDG_CONFIG_HOME': config, 'XDG_CACHE_HOME': paths['cache']}
        if extra:
            overrides.update(extra)
        env = common.minimal_env(overrides)
        for schema, entry in (('org.gnome.desktop.interface', 'toolkit-accessibility'),
                              ('org.gnome.desktop.a11y.applications', 'screen-reader-enabled')):
            subprocess.run(['gsettings', 'set', schema, entry, 'true'], env=env,
                           timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return env

    def import_book(app, path):
        click(app, 'Import book')
        deadline = time.monotonic() + 60
        dialog = None
        while time.monotonic() < deadline and dialog is None:
            found = search_windows('^Import book$')
            dialog = found[-1] if found else None
            if dialog is None:
                time.sleep(0.1)
        common.need(dialog is not None, 'the native import chooser never mapped')
        xdotool('windowactivate', '--sync', dialog)
        key('ctrl+l')
        chooser = wait_node(app, 'Import book', {'file chooser'}, 30)
        entry = None
        for candidate in bus.walk(chooser):
            if (bus.role(candidate) == 'text' and bus.states(candidate).get('showing')
                    and bus.states(candidate).get('sensitive')):
                entry = candidate
                break
        common.need(entry is not None, 'the chooser has no editable location entry')
        click_node(entry)
        key('ctrl+a')
        paste(str(path.resolve()))
        for _ in range(4):
            xdotool('windowactivate', '--sync', dialog)
            key('Return')
            time.sleep(0.8)
            if not search_windows('^Import book$'):
                break
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and search_windows('^Import book$'):
            time.sleep(0.2)
        if search_windows('^Import book$'):
            raise common.S02Error('the native import chooser did not accept %s' % path)
        return True

    def cleanup():
        """Kill any application left behind by an earlier phase."""
        for pid in pids_for(program):
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        if pids_for(program):
            wait_pids_gone(program, 20)

    def phase_default():
        cleanup()
        root, paths = prepare('default')
        trace = root / 'strace-open.log'
        log = open(str(root / 'application.log'), 'wb')
        proc = subprocess.Popen(['strace', '-f', '-o', str(trace), '-e', 'trace=openat,open',
                                 '--', str(program)], cwd=str(paths['cwd']),
                                env=application_env(paths), stdout=log,
                                stderr=subprocess.STDOUT)
        try:
            app = bus.wait_application(APPLICATION, timeout=150)
            identifier = wait_window(program, 150)
            active['window'] = identifier
            evidence['launches']['default'] = {'pid': proc.pid, 'window': identifier,
                                               'pids': pids_for(program),
                                               'geometry': window_geometry(identifier)}
            geometry = window_geometry(identifier)
            checks.add('default_launch_window',
                       window_name(identifier) == WINDOW_NAME
                       and geometry.get('WIDTH', 0) >= 1000 and geometry.get('HEIGHT', 0) >= 760,
                       'title %r geometry %s' % (window_name(identifier), geometry))
            evidence['atspi']['default'] = bus.dump(app)
            controls = {}
            for name in ('Import book', 'Continue reading', 'More reader actions'):
                controls[name] = bus.states(wait_node(app, name, timeout=45))
            checks.add('default_launch_controls',
                       all(controls[name].get('showing') for name in controls)
                       and not controls['Continue reading'].get('sensitive'),
                       json.dumps({name: sorted(controls[name]) for name in controls}))
            library = paths['data'] / 'exreader' / 'library.sqlite'
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not library.is_file():
                time.sleep(0.1)
            checks.add('xdg_data_home_used', library.is_file(),
                       'library created under XDG_DATA_HOME: %s' % library)
            evidence['screenshots']['default'] = screenshot(identifier, output / 'default-window.png')
            code = close_window(identifier, proc)
            checks.add('default_launch_close', code == 0, 'host exit code %d' % code)
            settings = paths['data'] / 'exreader' / 'reader.ini'
            checks.add('xdg_settings_written',
                       settings.is_file() and '[reader]' in settings.read_text(encoding='utf-8'),
                       'reader.ini under XDG_DATA_HOME: %s' % settings.is_file())
            checks.add('no_default_home_library',
                       not (paths['home'] / '.local' / 'share' / 'exreader').exists(),
                       'HOME/.local/share/exreader must not exist')
            checks.add('working_directory_untouched',
                       not any(paths['cwd'].iterdir()),
                       'the empty working directory stayed empty')
            trace_text = trace.read_text(encoding='utf-8', errors='replace')
            opens = trace_opens(trace_text, 'Reader.otf')
            evidence['launches']['default']['font_opens'] = opens[:8]
            expected_font = str(relocated / 'Reader.otf')
            checks.add('package_relative_font',
                       any(row['ok'] and row['path'] == expected_font for row in opens)
                       and not any(row['path'].startswith(str(paths['home'])) for row in opens),
                       'opened %s' % [row['path'] for row in opens if row['ok']][:4])
            attempts = [line for line in trace_text.splitlines() if workspace + '/' in line]
            successful = [line for line in attempts
                          if not line.rsplit('=', 1)[-1].strip().startswith('-1')]
            evidence['launches']['default']['workspace_open_attempts'] = len(attempts)
            checks.add('no_workspace_access', not successful,
                       '%d build-tree open attempts, %d succeeded' % (
                           len(attempts), len(successful)))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            log.close()
            wait_pids_gone(program, 30)
            wait_no_application(15)

    def phase_desktop():
        cleanup()
        wait_no_application(30)
        root, paths = prepare('desktop')
        env = application_env(paths, {'XDG_DATA_HOME': args.xdg_data.resolve()})
        launch_log = open(str(root / 'gtk-launch.log'), 'wb')
        try:
            # gtk-launch hands its stdio to the launched application: capturing it
            # through a pipe would block until the application itself exits.
            launch = subprocess.run(['gtk-launch', 'exreader'], cwd=str(paths['cwd']), env=env,
                                    stdout=launch_log, stderr=subprocess.STDOUT, timeout=90)
            launch_log.flush()
            launch_text = (root / 'gtk-launch.log').read_text(encoding='utf-8',
                                                             errors='replace').strip()
            checks.add('desktop_entry_launch', launch.returncode == 0,
                       'gtk-launch exit %d output %r' % (launch.returncode,
                                                         launch_text[:300]))
            bus.wait_application(APPLICATION, timeout=150)
            identifier = wait_window(program, 150)
            active['window'] = identifier
            desktop_pids = pids_for(program)
            evidence['launches']['desktop'] = {'window': identifier, 'pids': desktop_pids,
                                               'geometry': window_geometry(identifier)}
            checks.add('desktop_launch_window',
                       window_name(identifier) == WINDOW_NAME and bool(desktop_pids)
                       and all(os.readlink('/proc/%d/exe' % pid) == str(program)
                               for pid in desktop_pids),
                       'window %r pids %s' % (window_name(identifier), desktop_pids))
            library = args.xdg_data.resolve() / 'exreader' / 'library.sqlite'
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline and not library.is_file():
                time.sleep(0.1)
            checks.add('desktop_xdg_data_home', library.is_file(),
                       'desktop-launched host used XDG_DATA_HOME: %s' % library)
            evidence['screenshots']['desktop'] = screenshot(identifier, output / 'desktop-window.png')
            code = close_window(identifier)
            checks.add('desktop_launch_close', code == 0, 'desktop-launched host exited')
        finally:
            launch_log.close()
            cleanup()
            wait_no_application(15)

    def phase_readback():
        cleanup()
        wait_no_application(30)
        root, paths = prepare('readback')
        observation_path = root / 'observation.ini'
        log = open(str(root / 'application.log'), 'wb')
        proc = subprocess.Popen([str(program), str(relocated / 'Reader.otf'),
                                 str(paths['profile']), str(observation_path)],
                                cwd=str(paths['cwd']),
                                env=application_env(paths, {'LD_DEBUG': 'libs'}),
                                stdout=log, stderr=subprocess.STDOUT)
        try:
            app = bus.wait_application(APPLICATION, timeout=150)
            identifier = wait_window(program, 150)
            active['window'] = identifier
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                state = read_observation(observation_path)
                if common.observation_int(state, 'visible', 0) == 1:
                    break
                time.sleep(0.1)
            before = read_observation(observation_path)
            generation = common.observation_int(before, 'generation', 0)
            source_digest = common.sha256_file(fixture)
            import_book(app, fixture)
            deadline = time.monotonic() + 150
            state = {}
            while time.monotonic() < deadline:
                state = read_observation(observation_path)
                if (common.observation_int(state, 'book', 0) > 0
                        and common.observation_int(state, 'error', 1) == 0
                        and common.observation_int(state, 'generation', 0) > generation
                        and common.observation_int(state, 'saving', 0) == 0
                        and common.observation_int(state, 'busy', 0) == 0):
                    break
                time.sleep(0.2)
            evidence['launches']['readback'] = {'window': identifier, 'state': state,
                                                'before': before, 'pids': pids_for(program)}
            checks.add('readback_import',
                       common.observation_int(state, 'book', 0) > 0
                       and common.observation_int(state, 'books', 1) >= 1
                       and common.observation_int(state, 'error', 1) == 0,
                       json.dumps({key: state.get(key) for key in
                                   ('book', 'books', 'error', 'page', 'start', 'end', 'font')}))
            checks.add('readback_page_text',
                       common.observation_int(state, 'end', 0)
                       > common.observation_int(state, 'start', -1) >= 0,
                       'page %s offsets %s..%s' % (state.get('page'), state.get('start'),
                                                   state.get('end')))
            marker = manifest['marker']
            text_seen = ''
            text_nodes = 0
            try:
                click(app, 'More reader actions')
                time.sleep(0.5)
                click(app, 'Text and notes', {'menu'}, 25)
                key('Right')
                click(app, 'Show or hide text and notes', {'menu item'}, 25)
                wait_node(app, 'Selectable page text', timeout=40)
            except Exception as error:  # recorded, then judged by the tree scan below
                evidence['atspi']['text_pane_error'] = type(error).__name__ + ': ' + str(error)
            for candidate in bus.walk(app):
                extracted = bus.accessible_text(candidate)
                if not extracted:
                    continue
                text_nodes += 1
                value = extracted.get('text') or ''
                if marker and marker in value:
                    text_seen = value
                    break
            evidence['atspi']['readback_text'] = text_seen[:2000]
            evidence['atspi']['readback_text_nodes'] = text_nodes
            checks.add('readback_marker',
                       bool(marker) and marker in text_seen,
                       'AT-SPI text carries the fixture marker %r (%d text nodes, %d chars)' % (
                           marker, text_nodes, len(text_seen)))
            identifier = wait_window(program, 45)
            active['window'] = identifier
            evidence['screenshots']['readback'] = screenshot(identifier,
                                                             output / 'readback-window.png')
            evidence['atspi']['readback'] = bus.dump(app)
            code = close_window(identifier, proc)
            checks.add('readback_launch_close', code == 0, 'readback host exit code %d' % code)
            checks.add('readback_original_unchanged',
                       common.sha256_file(fixture) == source_digest,
                       'sha256 of the CI-generated original book is unchanged')
            log.close()
            log_text = (root / 'application.log').read_text(encoding='utf-8', errors='replace')
            loads = common.library_loads(log_text)
            prefixes = {'home': str(paths['home'].resolve()), 'payload': str(relocated),
                        'workspace': str(workspace)}
            outside = [item for item in loads
                       if common.classify_path(item, prefixes) not in ('system',)]
            evidence['launches']['readback']['library_loads'] = len(loads)
            checks.add('no_home_or_payload_libraries',
                       bool(loads) and not outside,
                       '%d loader inits, outside system: %s' % (len(loads), outside[:6]))
            checks.add('no_workspace_library', str(workspace) + '/' not in log_text,
                       'no loader path under the verifier workspace')
            remaining = common.tree_problems(relocated, producer['payload']['files'])
            checks.add('payload_not_mutated', not remaining,
                       'the relocated package is byte-identical after every launch'
                       if not remaining else '; '.join(remaining[:6]))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            log.close()
            wait_pids_gone(program, 30)
            wait_no_application(15)

    try:
        phases = (('default', phase_default), ('desktop', phase_desktop),
                  ('readback', phase_readback)) if initialised else ()
        for name, function in phases:
            try:
                function()
            except Exception as error:
                traceback.print_exc()
                checks.add('phase_%s_complete' % name, False,
                           type(error).__name__ + ': ' + str(error))
                evidence['launches'].setdefault(name, {})['error'] = (
                    type(error).__name__ + ': ' + str(error))
            else:
                checks.add('phase_%s_complete' % name, True, 'phase executed')
    finally:
        document = {
            'schema': 1, 'kind': 's02-runtime-smoke',
            'verifier_source': os.environ.get('GITHUB_SHA', ''),
            'relocated': str(relocated), 'program_sha256': common.sha256_file(program),
            'fixture': manifest, 'evidence': evidence,
            'checks': checks.items, 'problems': checks.failed(), 'ok': checks.accepted(),
        }
        common.write_json(output / 'smoke.json', document)
        print(json.dumps({'ok': checks.accepted(), 'failed': checks.failed(),
                          'checks': len(checks.items)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
