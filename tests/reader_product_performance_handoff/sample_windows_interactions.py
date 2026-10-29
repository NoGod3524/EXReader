#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Windows interaction run: shelf scroll and reading font change on the real product.

Runs the unchanged tests/reader_perf_windows/perf_windows.py main() in-process with
two wrappers: after its shelf paging operation, native mouse-wheel scrolling of the
real shelf list box is timed until the top row changes; after the eighth page turn
of a reading launch, the real font buttons are clicked and timed until the page
label changes. Latency is control-state end-to-end, not a frame time. Because the
font round trip can move the resume page, this run is separate from (and never
replaces) the main observation. Actions-only.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_perf_windows'))
import perf_windows as P  # noqa: E402

SCROLL_STEPS = 3
FONT_STEPS = 2
RESULT = {'shelf_scroll_down': [], 'shelf_scroll_up': [], 'font_bigger': [], 'font_smaller': [], 'font_order': [], 'faults': []}


def timed(host, action, changed, timeout=60):
    started = P.now_ms()
    action()
    host.poll(lambda: (True,) if changed() else None, timeout, interval=0.003)
    return round(P.now_ms() - started, 3)


def scroll(host):
    for name, notches, mover in (('shelf_scroll_up', 4, host.wheel_up), ('shelf_scroll_down', 4, host.wheel)):
        for _ in range(SCROLL_STEPS):
            top = host.lb_top()
            try:
                RESULT[name].append(timed(host, lambda: mover(notches), lambda: host.lb_top() != top))
            except Exception as error:  # a real failure is retained, not filtered
                RESULT['faults'].append('%s: %s' % (name, error))
                return


def fonts(host):
    """Two bigger and two smaller clicks. The font size persists and is clamped, so a launch that
    starts at the upper limit runs the smaller clicks first; the order used is recorded."""
    steps = [('font_bigger', 'font_inc'), ('font_smaller', 'font_dec')]
    for attempt, order in enumerate((steps, steps[::-1])):
        mark = {name: len(RESULT[name]) for name, _ in steps}
        try:
            for name, button in order * FONT_STEPS:
                label = host.label()
                RESULT[name].append(timed(host, lambda: host.click(button), lambda: host.label() != label, 20))
            RESULT['font_order'].append('bigger-first' if attempt == 0 else 'smaller-first')
            break
        except Exception as error:
            for name, count in mark.items():
                del RESULT[name][count:]
            if attempt == 1:
                RESULT['faults'].append('font: %s' % error)
    host.wait_enabled('next', 30)


original_shelf_next_page = P.op_shelf_next_page
original_page_turn = P.op_page_turn
turns = {'host': None, 'count': 0}


def shelf_next_page(host, *args, **kwargs):
    result = original_shelf_next_page(host, *args, **kwargs)
    scroll(host)
    return result


def page_turn(host, previous_key, *args, **kwargs):
    result = original_page_turn(host, previous_key, *args, **kwargs)
    if turns['host'] is not host:
        turns['host'], turns['count'] = host, 0
    turns['count'] += 1
    if turns['count'] == 8:
        fonts(host)
    return result


P.op_shelf_next_page = shelf_next_page
P.op_page_turn = page_turn

if __name__ == '__main__':
    argv = sys.argv[1:]
    output = Path(argv[argv.index('--output') + 1]).resolve()
    code = 1
    try:
        code = P.main()
    finally:
        output.mkdir(parents=True, exist_ok=True)
        (output / 'interactions.json').write_text(json.dumps(RESULT, indent=2) + '\n', encoding='utf-8')
        print('INTERACTIONS ' + json.dumps({k: len(v) for k, v in RESULT.items()}))
        for fault in RESULT['faults']:
            print('INTERACTION-FAULT ' + fault)
    # The wrapped observation is incomplete by design (only two cohorts); its own verdict
    # is printed above and kept, but this run is judged by the interaction samples alone.
    print('WRAPPED-OBSERVATION-EXIT %s' % code)
    sys.exit(1 if RESULT['faults'] or any(not RESULT[k] for k in RESULT if k not in ('faults', 'font_order')) else 0)
