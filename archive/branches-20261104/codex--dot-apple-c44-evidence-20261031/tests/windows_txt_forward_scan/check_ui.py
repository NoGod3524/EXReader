"""Actions-only real Windows TXT seek comparison, including original-byte identity.

No private navigation entry point or database mutation is used. The reference is
built from this same source with EXR_TXT_SCAN_FROM_FIRST; only the scan hint is
turned off. TXT_SCAN is observation, never a substitute for displayed UI text.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
spec = importlib.util.spec_from_file_location('compact_ui', ROOT / 'tests/reader_windows_compact/check_ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
sys.path.insert(0, str(ROOT / 'tests/reader_a11y_windows'))
from uia_layer import Uia

TIMEOUT = 240  # Original Windows TXT search timeout, not expanded for this suite.
EXR_CANCELLED = 9  # Public include/exr/base.h status enum.


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(path):
    """A real >16 MiB original, not a tiny file forced onto the large-TXT path."""
    with path.open('wb') as out:
        size, index = 0, 0
        while size <= 16 * 1024 * 1024:
            line = ('ROW%07d repeated needle; original line %07d. '
                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789.\n' % (index, index)).encode('ascii')
            out.write(line)
            size += len(line)
            index += 1
        out.write(b'EOF_UNIQUE_TARGET last original content.\n')
    return path.read_bytes()


def trace(app):
    lines = (app.profile / 'application.log').read_text(encoding='utf-8', errors='replace').splitlines()
    return [json.loads(line.split('TXT_SCAN ', 1)[1]) for line in lines if 'TXT_SCAN {' in line]


def page(app, automation):
    return (automation.control(app.control('page')).GetValuePattern().Value or '').replace('\r\n', '\n')


def hit_rows(dialog):
    box = ui.U.GetDlgItem(dialog, 174)
    result = []
    for i in range(ui.send(box, 0x18B)):
        text = C.create_unicode_buffer(4096)
        ui.send(box, 0x189, i, C.addressof(text))
        result.append((int(text.value.split()[0]) - 1, text.value))
    return result


def close_dialog(app, dialog):
    ui.send(dialog, 0x10)
    app.wait(lambda: not ui.U.IsWindow(dialog), timeout=30)
    app.wait_idle()


def find(app, query, offset):
    ui.command(app, 170)
    dialog = app.wait(lambda: ui.owned_dialog(app, 171), timeout=30)
    ui.P.set_text(ui.U.GetDlgItem(dialog, 171), query)
    ui.send(dialog, 0x111, 172)
    app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=TIMEOUT)
    for batch in range(1000):
        rows = hit_rows(dialog)
        matches = [i for i, row in enumerate(rows) if row[0] == offset]
        if matches:
            ui.send(ui.U.GetDlgItem(dialog, 174), 0x186, matches[0])
            return dialog
        assert rows and rows[-1][0] < offset, {'expected_offset': offset, 'rows': rows}
        assert ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 173)), (query, offset, rows)
        ui.send(dialog, 0x111, 173)
        app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=TIMEOUT)
    raise AssertionError('Target result exceeded the bounded batch traversal')


def seek(app, automation, source, case, query, offset):
    assert source[offset:offset + len(query.encode())] == query.encode(), (case, query, offset)
    dialog = find(app, query, offset)
    count = len(trace(app))
    began = time.perf_counter()
    ui.send(dialog, 0x111, 175)
    app.wait(lambda: '已独立核对' in ui.P.text(ui.U.GetDlgItem(dialog, 178)), timeout=TIMEOUT)
    app.wait_idle()
    elapsed = (time.perf_counter() - began) * 1000
    records = trace(app)[count:]
    records = [item for item in records if item['offset'] == offset and item['status'] == 0]
    assert records, {'case': case, 'status': app.status(), 'records': trace(app)[count:]}
    observation = records[-1]
    text = page(app, automation)
    start, end = observation['start'], observation['end']
    assert start <= offset < end, (case, observation)
    assert text == source[start:end].decode('utf-8'), {'case': case, 'trace': observation, 'shown': text[:100]}
    # Search may straddle a page boundary: its original start must be visible;
    # the UI selection is deliberately clipped to that page by the product.
    visible_query = source[offset:min(end, offset + len(query.encode()))].decode('utf-8')
    assert visible_query and visible_query in text, (case, visible_query, text)
    result = dict(case=case, query=query, offset=offset, scan=observation,
                  page_sha256=hashlib.sha256(text.encode()).hexdigest(),
                  page_text_chars=len(text), ui_elapsed_ms=elapsed,
                  page_label=app.label(), pid=app.process.pid)
    close_dialog(app, dialog)
    return result


def main():
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for key in ('candidate', 'reference', 'font', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = out / 'Forward scan original.txt'
    report = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  original=None, candidate_sha256=None, reference_sha256=None,
                  timeout_seconds=TIMEOUT, runs={}, comparisons=[], failures=[],
                  scope='Actual Windows application, native picker and search controls; two fresh profiles; same-source from-first reference; no database preload')
    os.environ['EXR_TRACE_TXT'] = '1'
    app = None
    boundary_cases = []
    try:
        source = fixture(original)
        report['original'] = dict(bytes=len(source), sha256=digest(original))
        for mode, exe in (('reuse', args.candidate), ('from_first', args.reference)):
            report['runs'][mode] = []
            report['active_case'] = dict(mode=mode, case='launch', started_unix=time.time())
            try:
                report['candidate_sha256' if mode == 'reuse' else 'reference_sha256'] = digest(exe)
                checks = report['runs'][mode] = []
                profile = out / ('profile-' + mode)
                app = ui.P.App(exe.resolve(), args.font.resolve(), profile)
                automation = Uia()
                assert automation.available, automation.error
                app.wait_idle()
                ui.picker(app, original)
                app.wait(lambda: ui.send(app.control('books'), 0x18B) == 1, timeout=300)
                ui.send(app.control('books'), 0x186, 0)
                app.click('open')
                app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=TIMEOUT)
                app.wait_idle()
                assert 'ROW0000000' in page(app, automation)

                def run_case(name, query, offset=None):
                    if offset is None:
                        offset = source.index(query.encode())
                    report['active_case'] = dict(mode=mode, case=name, query=query, offset=offset,
                                                 started_unix=time.time())
                    result = seek(app, automation, source, name, query, offset)
                    checks.append(result)
                    print('FORWARD_SCAN_CASE ' + json.dumps(dict(mode=mode, **result)), flush=True)
                    return result

                run_case('first-page', 'ROW0000000')
                run_case('forward-prefix', 'ROW0000100')
                # A second target on the current page, then one beyond it.
                warm = run_case('forward-nearby', 'ROW0000120')
                if mode == 'reuse':
                    start, end = warm['scan']['start'], warm['scan']['end']
                    # Exact displayed start and the byte on each side of its next boundary.
                    # Single-line queries preserve byte offsets in the real edit control.
                    for name, at in (('exact-page-start', start), ('last-byte-of-page', end - 1), ('next-page-boundary', end)):
                        if source[at:at + 1] == b'\n':
                            # A newline cannot be entered in the one-line search box;
                            # separately retain the exact range boundary and use adjacent byte.
                            boundary_cases.append((name + '-newline-adjacent', at + 1, source[at + 1:at + 13].split(b'\n')[0].decode()))
                        else:
                            query = source[at:at + 24].split(b'\n')[0].decode()
                            boundary_cases.append((name, at, query))
                    report['boundary_requests'] = boundary_cases
                for name, at, query in boundary_cases:
                    run_case(name, query, at)
                run_case('backward-before-current', 'ROW0000003')
                # Same exact phrase at two different original offsets, not substring-only evidence.
                offsets = [match.start() for match in re.finditer(b'repeated needle', source[:40000])]
                run_case('repeated-content-forward', 'repeated needle', offsets[25])
                run_case('repeated-content-backward', 'repeated needle', offsets[5])
                for number in (140, 10, 155, 8, 170):
                    run_case('alternating-%d' % number, 'ROW%07d' % number)

                before_font = checks[-1]
                ui.send(ui.U.GetDlgItem(app.window, 114), 0xF5)
                app.wait_idle()
                reflowed = run_case('font-reflow-same-target', 'ROW0000170')
                assert (reflowed['scan']['start'], reflowed['scan']['end'], reflowed['page_sha256']) != (
                    before_font['scan']['start'], before_font['scan']['end'], before_font['page_sha256']), 'Font change did not exercise a changed page boundary'
                after_font = run_case('font-reflow-forward', 'ROW0000180')
                assert after_font['scan']['font_size'] != before_font['scan']['font_size']
                run_case('font-reflow-backward', 'ROW0000010')
                app.settle((700, 480))
                app.wait_idle()
                resized = run_case('viewport-resize-forward', 'ROW0000190')
                resized['viewport_note'] = 'Native window resized to 700x480; pager dimensions are reported, not presumed to reflow.'
                app.settle((1100, 720))
                app.wait_idle()
                run_case('viewport-restored-backward', 'ROW0000020')

                saved = checks[-1]
                app.close()
                assert app.process.returncode == 0
                app = ui.P.App(exe.resolve(), args.font.resolve(), profile, existing=True)
                automation = Uia()
                app.wait(lambda: ui.visible(app, 123) and not ui.visible(app, 119), timeout=TIMEOUT)
                app.wait_idle()
                restored = page(app, automation)
                assert hashlib.sha256(restored.encode()).hexdigest() == saved['page_sha256']
                run_case('reopen-forward', 'ROW0000200')

                # Cancel a genuine distant seek only once its pagination has started.
                # Never replace the product worker with a fabricated successful result.
                query = 'ROW0001000'
                retry_offset = source.index(query.encode())
                report['active_case'] = dict(mode=mode, case='cancel-and-direct-retry', offset=retry_offset,
                                             started_unix=time.time())
                dialog = find(app, query, retry_offset)
                previous = page(app, automation)
                log_before = (app.profile / 'application.log').stat().st_size
                count = len(trace(app))
                ui.send(dialog, 0x111, 175)
                marker = 'TXT_SCAN_PROGRESS offset=%d generated=1' % retry_offset
                app.wait(lambda: marker in (app.profile / 'application.log').read_bytes()[log_before:].decode('utf-8', errors='replace'), timeout=TIMEOUT)
                ui.send(dialog, 0x111, 176)
                app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=TIMEOUT)
                assert '取消' in ui.P.text(ui.U.GetDlgItem(dialog, 178))
                assert page(app, automation) == previous
                cancelled = trace(app)[count:]
                assert cancelled and any(item['status'] == EXR_CANCELLED for item in cancelled), cancelled
                assert any(item['status'] == EXR_CANCELLED and item['calls'] > 0 and item['generated_pages'] > 0
                           for item in cancelled), 'Cancellation did not interrupt actual page generation'
                report.setdefault('cancellations', {})[mode] = cancelled
                # Directly retry the SAME result, without a page turn or reopen.
                before_retry = len(trace(app))
                began = time.perf_counter()
                ui.send(dialog, 0x111, 175)
                app.wait(lambda: '已独立核对' in ui.P.text(ui.U.GetDlgItem(dialog, 178)), timeout=TIMEOUT)
                app.wait_idle()
                retry = [item for item in trace(app)[before_retry:] if item['offset'] == retry_offset and item['status'] == 0]
                assert retry, trace(app)[before_retry:]
                chosen = retry[-1]
                text = page(app, automation)
                assert chosen['start'] <= retry_offset < chosen['end']
                assert text == source[chosen['start']:chosen['end']].decode()
                assert query in text
                checks.append(dict(case='cancel-direct-retry', offset=retry_offset, scan=chosen,
                                   page_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                   ui_elapsed_ms=(time.perf_counter() - began) * 1000))
                close_dialog(app, dialog)
                # Keep the genuine full-original EOF gate separate from lifecycle
                # recovery. It still uses exactly the same 240-second limit.
                run_case('full-original-eof', 'EOF_UNIQUE_TARGET')
                run_case('eof-current-page', 'EOF_UNIQUE_TARGET')
                run_case('eof-backward', 'ROW0000001')
                ui.P.M.screenshot(app.window, out / (mode + '-final.bmp'))
                app.close()
                assert app.process.returncode == 0
                app = None

            except Exception:
                report['failures'].append(dict(mode=mode, traceback=traceback.format_exc()))
                if app:
                    try:
                        dialog = ui.owned_dialog(app, 171)
                        report.setdefault('failed_case_observations', {})[mode] = dict(
                            active_case=report.get('active_case'), status=app.status(),
                            search_status=ui.P.text(ui.U.GetDlgItem(dialog, 178)) if dialog else None,
                            scan_records=trace(app), observed_unix=time.time())
                        ui.P.M.screenshot(app.window, out / (mode + '-failure.bmp'))
                        if dialog:
                            ui.send(dialog, 0x111, 176)
                            app.wait(lambda: ui.U.IsWindowEnabled(ui.U.GetDlgItem(dialog, 172)), timeout=30)
                    except Exception:
                        report['failures'].append(dict(mode=mode, observation_error=traceback.format_exc()))
            finally:
                if app:
                    try:
                        app.close()
                        report.setdefault('failed_case_observations', {}).setdefault(mode, {})['final_scan_records'] = trace(app)
                    except Exception:
                        report['failures'].append(dict(mode=mode, close_error=traceback.format_exc()))
                    app = None

        left, right = report['runs']['reuse'], report['runs']['from_first']
        report['completed_cases'] = dict(reuse=len(left), from_first=len(right))
        savings = []
        for a, b in zip(left, right):
            assert a['case'] == b['case'] and a['offset'] == b['offset']
            assert a['page_sha256'] == b['page_sha256'], (a, b)
            for field in ('page', 'start', 'end', 'font_size', 'width', 'height'):
                assert a['scan'][field] == b['scan'][field], (field, a, b)
            assert b['scan']['first'] == 0, b
            record = dict(case=a['case'], optimized_calls=a['scan']['calls'], baseline_calls=b['scan']['calls'],
                          optimized_generated_pages=a['scan']['generated_pages'], baseline_generated_pages=b['scan']['generated_pages'],
                          optimized_restored_checkpoints=a['scan']['restored_checkpoints'], baseline_restored_checkpoints=b['scan']['restored_checkpoints'],
                          optimized_scan_ms=a['scan']['elapsed_ms'], baseline_scan_ms=b['scan']['elapsed_ms'],
                          optimized_ui_ms=a['ui_elapsed_ms'], baseline_ui_ms=b['ui_elapsed_ms'], exact_page_equal=True)
            report['comparisons'].append(record)
            if a['scan']['first'] > 0:
                assert a['scan']['calls'] < b['scan']['calls'], record
                savings.append(record)
        assert savings, 'No measured forward scan reduction was demonstrated'
        assert any(item['optimized_generated_pages'] < item['baseline_generated_pages'] for item in savings), 'Only lookup-call savings, not actual generated-page savings, were demonstrated'
        report['measured_forward_savings'] = len(savings)
        assert digest(original) == report['original']['sha256'], 'Original fixture bytes changed'
        assert len(left) == len(right), 'Independent native runs completed different case counts'
        assert not report['failures'], 'One or more independent native runs failed; both results and common prefix retained'
        report['accepted'] = True
    except Exception:
        report['failures'].append(traceback.format_exc())
        if app:
            report['failed_case_observations'] = dict(status=app.status(), scan_records=trace(app),
                                                     observed_unix=time.time())
    finally:
        if app:
            try:
                ui.P.M.screenshot(app.window, out / 'failure.bmp')
                app.close()
            except Exception:
                report['failures'].append(traceback.format_exc())
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('FORWARD_SCAN_REPORT ' + json.dumps(report, ensure_ascii=False), flush=True)
    assert report['accepted'], report['failures']


if __name__ == '__main__':
    main()
