#!/usr/bin/env python3
"""Drive full Windows import through the real native chooser, preserving timing samples."""
import importlib.util
import sqlite3
from contextlib import closing
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
import perf_windows as perf

spec = importlib.util.spec_from_file_location('wave3_dialog_driver', Path('tests/reader_wave3_c09/check_ui.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class Adapter:
    def __init__(self, host):
        self.process, self.window = host.process, host.window

    def wait(self, probe, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('full host exited while waiting for native dialog')
            value = probe()
            if value:
                return value
            time.sleep(.01)
        raise TimeoutError('native dialog did not reach requested state')


def submit(host, fixture, timeout):
    """Time from native IDOK until idle is observed after the chooser driver returns.

    The retained chooser driver waits 0.4 s between IDOK attempts. That delay is
    included in this end-to-end measurement; busy WM_NULL probes run concurrently.
    """
    app = Adapter(host)
    samples, state = [], {'start': None, 'done': False, 'error': None}
    host.wait_enabled('import', 60)
    button = host.control('import')
    if not perf.U.IsWindowVisible(button):
        raise perf.MeasurementFault('full product import control is not visible')
    if not perf.U.PostMessageW(button, perf.BM_CLICK, 0, 0):
        raise perf.MeasurementFault('could not post native import click')
    original_post = driver.post_click

    def collect():
        try:
            while not state['done']:
                if state['start'] is not None and not driver.system_dialog(app):
                    busy = not host.import_enabled()
                    began = perf.now_ms()
                    try:
                        roundtrip = round(host.roundtrip(3000), 3)
                    except TimeoutError:
                        roundtrip = None
                    samples.append({'t_ms': round(perf.now_ms() - state['start'], 3), 'busy': busy,
                                    'roundtrip_ms': roundtrip, 'text_echo': None,
                                    'sample_ms': round(perf.now_ms() - began, 3)})
                time.sleep(.01)
        except Exception as error:
            state['error'] = '%s: %s' % (type(error).__name__, error)

    def capture_accept(dialog, identifier):
        if identifier == 1 and state['start'] is None:
            state['start'] = perf.now_ms()
        return original_post(dialog, identifier)

    driver.post_click = capture_accept
    worker = threading.Thread(target=collect, daemon=True)
    worker.start()
    try:
        driver.fill_system_dialog(app, fixture)
        if state['start'] is None:
            raise perf.MeasurementFault('native chooser was not accepted')
        while not host.import_enabled():
            if perf.now_ms() - state['start'] > timeout * 1000:
                raise perf.MeasurementFault('import did not complete in %s seconds' % timeout)
            time.sleep(.01)
        elapsed = round(perf.now_ms() - state['start'], 3)
    finally:
        state['done'] = True
        worker.join(timeout=5)
        driver.post_click = original_post
    if worker.is_alive() or state['error']:
        raise perf.MeasurementFault('busy input observer failed: %s' % state['error'])
    return elapsed, samples


def op_import(host, fixture, expected_title, timeout=300):
    elapsed, samples = submit(host, fixture, timeout)
    status = host.status()
    found = perf.op_search(host, expected_title,
        lambda app: app.lb_count() == 1 and expected_title in app.lb_item(0),
        lambda rows: len(rows) == 1 and expected_title in rows[0])
    busy = [sample for sample in samples if sample['busy'] and sample['roundtrip_ms'] is not None]
    return {'import_ms': elapsed, 'input_samples': samples, 'busy_input_samples': len(busy),
            'busy_input_p50_ms': perf.median([sample['roundtrip_ms'] for sample in busy]),
            'busy_input_max_ms': max((sample['roundtrip_ms'] for sample in busy), default=None),
            'input_timeouts': sum(sample['roundtrip_ms'] is None for sample in samples),
            'post_import_search_ms': found['ms'], 'post_import_rows': found['rows'],
            'status_after_import': status, 'visible': True, 'fixture': str(fixture),
            'fixture_bytes': Path(fixture).stat().st_size, 'fixture_sha256': perf.sha256(fixture),
            'title': expected_title}


def diagnostic_import(host, fixture, wait_s):
    elapsed, samples = submit(host, fixture['path'], wait_s)
    status = host.status()
    return {'path_accepted': True, 'echo': fixture['path'], 'completed': True,
            'elapsed_ms': elapsed, 'status_after_import': status, 'budget_s': wait_s,
            'busy_samples': sum(sample['busy'] for sample in samples), 'timed_out': False,
            'status_indicates_failure': ('失败' in status) or ('错误' in status),
            'native_dialog': True, 'samples': samples}


def environment(*args):
    result = original_environment(*args)
    result['measurement']['input_delivery'] = ('Native file chooser and SendMessageTimeoutW to real Win32 controls; '
                                               'import timing begins at native IDOK; busy response uses WM_NULL')
    result['measurement']['input_path_note'] = ('Native chooser driven with the retained wave3 dialog driver; '
                                                'IDOK-to-observed-idle includes its 0.4 s wait; no hidden path edit.')
    return result


original_environment = perf.environment

original_verify_corpus = perf.verify_corpus


def verify_corpus(template):
    result = original_verify_corpus(template)
    database = template / 'library.sqlite.product.sqlite'
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        total, distinct_ids, joined = connection.execute(
            'SELECT count(*), count(DISTINCT l.sdk_book_id), '
            'sum(CASE WHEN b.book_key IS NOT NULL AND b.deleted=0 THEN 1 ELSE 0 END) '
            'FROM reader_local_books l LEFT JOIN reader_books b ON b.book_key=l.book_key').fetchone()
    if (total, distinct_ids, joined) != (2202, 2202, 2202):
        raise perf.MeasurementFault('prepared product mapping is incomplete: %r' % ((total, distinct_ids, joined),))
    result['local_mapping_rows'] = total
    result['distinct_sdk_ids'] = distinct_ids
    result['visible_mapped_books'] = joined
    return result


perf.environment = environment
perf.op_import = op_import
perf.verify_corpus = verify_corpus
