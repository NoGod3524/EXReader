#!/usr/bin/env python3
"""Observe cold full-host startup phases without modifying the product or frozen gates."""
import ctypes as c
from ctypes import wintypes as w
from contextlib import closing
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
import perf_windows as perf

stage = Path('build/startup-stage')
out = Path('build/startup-observation'); out.mkdir(parents=True, exist_ok=True)
package, seed = stage / 'package/EXReader', stage / 'seed.sqlite'
source = json.loads((stage / 'source.json').read_text())
perf.U.GetPropW.argtypes = [w.HWND, w.LPCWSTR]
perf.U.GetPropW.restype = w.HANDLE
results = []
for index in range(8):
    profile = out / f'profile-{index:02d}'
    profile.mkdir()
    shutil.copy2(seed, profile / 'library.sqlite')
    instrumented = index % 2 == 1
    host = perf.Host(package / 'EXReader.exe', package / 'Reader.otf', profile, out / f'host-{index:02d}.log')
    row = {'index': index, 'catalog_poll': instrumented, 'pid': host.process.pid,
           'marks_ms': {}, 'transitions': [], 'catalog_samples': [], 'error': None}
    marks, previous, last_catalog = row['marks_ms'], None, 0.0
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if host.process.poll() is not None:
                raise RuntimeError('host exited before product shelf became interactive')
            if not host.window and host.find_window():
                marks['window_created'] = round(perf.now_ms() - host.t0, 3)
            if host.window:
                book = perf.U.GetDlgItem(host.window, perf.IDS['books'])
                metadata = perf.U.GetDlgItem(host.window, perf.IDS['metadata'])
                if perf.controls_present(host) and 'all_controls_found' not in marks:
                    marks['all_controls_found'] = round(perf.now_ms() - host.t0, 3)
                if 'first_ui_roundtrip' not in marks:
                    try:
                        host.roundtrip(20)
                        marks['first_ui_roundtrip'] = round(perf.now_ms() - host.t0, 3)
                    except TimeoutError:
                        pass
                snapshot = int(perf.U.GetPropW(book, 'EXReaderShelfSnapshot') or 0) if book else 0
                enabled = bool(metadata and perf.U.IsWindowEnabled(metadata))
                count, label = None, None
                if book:
                    try:
                        count = host.lb_count(30)
                        if count:
                            label = host.lb_item(0, 30)
                    except (TimeoutError, perf.MeasurementFault):
                        pass
                now = round(perf.now_ms() - host.t0, 3)
                if count and 'first_nonempty_list' not in marks: marks['first_nonempty_list'] = now
                if snapshot and 'first_product_snapshot' not in marks: marks['first_product_snapshot'] = now
                if enabled and 'first_metadata_enabled' not in marks: marks['first_metadata_enabled'] = now
                state = (count, bool(snapshot), enabled)
                if state != previous:
                    row['transitions'].append({'ms': now, 'row_count': count, 'snapshot': snapshot,
                                               'metadata_enabled': enabled, 'first_row': label})
                    previous = state
                if enabled and snapshot and count is not None and count >= 50 and label and '偏移' not in label:
                    host.roundtrip(5000)
                    marks['product_shelf_interactive'] = round(perf.now_ms() - host.t0, 3)
                    break
            if instrumented and time.monotonic() - last_catalog >= .1:
                last_catalog = time.monotonic()
                database = profile / 'library.sqlite.product.sqlite'
                entry = {'start_ms': round(perf.now_ms() - host.t0, 3)}
                if database.exists():
                    try:
                        with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=0)) as connection:
                            entry['local_book_count'] = connection.execute('SELECT count(*) FROM reader_local_books').fetchone()[0]
                    except sqlite3.Error as error:
                        entry['error'] = str(error)
                else:
                    entry['error'] = 'catalog not created'
                entry['end_ms'] = round(perf.now_ms() - host.t0, 3)
                row['catalog_samples'].append(entry)
            time.sleep(.01)
        else:
            raise TimeoutError('product shelf not interactive within 120 seconds')
    except Exception as error:
        row['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        row['peak'] = host.close()
        results.append(row)
        (out / 'partial.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)

summary = {'observer_source': os.environ['GITHUB_SHA'], 'observer_run': os.environ['GITHUB_RUN_ID'],
           'observer_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'producer': source,
           'environment': {'os': platform.platform(), 'processor': platform.processor(),
                           'logical_processors': os.cpu_count(), 'display': perf.display_identity(),
                           'image_os': os.environ.get('ImageOS'), 'image_version': os.environ.get('ImageVersion')},
           'method': '8 fresh copies of same 2202-book SDK seed; alternating read-only catalog polls at 100 ms',
           'limitations': ['First window bounds combined process startup, SDK open and font open; no separate SDK duration.',
                           'Product snapshot and metadata enabled are externally observed UI markers, not direct repair start/end probes.',
                           'Read-only SQLite catalog polls can contend with the writer; compare alternating non-polled launches.',
                           'Cold describes a new profile only; operating-system cache and cloud co-tenant load are uncontrolled.',
                           'No frame time or budget acceptance is measured.'],
           'performance_accepted': False, 'results': results}
(out / 'startup-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if any(row['error'] or 'product_shelf_interactive' not in row['marks_ms'] for row in results):
    sys.exit('startup observation incomplete; per-launch failures preserved')
