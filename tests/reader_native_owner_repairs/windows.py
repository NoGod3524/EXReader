"""Fresh native owner GUI regression; historical D12 primitives are explicit reuse."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

from prepare import ROOT, OUT, SOURCE
from reuse import D12, module

sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
import evidence
import keyboard
import w32


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def focus_regression(d12, name, exe):
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_preferences'))
    import check_ui as P
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
    import importlib.util
    spec = importlib.util.spec_from_file_location('repair_compact', ROOT / 'tests/reader_windows_compact/check_ui.py')
    compact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compact)
    U = P.U
    U.IsChild.argtypes = [W.HWND, W.HWND]
    U.IsChild.restype = W.BOOL
    U.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]
    U.SystemParametersInfoW.restype = W.BOOL
    folder = OUT / ('focus-' + name)
    folder.mkdir()
    trace = evidence.Trace(folder / 'keyboard.jsonl')
    result = dict(profile=name, accepted=False, program_sha256=sha(exe), observations=[])
    app = None
    original = W.RECT()
    assert U.SystemParametersInfoW(0x30, 0, C.byref(original), 0)
    result['original_work_area'] = [original.left, original.top, original.right, original.bottom]

    def native(parent):
        handle = keys.focus()
        return dict(hwnd=handle, descendant=bool(handle and U.IsChild(parent, handle)),
                    visible=bool(handle and U.IsWindowVisible(handle)),
                    enabled=bool(handle and U.IsWindowEnabled(handle)))

    def dialog():
        return next((h for h in w32.top_windows()
                     if w32.thread_id(h)[1] == app.process.pid and h != app.window
                     and U.IsWindowVisible(h)), None)

    try:
        for width, height, label in ((original.right - original.left, original.bottom - original.top, 'default'),
                                    (1024, 728, '1024'), (800, 600, 'small')):
            area = W.RECT(original.left, original.top,
                          min(original.right, original.left + width),
                          min(original.bottom, original.top + height))
            assert U.SystemParametersInfoW(0x2F, 0, C.byref(area), 0), 'actual temporary work area request failed'
            actual = W.RECT()
            assert U.SystemParametersInfoW(0x30, 0, C.byref(actual), 0)
            assert list((actual.left, actual.top, actual.right, actual.bottom)) == [area.left, area.top, area.right, area.bottom]
            app = P.App(exe, ROOT / 'build/host-font-cache/Reader.otf', folder / ('profile-' + label))
            app.wait_idle()
            bounds = w32.window_rect(app.window)
            row = dict(name='initial-' + label, actual_work_area=[area.left, area.top, area.right, area.bottom], outer=bounds)
            result['observations'].append(row)
            P.M.screenshot(app.window, folder / (label + '-initial.bmp'))
            assert area.left <= bounds[0] < bounds[2] <= area.right and area.top <= bounds[1] < bounds[3] <= area.bottom, row
            # Cross-process pointers cannot be used for WM_GETMINMAXINFO. A real
            # attempted native resize observes the effective minimum instead.
            app.settle((1, 1))
            resized = w32.window_rect(app.window)
            row['minimum_resize_outer'] = resized
            assert resized[2] - resized[0] <= area.right - area.left and resized[3] - resized[1] <= area.bottom - area.top, row
            if label != 'default':
                app.close()
                app = None
                continue
            app.settle((bounds[2] - bounds[0], bounds[3] - bounds[1]))
            compact.picker(app, ROOT / 'build/windows-raw3-host/compact-fixtures/Reading sample.txt')
            box = app.control('books')
            app.wait(lambda: P.send(box, 0x18B) == 1)
            P.send(box, 0x186, 0)
            app.click('open')
            app.wait_idle()
            app.wait(lambda: U.IsWindowVisible(app.control('page')))
            app.focus()
            keys = keyboard.Keyboard(app.window, trace=trace, delay=.18)
            keys.transport = 'sendinput'
            for view in ('reading', 'shelf'):
                if view == 'shelf':
                    keys.press('left', ('alt',))
                    app.wait(lambda: U.IsWindowVisible(app.control('books')) and not U.IsWindowVisible(app.control('page')))
                for title, key in [('search', ord('F')), ('navigation', ord('G')),
                                   ('records', ord('L')), ('preferences', 0xBC)]:
                    keys.press(key, ('ctrl',))
                    modal = app.wait(dialog, timeout=15)
                    # Initial async list loading may temporarily disable controls.
                    app.wait(lambda: native(modal)['enabled'], timeout=30)
                    samples = [native(modal)]
                    keys.press('tab')
                    samples.append(native(modal))
                    keys.press('tab', ('shift',))
                    samples.append(native(modal))
                    P.M.screenshot(modal, folder / (view + '-' + title + '.bmp'))
                    keys.press('escape')
                    app.wait(lambda: not U.IsWindow(modal), timeout=30)
                    after = native(app.window)
                    observed = dict(name=view + '-' + title, modal_focus=samples, after=after,
                                    actual_transport=keys.transport)
                    result['observations'].append(observed)
                    assert keys.transport == 'sendinput' and all(all(s[k] for k in ('descendant', 'visible', 'enabled')) for s in samples + [after]), observed
            app.close()
            assert app.process.returncode == 0
            app = None
        result['accepted'] = True
    except Exception:
        result['failure'] = traceback.format_exc()
    finally:
        if app:
            try:
                P.M.screenshot(app.window, folder / 'failure.bmp')
            except Exception:
                pass
            app.close()
        assert U.SystemParametersInfoW(0x2F, 0, C.byref(original), 0)
        trace.close()
        save(folder / 'report.json', result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    return result


def positive(d, profile, manifest, wires, iteration, oracle):
    folder = d.E / ('ui-' + iteration)
    folder.mkdir()
    result = dict(accepted=False, records=[], program_sha256=sha(OUT / 'programs/EXReaderShelfReview.exe'),
                  read_only_review_queries=[10, 11, 15, 16, 19, 40, 41, 42, 43, 44, 45])
    before = d.history(profile)
    app = None
    values = {rid: json.loads(raw) for rid, digest, raw in wires}
    try:
        app = d.App(OUT / 'programs/EXReaderShelfReview.exe', d.FONT, profile, existing=True)
        result['pid'] = app.process.pid
        titles = dict(d.query(profile, 'SELECT book_key,title FROM reader_books'))
        for record in manifest['reading_records']:
            rid = record['revision_id']
            row = dict(revision_id=rid, kind=record['kind'], role=record['role'], accepted=False)
            result['records'].append(row)
            modal = None
            try:
                d.send(app.window, 0x111, 46001)
                app.open(titles[record['capture']['route'][0]])
                app.wait_idle()
                modal = app.records()
                labels = d.labels(modal)
                if record['kind'] == 'progress':
                    index = 0
                else:
                    text = values[rid]['payload']['text']
                    matches = [i for i, label in enumerate(labels) if text and text in label]
                    assert len(matches) == 1, ('unique original text row', text, labels)
                    index = matches[0]
                box = d.U.GetDlgItem(modal, d.ROWS)
                d.send(box, 0x186, index)
                d.send(modal, 0x111, (1 << 16) | d.ROWS, box)
                assert d.send(box, 0x188) == index
                assert d.U.IsWindowEnabled(d.U.GetDlgItem(modal, d.OPEN))
                d.M.screenshot(modal, folder / (rid + '-controls.bmp'))
                d.send(d.U.GetDlgItem(modal, d.OPEN), 0xF5)
                app.record_idle(modal)
                observed = app.frame()
                observed.update(selection_start=app.q(40), selection_end=app.q(41), part=app.q(42),
                                frame_start=app.q(43), frame_end=app.q(44), selection_active=app.q(45))
                row['after'] = observed
                row['message'] = d.M.text(d.U.GetDlgItem(modal, d.MESSAGE))
                independent = next(x for x in oracle['records'] if x['revision_id'] == rid)
                row['independent_oracle'] = independent
                assert independent['found'] and independent['fresh_capture_equal'] and independent['retained_manifest_capture_equal']
                mode, unit, start, end = map(int, record['capture']['numbers'])
                if mode == 3:
                    target_ok = observed['fixed'] == 1 and observed['page'] == unit
                else:
                    target_ok = observed['fixed'] == 0 and observed['frame_start'] <= start <= observed['frame_end']
                    if mode == 2:
                        target_ok = target_ok and observed['part'] == unit
                assert target_ok, ('actual published frame differs from independent FOUND capture', observed, record)
                if end > start:
                    assert observed['selection_active'] == 1 and observed['selection_start'] == start and observed['selection_end'] == end and observed['selection_bytes'] == end - start, ('real native selection differs', observed, record)
                row['exact_jump_verified'] = True
                row['accepted'] = True
                d.M.screenshot(app.window, folder / (rid + '-frame.bmp'))
            except Exception:
                row['failure'] = traceback.format_exc()
            finally:
                if modal and d.U.IsWindow(modal):
                    app.close_records(modal)
                print(json.dumps(dict(ui_record=row, iteration=iteration), ensure_ascii=True), flush=True)
        result['history_unchanged'] = d.history(profile) == before
        result['accepted'] = len(result['records']) == 11 and all(x['accepted'] for x in result['records']) and result['history_unchanged']
    except Exception:
        result['failure'] = traceback.format_exc()
    finally:
        if app:
            app.close()
            result['exit_code'] = app.process.returncode
        save(folder / 'report.json', result)
    return result


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'win32'
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'programs').mkdir()
    (OUT / 'consumer').mkdir()
    built = ROOT / 'build/windows-raw3-host'
    for filename in ('EXReaderProduct.exe', 'EXReaderShelfReview.exe'):
        shutil.copyfile(built / 'raw-host' / filename, OUT / 'programs' / filename)
    shutil.copyfile(built / 'peer-owner-build/windows-peer-owner.exe', OUT / 'consumer/windows-peer-owner.exe')
    d = module(D12, 'tests/reader_dot_wave2/d12/check.py', 'historical_d12_primitives')
    d.E.mkdir()
    result = dict(accepted=False, source_sha=SOURCE, run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], guard_kind='native-owner-repairs',
                  historical_primitive_source=D12, historical_primitive_sha256=d.historical_source_sha256,
                  original_d12_acceptance_reused=False, complete_product=False, screen_reader_accepted=False,
                  focus=[], positive=[], null=[])
    def snapshot(profile, label):
        program = ROOT / 'build/native-owner-public/owner-public-state.exe'
        path = d.E / ('public-state-' + label + '.json')
        subprocess.run([str(program), str(profile), str(path)], check=True, timeout=120)
        value = json.loads(path.read_text())
        assert value['source_sha'] == SOURCE and value['program_sha256'] == sha(program)
        return value
    try:
        for name in ('legacy', 'raw'):
            result['focus'].append(focus_regression(d, name, built / (name + '-host/EXReaderProduct.exe')))
        proof, manifest, wires, originals, operations = d.mac_peer.load(d.E / 'mac')
        result['mac_proof'] = proof
        save(d.E / 'original-manifest.json', manifest)
        profile, received = d.receive('positive-receive', wires, originals)
        result['positive_receive'] = received
        assert received['accepted']
        initial = snapshot(profile, 'positive-before')
        for iteration in ('first', 'reopen'):
            oracle = d.oracle(profile, d.E / 'mac/sender', iteration)
            result['positive'].append(positive(d, profile, manifest, wires, iteration, oracle))
            after = snapshot(profile, 'positive-after-' + iteration)
            result['positive'][-1]['public_sdk_unchanged'] = initial['sdk_public_state'] == after['sdk_public_state']
            result['positive'][-1]['accepted'] = result['positive'][-1]['accepted'] and result['positive'][-1]['public_sdk_unchanged']
        mapping = {rid: (raw, digest) for rid, raw, digest in operations}
        closure = {}
        visiting = set()

        def visit(rid):
            assert rid not in visiting
            if rid in closure:
                return
            visiting.add(rid)
            raw, digest = mapping[rid]
            assert hashlib.sha256(raw).hexdigest() == digest
            for parent in json.loads(raw)['parents']:
                visit(parent)
            visiting.remove(rid)
            closure[rid] = (raw, digest)

        visit(d.NULL)
        null = json.loads(mapping[d.NULL][0])
        assert null['payload']['location']['selector']['exact']['base64'] is None
        key = null['payload']['book_key']
        for rid, (raw, digest) in mapping.items():
            value = json.loads(raw)
            if value['entity_kind'] == 'book' and value['entity_key'] == key:
                visit(rid)
        null_wires = [(rid, digest, raw) for rid, (raw, digest) in closure.items()]
        wireout = d.E / 'original-null-wires'
        wireout.mkdir()
        for rid, digest, raw in null_wires:
            (wireout / (rid + '.json')).write_bytes(raw)
        result['null_original_graph'] = [dict(id=rid, sha256=digest, bytes=len(raw)) for rid, digest, raw in null_wires]
        profile, received = d.receive('null-receive', null_wires, {key: originals[key]})
        result['null_receive'] = received
        assert received['accepted']
        initial = snapshot(profile, 'null-before')
        for iteration in ('first', 'reopen'):
            result['null'].append(d.null_ui(profile, key, iteration))
            after = snapshot(profile, 'null-after-' + iteration)
            result['null'][-1]['public_sdk_and_all_product_rows_unchanged'] = all(initial[k] == after[k] for k in ('sdk_public_state', 'product_readonly_state'))
            result['null'][-1]['accepted'] = result['null'][-1]['accepted'] and result['null'][-1]['public_sdk_and_all_product_rows_unchanged']
        result['accepted'] = len(result['focus']) == 2 and len(result['positive']) == 2 and len(result['null']) == 2 and all(x['accepted'] for x in result['focus'] + result['positive'] + result['null'])
    except Exception:
        result['failure'] = traceback.format_exc()
    finally:
        result['files'] = {p.relative_to(OUT).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
                           for p in OUT.rglob('*') if p.is_file() and p != OUT / 'report.json'}
        save(OUT / 'report.json', result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    if not result['accepted']:
        raise SystemExit('native Windows owner regression incomplete; original facts retained')


if __name__ == '__main__':
    main()
