"""Explicit new GTK owner source; preserve D09's original business observations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from reuse import D09, ROOT, source


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def prepare():
    folder = ROOT / 'build/native-owner-reuse/d09'
    folder.mkdir(parents=True, exist_ok=False)
    original = source(D09, 'tests/reader_dot_wave2/d09/audit.py').decode()
    before = "TARGET='803098e9df1a365a9b8e206805c2d179aca8501f'"
    after = "TARGET=os.environ['GITHUB_SHA']"
    assert original.count(before) == 1
    adapted = original.replace(before, after)
    assert adapted.replace(after, before) == original
    (folder / 'audit.py').write_text(adapted, encoding='utf-8')
    for name in ('contract.py', 'x11.py'):
        (folder / name).write_bytes(source(D09, 'tests/reader_dot_wave2/d09/' + name))
    save(folder / 'projection.json', dict(source_sha=os.environ['GITHUB_SHA'], historical_source=D09,
         historical_sha256=hashlib.sha256(original.encode()).hexdigest(),
         adapted_sha256=digest(folder / 'audit.py'), only_substitution=dict(before=before, after=after),
         reverse_projection_exact=True, historical_acceptance_reused=False))
    # Real legacy/OFF selector host from the complete unchanged owner builder.
    subprocess.run([sys.executable, ROOT / 'tools/build_linux_host.py', '--sdk',
        ROOT / 'build/reading-library/stage', '--sdk-version', '3.41.0', '--binary',
        ROOT / 'build/gtk-raw3/legacy-owner/actual-owner/gtk-host/exreader-linux',
        '--output', ROOT / 'build/native-owner-gtk-legacy-package'], check=True)


def focus(profile):
    sys.path.insert(0, str(ROOT / 'tests/reader_a11y_gtk'))
    sys.path.insert(0, str(ROOT / 'build/native-owner-reuse/d09'))
    import atspi_client as bus
    from driver import Host, wait_until, command
    from contract import modal_focus_ok
    folder = ROOT / ('build/native-owner-gtk-focus-' + profile)
    folder.mkdir()
    payload = ROOT / ('build/gtk-raw3/package/EXReader-Linux' if profile == 'raw' else
                      'build/native-owner-gtk-legacy-package/EXReader-Linux')
    host = Host(payload / 'bin/exreader-linux', payload / 'Reader.otf', folder)
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], profile=profile,
                  program_sha256=digest(host.binary), observations=[], complete_product=False)
    app = None

    def nodes(title, roles=None):
        return [n for n in bus.walk(app) if bus.name(n) == title
                and (roles is None or bus.role(n) in roles) and bus.states(n).get('showing')]

    def observation():
        dialogs = nodes('Reading records', ('dialog',))
        modal = dialogs[0] if len(dialogs) == 1 else None
        values = [dict(path=bus.path_of(n), name=bus.name(n), role=bus.role(n), states=bus.states(n),
                       descendant=bool(modal is not None and bus.is_ancestor(modal, n)))
                  for n in bus.focused_all(app)]
        return dict(dialog_path=bus.path_of(modal) if modal else '', dialog_states=bus.states(modal), focus=values)

    try:
        ok, reason = bus.init()
        assert ok, reason
        host.launch()
        app = bus.wait_application('exreader-linux')
        book = folder / 'Native focus.txt'
        book.write_text('Native records focus regression.\n' * 800, encoding='utf-8')
        host.key('F1')
        wait_until(lambda: nodes('Import book', ('file chooser',)), 20)
        host.activate(host.window_named('Import book'))
        host.key('ctrl+l', 'ctrl+a')
        host.type_text(str(book))
        wanted = hashlib.sha256(str(book).encode()).hexdigest()
        # The legacy owner has no preferences observation section. Read the
        # actual native chooser entry and button through AT-SPI in both builds.
        def chooser_ready():
            choosers = nodes('Import book', ('file chooser',))
            if len(choosers) != 1:
                return False
            descendants = list(bus.walk(choosers[0]))
            entered = [bus.accessible_text(n) for n in descendants
                       if bus.role(n) == 'text' and bus.states(n).get('showing')]
            accept = [n for n in descendants if bus.role(n) == 'push button' and bus.name(n) == 'Import'
                      and all(bus.states(n).get(k) for k in ('enabled', 'sensitive', 'showing'))]
            return bool(accept and any(t and t['text'] == str(book) for t in entered))
        wait_until(chooser_ready, 25, description='actual native chooser contains full path and enabled Import button')
        save(folder / 'import-chooser-tree.json', bus.dump(app))
        if profile == 'raw':
            wait_until(lambda: host.section('native_import').get('entry_sha256') == wanted
                       and host.section('native_import').get('selected_sha256') == wanted
                       and host.section('native_import').get('accept_sensitive') == '1', 20)
        def mapped_choosers():
            found = command('xdotool', 'search', '--onlyvisible', '--all', '--pid', str(host.process.pid), '--name', '^Import book$')
            return found.stdout.splitlines() if found.returncode == 0 else []
        report['import_evidence'] = dict(typed_path_sha256=wanted, first_accept_windows=mapped_choosers(),
                                         full_native_entry_and_enabled_accept_verified=True, accept_key_count=1)
        assert report['import_evidence']['first_accept_windows']
        host.key('Return')
        import time
        time.sleep(.6)
        if mapped_choosers():
            # Match the original D09 completion/accept route. A second key is
            # allowed only while the same real chooser remains mapped and the
            # original full path or selected fixture is still exposed there.
            choosers = nodes('Import book', ('file chooser',))
            assert len(choosers) == 1
            descendants = list(bus.walk(choosers[0]))
            selected = [bus.name(n) for n in descendants if bus.states(n).get('selected')]
            entered = [bus.accessible_text(n) for n in descendants if bus.role(n) == 'text' and bus.states(n).get('showing')]
            target_present = any(t and t['text'] == str(book) for t in entered) or any(name == book.name for name in selected)
            accepts = [n for n in descendants if bus.role(n) == 'push button' and bus.name(n) == 'Import'
                       and all(bus.states(n).get(k) for k in ('enabled', 'sensitive', 'showing'))]
            report['import_evidence'].update(second_accept_windows=mapped_choosers(), selected_names=selected,
                second_target_present=target_present, second_accept_enabled=bool(accepts), accept_key_count=2)
            save(folder / 'import-before-second-accept.json', bus.dump(app))
            assert target_present and accepts and set(report['import_evidence']['second_accept_windows']) == set(report['import_evidence']['first_accept_windows']), 'native chooser no longer exposes the original complete target'
            host.key('Return')
        wait_until(lambda: not mapped_choosers(), 40, description='actual native import chooser closes')
        host.wait_state(lambda s: s.get('book', 0) > 0 and not s.get('saving') and not s.get('busy'), timeout=90)
        for route in ('shortcut', 'menu', 'shortcut-reopen', 'menu-reopen'):
            if route.startswith('shortcut'):
                host.key('ctrl+shift+r')
            else:
                host.key('alt+m', 'Home', 'Right', 'Home')
                for _ in range(8):
                    if any(bus.name(n) == 'Reading records…' for n in bus.focused_all(app)):
                        break
                    host.key('Down')
                assert any(bus.name(n) == 'Reading records…' for n in bus.focused_all(app)), 'actual menu cannot reach Reading records'
                host.key('Return')
            wait_until(lambda: nodes('Reading records', ('dialog',)), 20)
            wait_until(lambda: modal_focus_ok(observation()), 20)
            samples = [observation()]
            host.key('Tab')
            samples.append(observation())
            host.key('shift+Tab')
            samples.append(observation())
            tree = bus.dump(app)
            save(folder / (route + '-tree.json'), tree)
            host.screenshot(folder / (route + '.png'), window='root')
            assert all(modal_focus_ok(value) for value in samples), samples
            host.key('Escape')
            wait_until(lambda: not nodes('Reading records', ('dialog',)), 20)
            frames = nodes('EXReader Linux', ('frame',))
            after = [dict(name=bus.name(n), path=bus.path_of(n), states=bus.states(n),
                          descendant=bool(frames and bus.is_ancestor(frames[0], n))) for n in bus.focused_all(app)]
            assert any(x['descendant'] and all(x['states'].get(k) for k in ('enabled', 'sensitive', 'visible', 'showing', 'focused')) for x in after), after
            report['observations'].append(dict(route=route, modal=samples, after=after, passed=True))
        report['accepted'] = len(report['observations']) == 4
    except Exception:
        report['failure'] = traceback.format_exc()
        if app:
            save(folder / 'failure-tree.json', bus.dump(app))
            host.screenshot(folder / 'failure.png', window='root')
    finally:
        if app and nodes('Import book', ('file chooser',)):
            host.key('Escape')
        report['exit_code'] = host.close()
        report['files'] = {p.relative_to(folder).as_posix(): dict(bytes=p.stat().st_size, sha256=digest(p)) for p in folder.rglob('*') if p.is_file()}
        save(folder / 'report.json', report)
        print(json.dumps(report), flush=True)
    assert report['accepted'], report.get('failure')


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--profile', choices=('legacy', 'raw'))
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        focus(args.profile)
