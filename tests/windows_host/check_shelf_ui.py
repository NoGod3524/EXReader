#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only standard Win32 controls over 2202 public-SDK originals."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent / 'worker_review'))
from check_worker import App, U, send, set_text

U.IsWindowEnabled.argtypes = [W.HWND]
U.IsWindowEnabled.restype = W.BOOL
U.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]


class Product(App):
    def wait_idle(self):
        end = time.monotonic() + 60
        while time.monotonic() < end:
            self.wait(lambda: U.IsWindowEnabled(self.control('import')))
            time.sleep(.15)
            if U.IsWindowEnabled(self.control('import')):
                return
        raise TimeoutError('Actual product worker did not become idle')

    def titles(self):
        box = self.control('books')
        count = send(box, 0x18B)
        assert 0 <= count <= 150
        result = []
        for index in range(count):
            value = C.create_unicode_buffer(1024)
            send(box, 0x189, index, C.addressof(value));result.append(value.value)
        return result

    def numbers(self):
        return [int(re.search(r'Shelf (\d{4})', title)[1]) for title in self.titles()]

    def top(self):
        values = self.numbers()
        index = send(self.control('books'), 0x18E)
        return values[index] if values and index < len(values) else None

    def search(self, value):
        set_text(U.GetDlgItem(self.window, 126), value)
        self.wait_idle()

    def scroll(self, direction, wanted):
        box = self.control('books')
        for _ in range(320):
            for _ in range(8):
                send(box, 0x20A, ((-120 if direction > 0 else 120) & 0xffff) << 16)
            time.sleep(.08)
            values = self.numbers()
            if values and wanted(values):
                self.wait_idle()
                return
        raise AssertionError('Native wheel traversal incomplete: ' + repr(self.numbers()))


def main():
    parser = argparse.ArgumentParser()
    for name in ('candidate', 'seed', 'package', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
    output = args.output.resolve();profile = output / 'profile';profile.mkdir(parents=True, exist_ok=False)
    with (output / 'seed.log').open('wb') as log:
        subprocess.run([str(args.seed.resolve()), str(profile / 'library.sqlite')], stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=180)
    app = None;checks = []

    def launch():
        return Product(args.candidate.resolve(), (args.package / 'Reader.otf').resolve(), profile, existing=True)

    try:
        app = launch();app.wait(lambda: len(app.numbers()) == 50)
        assert app.numbers() == list(range(50))
        checks.append('native_product_initial_page_is_50')
        with sqlite3.connect(str(profile / 'library.sqlite') + '.product.sqlite') as db:
            actual = {key: size for key, size in db.execute('SELECT book_key,source_bytes FROM reader_books')}
        expected = {}
        for number in range(2202):
            raw = ('Shelf original %04d. Read this book and return to the same shelf position.\n' % number).encode()
            expected['txt:' + hashlib.sha256(raw).hexdigest()] = len(raw)
        assert actual == expected
        checks.append('all_2202_original_identities_match_independent_input_bytes')
        app.scroll(1, lambda values: values[-1] == 2201)
        assert len(app.titles()) <= 150
        checks.append('forward_real_wheel_reaches_final_original_with_bounded_rows')
        app.scroll(-1, lambda values: values[0] == 0 and app.top() == 0)
        checks.append('reverse_real_wheel_restores_first_original')
        app.scroll(1, lambda values: app.top() is not None and app.top() > 200)
        time.sleep(.5);top = app.top()
        app.process.kill();app.process.wait(timeout=20);app.log.close();app = launch()
        app.wait(lambda: app.top() == top)
        checks.append('actual_top_key_survives_process_death')
        app.search('Author %_!');app.wait(lambda: len(app.numbers()) == 50 and all(number % 17 == 0 for number in app.numbers()))
        assert all(number % 17 == 0 for number in app.numbers())
        app.scroll(1, lambda values: values[-1] == 2193)
        checks.append('literal_author_search_and_continuation')
        app.search('No such book');app.wait(lambda: not app.titles())
        app.search('Another absent title');app.wait(lambda: not app.titles())
        checks.append('empty_and_repeated_empty_search_remove_stale_rows')
        set_text(U.GetDlgItem(app.window, 126), 'Shelf 0001')
        set_text(U.GetDlgItem(app.window, 126), 'Shelf 2050')
        app.wait(lambda: app.numbers() == [2050]);app.wait_idle()
        checks.append('latest_query_wins_after_rapid_input')
        app.open('Shelf 2050');app.wait(lambda: 'Shelf 2050' in app.status())
        checks.append('filtered_original_opens_by_stable_id')
        app.search('');app.wait(lambda: app.numbers() == list(range(50)))
        app.close();app = launch()
        app.wait(lambda: 'Shelf 2050' in app.status() and app.numbers() == list(range(50)))
        checks.append('active_book_outside_first_page_reopens_without_ui_cache_lookup')
        set_text(U.GetDlgItem(app.window, 126), 'Shelf 0100')
        app.close();app = launch();app.wait(lambda: app.numbers() == [100])
        checks.append('immediate_close_persists_search_before_debounce')
        extra = output / 'ZZZ_New_Outside_Window.txt';extra.write_text('A newly imported original beyond the first page.\n')
        app.search('');app.import_file(extra)
        app.search('ZZZ_New_Outside_Window');app.wait(lambda: len(app.titles()) == 1)
        app.open('ZZZ_New_Outside_Window');app.wait(lambda: 'ZZZ_New_Outside_Window' in app.status())
        checks.append('new_import_outside_cache_keeps_fallback_title_and_can_open')
        app.click('delete');app.wait_idle();app.wait(lambda: not app.titles())
        with sqlite3.connect(str(profile / 'library.sqlite') + '.product.sqlite') as db:
            assert db.execute("SELECT count(*) FROM reader_books WHERE title='ZZZ_New_Outside_Window'").fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0] == 2202
        checks.append('local_removal_hides_row_and_retains_global_metadata')
        app.close()
    finally:
        if app is not None and app.process.poll() is None:
            app.close()
    assert len(checks) == 13
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'originals': 2202, 'page_size': 50, 'cache_limit': 150,
              'scope': 'Windows downloaded-books functional UI', 'checks': checks, 'problems': [],
              'performance_accepted': False, 'complete_product': False,
              'binary_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
              'files': {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(output.rglob('*')) if path.is_file()}}
    (output / 'shelf-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
