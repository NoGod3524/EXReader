#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual GTK/X11 operations against 2202 public SDK originals, in Actions only."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_linux_host import Session, command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    folder = args.output.resolve()
    host = Session((args.payload / 'bin/exreader-linux').resolve(),
                   (args.payload / 'Reader.otf').resolve(), folder)
    checks = []
    observations = []

    def ready(predicate=lambda state: True):
        return host.wait(lambda state: not state.get('shelf_loading') and
                         not state.get('shelf_restoring') and predicate(state), timeout=60)

    def search(value):
        before = host.read()['shelf_queries']
        host.key('ctrl+f', 'ctrl+a')
        if value:
            host.paste(value)
        else:
            host.key('BackSpace')
        return ready(lambda state: state['shelf_queries'] > before)

    def shelf_state():
        parser = configparser.ConfigParser()
        parser.read(host.observe)
        return dict(parser['shelf'])

    def scroll(direction, predicate):
        # Real wheel events, not a host-only test command or SQL offset.
        command('xdotool', 'mousemove', '--window', host.window, '400', '500')
        for _ in range(320):
            subprocess.run(['xdotool', 'click', '--repeat', '8', '--delay', '15', str(5 if direction > 0 else 4)],
                           check=True, timeout=15)
            time.sleep(.08)
            current = host.read()
            assert current['books'] <= 150 and current['shelf_max_cached'] <= 150
            if not current['shelf_loading'] and not current['shelf_restoring'] and predicate(current):
                return current
        raise AssertionError('Actual wheel traversal did not reach requested shelf region: ' + repr(host.read()))

    try:
        host.launch()
        initial = ready(lambda state: state['books'] == 50)
        assert initial['shelf_first_id'] == 1 and initial['shelf_last_id'] == 50
        checks.append('startup_actual_product_only_50_rows')
        command('xdotool', 'windowsize', '--sync', host.window, '1100', '3100')
        ready(lambda state: state['books'] >= 100 and state['shelf_first_id'] == 1)
        checks.append('tall_viewport_prefetches_beyond_first_50_without_scroll_range')
        command('xdotool', 'windowsize', '--sync', host.window, '1040', '820')
        end = scroll(1, lambda state: state['shelf_last_id'] == 2202 and not state['shelf_after'] and state['shelf_top_id'] > 2180)
        assert end['books'] <= 150 and end['shelf_evicted'] > 0 and end['shelf_before']
        checks.append('wheel_traverses_all_2202_with_150_row_cache')
        back = scroll(-1, lambda state: state['shelf_first_id'] == 1 and not state['shelf_before'])
        assert back['shelf_evicted'] > end['shelf_evicted']
        checks.append('reverse_wheel_prepends_and_evicts_tail')
        mid = scroll(1, lambda state: state['shelf_top_id'] > 200)
        time.sleep(.6)
        saved = shelf_state()
        before_restart = host.read()['shelf_top_id']
        # Force process death after idle persistence; no graceful-close save credit.
        host.process.kill();host.process.wait(timeout=20);host.log.close();host.launch()
        restarted = ready(lambda state: state['shelf_top_id'] == before_restart)
        assert shelf_state()['top_key'] == saved['top_key']
        assert abs(float(shelf_state()['top_offset']) - float(saved['top_offset'])) < 2
        checks.append('stable_top_key_and_pixel_offset_survive_process_death')
        author = search('%_!')
        assert author['books'] == 50 and author['shelf_first_id'] == 1 and author['shelf_last_id'] == 834
        checks.append('literal_author_search_uses_real_metadata')
        empty = search('No such book')
        assert empty['books'] == 0 and not empty['shelf_before'] and not empty['shelf_after']
        another_empty = search('Another absent title')
        assert another_empty['books'] == 0
        checks.append('empty_search_has_no_stale_rows')
        # New input invalidates the old generation before the debounce expires.
        host.key('ctrl+f', 'ctrl+a');host.paste('Shelf 0001');host.key('ctrl+a');host.paste('Shelf 2050')
        found = ready(lambda state: state['books'] == 1 and state['shelf_first_id'] == 2051)
        assert found['shelf_last_id'] == 2051
        checks.append('rapid_search_rejects_stale_generation')
        time.sleep(.6)
        host.process.kill();host.process.wait(timeout=20);host.log.close();host.launch()
        ready(lambda state: state['books'] == 1 and state['shelf_first_id'] == 2051)
        checks.append('idle_query_persists_without_graceful_close')
        host.key('F2', 'Return')
        host.wait(lambda state: state['book'] == 2051 and state['reader_visible'] == 1)
        checks.append('selected_filtered_book_opens_original_not_cache_index')
        host.key('F2');ready(lambda state: state['books'] == 1)
        assert shelf_state()['selected_key']
        checks.append('reading_to_shelf_retains_selection_and_filter')
        search('')
        ready(lambda state: state['books'] == 50)
        checks.append('clearing_filter_returns_first_bounded_page')
        command('import', '-window', host.window, folder / 'shelf.png')
        command('xdotool', 'windowsize', host.window, '1100', '900')
        ready(lambda state: state['books'] <= 150)
        checks.append('resize_keeps_bounded_real_native_list')
        command('xdotool', 'key', '--clearmodifiers', 'ctrl+f', 'ctrl+a')
        subprocess.run(['xclip', '-selection', 'clipboard'], input=b'Shelf 0100', check=True)
        command('xdotool', 'key', '--clearmodifiers', 'ctrl+v', 'alt+F4')
        host.process.wait(timeout=30)
        assert host.process.returncode == 0
        host.log.close();host.launch()
        ready(lambda state: state['books'] == 1 and state['shelf_first_id'] == 101)
        checks.append('immediate_normal_close_persists_new_query_before_debounce')
        observations.append({'state': host.read(), 'process_status': Path(f'/proc/{host.process.pid}/status').read_text(),
                             'measurement_scope': 'observed process status only; no frozen UI/RSS budget'})
        host.close()
    finally:
        if host.process is not None and host.process.poll() is None:
            host.process.kill();host.process.wait(timeout=20)
        if host.log and not host.log.closed:
            host.log.close()
    assert len(checks) == 14
    report = {'accepted': True, 'complete_product': False, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'originals': 2202, 'page_size': 50, 'cache_limit': 150, 'checks': checks,
              'observations': observations, 'problems': [],
              'files': {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(folder.rglob('*')) if path.is_file()}}
    (folder / 'shelf-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
